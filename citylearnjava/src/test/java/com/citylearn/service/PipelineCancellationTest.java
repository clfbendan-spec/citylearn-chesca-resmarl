package com.citylearn.service;

import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.PyTaskMapper;
import com.citylearn.entity.PyTask;
import com.citylearn.vo.PyTaskVO;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PipelineCancellationTest {
    @TempDir Path root;

    @ParameterizedTest
    @ValueSource(ints = {0, 3})
    void stoppingParentTerminatesRunningChildAndCancelsWaitingEvaluation(int parentStatus) throws Exception {
        BaseDataService service = spy(new BaseDataService());
        PyTaskMapper mapper = mock(PyTaskMapper.class);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(root.toString());
        ReflectionTestUtils.setField(service, "pyTaskMapper", mapper);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        Map<String, PyTask> rows = new HashMap<>();
        rows.put("cancel-parent", task("cancel-parent", parentStatus, false));
        rows.get("cancel-parent").setType(PyTaskVO.TASK_TYPE_PIPELINE);
        rows.put("cancel-parent-train", task("cancel-parent-train", 0, true));
        rows.put("cancel-parent-eval", task("cancel-parent-eval", PyTaskVO.TASK_STATUS_WAITING, true));
        when(mapper.selectById(anyString())).thenAnswer(call -> rows.get(call.getArgument(0)));
        when(mapper.updateById(any(PyTask.class))).thenAnswer(call -> {
            PyTask update = call.getArgument(0);
            rows.get(update.getId()).setStatus(update.getStatus());
            return 1;
        });
        doReturn(new PyTaskVO()).when(service).getPyTaskResult(anyString());

        Process worker = new ProcessBuilder(javaExecutable(), "-cp", classpath(),
                Worker.class.getName(), "parent").redirectErrorStream(true).start();
        long childPid = Long.parseLong(worker.inputReader().readLine());
        ProcessHandle child = ProcessHandle.of(childPid).orElseThrow();
        @SuppressWarnings("unchecked")
        Map<String, Process> running = (Map<String, Process>)
                ReflectionTestUtils.getField(BaseDataService.class, "RUNNING_PROCESS");
        running.put("cancel-parent-train", worker);
        try {
            service.stopPyTask("cancel-parent");
            assertEquals(3, rows.get("cancel-parent").getStatus());
            assertEquals(3, rows.get("cancel-parent-train").getStatus(),
                    "The running training row must not remain active after parent cancellation");
            assertEquals(3, rows.get("cancel-parent-eval").getStatus(),
                    "Waiting evaluation must not start after cancellation");
            worker.onExit().get(8, TimeUnit.SECONDS);
            child.onExit().get(8, TimeUnit.SECONDS);
            assertFalse(worker.isAlive());
            assertFalse(child.isAlive(), "A task-owned descendant must not survive cancellation");
        } finally {
            child.destroyForcibly();
            worker.destroyForcibly();
            running.remove("cancel-parent-train");
            @SuppressWarnings("unchecked")
            Set<String> stopped = (Set<String>)
                    ReflectionTestUtils.getField(BaseDataService.class, "STOPPED_TASKS");
            stopped.removeAll(rows.keySet());
        }
    }

    private static PyTask task(String id, int status, boolean subtask) {
        PyTask task = new PyTask();
        task.setId(id);
        task.setStatus(status);
        task.setIsSubtask(subtask);
        return task;
    }

    private static String javaExecutable() {
        return Path.of(System.getProperty("java.home"), "bin",
                System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java").toString();
    }

    private static String classpath() {
        return System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
    }

    public static class Worker {
        public static void main(String[] args) throws Exception {
            if ("parent".equals(args[0])) {
                Process child = new ProcessBuilder(javaExecutable(), "-cp", classpath(),
                        Worker.class.getName(), "child").start();
                System.out.println(child.pid());
                System.out.flush();
            }
            Thread.sleep(TimeUnit.MINUTES.toMillis(2));
        }
    }
}
