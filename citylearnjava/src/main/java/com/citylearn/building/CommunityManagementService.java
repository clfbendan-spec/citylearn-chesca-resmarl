package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.*;
import java.util.*;

@Service
@DependsOn("buildingSchemaMigration")
public class CommunityManagementService {
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private BuildingIngestionService buildingService;
    @Resource private FileResourceProperties files;
    private final MeasurementContract contract = new MeasurementContract();

    public static boolean sharedField(String key) {
        return Set.of("month", "hour", "day_type", "daylight_savings_status", "carbon_intensity").contains(key)
                || key.startsWith("outdoor_") || key.startsWith("diffuse_solar_irradiance")
                || key.startsWith("direct_solar_irradiance") || key.startsWith("electricity_pricing");
    }
    public List<Map<String,Object>> list() {
        return jdbc.query("SELECT c.*,(SELECT COUNT(*) FROM community_building cb JOIN managed_building b ON b.id=cb.building_id AND b.archived=0 WHERE cb.community_id=c.id) building_count,"
                        + "(SELECT COUNT(*) FROM community_measurement m WHERE m.community_id=c.id) sample_count,"
                        + "(SELECT MAX(timestamp_ms) FROM community_measurement m WHERE m.community_id=c.id) last_sample FROM managed_community c WHERE archived=0 ORDER BY id DESC",
                (rs,n)-> {
                    Map<String,Object> row=decode(rs.getString("metadata"));
                    row.put("id",rs.getLong("id"));row.put("hasToken",rs.getString("token_hash")!=null);
                    row.put("buildingCount",rs.getLong("building_count"));row.put("count",rs.getLong("sample_count"));
                    long last=rs.getLong("last_sample");row.put("lastSample",rs.wasNull()?null:Instant.ofEpochMilli(last).toString());return row;
                });
    }
    public Map<String,Object> get(long id,boolean lock) {
        List<Map<String,Object>> found=jdbc.query("SELECT * FROM managed_community WHERE id=? AND archived=0"+(lock?" FOR UPDATE":""),
                (rs,n)-> {
                    Map<String,Object> row=decode(rs.getString("metadata"));row.put("id",rs.getLong("id"));
                    row.put("hasToken",rs.getString("token_hash")!=null);return row;
                },id);
        if(found.isEmpty()) throw new IllegalArgumentException("社区不存在或已删除");
        Map<String,Object> row=found.get(0);row.put("assets",assets(id));return row;
    }
    @Transactional public Map<String,Object> save(Long id,Map<String,Object> input) {
        Map<String,Object> previous=id==null?new LinkedHashMap<>():get(id,true);
        Map<String,Object> merged=new LinkedHashMap<>(previous);merged.putAll(input);
        Map<String,Object> data=new LinkedHashMap<>();
        String name=text(merged.get("name"));if(name.isEmpty()||name.length()>120)throw new IllegalArgumentException("社区名称应为1至120个字符");
        String timezone=text(merged.getOrDefault("timezone","Asia/Shanghai"));ZoneId.of(timezone);
        String currency=text(merged.getOrDefault("currency","CNY"));if(currency.isEmpty()||currency.length()>32)throw new IllegalArgumentException("请填写货币单位");
        int interval;try{interval=Integer.parseInt(merged.getOrDefault("intervalSeconds",3600).toString());}catch(RuntimeException e){throw new IllegalArgumentException("采样周期无效");}
        if(!List.of(60,300,900,1800,3600).contains(interval))throw new IllegalArgumentException("不支持的采样周期");
        String kind=text(merged.getOrDefault("timestampKind","measured"));if(!List.of("measured","assigned").contains(kind))throw new IllegalArgumentException("时间轴来源无效");
        data.put("name",name);data.put("timezone",timezone);data.put("currency",currency);data.put("intervalSeconds",interval);data.put("timestampKind",kind);
        if(id==null){
            GeneratedKeyHolder key=new GeneratedKeyHolder();jdbc.update(connection->{PreparedStatement ps=connection.prepareStatement("INSERT INTO managed_community(name,metadata) VALUES (?,?)",Statement.RETURN_GENERATED_KEYS);ps.setString(1,name);ps.setString(2,encode(data));return ps;},key);
            id=Objects.requireNonNull(key.getKey()).longValue();
        }else{
            boolean timingChanged=!Objects.equals(previous.get("timezone"),timezone)||!Objects.equals(previous.get("currency"),currency)
                    ||((Number)previous.get("intervalSeconds")).intValue()!=interval||!Objects.equals(previous.get("timestampKind"),kind);
            if(timingChanged){
                long sampleCount=jdbc.queryForObject("SELECT COUNT(*) FROM community_measurement WHERE community_id=?",Long.class,id);
                long buildingCount=jdbc.queryForObject("SELECT COUNT(*) FROM community_building cb JOIN managed_building b ON b.id=cb.building_id AND b.archived=0 WHERE cb.community_id=?",Long.class,id);
                if(sampleCount>0||buildingCount>0)throw new IllegalArgumentException("已有共享数据或建筑的社区不能修改时区、货币、采样周期或时间轴来源");
            }
            jdbc.update("UPDATE managed_community SET name=?,metadata=? WHERE id=?",name,encode(data),id);
        }
        return get(id,false);
    }
    public List<Map<String,Object>> buildings(long id){
        get(id,false);
        List<Long> ids=jdbc.query("SELECT b.id FROM community_building cb JOIN managed_building b ON b.id=cb.building_id AND b.archived=0 WHERE cb.community_id=? ORDER BY b.id",(rs,n)->rs.getLong(1),id);
        List<Map<String,Object>> result=new ArrayList<>();
        for(Map<String,Object> building:buildingService.list())if(ids.contains(((Number)building.get("id")).longValue()))result.add(building);
        return result;
    }
    @Transactional public Map<String,Object> addBuilding(long id,Map<String,Object> input){
        Map<String,Object> community=get(id,true);
        if(input.get("buildingId")!=null){
            long buildingId;try{buildingId=Long.parseLong(input.get("buildingId").toString());}catch(RuntimeException e){throw new IllegalArgumentException("建筑ID无效");}
            Map<String,Object> building=buildingService.get(buildingId,true);
            List<Long> owner=jdbc.query("SELECT community_id FROM community_building WHERE building_id=?",(rs,n)->rs.getLong(1),buildingId);
            if(!owner.isEmpty()&&owner.get(0)!=id)throw new IllegalArgumentException("建筑已属于其他社区");
            for(String key:List.of("timezone","currency","intervalSeconds","timestampKind"))if(!Objects.equals(String.valueOf(building.get(key)),String.valueOf(community.get(key))))throw new IllegalArgumentException("建筑与社区配置不一致: "+key);
            jdbc.update("INSERT IGNORE INTO community_building(community_id,building_id) VALUES (?,?)",id,buildingId);
            return buildingService.get(buildingId,false);
        }
        Map<String,Object> building=new LinkedHashMap<>(input);
        for(String key:List.of("timezone","currency","intervalSeconds","timestampKind"))building.put(key,community.get(key));
        building.put("communityId",id);return buildingService.save(null,building);
    }
    @Transactional public void delete(long id){
        get(id,true);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE community_id=? AND status IN ('queued','running')",Integer.class,id)>0)
            throw new IllegalArgumentException("社区有执行中的初步评估，请先取消或等待完成");
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_publication_task WHERE community_id=? AND status IN ('queued','running')",Integer.class,id)>0)
            throw new IllegalArgumentException("社区有执行中的数据集发布，请等待完成");
        long running=jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run r JOIN community_building cb ON cb.building_id=r.building_id WHERE cb.community_id=? AND r.status IN ('queued','running')",Long.class,id);
        if(running>0)throw new IllegalArgumentException("社区有排队或运行中的任务");
        jdbc.update("UPDATE managed_community SET archived=1,token_hash=NULL WHERE id=?",id);
        jdbc.update("UPDATE managed_building b JOIN community_building cb ON cb.building_id=b.id SET b.token_hash=NULL WHERE cb.community_id=?",id);
        jdbc.update("UPDATE citylearn_dataset SET enabled=0 WHERE BINARY schema_key IN (SELECT BINARY r.schema_key FROM community_dataset_release r JOIN community_dataset_owner o ON o.release_id=r.id WHERE o.community_id=?)",id);
    }
    @Transactional public String rotateToken(long id){
        get(id,true);byte[] bytes=new byte[32];new java.security.SecureRandom().nextBytes(bytes);
        String token=Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);jdbc.update("UPDATE managed_community SET token_hash=? WHERE id=?",hash(token),id);return token;
    }
    public boolean authenticate(long id,String authorization){
        if(authorization==null||!authorization.startsWith("Bearer "))return false;
        List<String> tokens=jdbc.query("SELECT token_hash FROM managed_community WHERE id=? AND archived=0",(rs,n)->rs.getString(1),id);
        return !tokens.isEmpty()&&tokens.get(0)!=null&&java.security.MessageDigest.isEqual(tokens.get(0).getBytes(StandardCharsets.UTF_8),hash(authorization.substring(7)).getBytes(StandardCharsets.UTF_8));
    }
    @Transactional public Map<String,Object> ingest(long id,List<Map<String,Object>> raw,Map<String,String> mapping,Map<String,String> units,String source,List<Map<String,String>> sourceFiles,String timestampKind){
        Map<String,Object> community=get(id,true);
        if(timestampKind!=null&&!timestampKind.equals(community.get("timestampKind")))throw new IllegalArgumentException("导入时间轴来源与社区不一致");
        if(raw==null||raw.isEmpty()||raw.size()>10000)throw new IllegalArgumentException("每批应为1至10000条");
        if(mapping==null)mapping=Map.of();if(units==null)units=Map.of();
        for(String key:mapping.keySet())if(!key.equals("timestamp")&&(!MeasurementContract.FIELDS.containsKey(key)||!sharedField(key)))throw new IllegalArgumentException("社区不支持测量字段: "+key);
        List<Map<String,Object>> originals=sourceFiles(sourceFiles);
        ZoneId zone=ZoneId.of(community.get("timezone").toString());int interval=((Number)community.get("intervalSeconds")).intValue();
        Map<Long,Map<String,Object>> normalized=new TreeMap<>();int duplicates=0;
        for(int i=0;i<raw.size();i++){
            Map<String,Object> row;
            try{
                if(raw.get(i)==null)throw new IllegalArgumentException("空测量行");
                for(String key:MeasurementContract.FIELDS.keySet())if(!sharedField(key)){
                    Object value=raw.get(i).get(mapping.getOrDefault(key,key));if(value!=null&&!value.toString().trim().isEmpty())throw new IllegalArgumentException("建筑本地字段不能导入社区: "+key);
                }
                row=contract.normalize(raw.get(i),zone,interval,mapping,units);
            }catch(RuntimeException e){throw new IllegalArgumentException("第"+(i+1)+"行: "+e.getMessage());}
            long timestamp=Instant.parse(row.get("timestamp").toString()).toEpochMilli();
            if(normalized.containsKey(timestamp)){Map<String,Object> previous=normalized.get(timestamp);int count=previous.size();merge(previous,row);if(count==previous.size())duplicates++;}
            else normalized.put(timestamp,row);
        }
        List<Map.Entry<Long,Map<String,Object>>> inserts=new ArrayList<>(),updates=new ArrayList<>();
        for(Map.Entry<Long,Map<String,Object>> row:normalized.entrySet()){
            List<String> existing=jdbc.query("SELECT payload FROM community_measurement WHERE community_id=? AND timestamp_ms=?",(rs,n)->rs.getString(1),id,row.getKey());
            if(existing.isEmpty())inserts.add(row);
            else{Map<String,Object> previous=decode(existing.get(0));int count=previous.size();merge(previous,row.getValue());
                if(count==previous.size())duplicates++;else updates.add(new AbstractMap.SimpleEntry<>(row.getKey(),previous));}
        }
        jdbc.batchUpdate("INSERT INTO community_measurement(community_id,timestamp_ms,payload,source) VALUES (?,?,?,?)",inserts,500,(ps,row)->{ps.setLong(1,id);ps.setLong(2,row.getKey());ps.setString(3,encode(row.getValue()));ps.setString(4,source);});
        jdbc.batchUpdate("UPDATE community_measurement SET payload=?,source=? WHERE community_id=? AND timestamp_ms=?",updates,500,(ps,row)->{ps.setString(1,encode(row.getValue()));ps.setString(2,source);ps.setLong(3,id);ps.setLong(4,row.getKey());});
        String batch=UUID.randomUUID().toString();String payload=encode(Map.of("rows",raw,"mapping",mapping,"units",units,"community",community,"sourceFiles",originals));
        jdbc.update("INSERT INTO community_ingestion_batch(id,community_id,source,raw_payload,payload_hash,accepted,duplicates) VALUES (?,?,?,?,?,?,?)",batch,id,source,payload,hash(payload),inserts.size()+updates.size(),duplicates);
        if("realtime".equals(source))HomeRealtimeMeasurements.retain(jdbc,mapper,"community",id,normalized);
        return Map.of("batchId",batch,"inserted",inserts.size(),"updated",updates.size(),"duplicates",duplicates);
    }
    private void merge(Map<String,Object> previous,Map<String,Object> incoming){
        for(Map.Entry<String,Object> entry:incoming.entrySet())if(previous.containsKey(entry.getKey())){
            Object old=previous.get(entry.getKey()),value=entry.getValue();
            boolean equal=old instanceof Number&&value instanceof Number?Math.abs(((Number)old).doubleValue()-((Number)value).doubleValue())<=1e-12:Objects.equals(old,value);
            if(!equal)throw new IllegalArgumentException("同一时间测量冲突，原记录已保留: "+incoming.get("timestamp")+" "+entry.getKey());
        }
        for(Map.Entry<String,Object> entry:incoming.entrySet())previous.putIfAbsent(entry.getKey(),entry.getValue());
    }
    public List<Map<String,Object>> rows(long id,String from,String to){
        Map<String,Object> community=get(id,false);long[] bounds=bounds(community,from,to);
        long count=jdbc.queryForObject("SELECT COUNT(*) FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<?",Long.class,id,bounds[0],bounds[1]);
        if(count>200000)throw new IllegalArgumentException("所选区间超过200000条，请缩小范围");
        return jdbc.query("SELECT payload FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms",(rs,n)->decode(rs.getString(1)),id,bounds[0],bounds[1]);
    }
    public Map<String,Object> measurements(long id,String from,String to){return measurements(id,from,to,1,100);}
    public Map<String,Object> measurements(long id,String from,String to,int page,int size){
        Map<String,Object> community=get(id,false);long[] range=bounds(community,from,to);int pageSize=pageSize(size);
        long count=jdbc.queryForObject("SELECT COUNT(*) FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<?",Long.class,id,range[0],range[1]);
        long offset=(long)(Math.max(1,page)-1)*pageSize;int currentPage=count==0?1:(int)Math.min(Math.max(1,page),(count+pageSize-1)/pageSize);
        if(currentPage!=Math.max(1,page))offset=(long)(currentPage-1)*pageSize;
        List<Map<String,Object>> samples=jdbc.query("SELECT payload FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT ? OFFSET ?",(rs,n)->decode(rs.getString(1)),id,range[0],range[1],pageSize,offset);
        Long first=jdbc.queryForObject("SELECT MIN(timestamp_ms) FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<?",Long.class,id,range[0],range[1]);
        Long last=jdbc.queryForObject("SELECT MAX(timestamp_ms) FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<?",Long.class,id,range[0],range[1]);
        Map<String,Object> result=new LinkedHashMap<>();result.put("samples",samples);result.put("count",count);result.put("page",currentPage);result.put("size",pageSize);result.put("pages",(count+pageSize-1)/pageSize);
        result.put("first",first==null?null:Instant.ofEpochMilli(first).toString());result.put("last",last==null?null:Instant.ofEpochMilli(last).toString());return result;
    }
    public Map<String,Object> batches(long id,int page,int size){
        get(id,false);int pageSize=pageSize(size);long count=jdbc.queryForObject("SELECT COUNT(*) FROM community_ingestion_batch WHERE community_id=?",Long.class,id);
        int currentPage=count==0?1:(int)Math.min(Math.max(1,page),(count+pageSize-1)/pageSize);long offset=(long)(currentPage-1)*pageSize;
        List<Map<String,Object>> values=jdbc.queryForList("SELECT id,source,accepted,duplicates,create_time AS createTime,payload_hash AS payloadHash FROM community_ingestion_batch WHERE community_id=? ORDER BY create_time DESC,id DESC LIMIT ? OFFSET ?",id,pageSize,offset);
        return Map.of("batches",values,"count",count,"page",currentPage,"size",pageSize,"pages",(count+pageSize-1)/pageSize);
    }
    private int pageSize(int size){return Math.max(1,Math.min(100,size));}
    private long[] bounds(Map<String,Object> community,String from,String to){
        ZoneId zone=ZoneId.of(community.get("timezone").toString());long start=from==null||from.isBlank()?Long.MIN_VALUE:contract.timestamp(from,zone).toEpochMilli();long end=to==null||to.isBlank()?Long.MAX_VALUE:contract.timestamp(to,zone).toEpochMilli();
        if(start>=end)throw new IllegalArgumentException("时间区间无效，结束时间不包含在内");return new long[]{start,end};
    }
    public Path assetDirectory(long id){
        get(id,false);Path root=Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize().resolve("community-assets");return root.resolve(Long.toString(id));
    }
    public List<Map<String,Object>> assets(long id){return jdbc.query("SELECT name,sha256,size_bytes FROM community_asset WHERE community_id=? ORDER BY name",(rs,n)->Map.of("name",rs.getString(1),"sha256",rs.getString(2),"size",rs.getLong(3)),id);}
    private List<Map<String,Object>> sourceFiles(List<Map<String,String>> sourceFiles){
        List<Map<String,Object>> result=new ArrayList<>();long total=0;if(sourceFiles==null)return result;
        if(sourceFiles.size()>8)throw new IllegalArgumentException("每批最多8个源CSV文件");
        for(Map<String,String> file:sourceFiles){
            if(file==null||text(file.get("name")).isEmpty()||file.get("name").length()>255||!file.containsKey("base64")&&!file.containsKey("content"))throw new IllegalArgumentException("源文件信息无效");
            byte[] bytes;try{bytes=file.containsKey("base64")?Base64.getDecoder().decode(file.get("base64")):file.get("content").getBytes(StandardCharsets.UTF_8);}catch(RuntimeException e){throw new IllegalArgumentException("源文件编码无效");}
            total+=bytes.length;if(bytes.length>20*1024*1024||total>40*1024*1024)throw new IllegalArgumentException("单个源CSV最多20MB，合计最多40MB");
            result.add(Map.of("name",file.get("name"),"base64",Base64.getEncoder().encodeToString(bytes),"sha256",BuildingDatasetExporter.sha256(bytes)));
        }return result;
    }
    private String text(Object value){return value==null?"":value.toString().trim();}
    private String hash(String value){return BuildingDatasetExporter.sha256(value.getBytes(StandardCharsets.UTF_8));}
    private String encode(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalArgumentException("数据序列化失败",e);}}
    private Map<String,Object> decode(String value){try{return mapper.readValue(value,new TypeReference<LinkedHashMap<String,Object>>(){});}catch(Exception e){throw new IllegalArgumentException("数据读取失败",e);}}
}
