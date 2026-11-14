package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import javax.annotation.PreDestroy;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

@Service
@DependsOn("buildingSchemaMigration")
public class CommunityAssessmentService {
    @Resource private CommunityManagementService communities;
    @Resource private CommunityPublicationService publication;
    @Resource private FileResourceProperties files;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private CommunityAssessmentTasks managedTasks;
    @Resource(name="pythonTaskExecutor") private Executor executor;
    @Value("${citylearn.python.executable:python}") private String python;
    private final Map<String,Process> processes=new ConcurrentHashMap<>();
    private volatile boolean stopping;

    @PostConstruct
    public void backfillPersistedKpis() {
        try {
            List<Map<String,Object>> rows=jdbc.queryForList("SELECT id,result_json FROM community_assessment_run WHERE status='succeeded' AND result_json IS NOT NULL");
            for(Map<String,Object> row:rows){
                Integer count=jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_kpi WHERE run_id=?",Integer.class,row.get("id"));
                if(count==null||count==0) persistKpis(Objects.toString(row.get("id")), mapper.readValue(Objects.toString(row.get("result_json"),"{}"),Map.class));
            }
        } catch(Exception ignored) { /* startup must remain available; failed runs are retried on next startup */ }
    }

    public List<Map<String,Object>> list(long community,String release) {
        requireRelease(community,release);
        synchronizeManagedTasks();
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT id,status,stage,create_time AS createTime,start_time AS startTime,end_time AS endTime,error_message AS error,config_json FROM community_assessment_run WHERE community_id=? AND release_id=? ORDER BY create_time DESC,id DESC LIMIT 100",community,release);
        for(Map<String,Object> row:rows)row.put("config",decode(row.remove("config_json")));
        return rows;
    }
    public Map<String,Object> get(long community,String release,String id) {
        requireRelease(community,release);
        List<Map<String,Object>> found=jdbc.queryForList("SELECT id,status,stage,create_time AS createTime,start_time AS startTime,end_time AS endTime,error_message AS error,config_json,result_json FROM community_assessment_run WHERE id=? AND community_id=? AND release_id=?",id,community,release);
        if(found.isEmpty()) throw new IllegalArgumentException("评估任务不属于该社区数据集");
        Map<String,Object> result=found.get(0);
        result.put("config",decode(result.remove("config_json")));
        Path directory=runDirectory(id);
        Object content=result.remove("result_json");
        if(content!=null)result.put("result",decode(content));
        else {
            Path partial=directory.resolve("result.json");
            if(Files.isRegularFile(partial))try {
                if(Files.size(partial)>20_000_000)throw new IllegalArgumentException("阶段结果文件过大");
                result.put("result",mapper.readValue(partial.toFile(),Map.class));
            }catch(Exception error){result.put("resultWarning","阶段结果暂不可读，下次轮询重试");}
            else result.put("result",null);
        }
        try {
            Path progress=directory.resolve("progress.json");
            if(Files.isRegularFile(progress)) {
                Map<String,Object> value=mapper.readValue(progress.toFile(),Map.class);
                result.put("progress",value);
                if("running".equals(result.get("status")))result.put("stage",value.getOrDefault("stage","running"));
            }
        }catch(Exception error){result.put("progressWarning","进度文件暂不可读，下次轮询重试");}
        Path log=directory.resolve("run.log");
        if(Files.isRegularFile(log))try(java.io.RandomAccessFile stream=new java.io.RandomAccessFile(log.toFile(),"r")){
            long size=stream.length();stream.seek(Math.max(0,size-8000));byte[] bytes=new byte[(int)Math.min(size,8000)];stream.readFully(bytes);
            result.put("log",new String(bytes,StandardCharsets.UTF_8));
        }catch(Exception ignored){}
        return result;
    }
    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> start(long community,String release)throws Exception {
        return start(community,release,Map.of());
    }
    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> start(long community,String release,Map<String,Object> options)throws Exception {
        return createRun(community,release,options,false);
    }
    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> startBaseline(long community,String release)throws Exception {
        communities.get(community,true);
        requireRelease(community,release);
        synchronizeManagedTasks();
        jdbc.queryForObject("SELECT id FROM building_experiment_lock WHERE id=1 FOR UPDATE",Integer.class);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE community_id=? AND release_id=? AND status IN ('queued','running')",Integer.class,community,release)>0)
            throw new IllegalArgumentException("该数据集已有初步评估任务正在执行");
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE status IN ('queued','running')",Integer.class)>0)
            throw new IllegalArgumentException("已有初步评估任务正在执行，请稍后重试");
        Map<String,Object> baseline=createRun(community,release,Map.of("algorithm","NOCONTROL"),true);
        return Map.of("runs",List.of(baseline));
    }
    private Map<String,Object> createRun(long community,String release,Map<String,Object> options,boolean managed)throws Exception {
        String algorithm=Objects.toString(options.getOrDefault("algorithm",""));
        if(!algorithm.isEmpty()&&!List.of("CHESCA","NOCONTROL").contains(algorithm))throw new IllegalArgumentException("目前仅支持 CHESCA 和 NOCONTROL");
        Map<String,Object> parameters=new LinkedHashMap<>();
        Object tau=options.getOrDefault("tau",1);
        int horizon=Integer.parseInt(tau.toString());
        if(horizon<1||horizon>3)throw new IllegalArgumentException("预测步数应为1至3");
        String balance=Objects.toString(options.getOrDefault("balance_type","C"));
        if(!List.of("A","B","C").contains(balance))throw new IllegalArgumentException("负荷平衡模式无效");
        parameters.put("tau",horizon);parameters.put("balance_type",balance);
        if(managed&&"NOCONTROL".equals(algorithm))parameters.put("dhw_storage_fix",true);
        if(managed&&options.get("bestSource") instanceof Map) {
            parameters.clear();
            parameters.putAll((Map<String,Object>)((Map<?,?>)options.get("bestSource")).get("parameters"));
        }
        Integer startStep=options.get("start_step")==null?null:Integer.valueOf(options.get("start_step").toString());
        Integer endStep=options.get("end_step")==null?null:Integer.valueOf(options.get("end_step").toString());
        if(stopping)throw new IllegalArgumentException("服务正在停止");
        communities.get(community,true);
        Path source=publication.directory(community,release).toRealPath();
        jdbc.queryForObject("SELECT id FROM building_experiment_lock WHERE id=1 FOR UPDATE",Integer.class);
        if(!managed&&jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE community_id=? AND release_id=? AND status IN ('queued','running')",Integer.class,community,release)>0)
            throw new IllegalArgumentException("该数据集已有初步评估任务正在执行");
        if(!managed&&jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE status IN ('queued','running')",Integer.class)>=2)
            throw new IllegalArgumentException("已有两个初步评估任务排队或执行，请稍后重试");
        String id=UUID.randomUUID().toString();Path directory=runDirectory(id),snapshot=directory.resolve("dataset");
        Files.createDirectories(snapshot);DatasetSnapshotFiles.cleanupOnRollback(directory);
        try(java.util.stream.Stream<Path> paths=Files.walk(source)){
            for(Path path:(Iterable<Path>)paths::iterator) {
                if(Files.isSymbolicLink(path))throw new IllegalArgumentException("数据集包含不允许的符号链接");
                Path target=snapshot.resolve(source.relativize(path)).normalize();
                if(!target.startsWith(snapshot))throw new IllegalArgumentException("数据集路径越界");
                if(Files.isDirectory(path))Files.createDirectories(target);else Files.copy(path,target);
            }
        }
        Map<String,Object> manifest=mapper.readValue(snapshot.resolve("manifest.json").toFile(),Map.class);
        Integer scoreStartStep=null,scoreEndStepExclusive=null;
        if("synthetic_ol1".equals(manifest.get("sourceMode"))){
            String registeredHash=jdbc.queryForObject("SELECT content_hash FROM community_dataset_release WHERE id=?",String.class,release);
            if(!(manifest.get("files") instanceof Map))throw new IllegalArgumentException("模拟场景缺少文件哈希清单");
            Map<String,String> packageFiles=new TreeMap<>();
            ((Map<?,?>)manifest.get("files")).forEach((key,value)->packageFiles.put(key.toString(),value.toString()));
            String calculatedHash=BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(packageFiles));
            if(!Objects.equals(registeredHash,manifest.get("contentHash"))||!Objects.equals(calculatedHash,registeredHash))
                throw new IllegalArgumentException("模拟场景清单与已发布版本哈希不一致");
            Map<?,?> generationConfig=mapper.readValue(snapshot.resolve("generation_config.json").toFile(),Map.class);
            Map<?,?> manifestConfig=(Map<?,?>)manifest.get("configuration");
            int configuredStart=((Number)generationConfig.get("startStep")).intValue();
            int configuredSteps=((Number)generationConfig.get("steps")).intValue();
            if(!generationConfig.equals(manifestConfig)||!Objects.equals(manifest.get("scoreStartStep"),configuredStart)||
                    !Objects.equals(manifest.get("scoreEndStepExclusive"),configuredStart+configuredSteps))
                throw new IllegalArgumentException("模拟场景计分窗口与已哈希生成配置不一致");
            Map<?,?> validation=mapper.readValue(snapshot.resolve("validation_report.json").toFile(),Map.class);
            if(!"passed".equals(validation.get("runtimeValidation"))||(!"NOCONTROL".equals(algorithm)&&
                    (!"passed".equals(validation.get("chescaSmokeTest"))||!Boolean.TRUE.equals(manifest.get("chescaCompatible")))))
                throw new IllegalArgumentException("模拟场景运行或 CHESCA 冒烟验证证据不完整");
            if(startStep!=null||endStep!=null)throw new IllegalArgumentException("模拟场景的计分窗口由生成清单固定，不能缩短仿真上下文");
            scoreStartStep=((Number)manifest.get("scoreStartStep")).intValue();
            scoreEndStepExclusive=((Number)manifest.get("scoreEndStepExclusive")).intValue();
            Map<?,?> sourceSchema=mapper.readValue(snapshot.resolve("schema.json").toFile(),Map.class);
            int sourceEnd=((Number)sourceSchema.get("simulation_end_time_step")).intValue()+1;
            if(scoreStartStep<0||scoreEndStepExclusive<=scoreStartStep||scoreEndStepExclusive>sourceEnd)
                throw new IllegalArgumentException("模拟场景计分窗口超出 schema 范围");
            parameters.put("score_start_step",scoreStartStep);
            parameters.put("score_end_step_exclusive",scoreEndStepExclusive);
        }
        if(startStep!=null||endStep!=null){
            Map<?,?> sourceSchema=mapper.readValue(snapshot.resolve("schema.json").toFile(),Map.class);
            int sourceStart=((Number)(sourceSchema.containsKey("simulation_start_time_step")?sourceSchema.get("simulation_start_time_step"):0)).intValue();
            int sourceEnd=((Number)sourceSchema.get("simulation_end_time_step")).intValue();
            int actualStart=startStep==null?sourceStart:startStep,actualEnd=endStep==null?sourceEnd:endStep;
            if(actualStart<sourceStart||actualEnd>sourceEnd||actualEnd<=actualStart)throw new IllegalArgumentException("评估时间范围超出数据集或无效");
            parameters.put("start_step",actualStart);parameters.put("end_step",actualEnd);
        }
        Object recorded=manifest.get("files");
        if(!(recorded instanceof Map)||((Map<?,?>)recorded).isEmpty())throw new IllegalArgumentException("数据集缺少文件完整性清单");
        for(Map.Entry<?,?> item:((Map<?,?>)recorded).entrySet()){
            Path path=snapshot.resolve(item.getKey().toString()).normalize();
            if(!path.startsWith(snapshot)||!Files.isRegularFile(path)||!BuildingDatasetExporter.sha256(Files.readAllBytes(path)).equals(item.getValue()))
                throw new IllegalArgumentException("数据集文件完整性校验失败: "+item.getKey());
        }
        Map<String,String> actual=new TreeMap<>();
        try(java.util.stream.Stream<Path> paths=Files.walk(snapshot)){
            for(Path path:paths.filter(Files::isRegularFile).collect(Collectors.toList())) {
                String name=snapshot.relativize(path).toString().replace(java.io.File.separatorChar,'/');
                if(!name.equals("manifest.json")&&!name.startsWith("__pycache__/")&&!name.endsWith(".pyc"))
                    actual.put(name,BuildingDatasetExporter.sha256(Files.readAllBytes(path)));
            }
        }
        Set<String> expected=((Map<?,?>)recorded).keySet().stream().map(Object::toString).collect(Collectors.toSet());
        if(!actual.keySet().equals(expected))throw new IllegalArgumentException("数据集存在清单外文件，不能确认完整性");
        Map<String,Object> config=new LinkedHashMap<>();config.put("releaseId",release);config.put("communityId",community);
        config.put("files",actual);config.put("schemaHash",actual.get("schema.json"));config.put("runner","community_assessment.py");
        if(!algorithm.isEmpty()){config.put("algorithm",algorithm);config.put("parameters",parameters);}
        if(options.get("bestSource") instanceof Map)config.put("bestSource",options.get("bestSource"));
        if(managed) {
            String schemaKey=jdbc.queryForObject("SELECT schema_key FROM community_dataset_release WHERE id=?",String.class,release);
            String name=jdbc.queryForObject("SELECT name FROM community_dataset_release WHERE id=?",String.class,release);
            String taskId=managedTasks.create(algorithm,schemaKey,name,snapshot,directory,parameters);
            config.put("taskId",taskId);
            config.put("evaluationTaskId",taskId+"-eval");
        }
        jdbc.update("INSERT INTO community_assessment_run(id,community_id,release_id,status,stage,config_json) VALUES (?,?,?,'queued','queued',?)",id,community,release,mapper.writeValueAsString(config));
        if(managed) {
            String taskId=config.get("taskId").toString();
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
                @Override public void afterCommit(){
                    try{managedTasks.execute(taskId);}
                    catch(RuntimeException error){managedTasks.failStart(taskId,error.getMessage());fail(id,"任务管理启动失败: "+error.getMessage());}
                }
            });
            return get(community,release,id);
        }
        List<String> command=new ArrayList<>(List.of(python,"-u",Paths.get(files.getPythonFilePath()).toAbsolutePath().resolve("community_assessment.py").toString(),"--schema",snapshot.resolve("schema.json").toString(),"--output-dir",directory.toString()));
        if(startStep!=null||endStep!=null)command.addAll(List.of("--start-step",parameters.get("start_step").toString(),"--end-step",parameters.get("end_step").toString()));
        if(scoreStartStep!=null)command.addAll(List.of("--score-start-step",scoreStartStep.toString(),"--score-end-step-exclusive",scoreEndStepExclusive.toString()));
        if(!algorithm.isEmpty()){
            command.addAll(List.of("--algorithm",algorithm,"--parameters-base64",Base64.getEncoder().encodeToString(mapper.writeValueAsBytes(parameters))));
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
            @Override public void afterCommit(){
                try{executor.execute(()->execute(id,command));}
                catch(RuntimeException error){fail(id,"评估队列提交失败: "+error.getMessage());}
            }
        });
        return get(community,release,id);
    }
    void execute(String id,List<String> command) {
        if(stopping){fail(id,"服务正在停止");return;}
        if(jdbc.update("UPDATE community_assessment_run SET status='running',stage='initializing',start_time=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",id)!=1)return;
        Process process=null;
        try {
            ProcessBuilder builder=new ProcessBuilder(command).directory(Paths.get(files.getPythonFilePath()).toFile()).redirectErrorStream(true).redirectOutput(runDirectory(id).resolve("run.log").toFile());
            builder.environment().put("PYTHONIOENCODING","utf-8");builder.environment().put("PYTHONHASHSEED","0");builder.environment().put("OMP_NUM_THREADS","1");builder.environment().put("MKL_NUM_THREADS","1");builder.environment().put("OPENBLAS_NUM_THREADS","1");
            process=builder.start();processes.put(id,process);
            if(stopping||!"running".equals(jdbc.queryForObject("SELECT status FROM community_assessment_run WHERE id=?",String.class,id)))process.destroyForcibly();
            if(!process.waitFor(4,TimeUnit.HOURS))throw new IllegalStateException("初步评估超过4小时限制");
            if(process.exitValue()!=0)throw new IllegalStateException("评估进程退出码 "+process.exitValue()+"，请查看任务日志");
            Path resultFile=runDirectory(id).resolve("result.json");
            if(Files.size(resultFile)>20_000_000)throw new IllegalStateException("结果文件过大");
            Map<String,Object> result=mapper.readValue(resultFile.toFile(),Map.class);
            if(!"succeeded".equals(result.get("status")))throw new IllegalStateException("算法评估失败，请查看日志和结果");
            persistKpis(id, result);
            persistHomeTrace(id);
            Object baseline=result.get("baseline");
            if(!(baseline instanceof Map)||!"succeeded".equals(((Map<?,?>)baseline).get("status")))throw new IllegalStateException("NoControl未成功完成，不能生成成功报告");
            if(!Files.isRegularFile(runDirectory(id).resolve("report.md")))throw new IllegalStateException("缺少初步报告");
            jdbc.update("UPDATE community_assessment_run SET status='succeeded',stage='completed',result_json=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status='running'",mapper.writeValueAsString(result),id);
        }catch(Exception error){fail(id,error.getMessage());}
        finally{if(process!=null&&process.isAlive())process.destroyForcibly();processes.remove(id);}
    }
    @SuppressWarnings("unchecked")
    private void persistKpis(String runId, Map<String,Object> result) throws Exception {
        jdbc.update("DELETE FROM community_assessment_kpi WHERE run_id=?", runId);
        for(String key:List.of("baseline","cases")){
            Object value=result.get(key); List<Map<String,Object>> cases=new ArrayList<>();
            if(value instanceof Map) cases.add((Map<String,Object>)value);
            else if(value instanceof List) for(Object item:(List<?>)value) if(item instanceof Map) cases.add((Map<String,Object>)item);
            for(Map<String,Object> item:cases){
                if(!"succeeded".equals(item.get("status"))) continue;
                String caseId=Objects.toString(item.getOrDefault("id", "unknown"));
                Map<String,Object> metrics=(Map<String,Object>)item.getOrDefault("metrics", Map.of());
                jdbc.update("INSERT INTO community_assessment_kpi(run_id,case_id,level_name,building_name,cost_total,discomfort_proportion,score,metrics_json) VALUES (?,?,?,?,?,?,?,?)",
                        runId,caseId,"district","District",metrics.get("cost_total"),metrics.get("discomfort_proportion"),metrics.get("score"),mapper.writeValueAsString(metrics));
                Object buildings=metrics.get("buildings");
                if(buildings instanceof List) for(Object building: (List<?>)buildings) if(building instanceof Map){
                    Map<String,Object> b=(Map<String,Object>)building;
                    jdbc.update("INSERT INTO community_assessment_kpi(run_id,case_id,level_name,building_name,cost_total,discomfort_proportion,score,metrics_json) VALUES (?,?,?,?,?,?,?,?)",
                            runId,caseId,"building",Objects.toString(b.getOrDefault("name","unknown")),b.get("cost_total"),b.get("discomfort_proportion"),b.get("score"),mapper.writeValueAsString(b));
                }
            }
        }
    }
    private void persistHomeTrace(String runId) throws IOException {
        Path trace=runDirectory(runId).resolve("home_trace.csv");
        if(!Files.isRegularFile(trace)) return;
        if(Files.size(trace)>8_000_000) throw new IllegalStateException("首页时序轨迹超过 8 MB 限制");
        String content=new String(Files.readAllBytes(trace),StandardCharsets.UTF_8);
        jdbc.update("INSERT INTO community_assessment_artifact(run_id,artifact_type,content) VALUES (?,?,?) ON DUPLICATE KEY UPDATE content=VALUES(content),create_time=CURRENT_TIMESTAMP",runId,"home_trace_csv",content);
    }
    @Transactional
    public void cancel(long community,String release,String id) {
        Map<String,Object> run=get(community,release,id);
        Map<?,?> config=(Map<?,?>)run.get("config");
        if(config.get("taskId")!=null)managedTasks.cancel(config.get("taskId").toString());
        if(jdbc.update("UPDATE community_assessment_run SET status='cancelled',stage='cancelled',end_time=CURRENT_TIMESTAMP WHERE id=? AND community_id=? AND release_id=? AND status IN ('queued','running')",id,community,release)!=1)
            throw new IllegalArgumentException("评估任务已结束，不能取消");
        Process process=processes.get(id);if(process!=null)process.destroyForcibly();
    }
    public Path report(long community,String release,String id) {
        if(!"succeeded".equals(get(community,release,id).get("status")))throw new IllegalArgumentException("评估尚未成功完成");
        Path report=runDirectory(id).resolve("report.md");
        if(!Files.isRegularFile(report))throw new IllegalArgumentException("报告文件不存在");return report;
    }
    private void requireRelease(long community,String release) {
        communities.get(community,false);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_dataset_owner WHERE community_id=? AND release_id=?",Integer.class,community,release)!=1)
            throw new IllegalArgumentException("数据集不属于该社区");
    }
    private Object decode(Object value){try{return value==null?null:mapper.readValue(value.toString(),Map.class);}catch(Exception error){throw new IllegalStateException("评估记录JSON无效",error);}}
    private void fail(String id,String message){jdbc.update("UPDATE community_assessment_run SET status='failed',stage='failed',error_message=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')",Objects.toString(message,"评估失败"),id);}
    @EventListener(WebServerInitializedEvent.class)
    public void recoverInterruptedRuns(){jdbc.update("UPDATE community_assessment_run SET status='failed',stage='interrupted',error_message='服务重启，评估已中断，请重新提交',end_time=CURRENT_TIMESTAMP WHERE status IN ('queued','running') AND JSON_EXTRACT(config_json,'$.taskId') IS NULL");}
    @org.springframework.scheduling.annotation.Scheduled(fixedDelay=3000)
    public synchronized void synchronizeManagedTasks() {
        for(Map<String,Object> row:jdbc.queryForList("SELECT id,config_json FROM community_assessment_run WHERE status IN ('queued','running') AND JSON_EXTRACT(config_json,'$.taskId') IS NOT NULL")) {
            String id=row.get("id").toString();
            try {
                Map<?,?> config=(Map<?,?>)decode(row.get("config_json"));
                int status=((Number)managedTasks.state(config.get("taskId").toString()).get("status")).intValue();
                if(status==0)jdbc.update("UPDATE community_assessment_run SET status='running',stage='evaluating',start_time=COALESCE(start_time,CURRENT_TIMESTAMP) WHERE id=? AND status='queued'",id);
                else if(status==1) {
                    Map<String,Object> result=mapper.readValue(runDirectory(id).resolve("result.json").toFile(),Map.class);
                    if(!"succeeded".equals(result.get("status")))throw new IllegalStateException("评估任务未产生成功结果，请查看任务管理日志");
                    persistKpis(id,result);persistHomeTrace(id);
                    jdbc.update("UPDATE community_assessment_run SET status='succeeded',stage='completed',result_json=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')",mapper.writeValueAsString(result),id);
                } else if(status==2||status==3||status==4) {
                    jdbc.update("UPDATE community_assessment_run SET status=?,stage=?,error_message=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')",
                            status==3?"cancelled":"failed",status==3?"cancelled":"failed","任务管理中的评估已"+(status==3?"取消":"失败，请查看任务日志"),id);
                }
            }catch(Exception error){fail(id,error.getMessage());}
        }
    }
    @PreDestroy public void stopProcesses(){
        stopping=true;processes.forEach((id,process)->{process.destroyForcibly();fail(id,"服务关闭，评估已中断");});
    }
    Path runDirectory(String id){
        if(id==null||!id.matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"))throw new IllegalArgumentException("无效评估编号");
        return Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize().resolve("outputs/community-assessments").resolve(id);
    }
}
