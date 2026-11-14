package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class BuildingIngestionTest {
    @Autowired BuildingIngestionService service;
    @Autowired org.springframework.jdbc.core.JdbcTemplate jdbc;
    @TempDir Path directory;

    Map<String, Object> building() {
        return service.save(null, new LinkedHashMap<>(Map.of(
                "name", "Ingestion integration test", "timezone", "Asia/Shanghai", "intervalSeconds", 3600,
                "batteryCapacity", 10, "batteryPower", 5, "batteryEfficiency", 0.95,
                "pvPower", 3, "coolingCop", 3, "heatingCop", 3, "dhwEfficiency", 0.9)));
    }

    String registeredVersion(long buildingId) {
        String version = UUID.randomUUID().toString();
        String key = "building_test_" + version.replace("-", "");
        jdbc.update("INSERT INTO building_dataset_version(id,building_id,schema_key,name,purpose,start_time,end_time,time_steps,relative_path,content_hash) VALUES (?,?,?,'Deletion fixture','train',?,?,2,?,'test-hash')",
                version, buildingId, key, "2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z", "datasets/" + key);
        jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled,sort_order,description) VALUES (?,'Deletion fixture',?,1,2,0,1,200,'test')", key, "datasets/" + key);
        return version;
    }

    @Test void deletedDatasetLeavesHistoryButCannotBeListedDownloadedOrDeletedByAnotherBuilding() {
        long id = ((Number)building().get("id")).longValue();
        long other = ((Number)building().get("id")).longValue();
        String version = registeredVersion(id);
        String run = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO building_experiment_run(id,building_id,version_id,mode,status,config_json) VALUES (?,?,?,'train','succeeded','{}')", run, id, version);
        assertThrows(IllegalArgumentException.class, () -> service.deleteVersion(other, version));
        assertEquals(1, ((List<?>)service.detail(id, null, null).get("versions")).size());
        service.deleteVersion(id, version);
        assertTrue(((List<?>)service.detail(id, null, null).get("versions")).isEmpty());
        assertThrows(IllegalArgumentException.class, () -> service.versionDirectory(id, version));
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run WHERE id=?", Integer.class, run));
        assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM building_dataset_version WHERE id=?", Integer.class, version));
        assertThrows(IllegalArgumentException.class, () -> service.deleteVersion(id, version));
    }

    @Test void buildingDeletionInvalidatesTokenAndDisablesAllPublishedDatasets() {
        long id = ((Number)building().get("id")).longValue();
        String token = service.rotateToken(id);
        String version = registeredVersion(id);
        service.ingest(id, List.of(MeasurementContractTest.complete("2026-01-01T00:00:00Z")), Map.of(), Map.of(), "history");
        service.deleteBuilding(id);
        assertFalse(service.authenticate(id, "Bearer " + token));
        assertFalse(service.list().stream().anyMatch(b -> ((Number)b.get("id")).longValue() == id));
        assertThrows(IllegalArgumentException.class, () -> service.get(id, false));
        assertThrows(IllegalArgumentException.class, () -> service.versionDirectory(id, version));
        assertEquals(0, jdbc.queryForObject("SELECT d.enabled FROM citylearn_dataset d JOIN building_dataset_version v ON BINARY v.schema_key=BINARY d.schema_key WHERE v.id=?", Integer.class, version));
    }

    @Test void activeExperimentsPreventBuildingAndDatasetDeletion() {
        long id = ((Number)building().get("id")).longValue();
        String version = registeredVersion(id);
        String run = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO building_experiment_run(id,building_id,version_id,mode,status,config_json) VALUES (?,?,?,'train','queued','{}')", run, id, version);
        for (String status : List.of("queued", "running")) {
            jdbc.update("UPDATE building_experiment_run SET status=? WHERE id=?", status, run);
            assertThrows(IllegalArgumentException.class, () -> service.deleteBuilding(id));
            assertThrows(IllegalArgumentException.class, () -> service.deleteVersion(id, version));
        }
        assertTrue(service.get(id, false).containsKey("id"));
        assertEquals(1, ((List<?>)service.detail(id, null, null).get("versions")).size());
    }
    @Test void retriesAreIdempotentConflictsRollbackAndTokensAreEnforced() {
        long id = ((Number) building().get("id")).longValue();
        Map<String, Object> row = MeasurementContractTest.complete("2026-01-01T00:00:00Z");
        assertEquals(1, service.ingest(id, List.of(row), Map.of(), Map.of(), "history").get("inserted"));
        assertEquals(1, service.ingest(id, List.of(row), Map.of(), Map.of(), "realtime").get("duplicates"));
        Map<String, Object> conflict = new LinkedHashMap<>(row);
        conflict.put("non_shiftable_load", 12);
        assertThrows(IllegalArgumentException.class, () -> service.ingest(id,
                List.of(MeasurementContractTest.complete("2026-01-01T01:00:00Z"), conflict),
                Map.of(), Map.of(), "history"));
        assertEquals(1L, ((Number) service.detail(id, null, null).get("count")).longValue());
        String token = service.rotateToken(id);
        assertTrue(service.authenticate(id, "Bearer " + token));
        assertFalse(service.authenticate(id, "Bearer invalid"));
        assertFalse(service.authenticate(id, "Bearer " + service.rotateToken(id) + "bad"));
        assertFalse(service.authenticate(id, "Bearer " + token));
    }
    @Test void buildingMeasurementPagesReturnBoundedSamplesAndStableTotals() {
        long id=((Number)building().get("id")).longValue();
        service.ingest(id,List.of(MeasurementContractTest.complete("2026-01-01T00:00:00Z"),MeasurementContractTest.complete("2026-01-01T01:00:00Z"),MeasurementContractTest.complete("2026-01-01T02:00:00Z")),Map.of(),Map.of(),"history");
        Map<String,Object> page=service.measurementPage(id,null,null,2,2);
        assertEquals(3L,page.get("count"));assertEquals(2,page.get("page"));assertEquals(2,page.get("size"));
        List<?> samples=(List<?>)page.get("samples");assertEquals(1,samples.size());
        assertEquals("2026-01-01T02:00:00Z",((Map<?,?>)samples.get(0)).get("timestamp"));
    }

    @Test void exportFreezesMetadataUsesCalendarAndDisablesFutureObservations() throws Exception {
        Map<String, Object> b = building();
        List<Map<String, Object>> rows = List.of(
                MeasurementContractTest.complete("2026-01-01T00:00:00Z"),
                MeasurementContractTest.complete("2026-01-01T01:00:00Z"));
        new BuildingDatasetExporter(new ObjectMapper()).write(directory, b, rows, "test-version");
        String csv = Files.readString(directory.resolve("Building_1.csv"));
        assertTrue(csv.contains("month,hour,day_type"));
        assertTrue(csv.contains("1,9,4,"));
        Map<?, ?> schema = new ObjectMapper().readValue(directory.resolve("schema.json").toFile(), Map.class);
        assertEquals(1, schema.get("simulation_end_time_step"));
        Map<?, ?> observations = (Map<?, ?>) schema.get("observations");
        assertEquals(false, ((Map<?, ?>) observations.get("outdoor_dry_bulb_temperature_predicted_1")).get("active"));
        Map<?, ?> actions = (Map<?, ?>) schema.get("actions");
        assertEquals(true, ((Map<?, ?>) actions.get("electrical_storage")).get("active"));
        Map<?, ?> definition = (Map<?, ?>) ((Map<?, ?>) schema.get("buildings")).get("Building_1");
        assertFalse(definition.containsKey("dynamics"));
        assertEquals("citylearn.building.Building", definition.get("type"));
        assertEquals("citylearn_ingested_devices.FixedCopHeatPump",
                ((Map<?, ?>) definition.get("cooling_device")).get("type"));
        assertTrue(Files.exists(directory.resolve("citylearn_ingested_devices.py")));
        assertTrue(Files.readString(directory.resolve("manifest.json")).contains("persistence"));
    }

    @Test void independentEvaluationRejectsOverlapWithTrainingSource() {
        assertThrows(IllegalArgumentException.class, () -> BuildingExperimentService.requireDisjoint(
                "2023-01-01T00:00:00Z", "2023-01-04T00:00:00Z",
                "2023-01-03T00:00:00Z", "2023-01-05T00:00:00Z"));
        assertDoesNotThrow(() -> BuildingExperimentService.requireDisjoint(
                "2023-01-01T00:00:00Z", "2023-01-04T00:00:00Z",
                "2023-01-04T00:00:00Z", "2023-01-05T00:00:00Z"));
    }

    @Test void historicalBackfillCanCompletePartialLiveObservationsWithoutOverwriting() {
        long id = ((Number) building().get("id")).longValue();
        service.ingest(id, List.of(Map.of("timestamp", "2026-01-01T00:00:00Z", "non_shiftable_load", 1)),
                Map.of(), Map.of(), "realtime");
        Map<String, Object> completed = MeasurementContractTest.complete("2026-01-01T00:00:00Z");
        assertEquals(1, service.ingest(id, List.of(completed), Map.of(), Map.of(), "history").get("updated"));
        assertEquals(1, service.ingest(id, List.of(completed), Map.of(), Map.of(), "history").get("duplicates"));
    }
    @Test void backfillPreservesOptionalFieldsAndAssignedTimePreviewRequiresSourceCalendar() {
        Map<String,Object> input=new LinkedHashMap<>(Map.of("name","Assigned external source","timezone","UTC","timestampKind","assigned","devices",Map.of()));
        long id=((Number)service.save(null,input).get("id")).longValue();
        List<Map<String,Object>> rows=List.of(MeasurementContractTest.complete("2026-01-01T00:00:00Z"),MeasurementContractTest.complete("2026-01-01T01:00:00Z"));
        for(Map<String,Object> row:rows) for(String key:List.of("cooling_demand","heating_demand","dhw_demand","solar_generation")) row.put(key,0.0);
        service.ingest(id,rows,Map.of(),Map.of(),"history");
        Map<String,Object> request=Map.of("from","2026-01-01T00:00:00Z","to","2026-01-01T02:00:00Z");
        assertEquals(false,service.preview(id,request).get("ready"));
        for(int i=0;i<rows.size();i++) {
            rows.get(i).put("day_type",2.0);rows.get(i).put("month",1.0);rows.get(i).put("hour",i+1.0);rows.get(i).put("daylight_savings_status",0.0);
            rows.get(i).put("electricity_pricing_predicted_1",0.3);
        }
        String csv="timestamp,day_type\n2026-01-01T00:00:00Z,2\n";
        assertEquals(2,service.ingest(id,rows,Map.of(),Map.of(),"history",List.of(Map.of("name","source.csv","content",csv))).get("updated"));
        String original=jdbc.queryForObject("SELECT raw_payload FROM building_ingestion_batch WHERE building_id=? AND accepted=2 AND raw_payload LIKE '%sourceFiles%source.csv%' LIMIT 1",String.class,id);
        assertTrue(original.contains(BuildingDatasetExporter.sha256(csv.getBytes(java.nio.charset.StandardCharsets.UTF_8))));
        assertEquals(true,service.preview(id,request).get("ready"));
        Map<String,Object> received=service.ingest(id,rows,Map.of(),Map.of(),"realtime");
        assertEquals(2,received.get("duplicates"));
        assertTrue(jdbc.queryForObject("SELECT raw_payload FROM building_ingestion_batch WHERE id=?",String.class,received.get("batchId")).contains("electricity_pricing_predicted_1"));
        List<?> samples=(List<?>)service.detail(id,null,null).get("samples");
        assertEquals(2.0,((Map<?,?>)samples.get(0)).get("day_type"));
    }
    @Test void generatedTimeKindIsExplicitAndCannotMixWithExistingMeasurementTime() {
        long id=((Number)service.save(null,new LinkedHashMap<>(Map.of("name","Generated clock","devices",Map.of()))).get("id")).longValue();
        List<Map<String,Object>> rows=List.of(Map.of("timestamp","2026-01-01T00:00:00Z","non_shiftable_load",1));
        assertThrows(IllegalArgumentException.class,()->service.ingest(id,rows,Map.of(),Map.of(),"history",List.of(),""));
        service.ingest(id,rows,Map.of(),Map.of(),"history",List.of(),"assigned");
        assertEquals("assigned",service.get(id,false).get("timestampKind"));
        assertThrows(IllegalArgumentException.class,()->service.ingest(id,rows,Map.of(),Map.of(),"history",List.of(),"measured"));
        assertEquals("assigned",service.get(id,false).get("timestampKind"));
    }

    @Test void schemaEquipmentIsPreservedAndExportedWithoutFixedCopTranslation() throws Exception {
        Map<String,Object> input = new LinkedHashMap<>(building());
        Map<String,Object> devices = new LinkedHashMap<>();
        devices.put("electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "autosize", false,
                "attributes", Map.of("capacity", 4.0, "nominal_power", 3.32, "efficiency", 0.95,
                        "depth_of_discharge", 0.8, "capacity_loss_coefficient", 0.00001, "loss_coefficient", 0.0001,
                        "power_efficiency_curve", List.of(List.of(0.0, 0.88), List.of(1.0, 0.9)))));
        devices.put("pv", Map.of("type", "citylearn.energy_model.PV", "autosize", false, "attributes", Map.of("nominal_power", 2.4)));
        for (String key : List.of("cooling_device", "heating_device")) devices.put(key,
                Map.of("type", "citylearn.energy_model.HeatPump", "autosize", false,
                        "attributes", Map.of("nominal_power", 4.1, "efficiency", 0.25,
                                "target_cooling_temperature", 8.0, "target_heating_temperature", 45.0)));
        devices.put("dhw_device", Map.of("type", "citylearn.energy_model.ElectricHeater", "autosize", false,
                "attributes", Map.of("nominal_power", 4.8, "efficiency", 0.94)));
        devices.put("dhw_storage", Map.of("type", "citylearn.energy_model.StorageTank", "autosize", false,
                "attributes", Map.of("capacity", 2.28, "loss_coefficient", 0.0032)));
        input.put("devices", devices);
        Map<String,Object> saved = service.save(null, input);
        assertEquals(devices, saved.get("devices"));
        new BuildingDatasetExporter(new ObjectMapper()).write(directory, saved, List.of(
                MeasurementContractTest.complete("2026-01-01T00:00:00Z"),
                MeasurementContractTest.complete("2026-01-01T01:00:00Z")), "schema-version");
        Map<?,?> schema = new ObjectMapper().readValue(directory.resolve("schema.json").toFile(), Map.class);
        Map<?,?> definition = (Map<?,?>)((Map<?,?>)schema.get("buildings")).get("Building_1");
        for (String key : devices.keySet()) assertEquals(devices.get(key), definition.get(key), key);
        assertFalse(Files.exists(directory.resolve("citylearn_ingested_devices.py")));
    }

    @Test void schemaEquipmentRejectsUnknownExecutableTypesAndInvalidCurves() {
        Map<String,Object> input = new LinkedHashMap<>(building());
        input.put("devices", Map.of("electrical_storage", Map.of("type", "untrusted.CustomBattery", "autosize", false,
                "attributes", Map.of("capacity", 4, "nominal_power", 3))));
        assertThrows(IllegalArgumentException.class, () -> service.save(null, input));
        input.put("devices", Map.of("electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "autosize", false,
                "attributes", Map.of("capacity", 4, "nominal_power", 3, "power_efficiency_curve",
                        List.of(List.of(0.7, 0.9), List.of(0.3, 0.8))))));
        assertThrows(IllegalArgumentException.class, () -> service.save(null, input));
    }

    @Test void photovoltaicAutosizingWithoutWeatherAssetsIsRejectedBeforeExport() {
        Map<String,Object> devices = Map.of(
                "electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "autosize", false,
                        "attributes", Map.of("capacity", 4, "nominal_power", 3)),
                "pv", Map.of("type", "citylearn.energy_model.PV", "autosize", true,
                        "attributes", Map.of("nominal_power", 2)));
        assertThrows(IllegalArgumentException.class, () -> SchemaEquipment.normalize(devices));
    }

    @Test void referenceTemplateKeepsOriginalDevicesAndRejectsUnconfiguredThermalDemand() throws Exception {
        ObjectMapper json = new ObjectMapper();
        Map<String,Object> devices;
        try (java.io.InputStream input = getClass().getResourceAsStream("/citylearn/equipment-template.json")) {
            devices = json.readValue(input, Map.class);
        }
        Map<String,Object> input = new LinkedHashMap<>(Map.of("name", "Native template", "devices", devices));
        Map<String,Object> saved = service.save(null, input);
        assertEquals(devices, saved.get("devices"));
        assertFalse(devices.containsKey("heating_device"));
        List<Map<String,Object>> rows = List.of(MeasurementContractTest.complete("2026-01-01T00:00:00Z"),
                MeasurementContractTest.complete("2026-01-01T01:00:00Z"));
        assertThrows(IllegalArgumentException.class, () -> new BuildingDatasetExporter(json).write(directory, saved, rows, "missing-heating"));
    }

    @Test void buildingsWithoutInstalledEquipmentCanSaveAndReceiveMeasurements() {
        Map<String,Object> saved = service.save(null, new LinkedHashMap<>(Map.of("name", "No installed equipment", "devices", Map.of())));
        assertEquals(Map.of(), saved.get("devices"));
        assertEquals(0.0, saved.get("batteryCapacity"));
        long id = ((Number)saved.get("id")).longValue();
        assertEquals(1, service.ingest(id, List.of(Map.of("timestamp", "2026-01-01T00:00:00Z", "non_shiftable_load", 2)), Map.of(), Map.of(), "realtime").get("inserted"));
    }

    @Test void exportedDatasetWithoutBatteryHasNoBatteryAction() throws Exception {
        Map<String,Object> building = new LinkedHashMap<>(Map.of("timezone", "Asia/Shanghai", "devices", Map.of()));
        List<Map<String,Object>> rows = List.of(MeasurementContractTest.complete("2026-01-01T00:00:00Z"), MeasurementContractTest.complete("2026-01-01T01:00:00Z"));
        for (Map<String,Object> row : rows) for (String field : List.of("cooling_demand", "heating_demand", "dhw_demand", "solar_generation")) row.put(field, 0.0);
        new BuildingDatasetExporter(new ObjectMapper()).write(directory, building, rows, "without-battery");
        Map<?,?> schema = new ObjectMapper().readValue(directory.resolve("schema.json").toFile(), Map.class);
        assertEquals(false, ((Map<?,?>)((Map<?,?>)schema.get("actions")).get("electrical_storage")).get("active"));
        Map<?,?> definition = (Map<?,?>)((Map<?,?>)schema.get("buildings")).get("Building_1");
        assertFalse(definition.containsKey("electrical_storage"));
        assertThrows(IllegalArgumentException.class, () -> BuildingExperimentService.requireBatteryAction(schema));
        assertDoesNotThrow(() -> BuildingExperimentService.requireBatteryAction(Map.of("actions", Map.of("electrical_storage", Map.of("active", true)))));
    }
}
