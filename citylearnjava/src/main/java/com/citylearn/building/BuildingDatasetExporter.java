package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import java.util.stream.Collectors;

public class BuildingDatasetExporter {
    private final ObjectMapper mapper;
    public BuildingDatasetExporter(ObjectMapper mapper) { this.mapper = mapper; }

    public String write(Path dir, Map<String, Object> building, List<Map<String, Object>> rows, String version) throws Exception {
        return write(dir,building,rows,version,null);
    }
    public String write(Path dir, Map<String, Object> building, List<Map<String, Object>> rows, String version, Object options) throws Exception {
        Files.createDirectories(dir);
        ZoneId zone = ZoneId.of(building.get("timezone").toString());
        List<String> energy = new ArrayList<>(List.of("month", "hour", "day_type", "daylight_savings_status"));
        energy.addAll(MeasurementContract.REQUIRED.stream()
                .filter(k -> !k.startsWith("outdoor_") && !k.contains("irradiance")
                        && !List.of("electricity_pricing", "carbon_intensity").contains(k)).collect(Collectors.toList()));
        energy.add("average_unmet_cooling_setpoint_difference");
        energy.add("hvac_mode");
        List<Map<String, Object>> data = new ArrayList<>();
        for (Map<String, Object> original : rows) {
            Map<String, Object> row = new LinkedHashMap<>(original);
            ZonedDateTime time = Instant.parse(row.get("timestamp").toString()).atZone(zone);
            for(String field:List.of("month","hour","day_type","daylight_savings_status"))
                if("assigned".equals(building.get("timestampKind")) && !row.containsKey(field)) throw new IllegalArgumentException("约定时间轴不能生成日历标签，请补齐源字段: "+field);
            row.putIfAbsent("month", time.getMonthValue());
            row.putIfAbsent("hour", time.getHour() + 1);
            row.putIfAbsent("day_type", time.getDayOfWeek().getValue());
            row.putIfAbsent("daylight_savings_status", zone.getRules().isDaylightSavings(time.toInstant()) ? 1 : 0);
            row.putIfAbsent("average_unmet_cooling_setpoint_difference", ((Number) row.get("indoor_dry_bulb_temperature")).doubleValue()
                    - ((Number) row.get("indoor_dry_bulb_temperature_cooling_set_point")).doubleValue());
            if(!row.containsKey("hvac_mode")) {
                boolean cooling=((Number)row.get("cooling_demand")).doubleValue()>0, heating=((Number)row.get("heating_demand")).doubleValue()>0;
                row.put("hvac_mode",cooling && heating?3:heating?2:cooling?1:0);
            }
            data.add(row);
        }
        csv(dir.resolve("Building_1.csv"), energy, data);
        List<String> weather = new ArrayList<>(List.of("outdoor_dry_bulb_temperature", "outdoor_relative_humidity",
                "diffuse_solar_irradiance", "direct_solar_irradiance"));
        List<String> pricing = new ArrayList<>(List.of("electricity_pricing"));
        // Forecast placeholders are causal persistence and are explicitly inactive observations.
        for (String field : new ArrayList<>(weather)) for (int i = 1; i <= 3; i++) weather.add(field + "_predicted_" + i);
        for (int i = 1; i <= 3; i++) pricing.add("electricity_pricing_predicted_" + i);
        for (Map<String, Object> row : data) {
            for (String key : weather) if (key.contains("_predicted_")) row.putIfAbsent(key, row.get(key.split("_predicted_")[0]));
            for (String key : pricing) if (key.contains("_predicted_")) row.putIfAbsent(key, row.get("electricity_pricing"));
        }
        csv(dir.resolve("weather.csv"), weather, data);
        csv(dir.resolve("pricing.csv"), pricing, data);
        csv(dir.resolve("carbon_intensity.csv"), List.of("carbon_intensity"), data);
        csv(dir.resolve("timestamps.csv"), List.of("timestamp"), data);

        Map<String, Object> observations = new LinkedHashMap<>();
        List<String> observable = new ArrayList<>(energy);
        observable.addAll(weather); observable.addAll(pricing);
        observable.addAll(List.of("carbon_intensity", "electrical_storage_soc", "net_electricity_consumption"));
        for (String key : observable) {
            boolean active = (!key.contains("_predicted_") || rows.stream().allMatch(r->r.containsKey(key))) && !List.of("average_unmet_cooling_setpoint_difference",
                    "daylight_savings_status", "hvac_mode").contains(key);
            observations.put(key, Map.of("active", active, "shared_in_central_agent", !energy.contains(key)));
        }
        Map<String, Object> definition = new LinkedHashMap<>();
        definition.put("type", "citylearn.building.Building");
        definition.put("include", true);
        definition.put("energy_simulation", "Building_1.csv");
        definition.put("weather", "weather.csv");
        definition.put("pricing", "pricing.csv");
        definition.put("carbon_intensity", "carbon_intensity.csv");
        definition.put("inactive_observations", List.of());
        definition.put("inactive_actions", List.of());
        boolean schemaEquipment = building.containsKey("devices");
        if (schemaEquipment) {
            Map<String,Object> devices = SchemaEquipment.normalize(building.get("devices"));
            for (String demand : List.of("cooling", "heating", "dhw")) {
                if (!devices.containsKey(demand + "_device") && rows.stream().anyMatch(r -> ((Number)r.get(demand + "_demand")).doubleValue() > 0))
                    throw new IllegalArgumentException("存在热需求但未配置设备: " + demand + "_device");
            }
            definition.putAll(devices);
        } else {
        definition.put("electrical_storage", device("Battery", Map.of("capacity", building.get("batteryCapacity"),
                "nominal_power", building.get("batteryPower"), "efficiency", building.get("batteryEfficiency"),
                "capacity_loss_coefficient", 0.0, "loss_coefficient", 0.0, "initial_soc", 0.5)));
        definition.put("pv", device("PV", Map.of("nominal_power", building.get("pvPower"))));
        definition.put("cooling_device", fixedCop(building.get("coolingCop")));
        definition.put("heating_device", fixedCop(building.get("heatingCop")));
        definition.put("dhw_device", device("ElectricHeater", Map.of("nominal_power", 1e8, "efficiency", building.get("dhwEfficiency"))));
        }
        definition.put("power_outage", Map.of("simulate_power_outage", false, "stochastic_power_outage", false));
        BuildingExportOptions configuration=BuildingExportOptions.parse(options,definition);
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("random_seed", 2023); schema.put("root_directory", null);
        schema.put("central_agent", true);
        schema.put("simulation_start_time_step", 0); schema.put("simulation_end_time_step", rows.size() - 1);
        schema.put("seconds_per_time_step", 3600);
        schema.put("observations", observations);
        boolean hasBattery = definition.containsKey("electrical_storage");
        Map<String,Object> actions=new LinkedHashMap<>();
        for(String key:BuildingExportOptions.STORAGE) {
            actions.put(key,Map.of("active",configuration.actions.contains(key)));
            observations.put(key+"_soc",Map.of("active",definition.containsKey(key),"shared_in_central_agent",false));
        }
        schema.put("actions", actions);
        schema.put("reward_function", configuration.rewardDefinition());
        schema.put("buildings", Map.of("Building_1", definition));
        mapper.writerWithDefaultPrettyPrinter().writeValue(dir.resolve("schema.json").toFile(), schema);
        if (!schemaEquipment) try (InputStream module = getClass().getResourceAsStream("/citylearn/citylearn_ingested_devices.py")) {
            if (module == null) throw new IOException("Missing fixed COP device adapter");
            Files.copy(module, dir.resolve("citylearn_ingested_devices.py"));
        }
        if(!configuration.reward.equals("energy")) try(InputStream module=getClass().getResourceAsStream("/citylearn/citylearn_external_rewards.py")) {
            if(module==null) throw new IOException("Missing external reward module");
            Files.copy(module,dir.resolve("citylearn_external_rewards.py"));
        }
        Map<String, String> hashes = new TreeMap<>();
        try (java.util.stream.Stream<Path> paths = Files.list(dir)) {
            for (Path file : paths.filter(Files::isRegularFile).collect(Collectors.toList()))
                hashes.put(file.getFileName().toString(), sha256(Files.readAllBytes(file)));
        }
        String hash = sha256(mapper.writeValueAsBytes(hashes));
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("version", version); manifest.put("building", building); manifest.put("timeSteps", rows.size());
        manifest.put("profile", configuration.profile.equals("storage")?"storage-exogenous-thermal-demand":hasBattery ? "battery-only-exogenous-thermal-demand" : "building-monitoring-exogenous-thermal-demand");
        manifest.put("dataContract", "CityLearn-Challenge-2023");
        manifest.put("forecastPolicy", "supplied forecasts preserved and active; missing forecasts use inactive persistence placeholders; horizons 6/12/24 hours");
        manifest.put("forecastHorizons",Map.of("1",6,"2",12,"3",24));
        manifest.put("timestampKind",building.getOrDefault("timestampKind","measured"));
        manifest.put("simulation",configuration.asMap());
        manifest.put("fieldSummary",summary(building,rows));
        manifest.put("thermalModel", "none; temperatures are measured exogenous traces, not counterfactual HVAC predictions");
        manifest.put("deviceModel", schemaEquipment ? "CityLearn native equipment; schema attributes and autosizing preserved" : "fixed COP approximation; no capacity saturation; initial battery SOC=0.5; no degradation");
        manifest.put("contentHash", hash); manifest.put("files", hashes);
        mapper.writerWithDefaultPrettyPrinter().writeValue(dir.resolve("manifest.json").toFile(), manifest);
        return hash;
    }

    public static List<Map<String,Object>> summary(Map<String,Object> building,List<Map<String,Object>> rows) {
        List<Map<String,Object>> result=new ArrayList<>();
        for(Map.Entry<String,Map<String,Object>> field:MeasurementContract.FIELDS.entrySet()) {
            String key=field.getKey(); long count=rows.stream().filter(row->row.containsKey(key)).count();
            String status=count==rows.size() && !rows.isEmpty()?"preserved":count>0 || MeasurementContract.REQUIRED.contains(key)?"missing":
                key.contains("_predicted_")?"disabled":MeasurementContract.CATEGORY.contains(key) && !key.equals("hvac_mode") && "assigned".equals(building.get("timestampKind"))?"missing":"generated";
            Map<String,Object> item=new LinkedHashMap<>(field.getValue()); item.put("status",status);item.put("present",count);item.put("total",rows.size());result.add(item);
        }
        return result;
    }

    private Map<String, Object> device(String type, Map<String, Object> attributes) {
        return Map.of("type", "citylearn.energy_model." + type, "autosize", false, "attributes", attributes);
    }
    private Map<String, Object> fixedCop(Object cop) {
        return Map.of("type", "citylearn_ingested_devices.FixedCopHeatPump", "autosize", false,
                "attributes", Map.of("nominal_power", 1e8, "fixed_cop", cop, "efficiency", 0.25,
                        "target_heating_temperature", 45.0, "target_cooling_temperature", 8.0));
    }
    private void csv(Path file, List<String> columns, List<Map<String, Object>> rows) throws IOException {
        try (BufferedWriter writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW)) {
            writer.write(String.join(",", columns)); writer.newLine();
            for (Map<String, Object> row : rows) {
                writer.write(columns.stream().map(key -> row.get(key).toString()).collect(Collectors.joining(","))); writer.newLine();
            }
        }
    }
    public static String sha256(byte[] content) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(content);
            StringBuilder hex = new StringBuilder();
            for (byte value : digest) hex.append(String.format("%02x", value));
            return hex.toString();
        } catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
