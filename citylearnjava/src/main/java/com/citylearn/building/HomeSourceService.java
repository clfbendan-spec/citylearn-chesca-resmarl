package com.citylearn.building;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.annotation.Resource;
import java.time.*;
import java.util.*;

@Service
@DependsOn("homeSourceMigration")
public class HomeSourceService {
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private CommunityManagementService communities;
    @Resource private HomeEvaluationService evaluations;
    private final MeasurementContract contract=new MeasurementContract();

    public Map<String,Object> source(){
        Long selected=jdbc.queryForObject("SELECT community_id FROM home_source_setting WHERE id=1",Long.class);
        List<Map<String,Object>> options=options();Map<String,Object> result=new LinkedHashMap<>();
        result.put("communityId",selected);result.put("options",options);
        Map<String,Object> selectedOption=null;
        for(Map<String,Object> option:options)if(selected!=null&&((Number)option.get("id")).longValue()==selected)selectedOption=option;
        result.put("mode",selected==null?"default":selectedOption==null?"invalid":"community");
        result.put("valid",selected==null||selectedOption!=null);result.put("community",selectedOption);
        result.put("message",selected!=null&&selectedOption==null?"已选社区已删除，请重新选择首页数据源":null);
        String taskId=evaluations.selected();result.put("taskId",taskId);
        if(taskId!=null){
            // Retain the selected identity when it disappears. Never silently
            // substitute the latest evaluation or the old community source.
            boolean valid=evaluations.available(taskId);
            result.put("mode",valid?"evaluation":"invalid");result.put("valid",valid);
            result.put("message",valid?null:"已选评估记录已删除或不可用，请重新选择首页数据源");
        }
        return result;
    }
    @Transactional public Map<String,Object> select(Long communityId){
        if(communityId!=null){
            communities.get(communityId,true);
        }
        jdbc.update("UPDATE home_evaluation_setting SET task_id=NULL WHERE id=1");
        jdbc.update("UPDATE home_source_setting SET community_id=? WHERE id=1",communityId);return source();
    }
    private boolean hasRealtime(long id){
        long shared=jdbc.queryForObject("SELECT COUNT(*) FROM home_realtime_measurement WHERE owner_kind='community' AND owner_id=?",Long.class,id);
        long local=jdbc.queryForObject("SELECT COUNT(*) FROM home_realtime_measurement m JOIN community_building cb ON cb.building_id=m.owner_id JOIN managed_building b ON b.id=cb.building_id AND b.archived=0 WHERE cb.community_id=? AND m.owner_kind='building'",Long.class,id);
        return shared+local>0;
    }
    private List<Map<String,Object>> options(){
        List<Map<String,Object>> options=new ArrayList<>();
        for(Map<String,Object> community:communities.list()){
            long id=((Number)community.get("id")).longValue();
            boolean realtime=hasRealtime(id);
            Map<String,Object> option=new LinkedHashMap<>();
            for(String key:List.of("id","name","timezone","currency","intervalSeconds"))option.put(key,community.get(key));
            option.put("timestampKind",community.get("timestampKind"));option.put("sourceMode",realtime?"realtime":"history");
            option.put("hasRealtime",realtime);option.put("lastRealtimeAt",realtime?lastReceived(id,null):null);options.add(option);
        }return options;
    }
    public Map<String,Object> snapshot(Long buildingId,String from,String to){
        Map<String,Object> source=source(),result=new LinkedHashMap<>();result.put("source",source);result.put("mode",source.get("mode"));
        result.put("current",null);result.put("samples",List.of());result.put("buildings",List.of());result.put("days",List.of());
        if(!"community".equals(source.get("mode")))return result;
        long id=((Number)source.get("communityId")).longValue();Map<String,Object> community=communities.get(id,false);
        Map<String,Object> option=(Map<String,Object>)source.get("community");boolean realtime="realtime".equals(option.get("sourceMode"));
        result.put("dataMode",realtime?"realtime":"history");result.put("timestampKind",community.get("timestampKind"));
        List<Map<String,Object>> buildings=communities.buildings(id);result.put("buildings",buildings);
        if(buildingId==null&&!buildings.isEmpty())buildingId=((Number)buildings.get(0).get("id")).longValue();
        boolean owned=buildingId==null;
        for(Map<String,Object> building:buildings)if(buildingId!=null&&((Number)building.get("id")).longValue()==buildingId)owned=true;
        if(!owned)throw new IllegalArgumentException("首页建筑不属于所选活动社区");
        result.put("buildingId",buildingId);result.put("timezone",community.get("timezone"));result.put("currency",community.get("currency"));result.put("intervalSeconds",community.get("intervalSeconds"));
        ZoneId zone=ZoneId.of(community.get("timezone").toString());
        List<Long> timestamps=realtime
                ?jdbc.query("SELECT DISTINCT timestamp_ms FROM home_realtime_measurement WHERE (owner_kind='community' AND owner_id=?) OR (owner_kind='building' AND owner_id=?) ORDER BY timestamp_ms DESC LIMIT 200000",(rs,n)->rs.getLong(1),id,buildingId==null?-1:buildingId)
                :historyTimestamps(id,buildingId);
        SortedSet<String> days=new TreeSet<>();for(long timestamp:timestamps)days.add(Instant.ofEpochMilli(timestamp).atZone(zone).toLocalDate().toString());result.put("days",days);
        Long latest=timestamps.isEmpty()?null:timestamps.get(0);
        long start=from==null||from.isBlank()?(latest==null?Long.MIN_VALUE:Instant.ofEpochMilli(latest).atZone(zone).toLocalDate().atStartOfDay(zone).toInstant().toEpochMilli()):contract.timestamp(from,zone).toEpochMilli();
        long end=to==null||to.isBlank()?Long.MAX_VALUE:contract.timestamp(to,zone).toEpochMilli();
        if(start>=end)throw new IllegalArgumentException("首页时间范围无效，结束时间不包含在内");
        TreeMap<Long,Map<String,Object>> samples=new TreeMap<>();
        List<Map<String,Object>> shared=realtime?load("community",id,start,end):loadCommunityHistory(id,start,end);
        List<Map<String,Object>> local=buildingId==null?List.of():realtime?load("building",buildingId,start,end):loadBuildingHistory(buildingId,start,end);
        for(Map<String,Object> row:shared)samples.put(Instant.parse(row.get("timestamp").toString()).toEpochMilli(),new LinkedHashMap<>(row));
        for(Map<String,Object> row:local){
            long time=Instant.parse(row.get("timestamp").toString()).toEpochMilli();Map<String,Object> combined=samples.computeIfAbsent(time,key->new LinkedHashMap<>());
            for(Map.Entry<String,Object> entry:row.entrySet()){
                Object old=combined.get(entry.getKey()),value=entry.getValue();
                boolean equal=old instanceof Number&&value instanceof Number?Math.abs(((Number)old).doubleValue()-((Number)value).doubleValue())<=1e-12:Objects.equals(old,value);
                if(combined.containsKey(entry.getKey())&&!equal)throw new IllegalArgumentException("首页共享与建筑测量冲突: "+row.get("timestamp")+" "+entry.getKey());
                combined.putIfAbsent(entry.getKey(),value);
            }
        }
        List<Map<String,Object>> rows=new ArrayList<>(samples.values());Map<String,Object> current=rows.isEmpty()?null:rows.get(rows.size()-1);
        for(Map<String,Object> row:rows)row.put("localTime",Instant.parse(row.get("timestamp").toString()).atZone(zone).toLocalDateTime().toString());
        result.put("samples",rows);result.put("current",current);
        result.put("freshness",realtime?freshness(latest,((Number)community.get("intervalSeconds")).intValue(),lastReceived(id,buildingId)):historical(latest));
        List<String> missing=new ArrayList<>();for(String field:MeasurementContract.FIELDS.keySet())if(current==null||!current.containsKey(field))missing.add(field);
        result.put("missingFields",missing);result.put("energy",energy(rows));result.put("actionsAvailable",false);result.put("socAvailable",false);
        return result;
    }
    private List<Map<String,Object>> load(String kind,long id,long start,long end){
        List<Map<String,Object>> rows=jdbc.query("SELECT payload FROM home_realtime_measurement WHERE owner_kind=? AND owner_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT 5001",(rs,n)->decode(rs.getString(1)),kind,id,start,end);
        if(rows.size()>5000)throw new IllegalArgumentException("首页时间范围超过5000条，请缩小范围");return rows;
    }
    private List<Long> historyTimestamps(long communityId,Long buildingId){
        SortedSet<Long> values=new TreeSet<>(Comparator.reverseOrder());
        values.addAll(jdbc.query("SELECT timestamp_ms FROM community_measurement WHERE community_id=? ORDER BY timestamp_ms DESC LIMIT 200001",(rs,n)->rs.getLong(1),communityId));
        if(buildingId!=null)values.addAll(jdbc.query("SELECT timestamp_ms FROM building_measurement WHERE building_id=? ORDER BY timestamp_ms DESC LIMIT 200001",(rs,n)->rs.getLong(1),buildingId));
        return new ArrayList<>(values);
    }
    private List<Map<String,Object>> loadCommunityHistory(long id,long start,long end){return loadHistory("SELECT payload FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT 5001",id,start,end);}
    private List<Map<String,Object>> loadBuildingHistory(long id,long start,long end){return loadHistory("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT 5001",id,start,end);}
    private List<Map<String,Object>> loadHistory(String sql,long id,long start,long end){
        List<Map<String,Object>> rows=jdbc.query(sql,(rs,n)->decode(rs.getString(1)),id,start,end);
        if(rows.size()>5000)throw new IllegalArgumentException("首页时间范围超过5000条，请缩小范围");return rows;
    }
    private Map<String,Object> energy(List<Map<String,Object>> rows){
        Map<String,Object> energy=new LinkedHashMap<>();Map<String,Object> coverage=new LinkedHashMap<>();
        Map<String,String> fields=new LinkedHashMap<>();fields.put("nonShiftableKwh","non_shiftable_load");fields.put("coolingDemandKwh","cooling_demand");fields.put("heatingDemandKwh","heating_demand");fields.put("dhwDemandKwh","dhw_demand");
        fields.forEach((name,field)->{double sum=0;int count=0;for(Map<String,Object> row:rows)if(row.get(field) instanceof Number){sum+=((Number)row.get(field)).doubleValue();count++;}energy.put(name,count==0?null:sum);coverage.put(name,count);});
        for(String field:List.of("home","gridIn","gridOut","pv","batIn","batOut","soc"))energy.put(field,null);
        energy.put("coverage",coverage);energy.put("sampleCount",rows.size());energy.put("completeFlow",false);return energy;
    }
    private Map<String,Object> freshness(Long latest,int interval,String received){
        Map<String,Object> value=new LinkedHashMap<>();long age=latest==null?0:Duration.between(Instant.ofEpochMilli(latest),Instant.now()).getSeconds();
        value.put("status",latest==null?"empty":age < -interval?"future":age>Math.max(120,interval*2L)?"stale":"fresh");
        value.put("latestTimestamp",latest==null?null:Instant.ofEpochMilli(latest).toString());value.put("ageSeconds",latest==null?null:age);value.put("receivedAt",received);return value;
    }
    private Map<String,Object> historical(Long latest){
        Map<String,Object> value=new LinkedHashMap<>();value.put("status",latest==null?"empty":"historical");
        value.put("latestTimestamp",latest==null?null:Instant.ofEpochMilli(latest).toString());value.put("ageSeconds",null);value.put("receivedAt",null);return value;
    }
    private String lastReceived(long id,Long buildingId){
        List<String> values=jdbc.query("SELECT MAX(received_at) FROM (SELECT received_at FROM home_realtime_measurement WHERE owner_kind='community' AND owner_id=? UNION ALL SELECT m.received_at FROM home_realtime_measurement m JOIN community_building cb ON cb.building_id=m.owner_id JOIN managed_building b ON b.id=m.owner_id AND b.archived=0 WHERE cb.community_id=? AND m.owner_kind='building' AND (? IS NULL OR m.owner_id=?)) receipts",
                (rs,n)->rs.getTimestamp(1)==null?null:rs.getTimestamp(1).toInstant().toString(),id,id,buildingId,buildingId);
        return values.isEmpty()?null:values.get(0);
    }
    private Map<String,Object> decode(String value){try{return mapper.readValue(value,new TypeReference<LinkedHashMap<String,Object>>(){});}catch(Exception e){throw new IllegalArgumentException("首页实时测量读取失败",e);}}
}
