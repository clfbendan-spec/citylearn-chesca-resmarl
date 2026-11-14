package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import javax.annotation.Resource;
import java.nio.file.*;
import java.time.*;
import java.util.*;

@Service
public class CommunityPublicationService {
    @Resource private CommunityManagementService communities;
    @Resource private BuildingIngestionService buildings;
    @Resource private CommunityDatasetService releases;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;
    @Resource private CommunityRuntimeValidator runtime;
    @Resource private DatasetDynamicsService dynamics;
    @Resource private PlatformTransactionManager transactionManager;
    private final MeasurementContract contract=new MeasurementContract();

    public Map<String,Object> availableRange(long community,Map<String,Object> request) throws Exception {
        try {
            Prepared prepared=prepare(community,Map.of("buildingIds",request.getOrDefault("buildingIds",List.of())),false,true);
            return Map.of("ready",true,"startTime",prepared.start.toString(),"endTime",prepared.end.toString(),
                    "sourceEndTime",prepared.end.plusSeconds(86400).toString(),"bufferHours",24);
        } catch(IllegalArgumentException error) {return Map.of("ready",false,"blocker",error.getMessage());}
    }

    public List<Map<String,Object>> list(long community) {
        communities.get(community,false);
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT c.id,c.schema_key AS schemaKey,c.name,c.start_time AS startTime,c.end_time AS endTime,c.time_steps AS timeSteps,c.building_count AS buildingCount,c.create_time AS createTime FROM community_dataset_release c JOIN community_dataset_owner o ON o.release_id=c.id JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY c.schema_key AND d.enabled=1 WHERE o.community_id=? ORDER BY c.create_time DESC,c.id",community);
        for(Map<String,Object> row:rows) {
            try {
                Path manifest=releases.directory(row.get("id").toString()).resolve("manifest.json");
                Map<?,?> source=mapper.readValue(manifest.toFile(),Map.class);
                if("synthetic_ol1".equals(source.get("sourceMode"))) {
                    row.put("sourceMode","synthetic_ol1");
                    row.put("sourceStartStep",0);
                    row.put("scoreStartStep",source.get("scoreStartStep"));
                    row.put("scoreEndStepExclusive",source.get("scoreEndStepExclusive"));
                    row.put("contentHash",source.get("contentHash"));
                } else row.put("sourceMode","external_snapshot");
            } catch(Exception error) { row.put("sourceMode","external_snapshot"); }
        }
        return rows;
    }

    @Transactional(readOnly=true)
    public Map<String,Object> preview(long community,Map<String,Object> request) throws Exception {
        Path temporary=Files.createTempDirectory("community-preview-");
        try {
            Prepared prepared=prepare(community,request,false);
            Map<String,Object> result=write(temporary.resolve("package"),temporary.resolve("sources"),prepared,"preview",false,null);
            result.put("ready",true); result.put("blocker","");return result;
        } catch(IllegalArgumentException error) {
            return Map.of("ready",false,"blocker",error.getMessage());
        } finally {removeTemporary(temporary);}
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> publish(long community,Map<String,Object> request) throws Exception {
        return publishWithProgress(community,request,null);
    }

    public Map<String,Object> publishWithProgress(long community,Map<String,Object> request,java.util.function.BiConsumer<Integer,Integer> progress) throws Exception {
        String name=Objects.toString(request.get("name"),"").trim();
        if(name.isEmpty() || name.length()>160) throw new IllegalArgumentException("请填写1–160个字符的数据集名称");
        TransactionTemplate transaction=new TransactionTemplate(transactionManager);
        Prepared prepared=transaction.execute(status->{
            try {return prepare(community,request,true);}
            catch(Exception error){throw new IllegalArgumentException(error.getMessage(),error);}
        });
        String id=UUID.randomUUID().toString(),key="community_"+id.replace("-","");
        Path output=Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize().resolve("datasets").resolve(key);
        Files.createDirectories(output.getParent());Files.createDirectory(output);
        try {
        Path temporary=Files.createTempDirectory("community-sources-");
        Map<String,Object> result;
        try {result=write(output,temporary,prepared,id,true,progress);} finally {removeTemporary(temporary);}
        Map<String,Object> manifest=mapper.readValue(output.resolve("manifest.json").toFile(),Map.class);
        String hash=manifest.get("contentHash").toString();
        String sources=mapper.writeValueAsString(manifest.get("sources"));
        return transaction.execute(status->{
            communities.get(community,true);
            DatasetSnapshotFiles.cleanupOnRollback(output);
            jdbc.update("INSERT INTO community_dataset_release(id,schema_key,name,start_time,end_time,time_steps,building_count,sources_json,content_hash) VALUES (?,?,?,?,?,?,?,?,?)",id,key,name,prepared.start.toString(),prepared.end.toString(),result.get("timeSteps"),prepared.ids.size(),sources,hash);
            jdbc.update("INSERT INTO community_dataset_owner(release_id,community_id) VALUES (?,?)",id,community);
            jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled,sort_order,description) VALUES (?,?,?,?,?,0,1,210,?)",key,name,"datasets/"+key,prepared.ids.size(),result.get("timeSteps"),"社区数据快照 · "+community+" · "+id);
            return Map.of("id",id,"schemaKey",key,"buildingCount",prepared.ids.size(),"timeSteps",result.get("timeSteps"),"startTime",prepared.start.toString(),"endTime",prepared.end.toString(),"contentHash",hash);
        });
        } catch(Exception error) {removeTemporary(output);throw error;}
    }

    public Path directory(long community,String release) {
        communities.get(community,false);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_dataset_owner WHERE community_id=? AND release_id=?",Integer.class,community,release)!=1)
            throw new IllegalArgumentException("数据集不属于该社区");
        return releases.directory(release);
    }
    @Transactional public void delete(long community,String release) {
        communities.get(community,true);directory(community,release);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE community_id=? AND release_id=? AND status IN ('queued','running')",Integer.class,community,release)>0)
            throw new IllegalArgumentException("该数据集有执行中的初步评估，请先取消或等待完成");
        releases.delete(release);
    }

    @SuppressWarnings("unchecked")
    private Prepared prepare(long community,Map<String,Object> request,boolean lock) throws Exception {
        return prepare(community,request,lock,false);
    }
    @SuppressWarnings("unchecked")
    private Prepared prepare(long community,Map<String,Object> request,boolean lock,boolean boundsOnly) throws Exception {
        Map<String,Object> metadata=communities.get(community,lock);
        Object selection=request.get("buildingIds");
        if(!(selection instanceof List) || ((List<?>)selection).isEmpty() || ((List<?>)selection).size()>20)
            throw new IllegalArgumentException("请选择社区内1–20栋建筑");
        List<Long> ids=new ArrayList<>();
        for(Object item:(List<?>)selection) {
            if(!(item instanceof Number) || ((Number)item).doubleValue()!=((Number)item).longValue() || ((Number)item).longValue()<=0)
                throw new IllegalArgumentException("建筑选择无效");
            long id=((Number)item).longValue();
            if(ids.contains(id)) throw new IllegalArgumentException("不能重复选择建筑");
            ids.add(id);
        }
        // A single lock order is used by ingestion and publication.
        Map<Long,Map<String,Object>> definitions=new HashMap<>();
        for(long id:new TreeSet<>(ids)) {
            if(jdbc.queryForObject("SELECT COUNT(*) FROM community_building WHERE community_id=? AND building_id=?",Integer.class,community,id)!=1)
                throw new IllegalArgumentException("所选建筑不属于该社区");
            definitions.put(id,buildings.get(id,lock));
        }
        ZoneId zone=ZoneId.of(metadata.get("timezone").toString());
        int interval=((Number)metadata.get("intervalSeconds")).intValue();
        Instant requestedStart=request.get("from")==null?null:contract.timestamp(request.get("from"),zone);
        Instant requestedEnd=request.get("to")==null?null:contract.timestamp(request.get("to"),zone);
        if((requestedStart==null)!=(requestedEnd==null)) throw new IllegalArgumentException("请选择完整的时间范围");
        Instant start=null,end=null;
        {
            for(long id:ids) {
                Map<String,Object> range=jdbc.queryForMap("SELECT MIN(timestamp_ms) AS first,MAX(timestamp_ms) AS last FROM building_measurement WHERE building_id=?",id);
                if(range.get("first")==null) throw new IllegalArgumentException("建筑没有接入数据: "+definitions.get(id).get("name"));
                Instant first=Instant.ofEpochMilli(((Number)range.get("first")).longValue());
                Instant last=Instant.ofEpochMilli(((Number)range.get("last")).longValue()).plusSeconds(interval);
                start=start==null || first.isAfter(start)?first:start;
                end=end==null || last.isBefore(end)?last:end;
            }
            if(start.isBefore(end)) {
                Instant joinedStart=start,joinedEnd=end;
                for(long id:ids) {
                    Set<String> required=new HashSet<>(MeasurementContract.REQUIRED);
                    if("assigned".equals(metadata.get("timestampKind"))) required.addAll(MeasurementContract.CATEGORY.stream().filter(k->!k.equals("hvac_mode")).collect(java.util.stream.Collectors.toSet()));
                    Instant first=completeBoundary(community,id,required,zone,interval,start,end,true);
                    Instant last=completeBoundary(community,id,required,zone,interval,start,end,false);
                    if(first==null || last==null) throw new IllegalArgumentException("建筑与社区共享数据没有完整小时交集: "+definitions.get(id).get("name"));
                    last=last.plusSeconds(3600);
                    if(first.isAfter(joinedStart)) joinedStart=first;
                    if(last.isBefore(joinedEnd)) joinedEnd=last;
                }
                start=joinedStart;end=joinedEnd;
            }
        }
        // End is exclusive: the last selected hour must still have its t+24 source hour.
        end=end.minusSeconds(CommunityForecastGenerator.BUFFER_HOURS*3600L);
        if(Duration.between(start,end).getSeconds()<7200)
            throw new IllegalArgumentException("共同完整数据不足：至少需要2小时发布数据和末尾24小时预测缓冲数据");
        if(boundsOnly) return new Prepared(community,ids,List.of(),List.of(),Map.of(),start,end,List.of());
        if(requestedStart!=null) {
            if(requestedStart.isBefore(start) || requestedEnd.isAfter(end))
                throw new IllegalArgumentException("发布时间范围超出可用区间，结束时间必须至少预留24小时；最晚结束边界为 "+end);
            start=requestedStart;end=requestedEnd;
        }
        long seconds=Duration.between(start,end).getSeconds();
        if(seconds<7200 || seconds%3600!=0 || start.getNano()!=0 || end.getNano()!=0 || start.atZone(zone).getMinute()!=0 || start.atZone(zone).getSecond()!=0)
            throw new IllegalArgumentException("请选择至少两个完整小时的共同时间范围");
        Instant bufferEnd=end.plusSeconds(CommunityForecastGenerator.BUFFER_HOURS*3600L);
        long expected=(seconds+CommunityForecastGenerator.BUFFER_HOURS*3600L)/interval;
        if(expected>200000 || seconds/3600*ids.size()>2000000) throw new IllegalArgumentException("发布范围超过200000条源记录或200万建筑小时");
        Map<String,Map<String,Object>> shared=new HashMap<>();
        for(Map<String,Object> row:communities.rows(community,start.toString(),bufferEnd.toString())) shared.put(row.get("timestamp").toString(),row);
        List<Map<String,Object>> ordered=new ArrayList<>();List<List<Map<String,Object>>> hourly=new ArrayList<>();
        List<Map<String,Object>> forecastReports=new ArrayList<>();
        for(long id:ids) {
            Map<String,Object> definition=definitions.get(id);
            for(String field:List.of("timezone","currency","intervalSeconds","timestampKind"))
                if(!Objects.equals(Objects.toString(metadata.get(field)),Objects.toString(definition.get(field))))
                    throw new IllegalArgumentException("建筑与社区时间/币种配置不一致: "+definition.get("name")+" / "+field);
            List<Map<String,Object>> raw=jdbc.query("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT 200001",(rs,n)->decode(rs.getString(1)),id,start.toEpochMilli(),bufferEnd.toEpochMilli());
            if(raw.size()!=expected) throw new IllegalArgumentException("建筑数据边界或内部存在缺失: "+definition.get("name"));
            List<Map<String,Object>> merged=new ArrayList<>();
            for(int i=0;i<raw.size();i++) {
                Map<String,Object> row=new LinkedHashMap<>(raw.get(i));String timestamp=start.plusSeconds((long)i*interval).toString();
                if(!timestamp.equals(row.get("timestamp"))) throw new IllegalArgumentException("建筑时间戳不连续: "+definition.get("name"));
                Map<String,Object> common=shared.get(timestamp);
                if(common!=null) for(Map.Entry<String,Object> value:common.entrySet()) {
                    if(row.containsKey(value.getKey()) && !equivalent(row.get(value.getKey()),value.getValue()))
                        throw new IllegalArgumentException("建筑与社区共享数据冲突: "+definition.get("name")+" / "+value.getKey()+" @ "+timestamp);
                    row.putIfAbsent(value.getKey(),value.getValue());
                }
                merged.add(row);
            }
            // Aggregate actuals separately; incomplete supplied forecasts are filled per hour.
            List<Map<String,Object>> actuals=new ArrayList<>();
            for(Map<String,Object> row:merged) {
                Map<String,Object> actual=new LinkedHashMap<>(row);
                actual.keySet().removeIf(key->key.contains("_predicted_"));
                actuals.add(actual);
            }
            List<Map<String,Object>> hours=contract.hourly(actuals,zone,interval);
            int samplesPerHour=3600/interval;
            for(int h=0;h<hours.size();h++) for(String key:MeasurementContract.FIELDS.keySet()) {
                if(!key.contains("_predicted_")) continue;
                List<Map<String,Object>> samples=merged.subList(h*samplesPerHour,(h+1)*samplesPerHour);
                if(samples.stream().allMatch(row->row.get(key) instanceof Number))
                    hours.get(h).put(key,samples.stream().mapToDouble(row->((Number)row.get(key)).doubleValue()).average().getAsDouble());
            }
            Map<String,Object> report=new CommunityForecastGenerator().generate(hours,(int)(seconds/3600));
            forecastReports.add(Map.of("buildingId",id,"fields",report));
            hours=new ArrayList<>(hours.subList(0,(int)(seconds/3600)));
            if(BuildingDatasetExporter.summary(definition,hours).stream().anyMatch(f->"missing".equals(f.get("status"))))
                throw new IllegalArgumentException("发布字段不完整，约定时间轴必须提供原日历字段: "+definition.get("name"));
            hourly.add(hours);ordered.add(definition);
        }
        return new Prepared(community,ids,ordered,hourly,Map.of("defaultsSource","citylearn_challenge_2023_phase_2_online_evaluation_1"),start,end,forecastReports);
    }

    private Instant completeBoundary(long community,long building,Set<String> required,ZoneId zone,int interval,
                                     Instant start,Instant end,boolean forward) {
        // Search in bounded batches; a long ingestion history must not block a small publication.
        Instant cursor=forward?start:end;
        while(forward?cursor.isBefore(end):cursor.isAfter(start)) {
            Instant lower=forward?cursor:cursor.minusSeconds(48*3600);
            Instant upper=forward?cursor.plusSeconds(48*3600):cursor;
            if(lower.isBefore(start)) lower=start;
            if(upper.isAfter(end)) upper=end;
            Map<String,Map<String,Object>> shared=new HashMap<>();
            for(Map<String,Object> row:communities.rows(community,lower.toString(),upper.toString()))
                shared.put(Objects.toString(row.get("timestamp"),""),row);
            List<Map<String,Object>> samples=jdbc.query("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms",
                    (rs,n)->decode(rs.getString(1)),building,lower.toEpochMilli(),upper.toEpochMilli());
            SortedMap<Instant,Integer> complete=new TreeMap<>();
            for(Map<String,Object> sample:samples) {
                Map<String,Object> merged=new HashMap<>(shared.getOrDefault(sample.get("timestamp"),Map.of()));
                merged.putAll(sample);
                if(!required.stream().allMatch(key->merged.get(key) instanceof Number)) continue;
                Instant hour=Instant.parse(sample.get("timestamp").toString()).atZone(zone).truncatedTo(java.time.temporal.ChronoUnit.HOURS).toInstant();
                complete.merge(hour,1,Integer::sum);
            }
            List<Instant> hours=new ArrayList<>();
            complete.forEach((hour,count)->{if(count==3600/interval) hours.add(hour);});
            if(!hours.isEmpty()) return forward?hours.get(0):hours.get(hours.size()-1);
            cursor=forward?upper:lower;
        }
        return null;
    }

    private Map<String,Object> write(Path output,Path scratch,Prepared prepared,String version,boolean generate,java.util.function.BiConsumer<Integer,Integer> progress) throws Exception {
        Files.createDirectories(scratch);
        CommunityDatasetExporter exporter=new CommunityDatasetExporter(mapper);
        List<CommunityDatasetExporter.Source> sources=new ArrayList<>();
        for(int i=0;i<prepared.ids.size();i++) {
            Path source=scratch.resolve("building-"+prepared.ids.get(i));
            String hash=new BuildingDatasetExporter(mapper).write(source,prepared.definitions.get(i),prepared.rows.get(i),version,Map.of("profile","storage","reward","energy"));
            sources.add(exporter.load(source,Map.of("buildingId",prepared.ids.get(i),"contentHash",hash,"source","community-measurement-snapshot")));
        }
        CommunityDatasetExporter.Window window=exporter.window(sources,prepared.start.toString(),prepared.end.toString());
        Map<String,Object> summary=new LinkedHashMap<>(exporter.preview(sources,window,null));
        exporter.write(output,sources,window,version);
        Map<String,Object> models=dynamics.prepare(output,generate,progress);
        if(models!=null) summary.putAll(models);
        if(generate) summary.putAll(runtime.validate(output));
        Map<String,Object> manifest=mapper.readValue(output.resolve("manifest.json").toFile(),Map.class);
        Map<String,Object> schema=mapper.readValue(output.resolve("schema.json").toFile(),Map.class);
        if(manifest.get("publicationSummary") instanceof Map) summary.putAll((Map<String,Object>)manifest.get("publicationSummary"));
        summary.put("rewardFunction",schema.get("reward_function"));
        summary.put("thermalModel","LSTMDynamics");
        summary.put("modelGenerationRequired",!generate);
        if(summary.get("buildings") instanceof List) {
            List<Map<String,Object>> details=(List<Map<String,Object>>)summary.get("buildings");
            Map<String,Map<String,Object>> exported=(Map<String,Map<String,Object>>)schema.get("buildings");
            for(int i=0;i<details.size();i++) {
                Map<String,Object> definition=exported.get("Building_"+(i+1));
                details.get(i).put("buildingId",prepared.ids.get(i));
                details.get(i).put("simulation",Map.of("buildingType",definition.get("type"),"dynamics",definition.getOrDefault("dynamics",Map.of()),"powerOutage",definition.getOrDefault("power_outage",Map.of())));
                Map<?,?> counts=(Map<?,?>)prepared.forecastReports.get(i).get("fields");
                for(Map<String,Object> field:(List<Map<String,Object>>)details.get(i).getOrDefault("fields",List.of())) {
                    Map<?,?> count=(Map<?,?>)counts.get(field.get("key"));
                    if(count==null) continue;
                    int generated=((Number)count.get("generated")).intValue(),provided=((Number)count.get("provided")).intValue();
                    field.put("generated",generated);field.put("present",provided);
                    field.put("status",generated==0?"preserved":provided==0?"generated":"mixed");
                }
            }
            manifest.put("publicationSummary",summary);
        }
        Map<String,Object> communityMetadata=communities.get(prepared.community,false);
        manifest.put("communityId",prepared.community);manifest.put("communityName",communityMetadata.get("name"));
        manifest.put("configuration",prepared.configuration);
        Map<String,Object> forecastGeneration=new LinkedHashMap<>(CommunityForecastGenerator.policy());
        forecastGeneration.put("sourceStartTime",prepared.start.toString());
        forecastGeneration.put("sourceEndTime",prepared.end.plusSeconds(86400).toString());
        forecastGeneration.put("buildings",prepared.forecastReports);
        manifest.put("forecastGeneration",forecastGeneration);
        manifest.put("forecastPolicy","supplied hourly forecasts preserved; missing forecasts generated from future observations with documented research errors; final 24 hours reserved");
        summary.put("forecastGeneration",forecastGeneration);
        mapper.writerWithDefaultPrettyPrinter().writeValue(output.resolve("manifest.json").toFile(),manifest);
        summary.put("configuration",prepared.configuration);summary.put("startTime",prepared.start.toString());summary.put("endTime",prepared.end.toString());
        summary.put("observationCount",((Map<?,?>)schema.get("observations")).values().stream().filter(v->Boolean.TRUE.equals(((Map<?,?>)v).get("active"))).count());
        summary.put("actionCount",((Map<?,?>)schema.get("actions")).values().stream().filter(v->Boolean.TRUE.equals(((Map<?,?>)v).get("active"))).count());
        return summary;
    }
    private boolean equivalent(Object first,Object second) {
        if(first instanceof Number && second instanceof Number) {
            double a=((Number)first).doubleValue(),b=((Number)second).doubleValue();return Math.abs(a-b)<=1e-12*Math.max(1,Math.max(Math.abs(a),Math.abs(b)));
        }
        return Objects.equals(first,second);
    }
    private Map<String,Object> decode(String value) {try{return mapper.readValue(value,Map.class);}catch(Exception error){throw new IllegalArgumentException("测量数据无效",error);}}
    private void removeTemporary(Path directory) throws Exception {
        if(!Files.exists(directory))return;
        try(java.util.stream.Stream<Path> paths=Files.walk(directory)){for(Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator)Files.deleteIfExists(path);}
    }
    private static class Prepared {
        final long community;final List<Long> ids;final List<Map<String,Object>> definitions;final List<List<Map<String,Object>>> rows;final Map<String,Object> configuration;final Instant start,end;
        final List<Map<String,Object>> forecastReports;
        Prepared(long community,List<Long> ids,List<Map<String,Object>> definitions,List<List<Map<String,Object>>> rows,Map<String,Object> configuration,Instant start,Instant end,List<Map<String,Object>> forecastReports){this.community=community;this.ids=ids;this.definitions=definitions;this.rows=rows;this.configuration=configuration;this.start=start;this.end=end;this.forecastReports=forecastReports;}
    }
}
