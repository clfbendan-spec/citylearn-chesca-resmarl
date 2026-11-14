package com.citylearn.service;

import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.*;
import com.citylearn.entity.*;
import com.citylearn.param.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Path;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class DirectEvaluationPipelineTest {
    @TempDir Path root;

    @Test void ruleAndBaselinePipelinesCreateOnlyEvaluationWithoutModelParameter() {
        for (String script : List.of("CHESCA.py", "NOCONTROL.py")) {
            BaseDataService service = new BaseDataService();
            PyTaskMapper tasks = mock(PyTaskMapper.class);
            PyFileMapper files = mock(PyFileMapper.class);
            FileResourceProperties properties = new FileResourceProperties();
            properties.setOutFilePath(root.resolve(script).toString());
            ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
            ReflectionTestUtils.setField(service, "pyFileMapper", files);
            ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
            PyFile file = new PyFile(); file.setId("eval"); file.setFileName(script);
            file.setScriptType(script.equals("NOCONTROL.py") ? "both" : "eval");
            when(files.selectById("eval")).thenReturn(file);
            List<PyTask> saved = new ArrayList<>();
            when(tasks.insert(any(PyTask.class))).thenAnswer(invocation -> {
                saved.add(invocation.getArgument(0)); return 1;
            });
            PipelineStepConfig step = new PipelineStepConfig();
            step.setPyId("eval");
            // The server must derive capabilities from its file registration, not this name.
            step.setScriptName("untrusted-client-name.py");
            PipelineTaskParam param = new PipelineTaskParam();
            param.setTaskName("Direct evaluation");
            param.setEvalConfig(step);
            service.createPipelineTask(param);
            assertEquals(2, saved.size());
            PyTask evaluation = saved.stream().filter(t -> t.getId().endsWith("-eval")).findFirst().orElseThrow();
            assertFalse(saved.stream().anyMatch(t -> t.getId().endsWith("-train")));
            assertFalse(evaluation.getConfig().contains("train-task-id"));
            assertTrue(evaluation.getConfig().contains(script));
        }
    }

    @Test void learnedPolicyCannotSkipTrainingBySpoofingRuleScriptName() {
        BaseDataService service = new BaseDataService();
        PyFileMapper files = mock(PyFileMapper.class);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        PyFile file = new PyFile(); file.setId("learned"); file.setFileName("AACMADRL_eval.py"); file.setScriptType("eval");
        when(files.selectById("learned")).thenReturn(file);
        PipelineStepConfig step = new PipelineStepConfig();
        step.setPyId("learned"); step.setScriptName("CHESCA.py");
        PipelineTaskParam param = new PipelineTaskParam();
        param.setTaskName("Must require training"); param.setEvalConfig(step);
        assertThrows(RuntimeException.class, () -> service.createPipelineTask(param));
    }

    @Test void frozenAacAnchorCreatesOnlyEvaluationAndRejectsConflictingTrainingSource() {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(root.toString());
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "algorithmParamConfigMapper", mock(AlgorithmParamConfigMapper.class));
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        PyFile file = new PyFile();
        file.setId("aac"); file.setFileName("AACMADRL_eval.py"); file.setScriptType("eval");
        when(files.selectById("aac")).thenReturn(file);
        List<PyTask> saved = new ArrayList<>();
        when(tasks.insert(any(PyTask.class))).thenAnswer(invocation -> {
            saved.add(invocation.getArgument(0)); return 1;
        });
        PipelineStepConfig step = new PipelineStepConfig();
        step.setPyId("aac"); step.setScriptName("untrusted.py");
        step.setConfig("[{\"type\":\"alone\",\"params\":[{\"id\":\"anchor\",\"param_name\":\"frozen-anchor\",\"value\":\"on\"}]}]");
        PipelineTaskParam param = new PipelineTaskParam();
        param.setTaskName("Frozen Anchor"); param.setEvalConfig(step);
        service.createPipelineTask(param);
        assertEquals(2, saved.size());
        assertFalse(saved.stream().anyMatch(t -> t.getId().endsWith("-train")));
        assertFalse(saved.get(1).getConfig().contains("train-task-id"));
        step.setConfig("[{\"type\":\"alone\",\"params\":[{\"id\":\"anchor\",\"param_name\":\"frozen-anchor\",\"value\":\"on\"},"
                + "{\"id\":\"source\",\"param_name\":\"train-task-id\",\"value\":\"another-task\"}]}]");
        assertThrows(RuntimeException.class, () -> service.createPipelineTask(param));
    }
}
