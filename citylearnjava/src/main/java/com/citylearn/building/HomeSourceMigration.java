package com.citylearn.building;

import org.springframework.context.annotation.DependsOn;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.stereotype.Component;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;

@Component
@DependsOn("buildingSchemaMigration")
public class HomeSourceMigration {
    @Resource private DataSource dataSource;
    @PostConstruct public void migrate(){
        new ResourceDatabasePopulator(new ClassPathResource("db/home_source.sql")).execute(dataSource);
        JdbcTemplate jdbc=new JdbcTemplate(dataSource);ObjectMapper mapper=new ObjectMapper();
        new org.springframework.transaction.support.TransactionTemplate(new org.springframework.jdbc.datasource.DataSourceTransactionManager(dataSource)).execute(status->{
            if(jdbc.queryForObject("SELECT COUNT(*) FROM community_migration WHERE id='home-realtime-provenance-v1'",Long.class)>0)return null;
            backfill(jdbc,mapper,"building");backfill(jdbc,mapper,"community");
            jdbc.update("INSERT IGNORE INTO community_migration(id) VALUES ('home-realtime-provenance-v1')");return null;
        });
    }
    @SuppressWarnings("unchecked") private void backfill(JdbcTemplate jdbc,ObjectMapper mapper,String kind){
        MeasurementContract contract=new MeasurementContract();
        for(Map<String,Object> batch:jdbc.queryForList("SELECT "+kind+"_id AS owner_id,raw_payload,create_time FROM "+kind+"_ingestion_batch WHERE source='realtime' ORDER BY create_time,id")){
            try{
                long id=((Number)batch.get("owner_id")).longValue();Map<String,Object> raw=mapper.readValue(batch.get("raw_payload").toString(),Map.class);
                Map<String,Object> metadata=(Map<String,Object>)raw.get(kind);
                if(metadata==null)throw new IllegalArgumentException("Missing captured ingestion metadata");
                Map<Long,Map<String,Object>> normalized=new TreeMap<>();
                for(Map<String,Object> row:(List<Map<String,Object>>)raw.get("rows")){
                    Map<String,Object> value=contract.normalize(row,ZoneId.of(metadata.get("timezone").toString()),((Number)metadata.get("intervalSeconds")).intValue(),(Map<String,String>)raw.getOrDefault("mapping",Map.of()),(Map<String,String>)raw.getOrDefault("units",Map.of()));
                    long time=Instant.parse(value.get("timestamp").toString()).toEpochMilli();normalized.computeIfAbsent(time,key->new LinkedHashMap<>()).putAll(value);
                }
                HomeRealtimeMeasurements.retain(jdbc,mapper,kind,id,normalized);
                // Historical receipt is kept instead of presenting the migration time as a new live update.
                for(Long time:normalized.keySet())jdbc.update("UPDATE home_realtime_measurement SET received_at=? WHERE owner_kind=? AND owner_id=? AND timestamp_ms=?",batch.get("create_time"),kind,id,time);
            }catch(Exception e){throw new IllegalStateException("Cannot restore realtime homepage provenance from immutable ingestion batch",e);}
        }
    }
}
