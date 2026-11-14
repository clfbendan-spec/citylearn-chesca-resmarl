package com.citylearn.service;

import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class DashboardTaskIdentityTest {
    @TempDir Path output;

    @Test void deletedSuccessfulTaskCannotExposeDetailOrTrace() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(output.toString());
        PyTask task = new PyTask();
        task.setId("deleted-eval"); task.setPyId("rules");
        task.setStatus(1); task.setIfDelete(true);
        PyFile file = new PyFile(); file.setId("rules");
        when(tasks.selectById("deleted-eval")).thenReturn(task);
        when(files.selectById("rules")).thenReturn(file);
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        Path directory = output.resolve("outkpis/deleted-eval");
        Files.createDirectories(directory);
        Files.writeString(directory.resolve("exported_kpis.csv"), "KPI,Building_1\ncost_total,0.75\n");
        Files.writeString(directory.resolve("decision_trace.json"),
                "{\"steps\":[{\"step\":0,\"episode\":1,\"buildings\":[]}]}");
        // Remaining artifacts do not make a deleted record available.
        assertAll(
                () -> assertThrows(IllegalArgumentException.class,
                        () -> service.getDashboardSimulationDetail("deleted-eval")),
                () -> assertThrows(IllegalArgumentException.class,
                        () -> service.getDashboardTracePage("deleted-eval", 0, 48, null)));
    }

    @Test void pagedTaskDetailAndFollowupKeepAllSourceStepsOnDisk() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(output.toString());
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        PyTask task = new PyTask();
        task.setId("owned"); task.setPyId("rules"); task.setStatus(1);
        PyFile file = new PyFile(); file.setId("rules");
        when(tasks.selectById("owned")).thenReturn(task);
        when(files.selectById("rules")).thenReturn(file);
        Path directory = output.resolve("outkpis/owned");
        Files.createDirectories(directory);
        var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        var trace = mapper.createObjectNode();
        var steps = trace.putArray("steps");
        for (int step = 10; step < 70; step++)
            steps.addObject().put("episode", 1).put("step", step).putArray("buildings");
        String original = mapper.writeValueAsString(trace);
        Files.writeString(directory.resolve("decision_trace.json"), original);
        var first = service.getDashboardSimulationDetail("owned", true);
        assertEquals(60, first.getTracePage().get("totalSteps"));
        assertEquals(48, mapper.readTree(first.getDecisionTraceJson()).get("steps").size());
        var last = service.getDashboardTracePage("owned", 48, 48, null);
        assertEquals(12, ((Map<?, ?>) last.get("tracePage")).get("returnedSteps"));
        assertEquals(58, mapper.readTree((String) last.get("decisionTraceJson")).at("/steps/0/step").asInt());
        assertEquals(original, Files.readString(directory.resolve("decision_trace.json")));
        assertThrows(IllegalArgumentException.class, () -> service.getDashboardTracePage("missing", 0, 48, null));
    }

    @Test void globalCheckpointCannotMakeMissingTaskModelReady() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(output.toString());
        properties.setPythonFilePath(output.toString());
        Path global = output.resolve("checkpoints/multi_agent_resume");
        Files.createDirectories(global);
        Files.writeString(global.resolve("rllib_checkpoint.json"), "{}");
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        PyTask task = new PyTask();
        task.setId("old-train"); task.setPyId("district"); task.setStatus(1);
        PyFile file = new PyFile(); file.setId("district");
        file.setFileName("District_MARL_train.py"); file.setScriptType("train");
        when(tasks.selectList(any())).thenReturn(List.of(task));
        when(files.selectList(any())).thenReturn(List.of(file));
        List<Map<String,Object>> options = service.getTrainModelTaskList("district");
        assertEquals(1, options.size());
        assertEquals(false, options.get(0).get("modelReady"));
        assertEquals(false, options.get(0).get("modelFromGlobal"));
        String resolved = ReflectionTestUtils.invokeMethod(service, "resolveSubTaskEvalCheckpoint", "old-eval");
        assertEquals(output.resolve("outkpis/old-train/checkpoints/multi_agent_resume").toAbsolutePath().toString(), resolved);
        Path owned = Path.of(resolved);
        Files.createDirectories(owned);
        Files.writeString(owned.resolve("rllib_checkpoint.json"), "{}");
        assertEquals(true, service.getTrainModelTaskList("district").get(0).get("modelReady"));
        assertEquals(resolved, ReflectionTestUtils.invokeMethod(service, "resolveSubTaskEvalCheckpoint", "old-eval"));
    }

    @Test void missingTaskArtifactsNeverBorrowScriptLevelKpis() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        KpisMapper kpis = mock(KpisMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(output.toString());
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "kpisMapper", kpis);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        PyTask task = new PyTask();
        task.setId("old-evaluation"); task.setPyId("shared-script"); task.setStatus(1);
        PyFile file = new PyFile(); file.setId("shared-script");
        when(tasks.selectById("old-evaluation")).thenReturn(task);
        when(files.selectById("shared-script")).thenReturn(file);
        // A script-level lookup is forbidden even if another run has saved KPI rows.
        when(kpis.selectList(any())).thenThrow(new AssertionError("Borrowed another run's KPI source"));
        var detail = service.getDashboardSimulationDetail("old-evaluation");
        assertTrue(detail.getKpiRows().isEmpty());
        assertEquals("", detail.getKpisCsv());
        assertTrue(detail.getArtifactWarnings().stream().anyMatch(s -> s.contains("KPI")));
        Path owned = output.resolve("outkpis/old-evaluation");
        Files.createDirectories(owned);
        String csv = "KPI,Building_1,District\ncost_total,0.75,0.75\n";
        Files.writeString(owned.resolve("exported_kpis.csv"), csv);
        var saved = service.getDashboardSimulationDetail("old-evaluation");
        assertEquals(csv, saved.getKpisCsv());
        assertEquals("0.75", saved.getKpiRows().get(0).get("Building_1"));
    }
}
