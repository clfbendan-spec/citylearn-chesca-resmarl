package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import javax.annotation.PreDestroy;
import javax.annotation.Resource;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BiConsumer;

/** Invokes the shared, dataset-specific temperature model builder. */
@Service
public class DatasetDynamicsService {
    @Resource private FileResourceProperties files;
    @Resource private ObjectMapper mapper;
    @Value("${citylearn.python.executable:python}") private String python;
    @Value("${citylearn.ol1.template-path:}") private String configuredTemplate;
    private final Set<Process> processes = ConcurrentHashMap.newKeySet();

    public Map<String,Object> prepare(Path directory, boolean generate, BiConsumer<Integer,Integer> progress) throws Exception {
        Path root = Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize();
        Path template = configuredTemplate.isBlank()
                ? root.getParent().getParent().resolve("datasets/citylearn_challenge_2023_phase_2_online_evaluation_1")
                : Paths.get(configuredTemplate);
        List<String> command = new ArrayList<>(List.of(python, "-u", root.resolve("dataset_dynamics.py").toString(),
                directory.toAbsolutePath().toString(), "--template", template.toAbsolutePath().toString()));
        if (!generate) command.add("--preview");
        ProcessBuilder builder = new ProcessBuilder(command).directory(root.toFile()).redirectErrorStream(true);
        builder.environment().put("PYTHONIOENCODING", "utf-8");
        Process process = builder.start(); processes.add(process);
        ExecutorService reader = Executors.newSingleThreadExecutor();
        try {
            Future<String> output = reader.submit(() -> {
                String last = "", line;
                StringBuilder tail = new StringBuilder();
                try (BufferedReader input = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                    while ((line = input.readLine()) != null) {
                        tail.append(line).append('\n');
                        if (tail.length() > 8000) tail.delete(0, tail.length() - 8000);
                        if (line.startsWith("{")) {
                            last = line;
                            Map<?,?> event = mapper.readValue(line, Map.class);
                            if (progress != null && event.get("completed") instanceof Number && event.get("total") instanceof Number)
                                progress.accept(((Number)event.get("completed")).intValue(), ((Number)event.get("total")).intValue());
                        }
                    }
                }
                if (process.waitFor() != 0) throw new IllegalArgumentException("温度模型生成失败: " + tail);
                return last;
            });
            return mapper.readValue(output.get(generate ? 7200 : 60, TimeUnit.SECONDS), Map.class);
        } catch (TimeoutException error) {
            throw new IllegalArgumentException("温度模型生成超时，请缩小发布时间范围", error);
        } catch (ExecutionException error) {
            throw new IllegalArgumentException(Objects.toString(error.getCause().getMessage(), "温度模型生成失败"), error);
        } finally {
            if (process.isAlive()) { process.destroyForcibly(); process.waitFor(10, TimeUnit.SECONDS); }
            processes.remove(process); reader.shutdownNow();
        }
    }

    @PreDestroy public void stop() { processes.forEach(Process::destroyForcibly); }
}
