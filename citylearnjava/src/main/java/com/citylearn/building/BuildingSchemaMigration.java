package com.citylearn.building;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import java.sql.PreparedStatement;
import java.sql.Statement;

@Configuration
public class BuildingSchemaMigration {
    @Resource private DataSource dataSource;
    @PostConstruct public void migrate() {
        new ResourceDatabasePopulator(new ClassPathResource("db/building_management.sql")).execute(dataSource);
        new ResourceDatabasePopulator(new ClassPathResource("db/community_management.sql")).execute(dataSource);
        migrateCommunities();
    }

    @SuppressWarnings("unchecked")
    private void migrateCommunities() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        ObjectMapper mapper = new ObjectMapper();
        org.springframework.jdbc.datasource.DataSourceTransactionManager manager =
                new org.springframework.jdbc.datasource.DataSourceTransactionManager(dataSource);
        new org.springframework.transaction.support.TransactionTemplate(manager).execute(status -> {
            if (jdbc.queryForObject("SELECT COUNT(*) FROM community_migration WHERE id='legacy-ownership-v1'", Long.class) > 0) return null;
            Map<String, Long> groups = new LinkedHashMap<>();
            for (Map<String, Object> building : jdbc.queryForList("SELECT b.id,b.name,b.metadata FROM managed_building b LEFT JOIN community_building cb ON cb.building_id=b.id WHERE b.archived=0 AND cb.building_id IS NULL ORDER BY b.id")) {
                try {
                    Map<String, Object> old = mapper.readValue(building.get("metadata").toString(), Map.class);
                    Map<String, Object> metadata = new LinkedHashMap<>();
                    metadata.put("timezone", old.getOrDefault("timezone", "Asia/Shanghai"));
                    metadata.put("currency", old.getOrDefault("currency", "CNY"));
                    metadata.put("intervalSeconds", old.getOrDefault("intervalSeconds", 3600));
                    metadata.put("timestampKind", old.getOrDefault("timestampKind", "measured"));
                    String group = mapper.writeValueAsString(metadata);
                    Long communityId = groups.get(group);
                    if (communityId == null) {
                        String name = "默认社区" + (groups.isEmpty() ? "" : " " + (groups.size() + 1));
                        if (building.get("name").toString().toLowerCase(Locale.ROOT).contains("online1")) name = "2023 Online1 社区";
                        metadata.put("name", name);
                        metadata.put("configuration", Map.of("schema", Map.of(), "buildings", Map.of()));
                        String payload = mapper.writeValueAsString(metadata);
                        String finalName = name;
                        GeneratedKeyHolder key = new GeneratedKeyHolder();
                        jdbc.update(connection -> {
                            PreparedStatement ps = connection.prepareStatement("INSERT INTO managed_community(name,metadata) VALUES (?,?)", Statement.RETURN_GENERATED_KEYS);
                            ps.setString(1, finalName); ps.setString(2, payload); return ps;
                        }, key);
                        communityId = Objects.requireNonNull(key.getKey()).longValue(); groups.put(group, communityId);
                    }
                    jdbc.update("INSERT IGNORE INTO community_building(community_id,building_id) VALUES (?,?)", communityId, building.get("id"));
                } catch (Exception e) { throw new IllegalStateException("Cannot migrate legacy building community", e); }
            }
            for (Map<String, Object> release : jdbc.queryForList("SELECT id,sources_json FROM community_dataset_release")) {
                try {
                    List<Map<String, Object>> sources = mapper.readValue(release.get("sources_json").toString(), List.class);
                    if (sources.isEmpty() || sources.get(0).get("buildingId") == null) continue;
                    List<Long> owners = jdbc.query("SELECT community_id FROM community_building WHERE building_id=?", (rs, n) -> rs.getLong(1), sources.get(0).get("buildingId"));
                    if (!owners.isEmpty()) jdbc.update("INSERT IGNORE INTO community_dataset_owner(release_id,community_id) VALUES (?,?)", release.get("id"), owners.get(0));
                } catch (Exception e) { throw new IllegalStateException("Cannot migrate legacy community release", e); }
            }
            jdbc.update("INSERT IGNORE INTO community_migration(id) VALUES ('legacy-ownership-v1')");
            return null;
        });
    }
}
