package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"citylearn.file.python-file-path=../citylearnpy","citylearn.community.validate-runtime=true"})
@Transactional
@EnabledIfEnvironmentVariable(named="CITYLEARN_PYTHON",matches=".+")
class CommunityPublicationDynamicsIntegrationTest {
    @Autowired CommunityPublicationService publication;
    @Autowired CommunityManagementService communities;
    @Autowired BuildingIngestionService buildings;
    @Autowired ObjectMapper mapper;

    @Test void publishesOnlyAfterFittingPortableModelsAndValidatingRealCityLearn() throws Exception {
        long community=((Number)communities.save(null,Map.of("name","Generated dynamics integration","timezone","UTC","currency","USD")).get("id")).longValue();
        long building=((Number)buildings.save(null,Map.of("name","Measured building","communityId",community,"devices",Map.of())).get("id")).longValue();
        List<Map<String,Object>> samples=new ArrayList<>();
        for(int i=0;i<96;i++) {
            Map<String,Object> row=MeasurementContractTest.complete(Instant.parse("2026-01-01T00:00:00Z").plusSeconds(i*3600L).toString());
            for(String field:List.of("cooling_demand","heating_demand","dhw_demand","solar_generation"))row.put(field,0.0);
            row.put("indoor_dry_bulb_temperature",22.0+Math.sin(i/12.0));
            samples.add(row);
        }
        buildings.ingest(building,samples,Map.of(),Map.of(),"history");
        Map<String,Object> request=Map.of("name","Generated dynamics integration","buildingIds",List.of(building));
        Map<String,Object> preview=publication.preview(community,request);
        assertEquals(true,preview.get("ready"),preview.toString());
        assertEquals(true,preview.get("modelGenerationRequired"));
        Map<String,Object> release=publication.publish(community,request);
        Path directory=publication.directory(community,release.get("id").toString());
        assertTrue(Files.size(directory.resolve("Building_1.pth"))>0);
        Map<?,?> manifest=mapper.readValue(directory.resolve("manifest.json").toFile(),Map.class);
        assertEquals("LSTMDynamics",manifest.get("thermalModel"));
        assertTrue(((Map<?,?>)manifest.get("files")).containsKey("Building_1.pth"));
        Map<?,?> summary=(Map<?,?>)manifest.get("publicationSummary");
        assertEquals(List.of("LSTMDynamicsBuilding"),summary.get("buildingClasses"));
        assertEquals(24,summary.get("verifiedSteps"));
        assertEquals(false,summary.get("modelGenerationRequired"));
        Map<?,?> schema=mapper.readValue(directory.resolve("schema.json").toFile(),Map.class);
        Map<?,?> defaults=mapper.readValue(Paths.get("../../datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json").toFile(),Map.class);
        assertEquals(defaults.get("reward_function"),schema.get("reward_function"));
        assertEquals(defaults.get("actions"),schema.get("actions"));
        assertEquals(72,release.get("timeSteps"));
    }
}
