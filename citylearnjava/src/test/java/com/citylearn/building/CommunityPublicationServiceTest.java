package com.citylearn.building;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import java.nio.file.Path;
import java.util.function.BiConsumer;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties={"citylearn.file.python-file-path=${java.io.tmpdir}/citylearn-community-publication-tests","citylearn.community.validate-runtime=false"})
@Transactional
class CommunityPublicationServiceTest {
    @Autowired CommunityPublicationService publication;
    @Autowired CommunityManagementService communities;
    @Autowired BuildingIngestionService buildings;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @MockBean DatasetDynamicsService dynamics;

    @BeforeEach void stubDynamics() throws Exception {
        when(dynamics.prepare(any(Path.class),anyBoolean(),nullable(BiConsumer.class))).thenAnswer(call -> {
            Path directory=call.getArgument(0);boolean generate=call.getArgument(1);
            if(generate)java.nio.file.Files.writeString(directory.resolve("Building_1.pth"),"test model");
            return Map.of("thermalModel","LSTMDynamics","modelGenerationRequired",!generate);
        });
    }

    long community(String name)throws Exception {
        String metadata=mapper.writeValueAsString(Map.of("name",name,"timezone","UTC","currency","USD","intervalSeconds",3600,"timestampKind","measured","configuration",Map.of()));
        jdbc.update("INSERT INTO managed_community(name,metadata) VALUES (?,?)",name,metadata);
        return jdbc.queryForObject("SELECT MAX(id) FROM managed_community",Long.class);
    }
    long building(long community,String name) {
        return ((Number)buildings.save(null,Map.of("name",name,"communityId",community,"devices",Map.of())).get("id")).longValue();
    }
    List<Map<String,Object>> rows() {
        List<Map<String,Object>> rows=new ArrayList<>();
        for(int i=0;i<28;i++) {
            Map<String,Object> row=MeasurementContractTest.complete(Instant.parse("2026-01-01T00:00:00Z").plusSeconds(i*3600L).toString());
            for(String key:List.of("cooling_demand","heating_demand","dhw_demand","solar_generation"))row.put(key,0.0);
            rows.add(row);
        }
        return rows;
    }
    @Test void joinsSharedRowsAndPublishesSingleOrSelectedBuildingsWithoutBuildingVersions()throws Exception {
        long community=community("Joined community"),first=building(community,"First"),second=building(community,"Second");
        List<Map<String,Object>> local=rows();
        for(Map<String,Object> row:local) {
            Map<String,Object> shared=new LinkedHashMap<>();shared.put("timestamp",row.get("timestamp"));
            for(String key:new ArrayList<>(row.keySet()))if(key.startsWith("outdoor_")||key.contains("irradiance")||List.of("electricity_pricing","carbon_intensity").contains(key))shared.put(key,row.remove(key));
            jdbc.update("INSERT INTO community_measurement(community_id,timestamp_ms,payload,source) VALUES (?,?,?,?)",community,Instant.parse(shared.get("timestamp").toString()).toEpochMilli(),mapper.writeValueAsString(shared),"history");
        }
        buildings.ingest(first,local,Map.of(),Map.of(),"history");buildings.ingest(second,local,Map.of(),Map.of(),"history");
        int versions=jdbc.queryForObject("SELECT COUNT(*) FROM building_dataset_version WHERE building_id IN (?,?)",Integer.class,first,second);
        Map<String,Object> preview=publication.preview(community,Map.of("buildingIds",List.of(first)));
        assertEquals(true,preview.get("ready"),preview.toString());
        assertEquals(1,preview.get("buildingCount"));
        Map<String,Object> single=publication.publish(community,Map.of("name","Single selection","buildingIds",List.of(first)));
        assertEquals(1,single.get("buildingCount"));assertEquals(4,single.get("timeSteps"));
        assertTrue(java.nio.file.Files.isRegularFile(publication.directory(community,single.get("id").toString()).resolve("schema.json")));
        assertEquals(versions,jdbc.queryForObject("SELECT COUNT(*) FROM building_dataset_version WHERE building_id IN (?,?)",Integer.class,first,second));
        assertEquals(2,publication.publish(community,Map.of("name","Both","buildingIds",List.of(second,first))).get("buildingCount"));
    }
    @Test void rejectsCrossCommunityAndConflictingSharedValuesAndMissingIntervals()throws Exception {
        long community=community("Conflict community"),other=community("Other community"),building=building(community,"Local"),foreign=building(other,"Foreign");
        buildings.ingest(building,rows(),Map.of(),Map.of(),"history");
        Map<String,Object> bounds=publication.availableRange(community,Map.of("buildingIds",List.of(building)));
        assertEquals("2026-01-01T04:00:00Z",bounds.get("endTime"));
        assertEquals("2026-01-02T04:00:00Z",bounds.get("sourceEndTime"));
        assertEquals(false,publication.preview(community,Map.of("buildingIds",List.of(foreign))).get("ready"));
        assertEquals(false,publication.preview(community,Map.of("buildingIds",List.of(building,building))).get("ready"));
        jdbc.update("INSERT INTO community_measurement(community_id,timestamp_ms,payload,source) VALUES (?,?,?,?)",community,Instant.parse("2026-01-01T00:00:00Z").toEpochMilli(),mapper.writeValueAsString(Map.of("timestamp","2026-01-01T00:00:00Z","electricity_pricing",99.0)),"history");
        Map<String,Object> preview=publication.preview(community,Map.of("buildingIds",List.of(building)));
        assertEquals(false,preview.get("ready"));assertTrue(preview.get("blocker").toString().contains("冲突"));
        jdbc.update("DELETE FROM community_measurement WHERE community_id=?",community);
        jdbc.update("DELETE FROM building_measurement WHERE building_id=? AND timestamp_ms=?",building,Instant.parse("2026-01-01T01:00:00Z").toEpochMilli());
        assertEquals(false,publication.preview(community,Map.of("buildingIds",List.of(building))).get("ready"));
        assertThrows(IllegalArgumentException.class,()->buildings.save(building,Map.of("name","Moved","communityId",other,"devices",Map.of())));
    }
    @Test void defaultRangeUsesCompleteJoinedDataAndKeepsInteriorGapValidation()throws Exception {
        long community=community("Shared interval"),building=building(community,"Local interval");
        List<Map<String,Object>> local=rows();
        for(int i=0;i<local.size();i++) {
            Map<String,Object> row=local.get(i);
            Object weather=row.remove("outdoor_dry_bulb_temperature");
            if(i>=1 && i<=26) {
                Map<String,Object> shared=Map.of("timestamp",row.get("timestamp"),"outdoor_dry_bulb_temperature",weather);
                jdbc.update("INSERT INTO community_measurement(community_id,timestamp_ms,payload,source) VALUES (?,?,?,?)",community,Instant.parse(row.get("timestamp").toString()).toEpochMilli(),mapper.writeValueAsString(shared),"history");
            }
        }
        buildings.ingest(building,local,Map.of(),Map.of(),"history");
        Map<String,Object> preview=publication.preview(community,Map.of("buildingIds",List.of(building)));
        assertEquals(true,preview.get("ready"),preview.toString());
        assertEquals("2026-01-01T01:00:00Z",preview.get("startTime"));
        assertEquals("2026-01-01T03:00:00Z",preview.get("endTime"));
        assertEquals(2,preview.get("timeSteps"));
        assertEquals(false,publication.preview(community,Map.of("buildingIds",List.of(building),"from","2026-01-01T00:00:00Z","to","2026-01-01T04:00:00Z")).get("ready"));
    }
    @Test void reserves24HoursAndRejectsExplicitEndInsideForecastBuffer() throws Exception {
        long community=community("Forecast boundaries"),building=building(community,"Weather building");
        buildings.ingest(building,rows(),Map.of(),Map.of(),"history");
        Map<String,Object> latest=Map.of("buildingIds",List.of(building),"from","2026-01-01T00:00:00Z","to","2026-01-01T04:00:00Z");
        assertEquals(true,publication.preview(community,latest).get("ready"));
        Map<String,Object> tooLate=Map.of("buildingIds",List.of(building),"from","2026-01-01T00:00:00Z","to","2026-01-01T05:00:00Z");
        assertEquals(false,publication.preview(community,tooLate).get("ready"));
        Map<String,Object> publish=new HashMap<>(tooLate);publish.put("name","Invalid end");
        assertThrows(IllegalArgumentException.class,()->publication.publish(community,publish));
        jdbc.update("DELETE FROM building_measurement WHERE building_id=? AND timestamp_ms=?",building,Instant.parse("2026-01-02T02:00:00Z").toEpochMilli());
        assertEquals(false,publication.preview(community,latest).get("ready"));
    }
    @Test void fillsMissingForecastsPreservesSuppliedAndRecordsTheirOrigin() throws Exception {
        long community=community("Forecast generation"),building=building(community,"Forecast source");
        List<Map<String,Object>> measurements=rows();
        for(int i=0;i<measurements.size();i++) {
            measurements.get(i).put("electricity_pricing",i/10.0);
            measurements.get(i).put("outdoor_dry_bulb_temperature",10.0+i);
        }
        measurements.get(0).put("outdoor_dry_bulb_temperature_predicted_1",42.0);
        buildings.ingest(building,measurements,Map.of(),Map.of(),"history");
        Map<String,Object> release=publication.publish(community,Map.of("name","Generated forecasts","buildingIds",List.of(building)));
        java.nio.file.Path directory=publication.directory(community,release.get("id").toString());
        List<String> weather=java.nio.file.Files.readAllLines(directory.resolve("weather_1.csv"));
        List<String> columns=Arrays.asList(weather.get(0).split(","));
        assertEquals(5,weather.size());
        assertEquals(42.0,Double.parseDouble(weather.get(1).split(",")[columns.indexOf("outdoor_dry_bulb_temperature_predicted_1")]));
        double generated=Double.parseDouble(weather.get(4).split(",")[columns.indexOf("outdoor_dry_bulb_temperature_predicted_3")]);
        assertTrue(generated>=35.65 && generated<=38.35);
        List<String> price=java.nio.file.Files.readAllLines(directory.resolve("pricing_1.csv"));
        assertEquals(2.7,Double.parseDouble(price.get(4).split(",")[3]),1e-12);
        Map<?,?> manifest=mapper.readValue(directory.resolve("manifest.json").toFile(),Map.class);
        assertTrue(manifest.containsKey("forecastGeneration"));
        Map<?,?> schema=mapper.readValue(directory.resolve("schema.json").toFile(),Map.class);
        assertEquals(true,((Map<?,?>)((Map<?,?>)schema.get("observations")).get("electricity_pricing_predicted_3")).get("active"));
    }
    @Test void rejectsLessThan26HoursEvenWhenSuppliedForecastsExist() throws Exception {
        long community=community("Short source"),building=building(community,"Short building");
        buildings.ingest(building,rows().subList(0,25),Map.of(),Map.of(),"history");
        Map<String,Object> result=publication.preview(community,Map.of("buildingIds",List.of(building)));
        assertEquals(false,result.get("ready"));
        assertTrue(result.get("blocker").toString().contains("24小时"));
    }
    @Test void rangeDiscoveryDoesNotLoadAllLongHistoryBeforeSelectingASmallWindow() throws Exception {
        long community=community("Long history"),building=building(community,"Long source");
        List<Map<String,Object>> source=rows();
        buildings.ingest(building,source,Map.of(),Map.of(),"history");
        Map<String,Object> old=new LinkedHashMap<>(source.get(0));
        old.put("timestamp","2000-01-01T00:00:00Z");
        jdbc.update("INSERT INTO building_measurement(building_id,timestamp_ms,payload,source) VALUES (?,?,?,'history')",
                building,946684800000L,mapper.writeValueAsString(old));
        // Many older shared samples must not prevent selecting the recent 28-hour source window.
        jdbc.update("INSERT INTO community_measurement(community_id,timestamp_ms,payload,source) " +
                "WITH RECURSIVE numbers AS (SELECT 0 n UNION ALL SELECT n+1 FROM numbers WHERE n<999), " +
                "hundreds AS (SELECT 0 n UNION ALL SELECT n+1 FROM hundreds WHERE n<200) " +
                "SELECT ?, 946684800000+(numbers.n+hundreds.n*1000)*3600000, '{}', 'history' FROM numbers CROSS JOIN hundreds WHERE numbers.n+hundreds.n*1000<200001",
                community);
        assertEquals(true,publication.availableRange(community,Map.of("buildingIds",List.of(building))).get("ready"));
        Map<String,Object> result=publication.preview(community,Map.of("buildingIds",List.of(building),
                "from","2026-01-01T00:00:00Z","to","2026-01-01T04:00:00Z"));
        assertEquals(true,result.get("ready"),result.toString());
    }
}
