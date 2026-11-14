package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class CommunityDatasetExporterTest {
    @TempDir Path root;
    final ObjectMapper mapper = new ObjectMapper();
    final CommunityDatasetExporter exporter = new CommunityDatasetExporter(mapper);

    CommunityDatasetExporter.Source source(String name, int hour, int count, boolean battery) throws Exception {
        Path dir = root.resolve(name);
        Map<String,Object> building = new LinkedHashMap<>(Map.of("timezone", "Asia/Shanghai", "currency", "CNY", "name", name));
        building.put("devices", battery ? Map.of("electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "autosize", false,
                "attributes", Map.of("capacity", 4, "nominal_power", 2, "initial_soc", 0.5))) : Map.of());
        List<Map<String,Object>> rows = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            Map<String,Object> row = MeasurementContractTest.complete(Instant.parse("2026-01-01T00:00:00Z").plusSeconds((hour+i)*3600L).toString());
            for (String key : List.of("cooling_demand", "heating_demand", "dhw_demand", "solar_generation")) row.put(key, 0.0);
            row.put("non_shiftable_load", hour+i+1.0);
            row.put("outdoor_dry_bulb_temperature", battery ? 15.0 : 25.0);
            rows.add(row);
        }
        String hash = new BuildingDatasetExporter(mapper).write(dir, building, rows, name);
        return exporter.load(dir, Map.of("buildingId", battery ? 1L : 2L, "versionId", name, "contentHash", hash));
    }

    @Test void cropsIntersectionPreservesEquipmentAndBuildingSpecificSignals() throws Exception {
        List<CommunityDatasetExporter.Source> sources = List.of(source("one", 0, 6, true), source("two", 2, 6, false));
        CommunityDatasetExporter.Window window = exporter.window(sources, null, null);
        assertEquals(Instant.parse("2026-01-01T02:00:00Z"), window.start);
        assertEquals(4, window.steps);
        Path output = root.resolve("community");
        exporter.write(output, sources, window, "community-id");
        Map<?,?> schema = mapper.readValue(output.resolve("schema.json").toFile(), Map.class);
        Map<?,?> buildings = (Map<?,?>)schema.get("buildings");
        assertEquals(2, buildings.size());
        Map<?,?> first = (Map<?,?>)buildings.get("Building_1"), second = (Map<?,?>)buildings.get("Building_2");
        assertTrue(first.containsKey("electrical_storage"));
        assertFalse(second.containsKey("electrical_storage"));
        assertTrue(((List<?>)second.get("inactive_actions")).contains("electrical_storage"));
        assertTrue(((List<?>)second.get("inactive_observations")).contains("electrical_storage_soc"));
        assertEquals(false, ((Map<?,?>)((Map<?,?>)schema.get("observations")).get("outdoor_dry_bulb_temperature")).get("shared_in_central_agent"));
        assertEquals(5, Files.readAllLines(output.resolve("Building_1.csv")).size());
        assertEquals(Files.readAllLines(output.resolve("Building_1.csv")), Files.readAllLines(output.resolve("Building_2.csv")));
        assertNotEquals(Files.readString(output.resolve(first.get("weather").toString())), Files.readString(output.resolve(second.get("weather").toString())));
        assertEquals("2026-01-01T02:00:00Z", Files.readAllLines(output.resolve("timestamps.csv")).get(1));
    }

    @Test void allowsSmallerRangeAndRejectsOutsideNonHourlyAndInsufficientIntersection() throws Exception {
        List<CommunityDatasetExporter.Source> sources = List.of(source("one", 0, 6, true), source("two", 2, 6, false));
        assertEquals(2, exporter.window(sources, "2026-01-01T03:00:00Z", "2026-01-01T05:00:00Z").steps);
        assertThrows(IllegalArgumentException.class, () -> exporter.window(sources, "2026-01-01T01:00:00Z", "2026-01-01T05:00:00Z"));
        assertThrows(IllegalArgumentException.class, () -> exporter.window(sources, "2026-01-01T02:30:00Z", "2026-01-01T05:30:00Z"));
        assertThrows(IllegalArgumentException.class, () -> exporter.window(List.of(sources.get(0), source("late", 5, 3, false)), null, null));
    }

    @Test void rejectsChangedSourceFileBeforeCombining() throws Exception {
        CommunityDatasetExporter.Source source = source("tampered", 0, 4, true);
        Files.writeString(source.directory.resolve("Building_1.csv"), "changed");
        assertThrows(IllegalArgumentException.class, () -> exporter.load(source.directory, source.info));
    }
    @Test void sharesOnlyIdenticalExogenousSignalsAndRejectsRewardConflict() throws Exception {
        List<CommunityDatasetExporter.Source> sources=List.of(source("share-a",0,4,true),source("share-b",0,4,false));
        exporter.write(root.resolve("shared"),sources,exporter.window(sources,null,null),"shared");
        Map<?,?> schema=mapper.readValue(root.resolve("shared/schema.json").toFile(),Map.class);
        Map<?,?> observations=(Map<?,?>)schema.get("observations");
        assertEquals(true,((Map<?,?>)observations.get("electricity_pricing")).get("shared_in_central_agent"));
        assertEquals(false,((Map<?,?>)observations.get("electrical_storage_soc")).get("shared_in_central_agent"));
        sources.get(1).schema.put("reward_function",Map.of("type","citylearn.reward_function.ComfortReward","attributes",Map.of()));
        assertThrows(IllegalArgumentException.class,()->exporter.write(root.resolve("conflict"),sources,exporter.window(sources,null,null),"conflict"));
    }
}
