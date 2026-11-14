package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties="citylearn.file.python-file-path=${java.io.tmpdir}/citylearn-community-tests")
@Transactional
class CommunityDatasetServiceTest {
    @Autowired CommunityDatasetService community;
    @Autowired BuildingIngestionService buildings;
    @Autowired JdbcTemplate jdbc;
    @Autowired FileResourceProperties files;
    @Autowired com.citylearn.service.CityLearnLocalDatasetService dataView;
    final List<Path> sourceDirectories=new ArrayList<>();

    Map<String,Object> source(String name,int start,int count) throws Exception {
        long id=((Number)buildings.save(null,new LinkedHashMap<>(Map.of("name",name,"timezone","Asia/Shanghai","currency","CNY","devices",Map.of()))).get("id")).longValue();
        List<Map<String,Object>> rows=new ArrayList<>();
        for (int i=0;i<count;i++) {
            Map<String,Object> row=MeasurementContractTest.complete(Instant.parse("2026-01-01T00:00:00Z").plusSeconds((start+i)*3600L).toString());
            for (String field:List.of("cooling_demand","heating_demand","dhw_demand","solar_generation")) row.put(field,0.0);
            rows.add(row);
        }
        buildings.ingest(id,rows,Map.of(),Map.of(),"history");
        Map<String,Object> version=buildings.publish(id,Map.of("name",name,"purpose","train","from",rows.get(0).get("timestamp"),"to",Instant.parse(rows.get(count-1).get("timestamp").toString()).plusSeconds(3600).toString()));
        sourceDirectories.add(Paths.get(files.getPythonFilePath()).resolve("datasets").resolve(version.get("schemaKey").toString()));
        return Map.of("buildingId",id,"versionId",version.get("id"));
    }
    @AfterEach void removeOwnSourceFiles() throws Exception {
        for (Path directory:sourceDirectories) if (Files.isDirectory(directory)) {
            try (java.util.stream.Stream<Path> paths=Files.walk(directory)) {
                for (Path path:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator) Files.deleteIfExists(path);
            }
        }
    }

    @Test void publishesIndependentSnapshotRegistersCatalogAndKeepsItAfterSourceDeletion() throws Exception {
        Map<String,Object> first=source("Community first",0,6), second=source("Community second",2,6);
        Map<String,Object> release=community.publish(Map.of("name","Community integration fixture","sources",List.of(first,second),"from","2026-01-01T03:00:00Z","to","2026-01-01T05:00:00Z"));
        String id=release.get("id").toString();
        Path directory=community.directory(id);
        assertEquals(2,release.get("timeSteps")); assertEquals(2,release.get("buildingCount"));
        assertTrue(Files.isRegularFile(directory.resolve("Building_2.csv")));
        assertEquals(2,jdbc.queryForObject("SELECT building_count FROM citylearn_dataset WHERE schema_key=?",Integer.class,release.get("schemaKey")));
        com.citylearn.vo.BuildingDataVO viewed=dataView.getBuildingRows("2",release.get("schemaKey").toString(),null,null,null).get(0);
        assertNotNull(viewed.getOutdoorDryBulbTemperature());
        assertNotNull(viewed.getElectricityPricing());
        assertNotNull(viewed.getCarbonIntensity());
        buildings.deleteVersion(((Number)first.get("buildingId")).longValue(),first.get("versionId").toString());
        assertEquals(directory,community.directory(id));
        assertTrue(community.list().stream().anyMatch(row->row.get("id").equals(id)));
        community.delete(id);
        assertThrows(IllegalArgumentException.class,()->community.directory(id));
        assertTrue(Files.isRegularFile(directory.resolve("schema.json")));
    }

    @Test void rejectsRepeatedBuildingsWrongOwnershipDeletedSourcesAndRangesOutsideIntersection() throws Exception {
        Map<String,Object> first=source("Validation first",0,6), second=source("Validation second",2,6);
        assertThrows(IllegalArgumentException.class,()->community.publish(Map.of("name","duplicate","sources",List.of(first,first))));
        Map<String,Object> wrong=Map.of("buildingId",first.get("buildingId"),"versionId",second.get("versionId"));
        assertThrows(IllegalArgumentException.class,()->community.publish(Map.of("name","wrong","sources",List.of(wrong,second))));
        assertThrows(IllegalArgumentException.class,()->community.publish(Map.of("name","outside","sources",List.of(first,second),"from","2026-01-01T01:00:00Z","to","2026-01-01T05:00:00Z")));
        buildings.deleteVersion(((Number)second.get("buildingId")).longValue(),second.get("versionId").toString());
        assertThrows(IllegalArgumentException.class,()->community.publish(Map.of("name","deleted","sources",List.of(first,second))));
        assertFalse(community.sources().stream().anyMatch(row->row.get("versionId").equals(second.get("versionId"))));
    }
    @Test void previewHasNoSideEffectsAndExplicitCommunityRewardIsFrozen() throws Exception {
        Map<String,Object> first=source("Preview first",0,4),second=source("Preview second",0,4);
        Map<String,Object> request=Map.of("name","Override reward","sources",List.of(first,second),"reward","carbon");
        int before=community.list().size();
        Map<String,Object> preview=community.preview(request);
        assertEquals(true,preview.get("ready"));
        assertEquals(before,community.list().size());
        Map<String,Object> release=community.publish(request);
        Path directory=community.directory(release.get("id").toString());
        assertTrue(Files.exists(directory.resolve("citylearn_external_rewards.py")));
        Map<?,?> schema=new com.fasterxml.jackson.databind.ObjectMapper().readValue(directory.resolve("schema.json").toFile(),Map.class);
        assertEquals("citylearn_external_rewards.PurchaseCarbonReward",((Map<?,?>)schema.get("reward_function")).get("type"));
        assertEquals(false,community.preview(Map.of("sources",List.of(first,second),"reward","unsupported")).get("ready"));
    }
}
