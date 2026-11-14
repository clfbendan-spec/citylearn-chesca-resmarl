package com.citylearn.building;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class HomeSourceServiceTest {
    @Autowired HomeSourceService home;
    @Autowired CommunityManagementService communities;
    @Autowired BuildingIngestionService buildings;
    @Autowired JdbcTemplate jdbc;
    long create(String name,String kind){return ((Number)communities.save(null,new LinkedHashMap<>(Map.of("name",name,"timezone","UTC","currency","USD","timestampKind",kind))).get("id")).longValue();}
    void shared(long id,String timestamp,String source,double value){communities.ingest(id,List.of(Map.of("timestamp",timestamp,"electricity_pricing",value)),Map.of(),Map.of(),source,List.of(),null);}
    @Test void historyOnlyCommunitiesAreSelectableAndResetPersists(){
        long history=create("History only","measured"),assigned=create("Assigned realtime","assigned"),realtime=create("Measured realtime","measured");
        shared(history,"2026-01-01T00:00:00Z","history",0.5);shared(assigned,"2026-01-01T00:00:00Z","realtime",0.5);
        assertEquals(history,home.select(history).get("communityId"));
        assertEquals("history",((Map<?,?>)home.source().get("community")).get("sourceMode"));
        assertEquals(assigned,home.select(assigned).get("communityId"));
        shared(realtime,"2026-01-01T00:00:00Z","realtime",0.5);
        assertEquals("realtime",((Map<?,?>)home.select(realtime).get("community")).get("sourceMode"));assertEquals(realtime,home.source().get("communityId"));
        assertEquals("community",home.snapshot(null,null,null).get("mode"));
        assertNull(home.select(null).get("communityId"));assertEquals("default",home.snapshot(null,null,null).get("mode"));
    }
    @Test void historyOnlySnapshotReadsSharedAndSelectedBuildingRowsAsHistorical(){
        long id=create("Assigned historical","assigned");long buildingId=((Number)communities.addBuilding(id,new LinkedHashMap<>(Map.of("name","Historical child","devices",Map.of()))).get("id")).longValue();
        String timestamp="2026-01-01T00:00:00Z";
        shared(id,timestamp,"history",0.5);
        buildings.ingest(buildingId,List.of(Map.of("timestamp",timestamp,"non_shiftable_load",1.2,"indoor_dry_bulb_temperature",22)),Map.of(),Map.of(),"history");
        home.select(id);Map<String,Object> snapshot=home.snapshot(buildingId,null,null);
        Map<?,?> current=(Map<?,?>)snapshot.get("current");
        assertEquals("history",snapshot.get("dataMode"));assertEquals("assigned",snapshot.get("timestampKind"));
        assertEquals(timestamp,current.get("timestamp"));assertEquals(0.5,current.get("electricity_pricing"));
        assertEquals(1.2,current.get("non_shiftable_load"));assertEquals(22.0,current.get("indoor_dry_bulb_temperature"));
        assertEquals(Set.of("2026-01-01"),snapshot.get("days"));
        assertEquals("historical",((Map<?,?>)snapshot.get("freshness")).get("status"));
        assertNull(((Map<?,?>)snapshot.get("freshness")).get("ageSeconds"));
    }
    @Test void exactTimestampsOnlyAndMissingActionsSocEnergyAreExplicit(){
        long id=create("Live measured","measured");
        long buildingId=((Number)communities.addBuilding(id,new LinkedHashMap<>(Map.of("name","Live child","devices",Map.of()))).get("id")).longValue();
        shared(id,"2026-01-01T00:00:00Z","realtime",0.5);
        buildings.ingest(buildingId,List.of(Map.of("timestamp","2026-01-01T01:00:00Z","non_shiftable_load",1.2,"indoor_dry_bulb_temperature",22)),Map.of(),Map.of(),"realtime");
        home.select(id);Map<String,Object> snapshot=home.snapshot(buildingId,null,null);
        Map<?,?> current=(Map<?,?>)snapshot.get("current");assertEquals("2026-01-01T01:00:00Z",current.get("timestamp"));
        assertEquals(22.0,current.get("indoor_dry_bulb_temperature"));assertFalse(current.containsKey("electricity_pricing"));
        assertFalse(current.containsKey("electrical_storage_soc"));assertFalse(current.containsKey("action_ele_final"));
        assertEquals("stale",((Map<?,?>)snapshot.get("freshness")).get("status"));
        assertEquals(1.2,((Map<?,?>)snapshot.get("energy")).get("nonShiftableKwh"));
        assertNull(((Map<?,?>)snapshot.get("energy")).get("gridIn"));
        shared(id,"2026-01-01T01:00:00Z","realtime",0.7);
        assertEquals(0.7,((Map<?,?>)home.snapshot(buildingId,null,null).get("current")).get("electricity_pricing"));
        long other=create("Other","measured");long otherBuilding=((Number)communities.addBuilding(other,new LinkedHashMap<>(Map.of("name","Other child","devices",Map.of()))).get("id")).longValue();
        assertThrows(IllegalArgumentException.class,()->home.snapshot(otherBuilding,null,null));
    }
    @Test void archivedSelectionIsInvalidAndNeverFallsBack(){
        long id=create("Soon archived","measured");shared(id,"2026-01-01T00:00:00Z","realtime",0.5);home.select(id);communities.delete(id);
        assertEquals("invalid",home.source().get("mode"));assertEquals(false,home.source().get("valid"));
        assertEquals("invalid",home.snapshot(null,null,null).get("mode"));assertNull(home.snapshot(null,null,null).get("current"));
    }
    @Test void conflictingSharedFieldIsReportedAndHistoryRowsAreNotSubstituted(){
        long id=create("Conflict live","measured");long child=((Number)communities.addBuilding(id,new LinkedHashMap<>(Map.of("name","Conflict child","devices",Map.of()))).get("id")).longValue();
        shared(id,"2026-01-01T00:00:00Z","realtime",0.5);
        buildings.ingest(child,List.of(Map.of("timestamp","2026-01-01T00:00:00Z","electricity_pricing",0.7,"non_shiftable_load",1)),Map.of(),Map.of(),"realtime");
        home.select(id);assertThrows(IllegalArgumentException.class,()->home.snapshot(child,null,null));
    }
    @Test void historicalBackfillNeverRemovesRealtimeValuesOrIntroducesHistoricalOnlyFields(){
        long id=create("Mixed provenance","measured"),child=((Number)communities.addBuilding(id,new LinkedHashMap<>(Map.of("name","Mixed child","devices",Map.of()))).get("id")).longValue();
        String timestamp="2026-01-01T00:00:00Z";shared(id,timestamp,"realtime",0.5);
        buildings.ingest(child,List.of(Map.of("timestamp",timestamp,"non_shiftable_load",1)),Map.of(),Map.of(),"realtime");
        communities.ingest(id,List.of(Map.of("timestamp",timestamp,"carbon_intensity",0.4)),Map.of(),Map.of(),"history",List.of(),null);
        buildings.ingest(child,List.of(Map.of("timestamp",timestamp,"indoor_dry_bulb_temperature",23)),Map.of(),Map.of(),"history");
        home.select(id);Map<?,?> current=(Map<?,?>)home.snapshot(child,null,null).get("current");
        assertEquals(0.5,current.get("electricity_pricing"));assertEquals(1.0,current.get("non_shiftable_load"));
        assertFalse(current.containsKey("carbon_intensity"));assertFalse(current.containsKey("indoor_dry_bulb_temperature"));
        // A duplicate received on the realtime channel is a real source even when the canonical row was imported earlier.
        communities.ingest(id,List.of(Map.of("timestamp",timestamp,"carbon_intensity",0.4)),Map.of(),Map.of(),"realtime",List.of(),null);
        assertEquals(0.4,((Map<?,?>)home.snapshot(child,null,null).get("current")).get("carbon_intensity"));
    }
    @Test void historicalFirstDuplicateRealtimeReportSwitchesFromHistoryToRealtime(){
        long id=create("Historical first","measured");String timestamp="2026-01-01T00:00:00Z";
        shared(id,timestamp,"history",0.5);
        assertEquals(id,home.select(id).get("communityId"));assertEquals("history",((Map<?,?>)home.source().get("community")).get("sourceMode"));
        Map<String,Object> duplicate=communities.ingest(id,List.of(Map.of("timestamp",timestamp,"electricity_pricing",0.5)),Map.of(),Map.of(),"realtime",List.of(),null);
        assertEquals(0,duplicate.get("inserted"));assertEquals(1,duplicate.get("duplicates"));
        assertEquals("realtime",((Map<?,?>)home.select(id).get("community")).get("sourceMode"));assertEquals(0.5,((Map<?,?>)home.snapshot(null,null,null).get("current")).get("electricity_pricing"));
    }
}
