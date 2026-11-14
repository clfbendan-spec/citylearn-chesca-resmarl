package com.citylearn.building;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ScenarioPackageConfiguratorTest {
    @TempDir Path root;
    private final ObjectMapper mapper = new ObjectMapper();
    private final ScenarioPackageConfigurator configurator = new ScenarioPackageConfigurator(mapper);

    private Map<String,Object> configuration() throws Exception {
        Files.createDirectories(root.resolve("assets"));
        Files.write(root.resolve("assets/model.pth"), new byte[]{11, 22, 33});
        Map<String,Object> model = new LinkedHashMap<>();
        model.put("input_size", 3); model.put("hidden_size", 16); model.put("num_layers", 2); model.put("lookback", 12);
        model.put("filename", "model.pth");
        model.put("input_observation_names", List.of("outdoor_dry_bulb_temperature", "cooling_demand", "indoor_dry_bulb_temperature"));
        model.put("input_normalization_minimum", List.of(-10, 0, 10)); model.put("input_normalization_maximum", List.of(50, 20, 40));
        Map<String,Object> building = new LinkedHashMap<>();
        building.put("type", "citylearn.building.LSTMDynamicsBuilding");
        building.put("dynamics", Map.of("type", "citylearn.dynamics.LSTMDynamics", "attributes", model));
        building.put("power_outage", Map.of("simulate_power_outage", true, "stochastic_power_outage", true,
                "stochastic_power_outage_model", Map.of("type", "citylearn.power_outage.ReliabilityMetricsPowerOutage", "attributes", Map.of("random_seed", 24, "saifi", 1.436, "caidi", 331.2))));
        building.put("inactive_actions", List.of()); building.put("inactive_observations", List.of());
        Map<String,Object> observations = new LinkedHashMap<>();
        for (String name : List.of("outdoor_dry_bulb_temperature", "cooling_demand", "indoor_dry_bulb_temperature", "power_outage", "electrical_storage_soc")) observations.put(name, Map.of("active", true, "shared_in_central_agent", true));
        Map<String,Object> schema = new LinkedHashMap<>();
        schema.put("observations", observations);
        schema.put("actions", Map.of("electrical_storage", Map.of("active", true), "dhw_storage", Map.of("active", true), "cooling_device", Map.of("active", true)));
        schema.put("reward_function", Map.of("type", "citylearn.reward_function.ComfortReward", "attributes", Map.of("band", 1, "lower_exponent", 2, "higher_exponent", 3)));
        schema.put("agent", Map.of("type", "citylearn.agents.sac.SACBasicRBC", "attributes", Map.of("hidden_dimension", List.of(256, 256), "discount", 0.9, "batch_size", 512)));
        schema.put("random_seed", 2023); schema.put("central_agent", true); schema.put("rolling_episode_split", false); schema.put("random_episode_split", false); schema.put("episode_time_steps", null);
        return new LinkedHashMap<>(Map.of("schema", schema, "buildings", Map.of("192", building, "194", building)));
    }

    private Path published(int count) throws Exception {
        Path output = root.resolve("published"); Files.createDirectories(output);
        Map<String,Object> buildings = new LinkedHashMap<>();
        for (int i = 1; i <= count; i++) {
            String filename = "Building_" + i + ".csv";
            Files.writeString(output.resolve(filename), "outdoor_dry_bulb_temperature,cooling_demand,indoor_dry_bulb_temperature\n20,2,24\n21,3,25\n");
            Map<String,Object> building = new LinkedHashMap<>();
            building.put("energy_simulation", filename); building.put("type", "citylearn.building.Building");
            building.put("cooling_device", Map.of("type", "citylearn.energy_model.HeatPump", "attributes", Map.of("nominal_power", 4)));
            building.put("dhw_device", Map.of("type", "citylearn.energy_model.ElectricHeater", "attributes", Map.of("nominal_power", 3)));
            building.put("dhw_storage", Map.of("type", "citylearn.energy_model.StorageTank", "attributes", Map.of("capacity", 2)));
            building.put("electrical_storage", Map.of("type", "citylearn.energy_model.Battery", "attributes", Map.of("capacity", 4, "nominal_power", 3.32)));
            buildings.put("Building_" + i, building);
        }
        mapper.writeValue(output.resolve("schema.json").toFile(), Map.of("buildings", buildings, "simulation_start_time_step", 0, "simulation_end_time_step", 1));
        mapper.writeValue(output.resolve("manifest.json").toFile(), Map.of("version", "test", "files", Map.of(), "contentHash", "old"));
        return output;
    }

    @SuppressWarnings("unchecked")
    @Test void preservesDynamicsOutageThreeActionsAndHashesEveryModel() throws Exception {
        Map<String,Object> config = configuration(); Path output = published(2);
        String hash = configurator.apply(output, config, List.of(192L, 194L), root.resolve("assets"));
        Map<String,Object> schema = mapper.readValue(output.resolve("schema.json").toFile(), Map.class);
        assertEquals(config.get("schema") instanceof Map ? ((Map<?,?>)config.get("schema")).get("agent") : null, schema.get("agent"));
        assertEquals(((Map<?,?>)config.get("schema")).get("actions"), schema.get("actions"));
        Map<String,Object> buildings = (Map<String,Object>)schema.get("buildings");
        Map<String,Object> first = (Map<String,Object>)buildings.get("Building_1");
        assertEquals(((Map<?,?>)((Map<?,?>)config.get("buildings")).get("192")).get("power_outage"), first.get("power_outage"));
        assertEquals("Building_1_dynamics.pth", ((Map<?,?>)((Map<?,?>)first.get("dynamics")).get("attributes")).get("filename"));
        assertArrayEquals(Files.readAllBytes(root.resolve("assets/model.pth")), Files.readAllBytes(output.resolve("Building_2_dynamics.pth")));
        Map<?,?> observations = (Map<?,?>)schema.get("observations");
        assertEquals(true, ((Map<?,?>)observations.get("outdoor_dry_bulb_temperature")).get("shared_in_central_agent"));
        assertEquals(false, ((Map<?,?>)observations.get("electrical_storage_soc")).get("shared_in_central_agent"));
        assertEquals(false, ((Map<?,?>)observations.get("indoor_dry_bulb_temperature")).get("shared_in_central_agent"));
        Map<?,?> manifest = mapper.readValue(output.resolve("manifest.json").toFile(), Map.class);
        Map<String,String> hashes = new TreeMap<>((Map<String,String>)manifest.get("files"));
        assertEquals(hash, BuildingDatasetExporter.sha256(mapper.writeValueAsBytes(hashes)));
        assertEquals(hash, manifest.get("contentHash"));
        assertFalse(hashes.containsKey("manifest.json"));
        assertEquals(BuildingDatasetExporter.sha256(new byte[]{11,22,33}), hashes.get("Building_1_dynamics.pth"));
        assertEquals("community-full-configured", manifest.get("profile"));
        assertEquals("LSTMDynamics", manifest.get("thermalModel"));
        assertEquals("model.pth", ((Map<?,?>)((Map<?,?>)((Map<?,?>)((Map<?,?>)config.get("buildings")).get("192")).get("dynamics")).get("attributes")).get("filename"));
    }

    @SuppressWarnings("unchecked")
    @Test void rejectsMissingAssetTraversalInconsistentDynamicsAndUnsupportedOptions() throws Exception {
        Map<String,Object> config = configuration();
        Files.delete(root.resolve("assets/model.pth"));
        Map<String,Object> missing = config;
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(missing, List.of(192L), root.resolve("assets")));
        config = configuration();
        Map<String,Object> building = (Map<String,Object>)((Map<?,?>)config.get("buildings")).get("192");
        Map<String,Object> attributes = (Map<String,Object>)((Map<?,?>)building.get("dynamics")).get("attributes");
        attributes.put("filename", "../model.pth");
        Map<String,Object> traversal = config;
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(traversal, List.of(192L), root.resolve("assets")));
        attributes.put("filename", "model.pth"); building.put("type", "citylearn.building.Building");
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(traversal, List.of(192L), root.resolve("assets")));
        building.put("type", "citylearn.building.LSTMDynamicsBuilding"); attributes.put("hidden_size", 0);
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(traversal, List.of(192L), root.resolve("assets")));
        attributes.put("hidden_size", 16);
        ((Map<String,Object>)config.get("schema")).put("root_directory", "C:/other");
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(traversal, List.of(192L), root.resolve("assets")));
    }

    @SuppressWarnings("unchecked")
    @Test void selectedBuildingCannotBeExcludedFromRuntime() throws Exception {
        Map<String,Object> config = configuration();
        Map<String,Object> building = (Map<String,Object>)((Map<?,?>)config.get("buildings")).get("192");
        building.put("include", false);
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(config, List.of(192L), root.resolve("assets")));
    }

    @SuppressWarnings("unchecked")
    @Test void validatesActualObservationAvailabilityAndHvacEquipment() throws Exception {
        Map<String,Object> config = configuration(); Path output = published(1);
        Map<String,Object> schema = (Map<String,Object>)config.get("schema");
        Map<String,Object> observations = (Map<String,Object>)schema.get("observations");
        observations.put("indoor_relative_humidity", Map.of("active", true, "shared_in_central_agent", false));
        assertThrows(IllegalArgumentException.class, () -> configurator.apply(output, config, List.of(192L), root.resolve("assets")));
        observations.remove("indoor_relative_humidity");
        observations.put("execute_python", Map.of("active", false));
        assertThrows(IllegalArgumentException.class, () -> configurator.validate(config, List.of(192L), root.resolve("assets")));
        observations.remove("execute_python");
        Map<String,Object> packageSchema = mapper.readValue(output.resolve("schema.json").toFile(), Map.class);
        ((Map<?,?>)((Map<?,?>)packageSchema.get("buildings")).get("Building_1")).remove("cooling_device");
        mapper.writeValue(output.resolve("schema.json").toFile(), packageSchema);
        assertThrows(IllegalArgumentException.class, () -> configurator.apply(output, config, List.of(192L), root.resolve("assets")));
    }

    @SuppressWarnings("unchecked")
    @Test void subsetSharesOnlyMatchingExogenousColumnsAndModelBytesChangeContentHash() throws Exception {
        Map<String,Object> config = configuration(); Path output = published(2);
        Files.writeString(output.resolve("Building_2.csv"), "outdoor_dry_bulb_temperature,cooling_demand,indoor_dry_bulb_temperature\n22,2,24\n23,3,25\n");
        configurator.apply(output, config, List.of(192L,194L), root.resolve("assets"));
        Map<?,?> schema = mapper.readValue(output.resolve("schema.json").toFile(), Map.class);
        assertEquals(false, ((Map<?,?>)((Map<?,?>)schema.get("observations")).get("outdoor_dry_bulb_temperature")).get("shared_in_central_agent"));
        output = published(1);
        String first = configurator.apply(output, config, List.of(194L), root.resolve("assets"));
        Files.write(root.resolve("assets/model.pth"), new byte[]{44,55,66});
        String second = configurator.apply(output, config, List.of(194L), root.resolve("assets"));
        assertNotEquals(first, second);
        schema = mapper.readValue(output.resolve("schema.json").toFile(), Map.class);
        assertEquals(true, ((Map<?,?>)((Map<?,?>)schema.get("observations")).get("outdoor_dry_bulb_temperature")).get("shared_in_central_agent"));
    }
}
