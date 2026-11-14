package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ExternalDataExportTest {
    @TempDir Path root;
    final ObjectMapper mapper=new ObjectMapper();
    Map<String,Object> building() {
        return new LinkedHashMap<>(Map.of("timezone","UTC","timestampKind","assigned","name","External","devices",Map.of()));
    }
    List<Map<String,Object>> rows() {
        List<Map<String,Object>> rows=List.of(MeasurementContractTest.complete("2023-06-01T00:00:00Z"),MeasurementContractTest.complete("2023-06-01T01:00:00Z"));
        for(int i=0;i<rows.size();i++) {
            Map<String,Object> row=rows.get(i);
            for(String demand:List.of("cooling_demand","heating_demand","dhw_demand","solar_generation")) row.put(demand,0.0);
            row.put("month",6.0);row.put("hour",i+1.0);row.put("day_type",2.0);row.put("daylight_savings_status",0.0);
            row.put("hvac_mode",0.0);row.put("average_unmet_cooling_setpoint_difference",-1.234);
            row.put("outdoor_dry_bulb_temperature_predicted_1",31.5);
        }
        return rows;
    }
    @Test void preservesSuppliedCalendarForecastAndAuxiliarySignals() throws Exception {
        new BuildingDatasetExporter(mapper).write(root,building(),rows(),"fidelity");
        List<String> lines=Files.readAllLines(root.resolve("Building_1.csv"));
        List<String> columns=Arrays.asList(lines.get(0).split(","));
        String[] first=lines.get(1).split(",");
        assertEquals(2.0,Double.parseDouble(first[columns.indexOf("day_type")]));
        assertEquals(-1.234,Double.parseDouble(first[columns.indexOf("average_unmet_cooling_setpoint_difference")]));
        Map<?,?> schema=mapper.readValue(root.resolve("schema.json").toFile(),Map.class);
        Map<?,?> obs=(Map<?,?>)schema.get("observations");
        assertEquals(true,((Map<?,?>)obs.get("outdoor_dry_bulb_temperature_predicted_1")).get("active"));
        assertEquals(false,((Map<?,?>)obs.get("outdoor_dry_bulb_temperature_predicted_2")).get("active"));
        Map<?,?> manifest=mapper.readValue(root.resolve("manifest.json").toFile(),Map.class);
        assertEquals("assigned",manifest.get("timestampKind"));
    }
    @Test void assignedTimeWithoutSourceCalendarCannotInventWeekdays() {
        List<Map<String,Object>> rows=rows(); rows.forEach(row->row.remove("day_type"));
        assertThrows(IllegalArgumentException.class,()->new BuildingDatasetExporter(mapper).write(root,building(),rows,"missing-calendar"));
    }
    @Test void storageActionsAndRewardAreExplicitAndUnavailableControlsAreRejected() throws Exception {
        Map<String,Object> building=building();
        building.put("devices",Map.of("dhw_storage",Map.of("type","citylearn.energy_model.StorageTank","attributes",Map.of("capacity",3)),
                "dhw_device",Map.of("type","citylearn.energy_model.ElectricHeater","attributes",Map.of("nominal_power",3,"efficiency",0.9))));
        new BuildingDatasetExporter(mapper).write(root,building,rows(),"storage",Map.of("profile","storage","reward","cost","actions",List.of("dhw_storage")));
        Map<?,?> schema=mapper.readValue(root.resolve("schema.json").toFile(),Map.class);
        assertEquals(true,((Map<?,?>)((Map<?,?>)schema.get("actions")).get("dhw_storage")).get("active"));
        assertTrue(Files.exists(root.resolve("citylearn_external_rewards.py")));
        assertEquals("citylearn_external_rewards.PurchaseCostReward",((Map<?,?>)schema.get("reward_function")).get("type"));
        assertThrows(IllegalArgumentException.class,()->BuildingExperimentService.requireBatteryAction(Map.of("actions",Map.of("electrical_storage",Map.of("active",true),"dhw_storage",Map.of("active",true)))));
        assertThrows(IllegalArgumentException.class,()->BuildingExportOptions.parse(Map.of("profile","storage","actions",List.of("cooling_device")),Map.of()));
        assertThrows(IllegalArgumentException.class,()->BuildingExportOptions.parse(Map.of("profile","battery","actions",List.of("dhw_storage")),(Map<String,Object>)building.get("devices")));
    }
}
