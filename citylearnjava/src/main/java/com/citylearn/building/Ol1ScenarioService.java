package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.annotation.PreDestroy;
import javax.annotation.Resource;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

@Service
public class Ol1ScenarioService {
    private static final List<String> BUILDINGS = List.of("Building_1", "Building_2", "Building_3");
    private static final String TEMPLATE_ID = "citylearn_challenge_2023_phase_2_online_evaluation_1";
    @Resource private CommunityManagementService communities;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;
    @Resource private PlatformTransactionManager transactionManager;
    @Resource(name = "pythonTaskExecutor") private Executor executor;
    @Value("$"+"{citylearn.python.executable:python}") private String python;
    @Value("$"+"{citylearn.ol1.template-path:}") private String configuredTemplate;
    private final Map<String, Process> processes = new ConcurrentHashMap<>();
    private volatile boolean stopping;

    @EventListener(WebServerInitializedEvent.class)
    public void recoverInterruptedTasks() {
        jdbc.update("UPDATE community_scenario_generation_task SET status='failed',stage='interrupted',error_message='服务重启，生成已中断，请重新提交',end_time=CURRENT_TIMESTAMP WHERE status IN ('queued','running')");
    }

    public Map<String,Object> preview(long community, Map<String,Object> config) throws Exception {
        communities.get(community, false);
        config = prepareConfiguration(community, config);
        validateConfig(config);
        Path temporary = Files.createTempFile("ol1-preview-", ".json");
        try {
            mapper.writeValue(temporary.toFile(), config);
            List<String> command = List.of(python, "-u", script().toString(), "preview", "--template", template().toString(), "--config", temporary.toString());
            Map<String,Object> result = runPreview(command);
            result.put("ready", true);
            result.put("runtimeRequiredBeforePublish", true);
            return result;
        } catch (Exception error) {
            return Map.of("ready", false, "blocker", Objects.toString(error.getMessage(), "OL1 预览失败"));
        } finally { Files.deleteIfExists(temporary); }
    }

    public List<Map<String,Object>> list(long community) {
        communities.get(community, false);
        return jdbc.queryForList("SELECT id,status,stage,completed,total,error_message AS error,create_time AS createTime,start_time AS startTime,end_time AS endTime,config_json FROM community_scenario_generation_task WHERE community_id=? ORDER BY create_time DESC LIMIT 50", community)
                .stream().map(row -> { try { row.put("config", mapper.readValue(Objects.toString(row.remove("config_json"), "{}"), Map.class)); } catch (Exception ignored) {} return row; }).toList();
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String,Object> start(long community, Map<String,Object> request) throws Exception {
        communities.get(community, true);
        String name = Objects.toString(request.get("name"), "").trim();
        if (name.isEmpty() || name.length() > 160) throw new IllegalArgumentException("请填写 1–160 个字符的版本名称");
        Object raw = request.getOrDefault("configuration", Map.of());
        if (!(raw instanceof Map)) throw new IllegalArgumentException("场景配置必须为对象");
        @SuppressWarnings("unchecked") Map<String,Object> config = prepareConfiguration(community, (Map<String,Object>) raw);
        validateConfig(config);
        if (stopping) throw new IllegalArgumentException("服务正在停止");
        if (jdbc.queryForObject("SELECT COUNT(*) FROM community_scenario_generation_task WHERE status IN ('queued','running')", Integer.class) >= 2)
            throw new IllegalArgumentException("已有两个场景生成任务排队或执行，请稍后重试");
        String id = UUID.randomUUID().toString();
        Path taskDir = taskDirectory(id);
        Files.createDirectories(taskDir);
        mapper.writeValue(taskDir.resolve("configuration.json").toFile(), config);
        jdbc.update("INSERT INTO community_scenario_generation_task(id,community_id,status,stage,config_json) VALUES (?,?,'queued','queued',?)",
                id, community, mapper.writeValueAsString(Map.of("name", name, "configuration", config, "templateId", TEMPLATE_ID)));
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                try { executor.execute(() -> execute(id, community, name, config)); }
                catch (RuntimeException error) { fail(id, "生成队列提交失败：" + error.getMessage()); }
            }
        });
        return get(community, id);
    }

    public Map<String,Object> get(long community, String id) {
        communities.get(community, false);
        List<Map<String,Object>> rows = jdbc.queryForList("SELECT id,status,stage,completed,total,error_message AS error,create_time AS createTime,start_time AS startTime,end_time AS endTime,config_json,result_json FROM community_scenario_generation_task WHERE community_id=? AND id=?", community, id);
        if (rows.isEmpty()) throw new IllegalArgumentException("模拟场景任务不属于该社区");
        Map<String,Object> row = rows.get(0);
        try {
            row.put("config", mapper.readValue(Objects.toString(row.remove("config_json"), "{}"), Map.class));
            String result = Objects.toString(row.remove("result_json"), "");
            if (!result.isEmpty()) row.put("result", mapper.readValue(result, Map.class));
        } catch (Exception error) { row.put("resultWarning", "任务结果暂不可读"); }
        Path log = taskDirectory(id).resolve("run.log");
        if (Files.isRegularFile(log)) try {
            byte[] bytes = Files.readAllBytes(log);
            int offset = Math.max(0, bytes.length - 8000);
            row.put("log", new String(bytes, offset, bytes.length - offset, StandardCharsets.UTF_8));
        } catch (Exception ignored) {}
        return row;
    }

    @Transactional
    public void cancel(long community, String id) {
        get(community, id);
        if (jdbc.update("UPDATE community_scenario_generation_task SET status='cancelled',stage='cancelled',end_time=CURRENT_TIMESTAMP WHERE id=? AND community_id=? AND status IN ('queued','running')", id, community) != 1)
            throw new IllegalArgumentException("生成任务已结束，不能取消");
        Process process = processes.get(id);
        if (process != null) {
            process.destroyForcibly();
            try {
                if (!process.waitFor(10, TimeUnit.SECONDS)) throw new IllegalStateException("生成进程尚未停止，请稍后查看任务状态");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("等待生成进程停止时被中断", error);
            }
        }
        removeTree(taskDirectory(id));
        removeGenerationFiles(id);
    }

    private void execute(String id, long community, String name, Map<String,Object> config) {
        if (stopping || jdbc.update("UPDATE community_scenario_generation_task SET status='running',stage='generating',start_time=CURRENT_TIMESTAMP WHERE id=? AND status='queued'", id) != 1) return;
        Process process = null;
        Path stage = stagingDirectory(id);
        try {
            Files.createDirectories(stage.getParent());
            Path configPath = taskDirectory(id).resolve("configuration.json");
            List<String> command = List.of(python, "-u", script().toString(), "generate", "--template", template().toString(),
                    "--output", stage.toString(), "--config", configPath.toString());
            ProcessBuilder builder = new ProcessBuilder(command).directory(pythonRoot().toFile()).redirectErrorStream(true);
            builder.environment().put("PYTHONIOENCODING", "utf-8");
            builder.environment().put("PYTHONHASHSEED", "0");
            builder.environment().put("OMP_NUM_THREADS", "1");
            builder.environment().put("MKL_NUM_THREADS", "1");
            process = builder.start();
            processes.put(id, process);
            if (!"running".equals(jdbc.queryForObject("SELECT status FROM community_scenario_generation_task WHERE id=?", String.class, id))) {
                process.destroyForcibly();
                process.waitFor(10, TimeUnit.SECONDS);
                return;
            }
            Process runningProcess = process;
            CompletableFuture<String> output = CompletableFuture.supplyAsync(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(runningProcess.getInputStream(), StandardCharsets.UTF_8));
                     java.io.BufferedWriter log = Files.newBufferedWriter(taskDirectory(id).resolve("run.log"), StandardCharsets.UTF_8,
                             StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
                    String line, finalLine = null;
                    while ((line = reader.readLine()) != null) {
                        log.write(line); log.newLine(); log.flush();
                        try {
                            Map<String,Object> event = mapper.readValue(line, Map.class);
                            if (event.containsKey("stage") && !event.containsKey("contentHash")) {
                                String stageName = Objects.toString(event.get("stage"), "generating");
                                int done = ((Number) event.getOrDefault("done", 0)).intValue();
                                int total = ((Number) event.getOrDefault("total", 0)).intValue();
                                jdbc.update("UPDATE community_scenario_generation_task SET stage=?,completed=?,total=? WHERE id=? AND status='running'",
                                        stageName, done, total, id);
                            } else finalLine = line;
                        } catch (Exception ignored) { }
                    }
                    return finalLine;
                } catch (Exception error) { throw new CompletionException(error); }
            });
            if (!process.waitFor(2, TimeUnit.HOURS)) {
                process.destroyForcibly();
                process.waitFor(10, TimeUnit.SECONDS);
                throw new IllegalStateException("模拟场景生成超过两小时限制");
            }
            String finalLine = output.get(15, TimeUnit.SECONDS);
            if (process.exitValue() != 0 || finalLine == null) throw new IllegalStateException("CityLearn 场景生成或运行验证失败，请查看任务日志");
            Map<String,Object> manifest = mapper.readValue(finalLine, Map.class);
            if (!Boolean.TRUE.equals(manifest.get("readyForEvaluation")) || !"passed".equals(manifest.get("runtimeValidation")))
                throw new IllegalStateException("运行验证未通过，拒绝发布");
            // A valid CityLearn package may use equipment/actions outside CHESCA's contract.
            // Keep its compatibility flag instead of discarding the generated dataset.
            publish(community, id, name, stage, manifest);
        } catch (Exception error) {
            fail(id, Objects.toString(error.getMessage(), "模拟场景生成失败"));
        } finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
                try { process.waitFor(10, TimeUnit.SECONDS); }
                catch (InterruptedException error) { Thread.currentThread().interrupt(); }
            }
            if (process == null || !process.isAlive()) removeGenerationFiles(id);
            try {
                if ("cancelled".equals(jdbc.queryForObject("SELECT status FROM community_scenario_generation_task WHERE id=?", String.class, id)))
                    removeTree(taskDirectory(id));
            } finally { processes.remove(id); }
        }
    }

    private void publish(long community, String taskId, String name, Path stage, Map<String,Object> manifest) throws Exception {
        String release = UUID.randomUUID().toString(), key = "community_" + release.replace("-", "");
        Path datasets = pythonRoot().resolve("datasets").normalize();
        Path target = datasets.resolve(key);
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);
        boolean[] moved = {false};
        try {
            transaction.execute(status -> {
                try {
                    communities.get(community, true);
                    if (!"running".equals(jdbc.queryForObject("SELECT status FROM community_scenario_generation_task WHERE id=? AND community_id=? FOR UPDATE", String.class, taskId, community)))
                        throw new IllegalStateException("场景生成任务已取消或结束");
                    if (!Files.isDirectory(stage) || Files.exists(target)) throw new IllegalStateException("场景发布目录无效或已存在");
                    Files.move(stage, target, StandardCopyOption.ATOMIC_MOVE);
                    moved[0] = true;
                    List<Long> owner = jdbc.query("SELECT building_id FROM community_building WHERE community_id=? ORDER BY building_id LIMIT 1", (rs, n) -> rs.getLong(1), community);
                    Map<String,Object> source = Map.of("sourceMode", "synthetic_ol1", "templateId", TEMPLATE_ID,
                            "templateHash", mapper.convertValue(manifest.get("sourceFiles"), Map.class).get("schema.json"),
                            "buildingId", owner.isEmpty() ? 0L : owner.get(0), "contentHash", manifest.get("contentHash"),
                            "sourceStepStart", 0, "scoreStartStep", manifest.get("scoreStartStep"),
                            "scoreEndStepExclusive", manifest.get("scoreEndStepExclusive"));
                    List<Map<String,Object>> provenance = new ArrayList<>();
                    Map<?,?> configuration = manifest.get("configuration") instanceof Map ? (Map<?,?>)manifest.get("configuration") : Map.of();
                    Object managed = configuration.get("managedBuildings");
                    if (managed instanceof List && !((List<?>)managed).isEmpty()) {
                        for (Object entry : (List<?>)managed) {
                            Map<?,?> building = (Map<?,?>)entry;
                            Map<String,Object> row = new LinkedHashMap<>(source);
                            row.put("buildingId", building.get("id")); row.put("buildingName", building.get("name"));
                            row.put("prototype", building.get("prototype")); row.put("buildingKey", "Building_" + (provenance.size() + 1));
                            provenance.add(row);
                        }
                    } else provenance.add(source);
                    int steps = ((Number)manifest.get("timeSteps")).intValue();
                    int count = ((Number)manifest.get("buildingCount")).intValue();
                    jdbc.update("INSERT INTO community_dataset_release(id,schema_key,name,start_time,end_time,time_steps,building_count,sources_json,content_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                            release, key, name, "source-step:0", "source-step:" + steps, steps, count, mapper.writeValueAsString(provenance), manifest.get("contentHash"));
                    jdbc.update("INSERT INTO community_dataset_owner(release_id,community_id) VALUES (?,?)", release, community);
                    jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled,sort_order,description) VALUES (?,?,?,?,?,?,1,220,?)",
                            key, name, "datasets/" + key, count, steps, Boolean.TRUE.equals(manifest.get("chescaCompatible")) ? 1 : 0,
                            "CityLearn OL1 simulated scenario · " + community + " · " + release);
                    Map<String,Object> result = Map.of("id", release, "schemaKey", key, "name", name, "buildingCount", count, "timeSteps", steps,
                            "sourceMode", "synthetic_ol1", "sourceStartStep", 0, "scoreStartStep", manifest.get("scoreStartStep"),
                            "scoreSteps", manifest.get("scoreSteps"), "contentHash", manifest.get("contentHash"));
                    if (jdbc.update("UPDATE community_scenario_generation_task SET status='succeeded',stage='published',completed=1,total=1,result_json=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status='running'",
                            mapper.writeValueAsString(result), taskId) != 1)
                        throw new IllegalStateException("场景生成任务已取消，拒绝发布");
                    return null;
                } catch (Exception error) { status.setRollbackOnly(); throw new IllegalStateException(error); }
            });
        } catch (Exception error) { if (moved[0]) removeTree(target); throw error; }
    }

    private Map<String,Object> runPreview(List<String> command) throws Exception {
        Process process = new ProcessBuilder(command).directory(pythonRoot().toFile()).redirectErrorStream(true).start();
        CompletableFuture<String> output = CompletableFuture.supplyAsync(() -> {
            try { return new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8); }
            catch (Exception error) { throw new CompletionException(error); }
        });
        if (!process.waitFor(40, TimeUnit.SECONDS)) { process.destroyForcibly(); throw new IllegalArgumentException("OL1 预览超时"); }
        String text = output.get(5, TimeUnit.SECONDS);
        if (process.exitValue() != 0) throw new IllegalArgumentException(text.length() > 1200 ? text.substring(text.length() - 1200) : text);
        return mapper.readValue(text.lines().reduce((a,b) -> b).orElseThrow(), Map.class);
    }

    private void validateConfig(Map<String,Object> config) {
        if (config.containsKey("managedBuildings")) return;
        Object selected = config.getOrDefault("buildings", BUILDINGS);
        if (!(selected instanceof List) || !BUILDINGS.equals(selected)) throw new IllegalArgumentException("当前版本需完整使用 OL1 三栋原型，避免 CHESCA 建筑与模型映射失配");
    }
    private Map<String,Object> prepareConfiguration(long community, Map<String,Object> input) throws Exception {
        if (!input.containsKey("buildingIds")) {
            if (input.containsKey("managedBuildings") || input.containsKey("community"))
                throw new IllegalArgumentException("建筑与社区配置必须由系统读取");
            return new LinkedHashMap<>(input);
        }
        if (!Set.of("buildingIds", "startStep", "steps").containsAll(input.keySet()))
            throw new IllegalArgumentException("模拟数据直接使用建筑与社区配置，不支持单独覆盖设备参数");
        if (!(input.get("buildingIds") instanceof List) || ((List<?>)input.get("buildingIds")).isEmpty())
            throw new IllegalArgumentException("请至少选择一栋社区建筑");
        Map<String,Object> settings = communities.get(community, false);
        if (!"3600".equals(Objects.toString(settings.get("intervalSeconds"))))
            throw new IllegalArgumentException("OL1 模拟数据要求社区采样周期为一小时");
        List<Map<String,Object>> owned = communities.buildings(community);
        Map<?,?> saved = settings.get("configuration") instanceof Map ? (Map<?,?>)settings.get("configuration") : Map.of();
        Map<?,?> local = saved.get("buildings") instanceof Map ? (Map<?,?>)saved.get("buildings") : Map.of();
        List<Map<String,Object>> selected = new ArrayList<>();
        Set<Long> seen = new HashSet<>();
        for (Object value : (List<?>)input.get("buildingIds")) {
            long id;
            try { id = Long.parseLong(value.toString()); } catch (RuntimeException error) { throw new IllegalArgumentException("建筑ID无效"); }
            if (!seen.add(id)) throw new IllegalArgumentException("不能重复选择建筑");
            Map<String,Object> building = owned.stream().filter(row -> ((Number)row.get("id")).longValue() == id).findFirst()
                    .orElseThrow(() -> new IllegalArgumentException("建筑不属于当前社区或已删除"));
            Map<String,Object> entry = new LinkedHashMap<>();
            entry.put("id", id); entry.put("name", building.get("name"));
            String name = Objects.toString(building.get("name"), "");
            // Keep a building's prototype stable when only a subset is selected.
            List<Long> stableIds = owned.stream().map(row -> ((Number)row.get("id")).longValue()).sorted().toList();
            entry.put("prototype", BUILDINGS.contains(name) ? name : BUILDINGS.get(stableIds.indexOf(id) % BUILDINGS.size()));
            if (local.get(Long.toString(id)) instanceof Map) {
                Map<?,?> definition = (Map<?,?>)local.get(Long.toString(id));
                Map<String,Object> overrides = new LinkedHashMap<>();
                // Simulated data always retains the Online1 prototype's dynamics.
                for (String key : List.of("power_outage", "inactive_actions", "inactive_observations"))
                    if (definition.containsKey(key)) overrides.put(key, definition.get(key));
                entry.put("definition", overrides);
            }
            if (building.containsKey("devices")) entry.put("devices", SchemaEquipment.normalize(building.get("devices")));
            else {
                // Older buildings store only scalar equipment attributes.
                Map<String,Object> devices = new LinkedHashMap<>();
                devices.put("electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "autosize", false,
                        "attributes", Map.of("capacity", building.getOrDefault("batteryCapacity", 6.4),
                                "nominal_power", building.getOrDefault("batteryPower", 5),
                                "efficiency", building.getOrDefault("batteryEfficiency", 0.9))));
                devices.put("pv", Map.of("type", "citylearn.energy_model.PV", "autosize", false,
                        "attributes", Map.of("nominal_power", building.getOrDefault("pvPower", 0))));
                entry.put("devices", devices);
                entry.put("legacyEquipment", true);
            }
            selected.add(entry);
        }
        Map<String,Object> config = new LinkedHashMap<>();
        config.put("startStep", input.getOrDefault("startStep", 0)); config.put("steps", input.getOrDefault("steps", 168));
        config.put("managedBuildings", selected);
        Map<String,Object> metadata = new LinkedHashMap<>();
        for (String key : List.of("timezone", "currency", "intervalSeconds", "timestampKind"))
            if (settings.containsKey(key)) metadata.put(key, settings.get(key));
        if (saved.get("schema") instanceof Map) metadata.put("schema", saved.get("schema"));
        config.put("community", metadata);
        return config;
    }
    private Path pythonRoot() { return Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize(); }
    private Path script() { Path path = pythonRoot().resolve("ol1_scenario_generator.py"); if (!Files.isRegularFile(path)) throw new IllegalStateException("缺少 OL1 场景生成器"); return path; }
    private Path template() {
        Path path;
        if (configuredTemplate != null && !configuredTemplate.isBlank()) path = Paths.get(configuredTemplate);
        else {
            Path workspace = pythonRoot().getParent() == null ? pythonRoot() : pythonRoot().getParent().getParent();
            path = workspace.resolve("datasets").resolve(TEMPLATE_ID);
        }
        path = path.toAbsolutePath().normalize();
        if (!Files.isRegularFile(path.resolve("schema.json"))) throw new IllegalStateException("找不到本地 CityLearn OL1 模板数据");
        return path;
    }
    private Path taskDirectory(String id) { return pythonRoot().resolve("outputs/ol1-scenario-tasks").resolve(id); }
    private Path stagingDirectory(String id) { return pythonRoot().resolve("datasets").resolve(".ol1-scenario-" + id); }
    private void removeGenerationFiles(String id) {
        Path output = stagingDirectory(id);
        removeTree(output);
        String prefix = "." + output.getFileName() + "-";
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(output.getParent())) {
            for (Path entry : entries) {
                if (entry.getFileName().toString().startsWith(prefix)) removeTree(entry);
            }
        } catch (java.io.IOException ignored) { }
    }
    private void fail(String id, String message) {
        jdbc.update("UPDATE community_scenario_generation_task SET status='failed',stage='failed',error_message=?,end_time=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')", message, id);
    }
    @EventListener(org.springframework.context.event.ContextClosedEvent.class)
    @PreDestroy public void stopProcesses() { stopping = true; processes.forEach((id, process) -> { process.destroyForcibly(); fail(id, "服务关闭，生成任务已中断"); }); }
    private void removeTree(Path directory) {
        try {
            if (!Files.exists(directory)) return;
            try (java.util.stream.Stream<Path> paths = Files.walk(directory)) {
                for (Path path : (Iterable<Path>) paths.sorted(Comparator.reverseOrder())::iterator) Files.deleteIfExists(path);
            }
        } catch (Exception ignored) { }
    }
}
