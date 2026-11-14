package com.citylearn.building;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import com.citylearn.common.SessionKeys;
import com.citylearn.vo.UserVO;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class Ol1ScenarioIntegrationTest {
    private static final Path PROJECT_ROOT = Path.of(System.getProperty("user.dir")).getParent();
    private static final Path PYTHON_ROOT = PROJECT_ROOT.resolve("citylearnpy");
    private static final Path TEMPLATE = PROJECT_ROOT.getParent().resolve("datasets/citylearn_challenge_2023_phase_2_online_evaluation_1");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("citylearn.file.python-file-path", () -> PYTHON_ROOT.toString());
        registry.add("citylearn.python.executable", () -> System.getenv().getOrDefault("CITYLEARN_PYTHON", "python"));
        registry.add("citylearn.ol1.template-path", () -> TEMPLATE.toString());
    }

    @Autowired Ol1ScenarioService scenarios;
    @Autowired CommunityManagementService communities;
    @Autowired CommunityPublicationService publications;
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    @Transactional
    void controllerRequiresLoginAndWritePermissionForTaskCreationAndCancellation() throws Exception {
        long community = ((Number) communities.save(null, Map.of("name", "OL1 API permission test")).get("id")).longValue();
        String endpoint = "/web/communities/" + community + "/datasets/generator";
        MockHttpSession reader = session("menu:buildingManagement");
        MockHttpSession writer = session("menu:buildingManagement", "building:write");
        mvc.perform(get(endpoint + "/tasks")).andExpect(jsonPath("$.code").value(401));
        mvc.perform(get(endpoint + "/tasks").session(reader)).andExpect(jsonPath("$.code").value(0));
        mvc.perform(post(endpoint + "/tasks").session(reader).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(403));
        String payload = "{\"name\":\"OL1 API task\",\"configuration\":{\"steps\":48,\"outageMode\":\"off\"}}";
        String response = mvc.perform(post(endpoint + "/tasks").session(writer).contentType("application/json").content(payload))
                .andExpect(jsonPath("$.code").value(0)).andExpect(jsonPath("$.data.status").value("queued"))
                .andReturn().getResponse().getContentAsString();
        String taskId = mapper.readTree(response).path("data").path("id").asText();
        try {
            mvc.perform(post(endpoint + "/tasks/" + taskId + "/cancel").session(reader).contentType("application/json").content("{}"))
                    .andExpect(jsonPath("$.code").value(403));
            mvc.perform(post(endpoint + "/tasks/" + taskId + "/cancel").session(writer).contentType("application/json").content("{}"))
                    .andExpect(jsonPath("$.code").value(0));
            mvc.perform(get(endpoint + "/tasks/" + taskId).session(reader))
                    .andExpect(jsonPath("$.code").value(0)).andExpect(jsonPath("$.data.status").value("cancelled"));
            assertTrue(publications.list(community).isEmpty());
        } finally { deleteTree(PYTHON_ROOT.resolve("outputs/ol1-scenario-tasks").resolve(taskId)); }
    }

    private static MockHttpSession session(String... permissions) {
        UserVO user = new UserVO();
        user.setRole("USER");
        user.setPermissions(java.util.Arrays.asList(permissions));
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionKeys.LOGIN_USER, user);
        session.setAttribute(SessionKeys.LOGIN_PERMS, user.getPermissions());
        return session;
    }

    @Test
    void cancellationStopsRunningGeneratorWithoutPublishingOrLeavingItsStagingFiles() throws Exception {
        long community = ((Number) communities.save(null, Map.of("name", "OL1 cancellation " + UUID.randomUUID())).get("id")).longValue();
        String taskId = null;
        try {
            taskId = scenarios.start(community, Map.of("name", "Cancellation test", "configuration",
                    Map.of("steps", 2208, "outageMode", "off"))).get("id").toString();
            long deadline = System.nanoTime() + java.time.Duration.ofMinutes(2).toNanos();
            Map<String,Object> task;
            do {
                task = scenarios.get(community, taskId);
                if ("runtime_validation".equals(task.get("stage"))) break;
                assertFalse("failed".equals(task.get("status")) || "succeeded".equals(task.get("status")), task.toString());
                Thread.sleep(50);
            } while (System.nanoTime() < deadline);
            assertEquals("runtime_validation", task.get("stage"), "the test must cancel a live generator after it creates staging files");
            String runningTask = taskId;
            Object service = org.springframework.test.util.AopTestUtils.getTargetObject(scenarios);
            Map<?,?> processes = (Map<?,?>) org.springframework.test.util.ReflectionTestUtils.getField(service, "processes");
            Process generator = (Process) processes.get(taskId);
            assertNotNull(generator, "the generator subprocess must be registered before cancellation");
            assertTrue(generator.isAlive(), "the generator subprocess must be confirmed live before cancellation");

            scenarios.cancel(community, taskId);
            deadline = System.nanoTime() + java.time.Duration.ofSeconds(20).toNanos();
            while (generator.isAlive() && System.nanoTime() < deadline) Thread.sleep(50);
            assertFalse(generator.isAlive(), "cancellation must terminate the generator");
            while (processes.containsKey(taskId) && System.nanoTime() < deadline) Thread.sleep(50);
            assertFalse(processes.containsKey(taskId), "the worker must finish cancellation cleanup");
            assertEquals("cancelled", scenarios.get(community, taskId).get("status"));
            assertTrue(publications.list(community).isEmpty(), "cancelled generation must never publish a release");
            try (var entries = Files.list(PYTHON_ROOT.resolve("datasets"))) {
                assertTrue(entries.noneMatch(path -> path.getFileName().toString().contains(runningTask)),
                        "cancellation must remove both the target and Python's random-suffix staging directory");
            }
            assertFalse(Files.exists(PYTHON_ROOT.resolve("outputs/ol1-scenario-tasks").resolve(taskId)),
                    "cancellation must remove its task files after the process has stopped");
        } finally {
            if (taskId != null) {
                String cancelledTask = taskId;
                try {
                    Map<String,Object> task = scenarios.get(community, taskId);
                    if ("queued".equals(task.get("status")) || "running".equals(task.get("status"))) scenarios.cancel(community, taskId);
                } finally {
                    try (var entries = Files.list(PYTHON_ROOT.resolve("datasets"))) {
                        for (Path entry : entries.filter(path -> path.getFileName().toString().contains(cancelledTask)).collect(java.util.stream.Collectors.toList()))
                            deleteTree(entry);
                    }
                    deleteTree(PYTHON_ROOT.resolve("outputs/ol1-scenario-tasks").resolve(taskId));
                }
            }
            communities.delete(community);
        }
    }

    @Test
    void previewsGeneratesValidatesPublishesAndListsImmutableOl1Release() throws Exception {
        assertTrue(Files.isRegularFile(TEMPLATE.resolve("schema.json")));
        long community = ((Number) communities.save(null, Map.of("name", "OL1 integration " + UUID.randomUUID())).get("id")).longValue();
        String releaseId = null;
        String taskId = null;
        try {
            Map<?,?> template = mapper.readValue(TEMPLATE.resolve("schema.json").toFile(), Map.class);
            Map<?,?> definition = (Map<?,?>)((Map<?,?>)template.get("buildings")).get("Building_3");
            Map<String,Object> devices = new java.util.LinkedHashMap<>();
            for (String key : SchemaEquipment.TYPES.keySet()) if (definition.containsKey(key)) devices.put(key, definition.get(key));
            ((Map<String,Object>)((Map<?,?>)devices.get("pv")).get("attributes")).put("nominal_power", 7);
            long building = ((Number)communities.addBuilding(community, Map.of("name", "Building_3", "devices", devices)).get("id")).longValue();
            Map<String,Object> configuration = Map.of("startStep", 24, "steps", 24, "buildingIds", java.util.List.of(building));
            Map<String,Object> preview = scenarios.preview(community, configuration);
            assertEquals(true, preview.get("ready"), preview.toString());
            assertEquals("synthetic_ol1", preview.get("sourceMode"));
            assertEquals(24, ((Number) preview.get("scoreSteps")).intValue());
            assertEquals(1, ((Number) preview.get("buildingCount")).intValue());

            Map<String,Object> task = scenarios.start(community,
                    Map.of("name", "OL1 integration scenario", "configuration", configuration));
            taskId = task.get("id").toString();
            long deadline = System.nanoTime() + java.time.Duration.ofMinutes(3).toNanos();
            do {
                task = scenarios.get(community, taskId);
                String status = task.get("status").toString();
                if ("succeeded".equals(status)) break;
                if ("failed".equals(status) || "cancelled".equals(status))
                    fail("Scenario generation ended as " + status + ": " + task.get("error") + "\n" + task.get("log"));
                Thread.sleep(250);
            } while (System.nanoTime() < deadline);
            assertEquals("succeeded", task.get("status"), "scenario generation exceeded its integration-test deadline");

            Map<?,?> result = (Map<?,?>) task.get("result");
            String publishedReleaseId = result.get("id").toString();
            releaseId = publishedReleaseId;
            assertNotNull(result.get("contentHash"));
            Map<String,Object> release = publications.list(community).stream()
                    .filter(row -> publishedReleaseId.equals(row.get("id"))).findFirst().orElseThrow();
            assertEquals("synthetic_ol1", release.get("sourceMode"));
            assertEquals(24, ((Number) release.get("scoreStartStep")).intValue());
            assertEquals(48, ((Number) release.get("scoreEndStepExclusive")).intValue());
            Path packageDirectory = PYTHON_ROOT.resolve("datasets").resolve(result.get("schemaKey").toString());
            assertTrue(Files.isRegularFile(packageDirectory.resolve("manifest.json")));
            assertTrue(Files.isRegularFile(packageDirectory.resolve("validation_report.json")));
            Map<?,?> exported = mapper.readValue(packageDirectory.resolve("schema.json").toFile(), Map.class);
            Map<?,?> exportedBuildings = (Map<?,?>)exported.get("buildings");
            assertEquals(1, exportedBuildings.size());
            Map<?,?> exportedBuilding = (Map<?,?>)exportedBuildings.get("Building_1");
            assertEquals(7, ((Number)((Map<?,?>)((Map<?,?>)exportedBuilding.get("pv")).get("attributes")).get("nominal_power")).intValue());
            assertArrayEquals(Files.readAllBytes(TEMPLATE.resolve("Building_3.pth")),
                    Files.readAllBytes(packageDirectory.resolve(((Map<?,?>)((Map<?,?>)exportedBuilding.get("dynamics")).get("attributes")).get("filename").toString())));
        } finally {
            if (taskId != null) {
                try {
                    Map<String,Object> task = scenarios.get(community, taskId);
                    if ("queued".equals(task.get("status")) || "running".equals(task.get("status")))
                        scenarios.cancel(community, taskId);
                    if (releaseId == null && task.get("result") instanceof Map && ((Map<?,?>) task.get("result")).get("id") != null)
                        releaseId = ((Map<?,?>) task.get("result")).get("id").toString();
                } catch (RuntimeException ignored) { }
            }
            if (releaseId != null) {
                try { publications.delete(community, releaseId); }
                catch (RuntimeException ignored) { }
                Path datasets = PYTHON_ROOT.resolve("datasets").toAbsolutePath().normalize();
                Path generatedPackage = datasets.resolve("community_" + releaseId.replace("-", "")).normalize();
                if (!generatedPackage.getParent().equals(datasets) || !generatedPackage.getFileName().toString().matches("community_[a-f0-9]{32}"))
                    throw new IllegalStateException("Refusing to clean an unexpected OL1 integration package path");
                deleteTree(generatedPackage);
                assertFalse(Files.exists(generatedPackage), "the test's generated OL1 package must be removed");
            }
            communities.delete(community);
            if (taskId != null) {
                Path taskDirectory = PYTHON_ROOT.resolve("outputs/ol1-scenario-tasks").resolve(taskId);
                deleteTree(taskDirectory);
            }
        }
    }

    private static void deleteTree(Path directory) throws Exception {
        if (!Files.exists(directory)) return;
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
        }
    }
}
