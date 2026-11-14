package com.citylearn.building;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"citylearn.file.python-file-path=${java.io.tmpdir}/citylearn-management-tests","citylearn.community.validate-runtime=false"})
@Transactional
class CommunityManagementServiceTest {
    @Autowired CommunityManagementService communities;
    @Autowired CommunityAssetService assets;
    @Autowired BuildingIngestionService buildings;
    @Autowired JdbcTemplate jdbc;
    long create(String name){return ((Number)communities.save(null,new LinkedHashMap<>(Map.of("name",name,"timezone","UTC","currency","USD"))).get("id")).longValue();}
    Map<String,Object> ingest(long id,List<Map<String,Object>> rows){return communities.ingest(id,rows,Map.of(),Map.of(),"history",List.of(),null);}

    @Test void tokenIsScopedRotatedAndRevokedByArchive(){
        long first=create("Token first"),second=create("Token second");String token=communities.rotateToken(first);
        assertTrue(communities.authenticate(first,"Bearer "+token));assertFalse(communities.authenticate(second,"Bearer "+token));
        assertFalse(communities.authenticate(first,token));String replacement=communities.rotateToken(first);
        assertFalse(communities.authenticate(first,"Bearer "+token));assertTrue(communities.authenticate(first,"Bearer "+replacement));
        communities.delete(first);assertFalse(communities.authenticate(first,"Bearer "+replacement));
        assertThrows(IllegalArgumentException.class,()->communities.get(first,false));
    }
    @Test void archivingCommunityRevokesChildCredentialsAndStopsWritesWhileRetainingHistory(){
        long owner=create("Archived owner"),other=create("Active owner");
        long id=((Number)communities.addBuilding(owner,new LinkedHashMap<>(Map.of("name","Archived child","devices",Map.of()))).get("id")).longValue();
        long otherId=((Number)communities.addBuilding(other,new LinkedHashMap<>(Map.of("name","Active child","devices",Map.of()))).get("id")).longValue();
        String token=buildings.rotateToken(id),otherToken=buildings.rotateToken(otherId);
        String timestamp="2026-01-01T00:00:00Z";
        buildings.ingest(id,List.of(Map.of("timestamp",timestamp,"non_shiftable_load",1)),Map.of(),Map.of(),"realtime");
        assertTrue(buildings.authenticate(id,"Bearer "+token));
        communities.delete(owner);
        assertFalse(buildings.authenticate(id,"Bearer "+token));
        assertTrue(buildings.authenticate(otherId,"Bearer "+otherToken));
        assertNull(jdbc.queryForObject("SELECT token_hash FROM managed_building WHERE id=?",String.class,id));
        assertThrows(IllegalArgumentException.class,()->buildings.ingest(id,List.of(Map.of("timestamp","2026-01-01T01:00:00Z","non_shiftable_load",2)),Map.of(),Map.of(),"history"));
        assertThrows(IllegalArgumentException.class,()->buildings.rotateToken(id));
        assertThrows(IllegalArgumentException.class,()->buildings.save(id,new LinkedHashMap<>(Map.of("name","Blocked change","devices",Map.of()))));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM building_measurement WHERE building_id=?",Integer.class,id));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM building_ingestion_batch WHERE building_id=?",Integer.class,id));
        assertEquals(owner,jdbc.queryForObject("SELECT community_id FROM community_building WHERE building_id=?",Long.class,id));
        assertFalse(buildings.list().stream().anyMatch(row->((Number)row.get("id")).longValue()==id));
        // A stored token must stay unusable even if an old backup restores its hash after archival.
        jdbc.update("UPDATE managed_building SET token_hash=? WHERE id=?",BuildingDatasetExporter.sha256(token.getBytes(java.nio.charset.StandardCharsets.UTF_8)),id);
        assertFalse(buildings.authenticate(id,"Bearer "+token));
    }
    @Test void sharesOneOwnerAndRejectsAnotherCommunity(){
        long first=create("Owner first"),second=create("Owner second");
        Map<String,Object> building=communities.addBuilding(first,new LinkedHashMap<>(Map.of("name","Owned building","devices",Map.of())));
        long id=((Number)building.get("id")).longValue();
        assertEquals(1,communities.buildings(first).size());assertTrue(communities.buildings(second).isEmpty());
        assertEquals(first,jdbc.queryForObject("SELECT community_id FROM community_building WHERE building_id=?",Long.class,id));
        assertThrows(IllegalArgumentException.class,()->communities.addBuilding(second,Map.of("buildingId",id)));
        assertEquals("UTC",building.get("timezone"));assertEquals("USD",building.get("currency"));
    }
    @Test void partialSharedRowsMergeWithoutLosingFieldsAndHistoryIsIsolated(){
        long first=create("Shared first"),second=create("Shared second");
        String timestamp="2026-01-01T00:00:00Z";
        assertEquals(1,ingest(first,List.of(Map.of("timestamp",timestamp,"outdoor_dry_bulb_temperature",12))).get("inserted"));
        assertEquals(1,ingest(first,List.of(Map.of("timestamp",timestamp,"electricity_pricing",0.5))).get("updated"));
        assertEquals(1,ingest(first,List.of(Map.of("timestamp",timestamp,"electricity_pricing",0.5+1e-13))).get("duplicates"));
        List<Map<String,Object>> rows=communities.rows(first,null,null);assertEquals(1,rows.size());
        assertEquals(12.0,rows.get(0).get("outdoor_dry_bulb_temperature"));assertEquals(0.5,rows.get(0).get("electricity_pricing"));
        assertTrue(communities.rows(second,null,null).isEmpty());
        assertEquals(3,((List<?>)communities.batches(first,1,100).get("batches")).size());
        assertThrows(IllegalArgumentException.class,()->ingest(first,List.of(Map.of("timestamp",timestamp,"non_shiftable_load",1))));
    }
    @Test void sharedMeasurementPagesAreBoundedAndKeepTotalAndRangeMetadata(){
        long id=create("Paged shared data");List<Map<String,Object>> rows=new ArrayList<>();
        for(int i=0;i<205;i++)rows.add(Map.of("timestamp",Instant.ofEpochSecond(1_767_225_600L+i*3600L).toString(),"outdoor_dry_bulb_temperature",10+i%20));
        ingest(id,rows);
        Map<String,Object> first=communities.measurements(id,null,null,1,100),third=communities.measurements(id,null,null,3,100);
        assertEquals(205L,first.get("count"));assertEquals(100,((List<?>)first.get("samples")).size());
        assertEquals(3L,first.get("pages"));assertEquals(5,((List<?>)third.get("samples")).size());
        assertEquals(1,first.get("page"));assertEquals(3,third.get("page"));
    }
    @Test void ingestionBatchPagesAreBounded(){
        long id=create("Paged batches");
        for(int i=0;i<3;i++)communities.ingest(id,List.of(Map.of("timestamp",Instant.ofEpochSecond(1_767_225_600L+i*3600L).toString(),"outdoor_dry_bulb_temperature",i)),Map.of(),Map.of(),"history",List.of(),null);
        Map<String,Object> first=communities.batches(id,1,2),second=communities.batches(id,2,2);
        assertEquals(3L,first.get("count"));assertEquals(2,((List<?>)first.get("batches")).size());assertEquals(1,((List<?>)second.get("batches")).size());
    }
    @Test void conflictRejectsEntireBatchBeforeAnyMeasurementOrBatchWrite(){
        long id=create("Conflict");String timestamp="2026-01-01T00:00:00Z";
        ingest(id,List.of(Map.of("timestamp",timestamp,"electricity_pricing",0.5)));
        assertThrows(IllegalArgumentException.class,()->ingest(id,List.of(Map.of("timestamp","2026-01-01T01:00:00Z","electricity_pricing",0.8),Map.of("timestamp",timestamp,"electricity_pricing",0.7))));
        assertEquals(1,communities.rows(id,null,null).size());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM community_ingestion_batch WHERE community_id=?",Integer.class,id));
        assertThrows(IllegalArgumentException.class,()->ingest(id,List.of(Map.of("timestamp","2026-01-01T01:00:00Z","carbon_intensity",0.4),Map.of("timestamp","2026-01-01T01:00:00Z","carbon_intensity",0.6))));
        assertEquals(1,communities.rows(id,null,null).size());
    }
    @Test void mappingUnitsRawSourceAndAssignedProvenanceAreRetained(){
        long id=create("Mapped");
        communities.ingest(id,List.of(Map.of("when","2026-01-01T00:00:00Z","co2",500)),Map.of("timestamp","when","carbon_intensity","co2"),Map.of("carbon_intensity","gCO2/kWh"),"realtime",List.of(Map.of("name","carbon.csv","content","when,co2\n2026-01-01T00:00:00Z,500\n")),"measured");
        assertEquals(0.5,communities.rows(id,null,null).get(0).get("carbon_intensity"));
        String original=jdbc.queryForObject("SELECT raw_payload FROM community_ingestion_batch WHERE community_id=?",String.class,id);
        assertTrue(original.contains("carbon.csv"));assertTrue(original.contains("sha256"));assertTrue(original.contains("gCO2/kWh"));
        assertThrows(IllegalArgumentException.class,()->communities.ingest(id,List.of(Map.of("timestamp","2026-01-01T01:00:00Z","carbon_intensity",0.5)),Map.of(),Map.of(),"history",List.of(),"assigned"));
    }
    @Test void assetRejectsUnsafeFilenamesAndExecutablePayloads() throws Exception {
        long id=create("Asset rejection");
        for(String name:List.of("../bad.pth","C:\\bad.pth","model.py",".hidden.pt","model name.pth","模型.pth","model..pth","MODEL.PTH")){
            assertThrows(IllegalArgumentException.class,()->assets.upload(id,new MockMultipartFile("file",name,"application/octet-stream",new byte[]{1,2,3})));
        }
        assertThrows(IllegalArgumentException.class,()->assets.upload(id,new MockMultipartFile("file","invalid.pth","application/octet-stream",new byte[]{1,2,3})));
        assertTrue(communities.assets(id).isEmpty());
    }
    @Test void originalOnlineModelIsValidatedStoredAndHashAddressedWithoutRenaming() throws Exception {
        long id=create("Original model");
        Path original=Paths.get("../citylearnpy/CHESCA-main/data/schemas/citylearn_challenge_2023_phase_2_online_evaluation_1/Building_1.pth");
        byte[] bytes=Files.readAllBytes(original);
        List<Map<String,Object>> stored=assets.upload(id,new MockMultipartFile("file","Building_1.pth","application/octet-stream",bytes));
        assertEquals("Building_1.pth",stored.get(0).get("name"));
        assertEquals(BuildingDatasetExporter.sha256(bytes),stored.get(0).get("sha256"));
        Path destination=communities.assetDirectory(id).resolve("Building_1.pth");
        assertArrayEquals(bytes,Files.readAllBytes(destination));
        assertEquals(stored,assets.upload(id,new MockMultipartFile("file","Building_1.pth","application/octet-stream",bytes)));
        assertEquals(stored,communities.get(id,false).get("assets"));
        List<Map<String,Object>> withPt=assets.upload(id,new MockMultipartFile("file","Building_1.pt","application/octet-stream",bytes));
        assertEquals(2,withPt.size());assertTrue(withPt.stream().anyMatch(asset->asset.get("name").equals("Building_1.pt")));
    }
}
