package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeUnit;

@Component
public class CommunityRuntimeValidator {
    @Value("${citylearn.python.executable:python}") private String python;
    @Value("${citylearn.community.validate-runtime:true}") private boolean enabled;
    public Map<String,Object> validate(Path directory)throws Exception {
        if(!enabled)return Map.of("runtimeValidation","disabled for isolated Java tests");
        Path script=Files.createTempFile("citylearn-validate-",".py"),log=Files.createTempFile("citylearn-validate-",".log");
        try {
            try(java.io.InputStream input=getClass().getResourceAsStream("/citylearn/validate_community_package.py")){
                if(input==null)throw new IllegalStateException("缺少CityLearn场景验证器");
                Files.copy(input,script,StandardCopyOption.REPLACE_EXISTING);
            }
            ProcessBuilder builder=new ProcessBuilder(python,script.toString(),directory.toAbsolutePath().toString());
            builder.environment().put("PYTHONIOENCODING","utf-8");builder.redirectErrorStream(true);builder.redirectOutput(log.toFile());
            Process process=builder.start();
            if(!process.waitFor(60,TimeUnit.SECONDS)){process.destroyForcibly();throw new IllegalArgumentException("CityLearn场景验证超时，请核对模型与配置");}
            String output=Files.readString(log,StandardCharsets.UTF_8).trim();
            if(process.exitValue()!=0)throw new IllegalArgumentException("CityLearn无法运行该场景: "+output.substring(Math.max(0,output.length()-1800)));
            String[] lines=output.split("\\R");
            return new ObjectMapper().readValue(lines[lines.length-1],Map.class);
        }finally{Files.deleteIfExists(script);Files.deleteIfExists(log);}
    }
}
