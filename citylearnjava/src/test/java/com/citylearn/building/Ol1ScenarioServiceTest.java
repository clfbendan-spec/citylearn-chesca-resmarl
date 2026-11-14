package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.SimpleTransactionStatus;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class Ol1ScenarioServiceTest {
    @Test
    void managedSelectionUsesOwnedBuildingEquipmentAndCommunitySettings() throws Exception {
        CommunityManagementService communities = mock(CommunityManagementService.class);
        when(communities.get(7L, false)).thenReturn(Map.of("timezone", "Asia/Shanghai", "currency", "CNY", "intervalSeconds", 3600,
                "configuration", Map.of("schema", Map.of("central_agent", false, "random_seed", 99),
                        "buildings", Map.of("21", Map.of("power_outage", Map.of("simulate_power_outage", false),
                                "type", "citylearn.building.Building", "dynamics", Map.of("attributes", Map.of("filename", "uploaded.pth")))))));
        Map<String,Object> devices = Map.of("pv", Map.of("type", "citylearn.energy_model.PV", "attributes", Map.of("nominal_power", 7)));
        when(communities.buildings(7L)).thenReturn(List.of(Map.of("id", 21L, "name", "Building_3", "devices", devices)));
        Ol1ScenarioService service = new Ol1ScenarioService();
        inject(service, "communities", communities);
        inject(service, "mapper", new ObjectMapper());
        Method prepare = Ol1ScenarioService.class.getDeclaredMethod("prepareConfiguration", long.class, Map.class);
        prepare.setAccessible(true);
        Map<?,?> config = (Map<?,?>) prepare.invoke(service, 7L, Map.of("buildingIds", List.of(21), "startStep", 24, "steps", 48));
        List<?> selected = (List<?>) config.get("managedBuildings");
        assertEquals(1, selected.size());
        Map<?,?> building = (Map<?,?>) selected.get(0);
        assertEquals("Building_3", building.get("prototype"));
        assertEquals(devices, building.get("devices"));
        assertEquals("CNY", ((Map<?,?>)config.get("community")).get("currency"));
        assertEquals(99, ((Map<?,?>)((Map<?,?>)config.get("community")).get("schema")).get("random_seed"));
        assertEquals(false, ((Map<?,?>)((Map<?,?>)building.get("definition")).get("power_outage")).get("simulate_power_outage"));
        assertFalse(((Map<?,?>)building.get("definition")).containsKey("dynamics"));
        assertFalse(((Map<?,?>)building.get("definition")).containsKey("type"));
        assertFalse(building.containsKey("modelAsset"));
        assertFalse(config.containsKey("batteryCapacity"));
        assertThrows(InvocationTargetException.class, () -> prepare.invoke(service, 7L, Map.of("buildingIds", List.of(99))));
        assertThrows(InvocationTargetException.class, () -> prepare.invoke(service, 7L, Map.of("buildingIds", List.of(21, 21))));
        assertThrows(InvocationTargetException.class, () -> prepare.invoke(service, 7L, Map.of("buildingIds", List.of(21), "batteryCapacity", 100)));
    }
    @Test
    void publishRollsBackAndRemovesMovedDirectoryWhenTaskCompletionLosesRaceToCancel() throws Exception {
        Path root = Files.createTempDirectory("ol1-publish-race-");
        try {
            Path datasets = Files.createDirectories(root.resolve("datasets"));
            Path stage = Files.createDirectories(datasets.resolve(".ol1-scenario-task"));
            Files.writeString(stage.resolve("manifest.json"), "{}");

            CommunityManagementService communities = mock(CommunityManagementService.class);
            JdbcTemplate jdbc = mock(JdbcTemplate.class);
            PlatformTransactionManager transactionManager = mock(PlatformTransactionManager.class);
            when(transactionManager.getTransaction(any(TransactionDefinition.class))).thenReturn(new SimpleTransactionStatus());
            when(jdbc.queryForObject(contains("SELECT status"), eq(String.class), eq("task"), eq(7L))).thenReturn("running");
            when(jdbc.query(contains("SELECT building_id"), any(RowMapper.class), eq(7L))).thenReturn(List.of());
            doAnswer(call -> call.<String>getArgument(0).startsWith("UPDATE community_scenario_generation_task SET status='succeeded'") ? 0 : 1)
                    .when(jdbc).update(anyString(), any(Object[].class));
            when(communities.get(7L, true)).thenReturn(Map.of());

            FileResourceProperties files = new FileResourceProperties();
            files.setPythonFilePath(root.toString());
            Ol1ScenarioService service = new Ol1ScenarioService();
            inject(service, "communities", communities);
            inject(service, "jdbc", jdbc);
            inject(service, "mapper", new ObjectMapper());
            inject(service, "files", files);
            inject(service, "transactionManager", transactionManager);

            Map<String,Object> manifest = Map.of(
                    "sourceFiles", Map.of("schema.json", "schema-hash"), "timeSteps", 48,
                    "buildingCount", 3, "contentHash", "content-hash", "scoreStartStep", 24,
                    "scoreEndStepExclusive", 48, "scoreSteps", 24, "chescaCompatible", true);
            Method publish = Ol1ScenarioService.class.getDeclaredMethod("publish", long.class, String.class,
                    String.class, Path.class, Map.class);
            publish.setAccessible(true);

            InvocationTargetException failure = assertThrows(InvocationTargetException.class,
                    () -> publish.invoke(service, 7L, "task", "Scenario", stage, manifest));

            assertInstanceOf(IllegalStateException.class, failure.getCause());
            verify(jdbc).queryForObject(
                    eq("SELECT status FROM community_scenario_generation_task WHERE id=? AND community_id=? FOR UPDATE"),
                    eq(String.class), eq("task"), eq(7L));
            try (var entries = Files.list(datasets)) {
                assertTrue(entries.toList().isEmpty(), "failed publication must remove the moved release directory");
            }
            verify(transactionManager).rollback(any());
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }

    private static void inject(Object target, String name, Object value) throws Exception {
        Field field = Ol1ScenarioService.class.getDeclaredField(name);
        field.setAccessible(true);
        field.set(target, value);
    }
}
