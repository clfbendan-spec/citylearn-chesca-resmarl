package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.annotation.Resource;
import java.nio.file.*;
import java.util.*;

@Service
@DependsOn("buildingSchemaMigration")
public class CommunityDatasetService {
    @Resource private BuildingIngestionService buildings;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;

    public List<Map<String,Object>> sources() {
        return jdbc.queryForList("SELECT v.id AS versionId,v.building_id AS buildingId,b.name AS buildingName,v.name AS versionName,"
                + "v.start_time AS startTime,v.end_time AS endTime,v.time_steps AS timeSteps,v.create_time AS createTime"
                + " FROM building_dataset_version v JOIN managed_building b ON b.id=v.building_id AND b.archived=0"
                + " JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY v.schema_key AND d.enabled=1 ORDER BY b.id,v.create_time DESC,v.id");
    }
    public List<Map<String,Object>> list() {
        return jdbc.queryForList("SELECT c.id,c.schema_key AS schemaKey,c.name,c.start_time AS startTime,c.end_time AS endTime,"
                + "c.building_count AS buildingCount,c.time_steps AS timeSteps,c.create_time AS createTime"
                + " FROM community_dataset_release c JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY c.schema_key AND d.enabled=1 ORDER BY c.create_time DESC,c.id");
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> publish(Map<String,Object> request) throws Exception {
        String name=request.getOrDefault("name","").toString().trim();
        if (name.isEmpty() || name.length()>160) throw new IllegalArgumentException("请填写 1–160 个字符的数据集名称");
        List<CommunityDatasetExporter.Source> sources=selectedSources(request,true);
        CommunityDatasetExporter exporter=new CommunityDatasetExporter(mapper);
        CommunityDatasetExporter.Window window=selectedWindow(exporter,sources,request);
        String reward=rewardOverride(request);
        exporter.preview(sources,window,reward);
        String id=UUID.randomUUID().toString(), key="community_"+id.replace("-","");
        Path root=Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize();
        Path directory=root.resolve("datasets").resolve(key);
        Files.createDirectories(directory.getParent()); Files.createDirectory(directory);
        DatasetSnapshotFiles.cleanupOnRollback(directory);
        String hash=exporter.write(directory,sources,window,id,reward);
        List<Map<String,Object>> provenance=new ArrayList<>();
        for (CommunityDatasetExporter.Source source:sources) provenance.add(source.info);
        jdbc.update("INSERT INTO community_dataset_release(id,schema_key,name,start_time,end_time,time_steps,building_count,sources_json,content_hash) VALUES (?,?,?,?,?,?,?,?,?)",id,key,name,window.start.toString(),window.end.toString(),window.steps,sources.size(),mapper.writeValueAsString(provenance),hash);
        jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled,sort_order,description) VALUES (?,?,?,?,?,0,1,210,?)",key,name,"datasets/"+key,sources.size(),window.steps,"建筑接入社区数据集 · "+id);
        return Map.of("id",id,"schemaKey",key,"buildingCount",sources.size(),"timeSteps",window.steps,"startTime",window.start.toString(),"endTime",window.end.toString());
    }
    public Map<String,Object> preview(Map<String,Object> request) throws Exception {
        try {
            CommunityDatasetExporter exporter=new CommunityDatasetExporter(mapper);
            List<CommunityDatasetExporter.Source> sources=selectedSources(request,false);
            return exporter.preview(sources,selectedWindow(exporter,sources,request),rewardOverride(request));
        } catch(IllegalArgumentException error) {return Map.of("ready",false,"blocker",error.getMessage());}
    }
    private String rewardOverride(Map<String,Object> request) {
        Object reward=request.get("reward");
        return reward==null || "source".equals(reward)?null:reward.toString();
    }
    private CommunityDatasetExporter.Window selectedWindow(CommunityDatasetExporter exporter,List<CommunityDatasetExporter.Source> sources,Map<String,Object> request) {
        Object from=request.get("from"),to=request.get("to");
        if((from==null)!=(to==null)) throw new IllegalArgumentException("请选择完整的时间范围");
        return exporter.window(sources,from==null?null:from.toString(),to==null?null:to.toString());
    }
    private List<CommunityDatasetExporter.Source> selectedSources(Map<String,Object> request,boolean lock) throws Exception {
        Object selection=request.get("sources");
        if (!(selection instanceof List) || ((List<?>)selection).size()<2 || ((List<?>)selection).size()>20)
            throw new IllegalArgumentException("请选择 2–20 栋不同建筑，每栋选择一个已发布数据集");
        Map<Long,String> selected=new TreeMap<>();
        for (Object item:(List<?>)selection) {
            if (!(item instanceof Map)) throw new IllegalArgumentException("建筑与数据集选择无效");
            Map<?,?> entry=(Map<?,?>)item;
            if (!(entry.get("buildingId") instanceof Number) || !(entry.get("versionId") instanceof String)) throw new IllegalArgumentException("建筑与数据集选择无效");
            long id=((Number)entry.get("buildingId")).longValue(); String version=(String)entry.get("versionId");
            if (id<=0 || !version.matches("[a-f0-9-]{36}") || selected.put(id,version)!=null)
                throw new IllegalArgumentException("每栋建筑只能选择一个已发布数据集");
        }
        for (long id:selected.keySet()) buildings.get(id,lock);
        CommunityDatasetExporter exporter=new CommunityDatasetExporter(mapper);
        List<CommunityDatasetExporter.Source> sources=new ArrayList<>();
        for (Map.Entry<Long,String> entry:selected.entrySet()) {
            Path directory=buildings.versionDirectory(entry.getKey(),entry.getValue());
            Map<String,Object> info=jdbc.queryForMap("SELECT building_id AS buildingId,id AS versionId,name AS versionName,content_hash AS contentHash FROM building_dataset_version WHERE id=? AND building_id=?",entry.getValue(),entry.getKey());
            sources.add(exporter.load(directory,info));
        }
        return sources;
    }

    public Path directory(String id) {
        List<String> keys=jdbc.query("SELECT c.schema_key FROM community_dataset_release c JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY c.schema_key AND d.enabled=1 WHERE c.id=?",(rs,n)->rs.getString(1),id);
        if (keys.isEmpty()) throw new IllegalArgumentException("社区数据集不存在或已删除");
        if (!keys.get(0).matches("community_[a-f0-9]{32}")) throw new IllegalArgumentException("无效社区数据集路径");
        return Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize().resolve("datasets").resolve(keys.get(0));
    }
    @Transactional public void delete(String id) {
        jdbc.queryForList("SELECT id FROM managed_community WHERE id IN (SELECT community_id FROM community_dataset_owner WHERE release_id=?) FOR UPDATE",id);
        directory(id);
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_assessment_run WHERE release_id=? AND status IN ('queued','running')",Integer.class,id)>0)
            throw new IllegalArgumentException("数据集正在初步评估，不能删除");
        jdbc.update("UPDATE citylearn_dataset SET enabled=0 WHERE BINARY schema_key=(SELECT BINARY schema_key FROM community_dataset_release WHERE id=?)",id);
    }
}
