package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;

/** Homepage projection retains exactly fields submitted through the realtime ingestion channel. */
final class HomeRealtimeMeasurements {
    private HomeRealtimeMeasurements(){}
    static void retain(JdbcTemplate jdbc,ObjectMapper mapper,String kind,long id,Map<Long,Map<String,Object>> normalized){
        for(Map.Entry<Long,Map<String,Object>> entry:normalized.entrySet()){
            List<String> existing=jdbc.query("SELECT payload FROM home_realtime_measurement WHERE owner_kind=? AND owner_id=? AND timestamp_ms=? FOR UPDATE",(rs,n)->rs.getString(1),kind,id,entry.getKey());
            try{
                Map<String,Object> payload=existing.isEmpty()?new LinkedHashMap<>():mapper.readValue(existing.get(0),Map.class);
                payload.putAll(entry.getValue());String encoded=mapper.writeValueAsString(payload);
                jdbc.update("INSERT INTO home_realtime_measurement(owner_kind,owner_id,timestamp_ms,payload) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE payload=VALUES(payload),received_at=CURRENT_TIMESTAMP(6)",kind,id,entry.getKey(),encoded);
            }catch(Exception e){throw new IllegalArgumentException("实时测量首页投影保存失败",e);}
        }
    }
}
