package com.citylearn.building;

import org.junit.jupiter.api.Test;
import java.time.ZoneId;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class MeasurementContractTest {
    private final MeasurementContract contract = new MeasurementContract();
    private final ZoneId zone = ZoneId.of("Asia/Shanghai");

    @Test void convertsPowerAndOffsetTimestampsWithoutChangingEnergy() {
        Map<String, Object> raw = new HashMap<>();
        raw.put("time", "2026-01-01T08:00:00+08:00");
        raw.put("meter", 2.0);
        Map<String, Object> actual = contract.normalize(raw, zone, 900,
                Map.of("timestamp", "time", "non_shiftable_load", "meter"), Map.of("non_shiftable_load", "kW"));
        assertEquals("2026-01-01T00:00:00Z", actual.get("timestamp"));
        assertEquals(0.5, actual.get("non_shiftable_load"));
        raw.put("time", "2026-01-01T00:00:00Z");
        assertEquals(actual, contract.normalize(raw, zone, 900,
                Map.of("timestamp", "time", "non_shiftable_load", "meter"), Map.of("non_shiftable_load", "kW")));
    }

    @Test void rejectsDstAmbiguityAndNonexistentWallClockTimes() {
        for (String time : List.of("2026-11-01T01:00:00", "2026-03-08T02:00:00")) {
            assertThrows(IllegalArgumentException.class, () -> contract.normalize(
                    Map.of("timestamp", time, "non_shiftable_load", 1), ZoneId.of("America/New_York"),
                    3600, Map.of(), Map.of()));
        }
    }

    @Test void rejectsNonfiniteNegativeEnergyUnsupportedUnitsAndUnalignedTimestamps() {
        for (Object value : List.of("NaN", "Infinity", -1)) {
            assertThrows(IllegalArgumentException.class, () -> contract.normalize(
                    Map.of("timestamp", "2026-01-01T00:00:00Z", "non_shiftable_load", value),
                    zone, 3600, Map.of(), Map.of()));
        }
        assertThrows(IllegalArgumentException.class, () -> contract.normalize(
                Map.of("timestamp", "2026-01-01T00:00:00Z", "solar_generation", 1),
                zone, 3600, Map.of(), Map.of("solar_generation", "kWh")));
        assertThrows(IllegalArgumentException.class, () -> contract.normalize(
                Map.of("timestamp", "2026-01-01T00:02:00Z", "non_shiftable_load", 1),
                zone, 900, Map.of(), Map.of()));
    }

    @Test void aggregatesEnergyBySumAndTemperatureByMeanAndDetectsMissingSamples() {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            Map<String, Object> row = complete(String.format("2026-01-01T%02d:%02d:00Z", i / 4, i % 4 * 15));
            row.put("non_shiftable_load", 0.25);
            row.put("indoor_dry_bulb_temperature", 20.0 + i % 4);
            rows.add(row);
        }
        List<Map<String, Object>> hourly = contract.hourly(rows, zone, 900);
        assertEquals(2, hourly.size());
        assertEquals(1.0, hourly.get(0).get("non_shiftable_load"));
        assertEquals(21.5, hourly.get(0).get("indoor_dry_bulb_temperature"));
        rows.remove(3);
        assertThrows(IllegalArgumentException.class, () -> contract.hourly(rows, zone, 900));
    }

    @Test void preservesIncompleteObservationsButBlocksPublication() {
        Map<String, Object> row = contract.normalize(Map.of("timestamp", "2026-01-01T00:00:00Z",
                "non_shiftable_load", 1), zone, 3600, Map.of(), Map.of());
        assertEquals(2, row.size());
        assertThrows(IllegalArgumentException.class, () -> contract.hourly(List.of(row), zone, 3600));
    }

    @Test void citylearnSolarInputIsPerKilowattPowerAndNotIntervalEnergy() {
        Map<String, Object> row = contract.normalize(Map.of("timestamp", "2026-01-01T00:00:00Z",
                "solar_generation", 800), zone, 3600, Map.of(), Map.of());
        assertEquals(800.0, row.get("solar_generation"));
        assertEquals(2.4, 3.0 * ((Number) row.get("solar_generation")).doubleValue() / 1000.0, 1e-9);
    }

    static Map<String, Object> complete(String timestamp) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("timestamp", timestamp);
        for (String field : MeasurementContract.REQUIRED) row.put(field, 1.0);
        row.put("indoor_dry_bulb_temperature", 24.0);
        row.put("indoor_dry_bulb_temperature_cooling_set_point", 26.0);
        row.put("indoor_dry_bulb_temperature_heating_set_point", 20.0);
        return row;
    }

    @Test void preservesOptionalCategoriesAndForecastsWithoutRequiringThem() {
        Map<String,Object> input = new LinkedHashMap<>(complete("2026-01-01T00:00:00Z"));
        input.put("day_type", 2); input.put("hvac_mode", 3);
        input.put("outdoor_dry_bulb_temperature_predicted_1", 31.5);
        Map<String,Object> row = contract.normalize(input, zone, 3600, Map.of(), Map.of());
        assertEquals(2.0, row.get("day_type"));
        assertEquals(31.5, row.get("outdoor_dry_bulb_temperature_predicted_1"));
        input.put("day_type", 2.5);
        assertThrows(IllegalArgumentException.class, () -> contract.normalize(input, zone, 3600, Map.of(), Map.of()));
    }

    @Test void categoryValuesMustAgreeWithinHourAndOptionalColumnsCannotBePartial() {
        List<Map<String,Object>> rows = new ArrayList<>();
        for (int i=0;i<4;i++) {
            Map<String,Object> row=complete(String.format("2026-01-01T%02d:%02d:00Z",i/2,i%2*30));
            row.put("day_type",2.0); rows.add(row);
        }
        assertEquals(2.0, contract.hourly(rows, zone, 1800).get(0).get("day_type"));
        rows.get(1).put("day_type",3.0);
        assertThrows(IllegalArgumentException.class, () -> contract.hourly(rows, zone, 1800));
        rows.get(1).put("day_type",2.0);
        rows.get(0).put("electricity_pricing_predicted_1",0.3);
        assertThrows(IllegalArgumentException.class, () -> contract.hourly(rows, zone, 1800));
    }
}
