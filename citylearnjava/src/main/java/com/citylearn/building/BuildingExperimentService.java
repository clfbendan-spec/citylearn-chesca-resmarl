package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import javax.annotation.Resource;
import javax.annotation.PreDestroy;
import org.springframework.context.event.EventListener;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;

@Service
public class BuildingExperimentService {
    @Resource private BuildingIngestionService buildings;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;
    @Resource(name = "pythonTaskExecutor") private Executor executor;
    @Value("${citylearn.python.executable:python}") private String python;
    private final Map<String, Process> processes = new ConcurrentHashMap<>();

    public List<Map<String, Object>> list(long id) {
        buildings.get(id, false);
        List<Map<String, Object>> rows = jdbc.queryForList("SELECT r.*,v.name AS versionName FROM building_experiment_run r"
                + " JOIN building_dataset_version v ON v.id=r.version_id WHERE r.building_id=? ORDER BY r.create_time DESC LIMIT 100", id);
        for (Map<String, Object> row : rows) {
            try {
                row.put("config", mapper.readValue(row.remove("config_json").toString(), Map.class));
                Object result = row.remove("result_json");
                row.put("result", result == null ? null : mapper.readValue(result.toString(), Map.class));
                Path dir = runDirectory(row.get("id").toString());
                Path progress = dir.resolve("progress.json");
                if (Files.isRegularFile(progress)) row.put("progress", mapper.readValue(progress.toFile(), Map.class));
                Path log = dir.resolve("run.log");
                if (Files.isRegularFile(log)) {
                    // Read only the tail; long training logs must not grow every polling response.
                    try (java.io.RandomAccessFile stream = new java.io.RandomAccessFile(log.toFile(), "r")) {
                        long size = stream.length(); stream.seek(Math.max(0, size - 8000));
                        byte[] tail = new byte[(int) Math.min(size, 8000)]; stream.readFully(tail);
                        row.put("log", new String(tail, java.nio.charset.StandardCharsets.UTF_8));
                    }
                }
            } catch (Exception e) { row.put("inspectionError", e.getMessage()); }
        }
        return rows;
    }

    @Transactional(rollbackFor = Exception.class)
    public String start(long buildingId, Map<String, Object> request) throws Exception {
        buildings.get(buildingId, true);
        String version = String.valueOf(request.get("versionId"));
        Path source = buildings.versionDirectory(buildingId, version);
        requireBatteryAction(mapper.readValue(source.resolve("schema.json").toFile(), Map.class));
        String mode = String.valueOf(request.get("mode"));
        if (!List.of("train", "evaluation").contains(mode)) throw new IllegalArgumentException("无效实验类型");
        String purpose = jdbc.queryForObject("SELECT purpose FROM building_dataset_version WHERE id=?", String.class, version);
        if ("train".equals(mode) && !"train".equals(purpose)) throw new IllegalArgumentException("训练只能使用训练版本");
        if ("evaluation".equals(mode) && "train".equals(purpose)) throw new IllegalArgumentException("独立评估请选择验证或评估版本");
        int steps = Integer.parseInt(request.getOrDefault("steps", 10000).toString());
        int seed = Integer.parseInt(request.getOrDefault("seed", 2023).toString());
        if (steps < 32 || steps > 1000000 || seed < 0) throw new IllegalArgumentException("训练步数范围 32–1000000，seed 应为非负数");
        jdbc.queryForObject("SELECT id FROM building_experiment_lock WHERE id=1 FOR UPDATE", Integer.class);
        if (jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run WHERE status IN ('queued','running')", Integer.class) >= 2)
            throw new IllegalArgumentException("已有两个实验排队或执行，请等待完成");
        String id = UUID.randomUUID().toString();
        List<String> command = new ArrayList<>(List.of(python, "-u",
                Paths.get(files.getPythonFilePath()).toAbsolutePath().resolve("building_experiment.py").toString(),
                "--schema", source.resolve("schema.json").toString(), "--output-dir", runDirectory(id).toString(),
                "--mode", mode, "--steps", String.valueOf(steps), "--seed", String.valueOf(seed)));
        String modelId = Objects.toString(request.get("modelRunId"), "");
        if (!modelId.isEmpty()) {
            Integer found = jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run WHERE id=? AND building_id=?"
                    + " AND mode='train' AND status='succeeded'", Integer.class, modelId, buildingId);
            if (found == null || found != 1 || !"evaluation".equals(mode)) throw new IllegalArgumentException("请选择同建筑成功训练的模型");
            Map<String, Object> trained = jdbc.queryForMap("SELECT v.start_time,v.end_time FROM building_dataset_version v"
                    + " JOIN building_experiment_run r ON r.version_id=v.id WHERE r.id=?", modelId);
            Map<String, Object> evaluated = jdbc.queryForMap("SELECT start_time,end_time FROM building_dataset_version WHERE id=?", version);
            requireDisjoint(trained.get("start_time").toString(), trained.get("end_time").toString(),
                    evaluated.get("start_time").toString(), evaluated.get("end_time").toString());
            command.add("--model"); command.add(runDirectory(modelId).resolve("model.zip").toString());
        }
        Files.createDirectories(runDirectory(id));
        jdbc.update("INSERT INTO building_experiment_run(id,building_id,version_id,mode,status,config_json) VALUES (?,?,?,?,'queued',?)",
                id, buildingId, version, mode, mapper.writeValueAsString(Map.of("steps", steps, "seed", seed, "modelRunId", modelId,
                        "versionId", version, "evaluation", "chronological held-out 20% for training; full range for standalone evaluation")));
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                try { executor.execute(() -> execute(id, command)); }
                catch (RuntimeException e) { jdbc.update("UPDATE building_experiment_run SET status='failed',error_message=? WHERE id=?", e.getMessage(), id); }
            }
        });
        return id;
    }
    static void requireBatteryAction(Map<?,?> schema) {
        Object actions = schema.get("actions");
        Object battery = actions instanceof Map ? ((Map<?,?>)actions).get("electrical_storage") : null;
        if (!(battery instanceof Map) || !Boolean.TRUE.equals(((Map<?,?>)battery).get("active")))
            throw new IllegalArgumentException("此数据版本未配置储能电池，不能运行电池调度训练或评估；建筑仍可接入和查看数据");
        for(Object key:((Map<?,?>)actions).keySet()) if(!"electrical_storage".equals(key) && ((Map<?,?>)((Map<?,?>)actions).get(key)).get("active")==Boolean.TRUE)
            throw new IllegalArgumentException("此入口仅支持电池动作；多储能数据集请使用匹配的训练算法");
    }
    private void execute(String id, List<String> command) {
        if (jdbc.update("UPDATE building_experiment_run SET status='running' WHERE id=? AND status='queued'", id) != 1) return;
        try {
            ProcessBuilder builder = new ProcessBuilder(command).directory(Paths.get(files.getPythonFilePath()).toFile())
                    .redirectErrorStream(true).redirectOutput(runDirectory(id).resolve("run.log").toFile());
            builder.environment().put("PYTHONIOENCODING", "utf-8");
            builder.environment().put("PYTHONHASHSEED", "0");
            Process process = builder.start(); processes.put(id, process);
            String status = jdbc.queryForObject("SELECT status FROM building_experiment_run WHERE id=?", String.class, id);
            if ("cancelled".equals(status)) process.destroyForcibly();
            if (!process.waitFor(12, TimeUnit.HOURS)) { process.destroyForcibly(); throw new IllegalStateException("实验超过 12 小时"); }
            if (process.exitValue() != 0) throw new IllegalStateException("Python 退出码 " + process.exitValue() + "，请查看实验日志");
            String result = Files.readString(runDirectory(id).resolve("result.json"));
            jdbc.update("UPDATE building_experiment_run SET status='succeeded',result_json=? WHERE id=? AND status='running'", result, id);
        } catch (Exception e) {
            jdbc.update("UPDATE building_experiment_run SET status='failed',error_message=? WHERE id=? AND status='running'", e.getMessage(), id);
        } finally { processes.remove(id); }
    }
    public void cancel(long buildingId, String id) {
        buildings.get(buildingId, false);
        int count = jdbc.update("UPDATE building_experiment_run SET status='cancelled' WHERE id=? AND building_id=?"
                + " AND status IN ('queued','running')", id, buildingId);
        if (count == 0) throw new IllegalArgumentException("实验不存在或已结束");
        Process process = processes.get(id);
        if (process != null) process.destroyForcibly();
    }
    static void requireDisjoint(String trainingStart, String trainingEnd, String evaluationStart, String evaluationEnd) {
        if (Instant.parse(trainingStart).isBefore(Instant.parse(evaluationEnd))
                && Instant.parse(evaluationStart).isBefore(Instant.parse(trainingEnd)))
            throw new IllegalArgumentException("独立评估时间不得与模型训练版本重叠");
    }
    @EventListener(WebServerInitializedEvent.class)
    public void recoverInterruptedRuns() {
        jdbc.update("UPDATE building_experiment_run SET status='failed',error_message='服务重启，实验已中断，请重新提交'"
                + " WHERE status IN ('queued','running')");
    }
    @PreDestroy
    public void stopProcesses() {
        processes.forEach((id, process) -> {
            process.destroyForcibly();
            jdbc.update("UPDATE building_experiment_run SET status='failed',error_message='服务关闭，实验已中断'"
                    + " WHERE id=? AND status='running'", id);
        });
    }
    private Path runDirectory(String id) {
        if (!id.matches("[a-f0-9-]{36}")) throw new IllegalArgumentException("无效实验编号");
        return Paths.get(files.getPythonFilePath()).toAbsolutePath().resolve("outputs/building-experiments").resolve(id);
    }
}
