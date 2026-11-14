package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.stream.Collectors;

public class CommunityDatasetExporter {
    private final ObjectMapper mapper;
    public CommunityDatasetExporter(ObjectMapper mapper) { this.mapper = mapper; }

    public static class Source {
        public final Path directory;
        public final Map<String,Object> info, schema, metadata;
        public Map<String,Object> manifest;
        public final List<Instant> timestamps;
        Source(Path directory, Map<String,Object> info, Map<String,Object> schema, Map<String,Object> metadata, List<Instant> timestamps) {
            this.directory=directory; this.info=info; this.schema=schema; this.metadata=metadata; this.timestamps=timestamps;
        }
    }
    public static class Window {
        public final Instant start, end;
        public final int steps;
        Window(Instant start, Instant end) { this.start=start; this.end=end; this.steps=(int)Duration.between(start,end).toHours(); }
    }

    @SuppressWarnings("unchecked")
    public Source load(Path directory, Map<String,Object> info) throws Exception {
        Map<String,Object> manifest = mapper.readValue(directory.resolve("manifest.json").toFile(), Map.class);
        Map<String,String> hashes = new TreeMap<>((Map<String,String>)manifest.get("files"));
        String contentHash = BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(hashes));
        if (!contentHash.equals(info.get("contentHash")) || !contentHash.equals(manifest.get("contentHash")))
            throw new IllegalArgumentException("源数据集校验失败，请重新发布建筑数据集");
        if (!hashes.keySet().containsAll(List.of("schema.json", "timestamps.csv")))
            throw new IllegalArgumentException("源数据集缺少时间戳或配置");
        for (Map.Entry<String,String> file : hashes.entrySet()) {
            Path path = localFile(directory, file.getKey());
            if (!Files.isRegularFile(path) || !file.getValue().equals(BuildingDatasetExporter.sha256(Files.readAllBytes(path))))
                throw new IllegalArgumentException("源数据集文件已改变: " + file.getKey());
        }
        Map<String,Object> schema = mapper.readValue(directory.resolve("schema.json").toFile(), Map.class);
        if (((Number)schema.get("seconds_per_time_step")).doubleValue()!=3600 || ((Map<?,?>)schema.get("buildings")).size()!=1)
            throw new IllegalArgumentException("请选择已发布的单建筑小时数据集");
        List<String> lines = Files.readAllLines(directory.resolve("timestamps.csv"), StandardCharsets.UTF_8);
        if (lines.size()<3 || lines.size()>200001 || !lines.get(0).equals("timestamp"))
            throw new IllegalArgumentException("源数据集时间戳无效");
        List<Instant> times = new ArrayList<>();
        for (int i=1;i<lines.size();i++) {
            Instant time = Instant.parse(lines.get(i));
            if (!times.isEmpty() && !times.get(times.size()-1).plusSeconds(3600).equals(time))
                throw new IllegalArgumentException("源数据集存在时间缺口");
            times.add(time);
        }
        if (((Number)schema.get("simulation_start_time_step")).intValue()!=0 || ((Number)schema.get("simulation_end_time_step")).intValue()!=times.size()-1)
            throw new IllegalArgumentException("源数据集步数与时间戳不一致");
        Map<String,Object> metadata=(Map<String,Object>)manifest.get("building");
        ZoneId zone=ZoneId.of(metadata.get("timezone").toString());
        if (times.get(0).atZone(zone).getMinute()!=0 || times.get(0).getEpochSecond()%60!=0 || times.get(0).getNano()!=0)
            throw new IllegalArgumentException("源数据集未对齐整小时");
        Source source=new Source(directory, info, schema, metadata, times); source.manifest=manifest; return source;
    }

    public Window window(List<Source> sources, String from, String to) {
        if (sources.isEmpty() || sources.size()>20) throw new IllegalArgumentException("请选择 1–20 栋不同建筑");
        Instant start = sources.stream().map(s->s.timestamps.get(0)).max(Instant::compareTo).get();
        Instant end = sources.stream().map(s->s.timestamps.get(s.timestamps.size()-1).plusSeconds(3600)).min(Instant::compareTo).get();
        Object zone=sources.get(0).metadata.get("timezone"), currency=sources.get(0).metadata.getOrDefault("currency", "");
        for (Source source:sources) {
            if (!Objects.equals(zone,source.metadata.get("timezone"))) throw new IllegalArgumentException("社区建筑必须使用相同时区");
            if (!Objects.equals(currency,source.metadata.getOrDefault("currency", ""))) throw new IllegalArgumentException("社区建筑必须使用相同电价币种");
            if(!Objects.equals(sources.get(0).metadata.getOrDefault("timestampKind","measured"),source.metadata.getOrDefault("timestampKind","measured")))
                throw new IllegalArgumentException("真实时间与约定时间轴不能混合发布");
        }
        Instant chosenStart=from==null?start:Instant.parse(from), chosenEnd=to==null?end:Instant.parse(to);
        if (chosenStart.isBefore(start) || chosenEnd.isAfter(end) || !chosenEnd.isAfter(chosenStart))
            throw new IllegalArgumentException("所选时段必须位于各建筑数据集的共同时间范围内");
        long seconds=Duration.between(chosenStart,chosenEnd).getSeconds();
        if (seconds<7200 || seconds%3600!=0 || chosenStart.getNano()!=0 || chosenEnd.getNano()!=0)
            throw new IllegalArgumentException("至少需要两个完整小时，时间范围须对齐整小时");
        if (seconds/3600*sources.size()>2000000) throw new IllegalArgumentException("单个社区数据集最多包含 200 万建筑小时");
        for (Source source:sources) {
            int offset=source.timestamps.indexOf(chosenStart);
            if (offset<0) throw new IllegalArgumentException("所选开始时间未对齐源数据集的小时边界");
            for (int i=0;i<seconds/3600;i++) if (!source.timestamps.get(offset+i).equals(chosenStart.plusSeconds(i*3600L)))
                throw new IllegalArgumentException("各建筑时间戳不一致");
        }
        return new Window(chosenStart,chosenEnd);
    }

    @SuppressWarnings("unchecked")
    public String write(Path output, List<Source> sources, Window window, String id) throws Exception {
        return write(output,sources,window,id,null);
    }
    @SuppressWarnings("unchecked")
    public String write(Path output, List<Source> sources, Window window, String id,String reward) throws Exception {
        Map<String,Object> summary=preview(sources,window,reward);
        Files.createDirectories(output);
        Map<String,Object> schema=mapper.readValue(mapper.writeValueAsBytes(sources.get(0).schema),Map.class);
        Map<String,Map<String,Object>> observations=new LinkedHashMap<>(), actions=new LinkedHashMap<>();
        for (Source source:sources) {
            mergeSignals(observations,(Map<String,Map<String,Object>>)source.schema.get("observations"));
            mergeSignals(actions,(Map<String,Map<String,Object>>)source.schema.get("actions"));
        }
        Set<String> shared=new HashSet<>((List<String>)summary.get("sharedObservations"));
        observations.forEach((key,signal)->signal.put("shared_in_central_agent",shared.contains(key)));
        Map<String,Object> buildings=new LinkedHashMap<>();
        List<Map<String,Object>> provenance=new ArrayList<>();
        for (int i=0;i<sources.size();i++) {
            Source source=sources.get(i); String key="Building_"+(i+1);
            Map<String,Object> definition=mapper.readValue(mapper.writeValueAsBytes(((Map<?,?>)source.schema.get("buildings")).values().iterator().next()),Map.class);
            String suffix="_"+(i+1)+".csv";
            Map<String,String> files=Map.of("energy_simulation",key+".csv", "weather","weather"+suffix, "pricing","pricing"+suffix, "carbon_intensity","carbon_intensity"+suffix);
            int offset=source.timestamps.indexOf(window.start);
            for (Map.Entry<String,String> file:files.entrySet()) {
                copyRange(localFile(source.directory,definition.get(file.getKey()).toString()),output.resolve(file.getValue()),offset,window.steps,source.timestamps.size());
                definition.put(file.getKey(),file.getValue());
            }
            definition.put("inactive_observations",inactive(observations,(Map<String,Map<String,Object>>)source.schema.get("observations"),(List<String>)definition.get("inactive_observations")));
            definition.put("inactive_actions",inactive(actions,(Map<String,Map<String,Object>>)source.schema.get("actions"),(List<String>)definition.get("inactive_actions")));
            buildings.put(key,definition);
            Map<String,Object> entry=new LinkedHashMap<>(source.info); entry.put("buildingKey",key); entry.put("buildingName",source.metadata.get("name"));
            provenance.add(entry);
            for(String module:List.of("citylearn_ingested_devices.py","citylearn_external_rewards.py")) {
              Path adapter=source.directory.resolve(module);
              if (Files.isRegularFile(adapter)) {
                Path target=output.resolve(adapter.getFileName());
                if (Files.exists(target) && !Arrays.equals(Files.readAllBytes(target),Files.readAllBytes(adapter)))
                    throw new IllegalArgumentException("源数据集使用了不同版本的设备适配器，请重新发布");
                if (!Files.exists(target)) Files.copy(adapter,target);
              }
            }
        }
        copyRange(sources.get(0).directory.resolve("timestamps.csv"),output.resolve("timestamps.csv"),sources.get(0).timestamps.indexOf(window.start),window.steps,sources.get(0).timestamps.size());
        schema.put("root_directory",null); schema.put("central_agent",true); schema.put("simulation_start_time_step",0);
        schema.put("simulation_end_time_step",window.steps-1); schema.put("buildings",buildings); schema.put("observations",observations); schema.put("actions",actions);
        schema.put("reward_function",summary.get("rewardFunction"));
        String rewardType=((Map<?,?>)summary.get("rewardFunction")).get("type").toString();
        if(rewardType.startsWith("citylearn_external_rewards.") && !Files.exists(output.resolve("citylearn_external_rewards.py")))
            try(InputStream module=getClass().getResourceAsStream("/citylearn/citylearn_external_rewards.py")) {
                if(module==null) throw new IOException("Missing external reward module");
                Files.copy(module,output.resolve("citylearn_external_rewards.py"));
            }
        mapper.writerWithDefaultPrettyPrinter().writeValue(output.resolve("schema.json").toFile(),schema);
        Map<String,String> hashes=new TreeMap<>();
        try (java.util.stream.Stream<Path> paths=Files.list(output)) {
            for (Path file:paths.filter(Files::isRegularFile).collect(Collectors.toList())) hashes.put(file.getFileName().toString(),BuildingDatasetExporter.sha256(Files.readAllBytes(file)));
        }
        String hash=BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(hashes));
        Map<String,Object> manifest=new LinkedHashMap<>();
        manifest.put("version",id); manifest.put("profile","community-ingested-exogenous-thermal-demand");
        manifest.put("dataContract","CityLearn-Challenge-2023"); manifest.put("sources",provenance); manifest.put("buildingCount",sources.size()); manifest.put("timeSteps",window.steps);
        manifest.put("startTime",window.start.toString()); manifest.put("endTime",window.end.toString());
        manifest.put("building",Map.of("timezone",sources.get(0).metadata.get("timezone"),"currency",sources.get(0).metadata.getOrDefault("currency","")));
        manifest.put("forecastPolicy","preserve source forecast availability and horizons; inactive placeholders remain inactive"); manifest.put("thermalModel","measured exogenous thermal demand; no learned temperature dynamics");
        manifest.put("timestampKind",sources.get(0).metadata.getOrDefault("timestampKind","measured"));
        manifest.put("forecastHorizons",Map.of("1",6,"2",12,"3",24));
        manifest.put("publicationSummary",summary);
        manifest.put("files",hashes); manifest.put("contentHash",hash);
        mapper.writerWithDefaultPrettyPrinter().writeValue(output.resolve("manifest.json").toFile(),manifest);
        return hash;
    }

    @SuppressWarnings("unchecked")
    public Map<String,Object> preview(List<Source> sources,Window window,String reward) throws Exception {
        Map<String,Object> first=sources.get(0).schema;
        Object selectedReward=first.get("reward_function");
        if(reward!=null) selectedReward=BuildingExportOptions.parse(Map.of("reward",reward),Map.of()).rewardDefinition();
        for(Source source:sources) {
            for(String field:List.of("random_seed","agent","rolling_episode_split","random_episode_split","episode_time_steps"))
                if(!Objects.equals(first.get(field),source.schema.get(field))) throw new IllegalArgumentException("源数据集运行配置冲突: "+field);
            if(reward==null && !Objects.equals(first.get("reward_function"),source.schema.get("reward_function")))
                throw new IllegalArgumentException("源数据集的奖励配置不一致，请选择奖励配置一致的数据集");
            Map<?,?> definition=(Map<?,?>)((Map<?,?>)source.schema.get("buildings")).values().iterator().next();
            Object outage=definition.get("power_outage");
            if(!"citylearn.building.Building".equals(definition.get("type")) || definition.containsKey("dynamics") ||
                    outage instanceof Map && Boolean.TRUE.equals(((Map<?,?>)outage).get("simulate_power_outage")))
                throw new IllegalArgumentException("外部数据社区不支持学习动力学或停电场景");
            Map<?,?> localActions=(Map<?,?>)source.schema.get("actions");
            for(Object key:localActions.keySet()) if(Boolean.TRUE.equals(((Map<?,?>)localActions.get(key)).get("active")) && !BuildingExportOptions.STORAGE.contains(key.toString()))
                throw new IllegalArgumentException("不支持的社区控制动作: "+key);
            Map<?,?> localObservations=(Map<?,?>)source.schema.get("observations");
            boolean forecast=localObservations.entrySet().stream().anyMatch(entry->entry.getKey().toString().contains("_predicted_") && Boolean.TRUE.equals(((Map<?,?>)entry.getValue()).get("active")));
            if(forecast && !Map.of("1",6,"2",12,"3",24).equals(source.manifest.get("forecastHorizons")))
                throw new IllegalArgumentException("源预测时距不一致或未声明");
        }
        Map<String,Map<String,Object>> observations=new LinkedHashMap<>();
        for(Source source:sources) mergeSignals(observations,(Map<String,Map<String,Object>>)source.schema.get("observations"));
        List<Map<String,String>> digests=new ArrayList<>();
        for(Source source:sources) digests.add(signalDigests(source,window));
        List<String> shared=new ArrayList<>();
        for(String key:observations.keySet()) {
            boolean exogenous=List.of("month","hour","day_type","daylight_savings_status","carbon_intensity").contains(key) || key.startsWith("outdoor_") || key.contains("irradiance") || key.startsWith("electricity_pricing");
            if(!exogenous || !Boolean.TRUE.equals(observations.get(key).get("active"))) continue;
            String digest=digests.get(0).get(key);
            boolean same=digest!=null;
            for(int i=0;i<sources.size();i++) {
                Map<?,?> signals=(Map<?,?>)sources.get(i).schema.get("observations");
                Map<?,?> def=(Map<?,?>)((Map<?,?>)sources.get(i).schema.get("buildings")).values().iterator().next();
                List<?> inactive=(List<?>)def.get("inactive_observations");
                same &= signals.containsKey(key) && Boolean.TRUE.equals(((Map<?,?>)signals.get(key)).get("active")) && (inactive==null || !inactive.contains(key)) && Objects.equals(digest,digests.get(i).get(key));
            }
            if(same) shared.add(key);
        }
        List<Map<String,Object>> summaries=new ArrayList<>();
        for(Source source:sources) {
            Map<String,Object> summary=new LinkedHashMap<>();summary.put("buildingName",source.metadata.getOrDefault("name",source.info.get("buildingId")));
            summary.put("fields",source.manifest.getOrDefault("fieldSummary",List.of()));
            summary.put("simulation",source.manifest.getOrDefault("simulation",Map.of("profile","legacy-battery")));
            summary.put("forecastPolicy",source.manifest.getOrDefault("forecastPolicy","unknown"));summaries.add(summary);
        }
        return Map.of("ready",true,"blocker","","buildingCount",sources.size(),"timeSteps",window.steps,"sharedObservations",shared,"rewardFunction",selectedReward,"buildings",summaries);
    }
    private Map<String,String> signalDigests(Source source,Window window) throws Exception {
        Map<String,String> result=new HashMap<>();
        Map<?,?> definition=(Map<?,?>)((Map<?,?>)source.schema.get("buildings")).values().iterator().next();
        int offset=source.timestamps.indexOf(window.start);
        for(String file:List.of("energy_simulation","weather","pricing","carbon_intensity")) {
            try(BufferedReader reader=Files.newBufferedReader(localFile(source.directory,definition.get(file).toString()),StandardCharsets.UTF_8)) {
                String[] columns=reader.readLine().split(",",-1);
                java.security.MessageDigest[] hashes=new java.security.MessageDigest[columns.length];
                for(int i=0;i<columns.length;i++) hashes[i]=java.security.MessageDigest.getInstance("SHA-256");
                String line;int row=0;
                while((line=reader.readLine())!=null) {
                    if(row>=offset && row<offset+window.steps) {
                        String[] values=line.split(",",-1);
                        if(values.length!=columns.length) throw new IllegalArgumentException("源CSV列数无效");
                        for(int i=0;i<columns.length;i++) hashes[i].update((Double.toHexString(Double.parseDouble(values[i]))+"\n").getBytes(StandardCharsets.UTF_8));
                    }
                    row++;
                }
                if(row!=source.timestamps.size()) throw new IllegalArgumentException("源CSV行数无效");
                for(int i=0;i<columns.length;i++) result.put(columns[i],Base64.getEncoder().encodeToString(hashes[i].digest()));
            }
        }
        return result;
    }

    private void mergeSignals(Map<String,Map<String,Object>> target,Map<String,Map<String,Object>> source) {
        source.forEach((key,value)->{
            boolean active=Boolean.TRUE.equals(value.get("active")) || target.containsKey(key) && Boolean.TRUE.equals(target.get(key).get("active"));
            target.put(key,new LinkedHashMap<>(value)); target.get(key).put("active",active);
        });
    }
    private List<String> inactive(Map<String,Map<String,Object>> combined,Map<String,Map<String,Object>> original,List<String> existing) {
        Set<String> result=new LinkedHashSet<>(existing==null?List.of():existing);
        combined.forEach((key,value)->{if (Boolean.TRUE.equals(value.get("active")) && (!original.containsKey(key) || !Boolean.TRUE.equals(original.get(key).get("active")))) result.add(key);});
        return new ArrayList<>(result);
    }
    private Path localFile(Path directory,String name) {
        if (name==null || !name.matches("[A-Za-z0-9_.-]+") || name.equals(".") || name.equals("..")) throw new IllegalArgumentException("无效源数据集文件路径");
        return directory.resolve(name);
    }
    private void copyRange(Path source,Path target,int offset,int count,int expected) throws IOException {
        // Source CSV files are generated numeric tables, with one unquoted record per line.
        try (BufferedReader reader=Files.newBufferedReader(source,StandardCharsets.UTF_8); BufferedWriter writer=Files.newBufferedWriter(target,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW)) {
            String header=reader.readLine(); if (header==null) throw new IllegalArgumentException("源 CSV 缺少表头");
            writer.write(header); writer.newLine(); String line; int index=0;
            while ((line=reader.readLine())!=null) { if (index>=offset && index<offset+count) {writer.write(line); writer.newLine();} index++; }
            if (index!=expected) throw new IllegalArgumentException("源 CSV 行数与时间戳不一致");
        }
    }
}
