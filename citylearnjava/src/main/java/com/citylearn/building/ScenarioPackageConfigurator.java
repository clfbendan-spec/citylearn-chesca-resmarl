package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Collectors;

/** Applies the supported, declarative CityLearn scenario configuration to measured packages. */
public final class ScenarioPackageConfigurator {
    private static final Set<String> GLOBAL = Set.of("observations", "actions", "reward_function", "agent", "central_agent", "random_seed", "rolling_episode_split", "random_episode_split", "episode_time_steps", "simulation_start_time_step", "simulation_end_time_step", "seconds_per_time_step", "root_directory");
    private static final Set<String> ACTIONS = Set.of("cooling_storage", "heating_storage", "dhw_storage", "electrical_storage", "cooling_device", "heating_device", "cooling_or_heating_device");
    private static final Set<String> ENERGY = Set.of("month", "day_type", "hour", "daylight_savings_status", "indoor_dry_bulb_temperature", "average_unmet_cooling_setpoint_difference", "indoor_relative_humidity", "non_shiftable_load", "solar_generation", "cooling_demand", "heating_demand", "dhw_demand", "occupant_count", "hvac_mode", "comfort_band", "indoor_dry_bulb_temperature_cooling_set_point", "indoor_dry_bulb_temperature_heating_set_point");
    private static final Set<String> STATE = Set.of("power_outage", "net_electricity_consumption", "cooling_device_efficiency", "heating_device_efficiency", "cooling_electricity_consumption", "heating_electricity_consumption", "dhw_electricity_consumption", "cooling_storage_soc", "heating_storage_soc", "dhw_storage_soc", "electrical_storage_soc", "cooling_storage_electricity_consumption", "heating_storage_electricity_consumption", "dhw_storage_electricity_consumption", "electrical_storage_electricity_consumption", "indoor_dry_bulb_temperature_cooling_delta", "indoor_dry_bulb_temperature_heating_delta");
    private static final Set<String> AGENT_ATTRIBUTES = Set.of("hidden_dimension", "discount", "tau", "lr", "batch_size", "replay_buffer_capacity", "standardize_start_time_step", "end_exploration_time_step", "action_scaling_coef", "reward_scaling", "update_per_time_step", "alpha", "automatic_entropy_tuning", "entropy_target", "start_training_time_step", "random_seed", "deterministic_start_time_step");
    private final ObjectMapper mapper;

    public ScenarioPackageConfigurator(ObjectMapper mapper) { this.mapper = mapper; }

    public Map<String,Object> validate(Map<String,Object> configuration, List<Long> buildingIds, Path assetDirectory) throws Exception {
        Map<String,Object> config = copy(configuration == null ? Map.of() : configuration);
        keys(config, Set.of("schema", "buildings"), "configuration");
        if (buildingIds == null || buildingIds.isEmpty() || new HashSet<>(buildingIds).size() != buildingIds.size() || buildingIds.stream().anyMatch(Objects::isNull)) fail("Select distinct buildings");
        Map<String,Object> schema = object(config.getOrDefault("schema", Map.of()), "schema");
        keys(schema, GLOBAL, "schema");
        if (schema.get("root_directory") != null && !"".equals(schema.get("root_directory"))) fail("root_directory must be empty; packages use portable local paths");
        for (String field : List.of("simulation_start_time_step", "simulation_end_time_step")) if (schema.containsKey(field)) integer(schema.get(field), 0, Integer.MAX_VALUE, field);
        if (schema.containsKey("seconds_per_time_step") && number(schema.get("seconds_per_time_step"), "seconds_per_time_step") != 3600) fail("Published community packages require 3600 seconds per time step");
        for (String field : List.of("central_agent", "rolling_episode_split", "random_episode_split")) if (schema.containsKey(field)) bool(schema.get(field), field);
        if (schema.get("random_seed") != null) integer(schema.get("random_seed"), 0, Integer.MAX_VALUE, "random_seed");
        Object episode = schema.get("episode_time_steps");
        if (episode instanceof List) {
            for (Object range : (List<?>)episode) {
                List<?> pair = list(range, "episode_time_steps range");
                if (pair.size() != 2) fail("Episode ranges need start and end");
                integer(pair.get(0), 0, Integer.MAX_VALUE, "episode start");
                integer(pair.get(1), ((Number)pair.get(0)).intValue(), Integer.MAX_VALUE, "episode end");
            }
        } else if (episode != null) integer(episode, 2, Integer.MAX_VALUE, "episode_time_steps");
        if (schema.containsKey("observations")) signals(schema.get("observations"), true);
        if (schema.containsKey("actions")) signals(schema.get("actions"), false);
        if (schema.containsKey("reward_function")) definition(schema.get("reward_function"), false);
        if (schema.containsKey("agent")) definition(schema.get("agent"), true);
        Map<String,Object> buildings = object(config.getOrDefault("buildings", Map.of()), "buildings");
        Set<String> selectedIds = buildingIds.stream().map(Object::toString).collect(Collectors.toSet());
        for (Map.Entry<String,Object> entry : buildings.entrySet()) {
            if (!entry.getKey().matches("[1-9][0-9]*")) fail("Building configuration keys must be building IDs");
            Map<String,Object> building = object(entry.getValue(), "building " + entry.getKey());
            if (!selectedIds.contains(entry.getKey())) continue;
            Set<String> allowed = new HashSet<>(SchemaEquipment.TYPES.keySet());
            allowed.addAll(List.of("type", "include", "dynamics", "power_outage", "inactive_actions", "inactive_observations"));
            keys(building, allowed, "building " + entry.getKey());
            if (building.containsKey("include")) {
                bool(building.get("include"), "include");
                if (!Boolean.TRUE.equals(building.get("include"))) fail("所选发布建筑不能设置 include=false，请从发布选择中移除该建筑");
            }
            for (String field : List.of("inactive_actions", "inactive_observations")) if (building.containsKey(field)) {
                for (Object name : list(building.get(field), field)) {
                    if (!(name instanceof String) || !(field.equals("inactive_actions") ? ACTIONS.contains(name) : supported(name.toString()))) fail("Unsupported " + field + ": " + name);
                }
            }
            String type = Objects.toString(building.get("type"), "citylearn.building.Building");
            if (!Set.of("citylearn.building.Building", "citylearn.building.LSTMDynamicsBuilding").contains(type)) fail("Unsupported building type: " + type);
            boolean dynamic = building.get("dynamics") != null;
            if (dynamic != type.equals("citylearn.building.LSTMDynamicsBuilding")) fail("LSTMDynamicsBuilding 与 LSTMDynamics 必须同时配置");
            if (dynamic) dynamics(building.get("dynamics"), assetDirectory);
            if (building.containsKey("power_outage")) outage(building.get("power_outage"));
            Map<String,Object> devices = new LinkedHashMap<>();
            for (String name : SchemaEquipment.TYPES.keySet()) if (building.get(name) != null) devices.put(name, building.get(name));
            if (!devices.isEmpty()) SchemaEquipment.normalize(devices);
        }
        config.put("schema", schema); config.put("buildings", buildings);
        return config;
    }

    public String apply(Path publishedDirectory, Map<String,Object> configuration, List<Long> buildingIds, Path assetDirectory) throws Exception {
        Map<String,Object> config = validate(configuration, buildingIds, assetDirectory);
        Map<String,Object> schema = read(publishedDirectory.resolve("schema.json"));
        Map<String,Object> overrides = object(config.get("schema"), "schema");
        for (String field : List.of("simulation_start_time_step", "simulation_end_time_step", "seconds_per_time_step")) {
            if (overrides.containsKey(field) && number(overrides.get(field), field) != number(schema.get(field), field)) fail("Scenario time bounds must match the published selection: " + field);
        }
        schema.putAll(overrides);
        schema.put("root_directory", null);
        Map<String,Object> buildings = object(schema.get("buildings"), "exported buildings");
        if (buildings.size() != buildingIds.size()) fail("Selected buildings do not match package");
        Map<String,Object> perBuilding = object(config.get("buildings"), "buildings");
        Map<String,Object> observations = object(schema.get("observations"), "observations");
        Map<String,Object> actions = object(schema.get("actions"), "actions");
        List<Map<String,String>> series = new ArrayList<>();
        List<Map<String,Object>> assets = new ArrayList<>();
        boolean dynamic = false;
        for (int i = 0; i < buildingIds.size(); i++) {
            String key = "Building_" + (i + 1);
            Map<String,Object> building = object(buildings.get(key), key);
            Map<String,Object> local = object(perBuilding.getOrDefault(buildingIds.get(i).toString(), Map.of()), "building configuration");
            for (String equipment : SchemaEquipment.TYPES.keySet()) if (local.containsKey(equipment) && !mapper.valueToTree(local.get(equipment)).equals(mapper.valueToTree(building.get(equipment)))) fail("Configure equipment through building devices: " + equipment);
            building.putAll(local);
            Map<String,String> columns = columns(publishedDirectory, building);
            series.add(columns);
            if (building.get("power_outage") instanceof Map) {
                Map<String,Object> outage = object(building.get("power_outage"), "power_outage");
                if (Boolean.TRUE.equals(outage.get("simulate_power_outage")) && !Boolean.TRUE.equals(outage.get("stochastic_power_outage")) && !columns.containsKey("power_outage")) fail("Measured power outage simulation requires the power_outage CSV column");
            }
            if (building.get("dynamics") != null) {
                dynamic = true;
                Map<String,Object> attributes = object(object(building.get("dynamics"), "dynamics").get("attributes"), "dynamics.attributes");
                for (Object name : list(attributes.get("input_observation_names"), "input_observation_names")) {
                    String base = name.toString().replaceFirst("_(sin|cos)$", "");
                    if (!columns.containsKey(base)) fail("缺少动力学模型输入数据列: " + name);
                }
                Path source = asset(assetDirectory, attributes.get("filename").toString());
                String filename = key + "_dynamics.pth";
                byte[] bytes = Files.readAllBytes(source);
                Files.write(publishedDirectory.resolve(filename), bytes);
                attributes.put("filename", filename);
                assets.add(Map.of("buildingId", buildingIds.get(i), "filename", filename, "sha256", BuildingDatasetExporter.sha256(bytes), "size", bytes.length));
            }
            List<?> inactiveActions = list(building.getOrDefault("inactive_actions", List.of()), "inactive_actions");
            for (Map.Entry<String,Object> action : actions.entrySet()) {
                if (!Boolean.TRUE.equals(object(action.getValue(), "action").get("active")) || inactiveActions.contains(action.getKey())) continue;
                String name = action.getKey();
                if (name.equals("cooling_or_heating_device")) {
                    if (building.get("dynamics") == null || building.get("cooling_device") == null || building.get("heating_device") == null) fail("Combined HVAC action requires dynamics and both HVAC devices");
                } else {
                    if (building.get(name) == null) fail("启用动作需要配置对应设备: " + key + "." + name);
                    if (name.endsWith("_device") && building.get("dynamics") == null) fail("HVAC 控制动作需要学习动力学模型: " + name);
                    if (name.endsWith("_storage") && !name.equals("electrical_storage") && building.get(name.replace("_storage", "_device")) == null) fail("Thermal storage action requires its device: " + name);
                }
            }
            List<?> inactive = list(building.getOrDefault("inactive_observations", List.of()), "inactive_observations");
            for (Map.Entry<String,Object> observation : observations.entrySet()) {
                if (!Boolean.TRUE.equals(object(observation.getValue(), "observation").get("active")) || inactive.contains(observation.getKey())) continue;
                String name = observation.getKey();
                if (!columns.containsKey(name) && !STATE.contains(name)) fail("缺少观测数据列: " + name);
                if (name.endsWith("_soc") && building.get(name.substring(0, name.length() - 4)) == null) fail("SOC 观测需要配置对应储能设备: " + name);
                if (name.endsWith("_device_efficiency") && building.get(name.replace("_efficiency", "")) == null) fail("Device efficiency observation requires equipment: " + name);
                if (name.endsWith("_storage_electricity_consumption") && building.get(name.replace("_electricity_consumption", "")) == null) fail("Storage observation requires equipment: " + name);
                if (name.endsWith("_delta") && (!columns.containsKey("indoor_dry_bulb_temperature") || !columns.containsKey(name.replace("_delta", "_set_point")))) fail("Temperature delta observation requires temperature and set point columns: " + name);
            }
        }
        for (Map.Entry<String,Object> entry : observations.entrySet()) {
            Map<String,Object> signal = object(entry.getValue(), "observation");
            if (!Boolean.TRUE.equals(signal.get("shared_in_central_agent"))) continue;
            String name = entry.getKey(), first = series.get(0).get(name);
            boolean same = shared(name) && first != null;
            for (Map<String,String> columns : series) same &= Objects.equals(first, columns.get(name));
            signal.put("shared_in_central_agent", same);
        }
        checkEpisode(schema);
        mapper.writerWithDefaultPrettyPrinter().writeValue(publishedDirectory.resolve("schema.json").toFile(), schema);
        Map<String,Object> manifest = read(publishedDirectory.resolve("manifest.json"));
        manifest.put("profile", "community-full-configured");
        manifest.put("thermalModel", dynamic ? "LSTMDynamics" : "measured exogenous thermal demand");
        manifest.put("modelAssets", assets);
        Map<String,Object> summary = new LinkedHashMap<>(object(manifest.getOrDefault("publicationSummary", Map.of()), "publicationSummary"));
        summary.put("ready", true); summary.put("profile", "community-full-configured");
        summary.put("thermalModel", manifest.get("thermalModel")); summary.put("rewardFunction", schema.get("reward_function"));
        summary.put("sharedObservations", observations.entrySet().stream().filter(e -> Boolean.TRUE.equals(object(e.getValue(), "observation").get("shared_in_central_agent"))).map(Map.Entry::getKey).collect(Collectors.toList()));
        manifest.put("publicationSummary", summary);
        Map<String,String> hashes = new TreeMap<>();
        try (java.util.stream.Stream<Path> paths = Files.walk(publishedDirectory)) {
            for (Path file : paths.filter(Files::isRegularFile).collect(Collectors.toList())) {
                String relative = publishedDirectory.relativize(file).toString().replace('\\', '/');
                if (!relative.equals("manifest.json")) hashes.put(relative, BuildingDatasetExporter.sha256(Files.readAllBytes(file)));
            }
        }
        String hash = BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(hashes));
        manifest.put("files", hashes); manifest.put("contentHash", hash);
        mapper.writerWithDefaultPrettyPrinter().writeValue(publishedDirectory.resolve("manifest.json").toFile(), manifest);
        return hash;
    }

    private void signals(Object value, boolean observation) {
        for (Map.Entry<String,Object> entry : object(value, "signals").entrySet()) {
            if (!(observation ? supported(entry.getKey()) : ACTIONS.contains(entry.getKey()))) fail("不支持的观测或动作: " + entry.getKey());
            Map<String,Object> signal = object(entry.getValue(), entry.getKey());
            keys(signal, observation ? Set.of("active", "shared_in_central_agent") : Set.of("active"), entry.getKey());
            bool(signal.get("active"), entry.getKey() + ".active");
            if (signal.containsKey("shared_in_central_agent")) bool(signal.get("shared_in_central_agent"), "shared_in_central_agent");
        }
    }

    private void definition(Object value, boolean agent) {
        Map<String,Object> definition = object(value, agent ? "agent" : "reward_function");
        keys(definition, Set.of("type", "attributes"), "definition");
        String type = Objects.toString(definition.get("type"), "");
        Set<String> types = agent ? Set.of("citylearn.agents.sac.SAC", "citylearn.agents.sac.SACRBC", "citylearn.agents.sac.SACBasicRBC", "citylearn.agents.rbc.RBC", "citylearn.agents.rbc.BasicRBC", "citylearn.agents.rbc.OptimizedRBC", "citylearn.agents.rbc.BasicBatteryRBC") : Set.of("citylearn.reward_function.RewardFunction", "citylearn.reward_function.ComfortReward", "citylearn.reward_function.MARL", "citylearn.reward_function.IndependentSACReward", "citylearn.reward_function.SolarPenaltyReward", "citylearn.reward_function.SolarPenaltyAndComfortReward");
        if (!types.contains(type)) fail("不支持的运行时类: " + type);
        Map<String,Object> attributes = object(definition.getOrDefault("attributes", Map.of()), "attributes");
        Set<String> allowed = agent ? AGENT_ATTRIBUTES : type.endsWith("SolarPenaltyAndComfortReward") ? Set.of("band", "lower_exponent", "higher_exponent", "coefficients") : type.endsWith("ComfortReward") ? Set.of("band", "lower_exponent", "higher_exponent") : type.endsWith(".RewardFunction") ? Set.of("exponent") : Set.of();
        keys(attributes, allowed, type + " attributes");
        for (Map.Entry<String,Object> attribute : attributes.entrySet()) {
            if (attribute.getValue() == null) continue;
            if (attribute.getKey().equals("hidden_dimension") || attribute.getKey().equals("coefficients")) {
                for (Object number : list(attribute.getValue(), attribute.getKey())) number(number, attribute.getKey());
            } else if (attribute.getKey().equals("automatic_entropy_tuning")) bool(attribute.getValue(), attribute.getKey());
            else number(attribute.getValue(), attribute.getKey());
        }
    }

    private void dynamics(Object value, Path directory) throws Exception {
        Map<String,Object> model = object(value, "dynamics");
        keys(model, Set.of("type", "attributes"), "dynamics");
        if (!"citylearn.dynamics.LSTMDynamics".equals(model.get("type"))) fail("仅支持运行时内置的 LSTMDynamics 模型");
        Map<String,Object> a = object(model.get("attributes"), "dynamics.attributes");
        keys(a, Set.of("filename", "input_size", "hidden_size", "num_layers", "lookback", "input_observation_names", "input_normalization_minimum", "input_normalization_maximum", "dropout"), "dynamics.attributes");
        integer(a.get("hidden_size"), 1, 4096, "hidden_size"); integer(a.get("num_layers"), 1, 64, "num_layers"); integer(a.get("lookback"), 1, 8760, "lookback");
        List<?> names = list(a.get("input_observation_names"), "input_observation_names"), min = list(a.get("input_normalization_minimum"), "minimum"), max = list(a.get("input_normalization_maximum"), "maximum");
        if (names.isEmpty() || names.size() > 256 || names.size() != min.size() || names.size() != max.size() || new HashSet<>(names).size() != names.size()) fail("LSTM 输入名称与归一化数组必须非空、长度相同，且输入名称不可重复");
        if (a.get("input_size") != null) integer(a.get("input_size"), names.size(), names.size(), "input_size");
        for (int i = 0; i < names.size(); i++) {
            if (!(names.get(i) instanceof String) || !supported(names.get(i).toString().replaceFirst("_(sin|cos)$", ""))) fail("Unsupported dynamics observation: " + names.get(i));
            if (number(max.get(i), "maximum") <= number(min.get(i), "minimum")) fail("LSTM 归一化最大值必须大于最小值");
        }
        if (!names.get(names.size() - 1).equals("indoor_dry_bulb_temperature")) fail("LSTM final input must be indoor_dry_bulb_temperature");
        if (a.get("dropout") != null && (number(a.get("dropout"), "dropout") < 0 || number(a.get("dropout"), "dropout") > 1)) fail("dropout must be between 0 and 1");
        if (!(a.get("filename") instanceof String)) fail("请填写模型资源 filename");
        asset(directory, a.get("filename").toString());
    }

    private void outage(Object value) {
        Map<String,Object> outage = object(value, "power_outage");
        keys(outage, Set.of("simulate_power_outage", "stochastic_power_outage", "stochastic_power_outage_model"), "power_outage");
        for (String field : List.of("simulate_power_outage", "stochastic_power_outage")) if (outage.containsKey(field)) bool(outage.get(field), field);
        if (outage.get("stochastic_power_outage_model") == null) return;
        Map<String,Object> model = object(outage.get("stochastic_power_outage_model"), "outage model");
        keys(model, Set.of("type", "attributes"), "outage model");
        if (!"citylearn.power_outage.ReliabilityMetricsPowerOutage".equals(model.get("type"))) fail("Unsupported outage model");
        Map<String,Object> a = object(model.getOrDefault("attributes", Map.of()), "outage attributes");
        keys(a, Set.of("random_seed", "saifi", "caidi", "start_time_steps"), "outage attributes");
        if (a.get("random_seed") != null) integer(a.get("random_seed"), 0, Integer.MAX_VALUE, "outage random_seed");
        if (a.get("saifi") != null && (number(a.get("saifi"), "saifi") < 0 || number(a.get("saifi"), "saifi") > 365)) fail("saifi must be between 0 and 365");
        if (a.get("caidi") != null && number(a.get("caidi"), "caidi") < 0) fail("caidi must be nonnegative");
        if (a.get("start_time_steps") != null) {
            List<?> starts = list(a.get("start_time_steps"), "start_time_steps");
            if (starts.isEmpty()) fail("start_time_steps must not be empty");
            for (Object start : starts) integer(start, 0, 23, "start_time_steps");
        }
    }

    private Path asset(Path directory, String filename) throws Exception {
        if (directory == null || !filename.matches("[A-Za-z0-9][A-Za-z0-9_.-]*\\.(pth|pt)") || filename.contains("..")) throw new IllegalArgumentException("模型资源文件名无效，仅允许社区内的 .pth 或 .pt 文件");
        Path root = directory.toRealPath(), file = root.resolve(filename);
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || !file.toRealPath().startsWith(root)) throw new IllegalArgumentException("模型资源不存在，请先上传: " + filename);
        long size = Files.size(file);
        if (size < 1 || size > 100L * 1024 * 1024) fail("Model asset size must be 1 byte to 100 MiB");
        return file;
    }

    private Map<String,String> columns(Path directory, Map<String,Object> building) throws Exception {
        Map<String,String> output = new HashMap<>();
        for (String field : List.of("energy_simulation", "weather", "pricing", "carbon_intensity")) {
            if (building.get(field) == null) continue;
            Path root = directory.toRealPath(), file = root.resolve(building.get(field).toString()).normalize();
            if (!file.startsWith(root) || !Files.isRegularFile(file) || !file.toRealPath().startsWith(root)) fail("Invalid package CSV path");
            try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String header = reader.readLine();
                if (header == null) fail("Empty package CSV");
                String[] names = header.split(",", -1);
                MessageDigest[] hashes = new MessageDigest[names.length];
                for (int i = 0; i < names.length; i++) hashes[i] = MessageDigest.getInstance("SHA-256");
                String line;
                while ((line = reader.readLine()) != null) {
                    String[] values = line.split(",", -1);
                    if (values.length != names.length) fail("Invalid package CSV row");
                    for (int i = 0; i < names.length; i++) {
                        double number = Double.parseDouble(values[i]);
                        if (!Double.isFinite(number)) fail("Nonfinite CSV value");
                        hashes[i].update((Double.toHexString(number == 0 ? 0 : number) + "\n").getBytes(StandardCharsets.UTF_8));
                    }
                }
                for (int i = 0; i < names.length; i++) output.put(names[i], Base64.getEncoder().encodeToString(hashes[i].digest()));
            }
        }
        return output;
    }

    private void checkEpisode(Map<String,Object> schema) {
        int end = ((Number)schema.get("simulation_end_time_step")).intValue();
        Object episode = schema.get("episode_time_steps");
        if (episode instanceof Number && ((Number)episode).intValue() > end + 1) fail("episode_time_steps 超过已发布时段，请缩短回合长度或扩大发布范围");
        if (episode instanceof List) for (Object pair : (List<?>)episode) if (((Number)((List<?>)pair).get(1)).intValue() > end) fail("回合时间范围超过已发布时段，请调整 episode_time_steps");
    }
    private static boolean shared(String name) { return Set.of("month", "day_type", "hour", "daylight_savings_status", "carbon_intensity").contains(name) || name.startsWith("outdoor_") || name.startsWith("electricity_pricing") || name.contains("solar_irradiance"); }
    private static boolean supported(String name) { return ENERGY.contains(name) || STATE.contains(name) || name.equals("carbon_intensity") || name.matches("(outdoor_dry_bulb_temperature|outdoor_relative_humidity|diffuse_solar_irradiance|direct_solar_irradiance|electricity_pricing)(_predicted_[123])?"); }
    @SuppressWarnings("unchecked") private Map<String,Object> copy(Map<String,Object> value) throws Exception { return mapper.readValue(mapper.writeValueAsBytes(value), Map.class); }
    @SuppressWarnings("unchecked") private Map<String,Object> read(Path file) throws Exception { return mapper.readValue(file.toFile(), Map.class); }
    @SuppressWarnings("unchecked") private static Map<String,Object> object(Object value, String field) { if (!(value instanceof Map)) throw new IllegalArgumentException(field + " must be an object"); return (Map<String,Object>)value; }
    private static List<?> list(Object value, String field) { if (!(value instanceof List)) throw new IllegalArgumentException(field + " must be an array"); return (List<?>)value; }
    private static void keys(Map<String,Object> value, Set<String> allowed, String field) { for (String key : value.keySet()) if (!allowed.contains(key)) fail("不支持的配置项 " + field + "." + key); }
    private static void bool(Object value, String field) { if (!(value instanceof Boolean)) fail(field + " must be boolean"); }
    private static double number(Object value, String field) { if (!(value instanceof Number) || !Double.isFinite(((Number)value).doubleValue())) throw new IllegalArgumentException(field + " must be a finite number"); return ((Number)value).doubleValue(); }
    private static void integer(Object value, int min, int max, String field) { double n = number(value, field); if (n != Math.rint(n) || n < min || n > max) fail(field + " is outside its supported integer range"); }
    private static void fail(String message) { throw new IllegalArgumentException(message); }
}
