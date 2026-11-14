package com.citylearn.building;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;
import javax.annotation.Resource;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

@Service
public class CommunityAssetService {
    @Resource private CommunityManagementService communities;
    @Resource private JdbcTemplate jdbc;
    @Value("${citylearn.python.executable:python}") private String python;
    private static final long MAX_BYTES=50L*1024*1024;

    @Transactional public List<Map<String,Object>> upload(long id,MultipartFile file) throws IOException {
        communities.get(id,true);
        String name=file.getOriginalFilename();
        if(name==null||name.length()>180||!name.matches("[A-Za-z0-9][A-Za-z0-9_.-]*\\.(pth|pt)")||name.contains(".."))
            throw new IllegalArgumentException("模型文件名仅允许英文字母、数字、下划线、短横线和点，以字母或数字开头、.pth或.pt结尾，不能包含路径或连续两个点");
        if(file.getSize()<=0||file.getSize()>MAX_BYTES)throw new IllegalArgumentException("模型大小应为1字节至50MB");
        Path directory=communities.assetDirectory(id);Files.createDirectories(directory);
        Path realRoot=directory.getParent().toRealPath(),realDirectory=directory.toRealPath();
        if(!realDirectory.startsWith(realRoot))throw new IllegalArgumentException("模型目录无效");
        Path destination=directory.resolve(name).normalize();
        if(!destination.getParent().equals(directory)||Files.isSymbolicLink(destination))throw new IllegalArgumentException("模型路径无效");
        Path temporary=Files.createTempFile(directory,".upload-",".tmp");
        try{
            try(java.io.InputStream input=file.getInputStream();java.io.OutputStream output=Files.newOutputStream(temporary)){
                byte[] buffer=new byte[8192];long total=0;int read;
                while((read=input.read(buffer))!=-1){total+=read;if(total>MAX_BYTES)throw new IllegalArgumentException("模型超过50MB");output.write(buffer,0,read);}
            }
            validate(temporary);
            byte[] bytes=Files.readAllBytes(temporary);String hash=BuildingDatasetExporter.sha256(bytes);
            List<String> registered=jdbc.query("SELECT sha256 FROM community_asset WHERE community_id=? AND name=?",(rs,n)->rs.getString(1),id,name);
            if(!registered.isEmpty()){
                if(!registered.get(0).equals(hash))throw new IllegalArgumentException("同名模型内容不同，请使用新文件名");
                if(!Files.isRegularFile(destination)||!BuildingDatasetExporter.sha256(Files.readAllBytes(destination)).equals(hash))throw new IllegalArgumentException("已登记模型文件缺失或哈希不一致");
                return communities.assets(id);
            }
            if(Files.exists(destination))throw new IllegalArgumentException("同名文件已存在，请使用新文件名");
            Files.move(temporary,destination,StandardCopyOption.ATOMIC_MOVE);
            if(TransactionSynchronizationManager.isSynchronizationActive())TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
                @Override public void afterCompletion(int status){if(status!=STATUS_COMMITTED)try{Files.deleteIfExists(destination);}catch(IOException ignored){}}
            });
            try{jdbc.update("INSERT INTO community_asset(community_id,name,sha256,size_bytes) VALUES (?,?,?,?)",id,name,hash,bytes.length);}
            catch(RuntimeException e){Files.deleteIfExists(destination);throw e;}
            return communities.assets(id);
        }finally{Files.deleteIfExists(temporary);}
    }
    private void validate(Path path) throws IOException {
        // weights_only disallows arbitrary pickle globals; only plain tensor state dictionaries are accepted.
        String script="import sys,torch\nfrom collections.abc import Mapping\n"
                +"v=torch.load(sys.argv[1],map_location='cpu',weights_only=True)\n"
                +"assert isinstance(v,Mapping),'Expected checkpoint or tensor state dictionary'\n"
                +"v=v.get('model_state_dict',v.get('state_dict',v))\n"
                +"assert isinstance(v,Mapping) and len(v)>0,'Expected tensor state dictionary'\n"
                +"assert all(isinstance(k,str) and isinstance(t,torch.Tensor) for k,t in v.items()),'Expected named tensors only'\n"
                +"assert all(t.numel()<=100000000 and torch.isfinite(t).all().item() for t in v.values()),'Invalid tensor values'\n";
        Path log=Files.createTempFile("citylearn-model-validation-",".log");Process process=null;
        try{
            process=new ProcessBuilder(python,"-I","-c",script,path.toAbsolutePath().toString()).redirectErrorStream(true).redirectOutput(log.toFile()).start();
            if(!process.waitFor(45,TimeUnit.SECONDS)){process.destroyForcibly();throw new IllegalArgumentException("模型验证超时");}
            if(process.exitValue()!=0)throw new IllegalArgumentException("模型验证失败：必须为可安全读取的PyTorch张量state_dict");
        }catch(InterruptedException e){Thread.currentThread().interrupt();if(process!=null)process.destroyForcibly();throw new IllegalArgumentException("模型验证已中断",e);}
        finally{Files.deleteIfExists(log);}
    }
}
