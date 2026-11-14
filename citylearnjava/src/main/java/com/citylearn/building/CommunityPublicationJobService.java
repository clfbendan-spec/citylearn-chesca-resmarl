package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.context.event.EventListener;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import javax.annotation.Resource;
import java.util.*;
import java.util.concurrent.Executor;

@Service
public class CommunityPublicationJobService {
    @Resource private CommunityManagementService communities;
    @Resource private CommunityPublicationService publication;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource(name="pythonTaskExecutor") private Executor executor;

    @EventListener(WebServerInitializedEvent.class)
    public void recover() {
        jdbc.update("UPDATE community_publication_task SET status='failed',error_message='服务重启，发布已中断，请重新发布',end_time=CURRENT_TIMESTAMP WHERE status IN ('queued','running')");
    }

    @Transactional(rollbackFor=Exception.class)
    public Map<String,Object> start(long community,Map<String,Object> request) throws Exception {
        communities.get(community,true);
        String name=Objects.toString(request.get("name"),"").trim();
        if(name.isEmpty() || name.length()>160) throw new IllegalArgumentException("请填写1–160个字符的数据集名称");
        if(jdbc.queryForObject("SELECT COUNT(*) FROM community_publication_task WHERE community_id=? AND status IN ('queued','running')",Integer.class,community)>0)
            throw new IllegalArgumentException("该社区已有发布任务，请等待任务结束");
        if(!(request.get("buildingIds") instanceof List) || ((List<?>)request.get("buildingIds")).isEmpty())
            throw new IllegalArgumentException("请选择发布建筑");
        String id=UUID.randomUUID().toString();
        Map<String,Object> snapshot=mapper.readValue(mapper.writeValueAsBytes(request),Map.class);
        jdbc.update("INSERT INTO community_publication_task(id,community_id,status,stage,request_json) VALUES (?,?,'queued','queued',?)",id,community,mapper.writeValueAsString(snapshot));
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                try {executor.execute(()->execute(id,community,snapshot));}
                catch(RuntimeException error){fail(id,error);}
            }
        });
        return get(community,id);
    }

    public List<Map<String,Object>> list(long community) {
        communities.get(community,false);
        return jdbc.queryForList("SELECT id,status,stage,completed,total,error_message AS error,create_time AS createTime FROM community_publication_task WHERE community_id=? ORDER BY create_time DESC LIMIT 20",community);
    }

    public Map<String,Object> get(long community,String id) {
        communities.get(community,false);
        List<Map<String,Object>> rows=jdbc.queryForList("SELECT id,status,stage,completed,total,error_message AS error,result_json FROM community_publication_task WHERE community_id=? AND id=?",community,id);
        if(rows.isEmpty()) throw new IllegalArgumentException("发布任务不存在");
        Map<String,Object> row=rows.get(0);
        Object result=row.remove("result_json");
        try {if(result!=null) row.put("result",mapper.readValue(result.toString(),Map.class));}
        catch(Exception error){throw new IllegalStateException("发布结果无效",error);}
        return row;
    }

    private void execute(String id,long community,Map<String,Object> request) {
        if(jdbc.update("UPDATE community_publication_task SET status='running',stage='exporting',start_time=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",id)!=1)return;
        try {
            Map<String,Object> result=publication.publishWithProgress(community,request,(done,total)->jdbc.update(
                    "UPDATE community_publication_task SET stage='generating_models',completed=?,total=? WHERE id=? AND status='running'",done,total,id));
            jdbc.update("UPDATE community_publication_task SET status='succeeded',stage='published',completed=total,result_json=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status='running'",mapper.writeValueAsString(result),id);
        } catch(Exception error){fail(id,error);}
    }

    private void fail(String id,Exception error) {
        jdbc.update("UPDATE community_publication_task SET status='failed',stage='failed',error_message=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')",Objects.toString(error.getMessage(),"发布失败"),id);
    }
}
