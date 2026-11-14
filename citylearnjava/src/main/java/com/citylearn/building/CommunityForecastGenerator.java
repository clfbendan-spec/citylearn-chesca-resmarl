package com.citylearn.building;

import java.time.Instant;
import java.util.*;

/** Research forecasts constructed from future observations, not an operational forecaster. */
public final class CommunityForecastGenerator {
    public static final int BUFFER_HOURS = 24;
    public static final long SEED = 2023L;
    public static final List<String> BASES = List.of("outdoor_dry_bulb_temperature", "outdoor_relative_humidity",
            "diffuse_solar_irradiance", "direct_solar_irradiance", "electricity_pricing");
    private static final int[] HORIZONS = {6, 12, 24};
    private static final double[] TEMPERATURE_ERROR = {0.3, 0.65, 1.35};
    private static final double[] RELATIVE_ERROR = {0.025, 0.05, 0.1};

    public Map<String,Object> generate(List<Map<String,Object>> source, int steps) {
        if (steps < 2 || source.size() < steps + BUFFER_HOURS)
            throw new IllegalArgumentException("发布区间之外还需要24小时连续原始数据");
        Instant start = Instant.parse(source.get(0).get("timestamp").toString());
        for (int i = 0; i < steps + BUFFER_HOURS; i++)
            if (!start.plusSeconds(i * 3600L).toString().equals(source.get(i).get("timestamp")))
                throw new IllegalArgumentException("预测缓冲区时间戳不连续");
        Map<String,Object> fields = new LinkedHashMap<>();
        for (String base : BASES) for (int h = 0; h < HORIZONS.length; h++) {
            String key = base + "_predicted_" + (h + 1);
            int generated = 0;
            for (int i = 0; i < steps; i++) {
                Map<String,Object> row = source.get(i);
                if (row.get(key) instanceof Number) continue;
                double future = ((Number)source.get(i + HORIZONS[h]).get(base)).doubleValue();
                // Keyed randomness keeps previews, republishing, and shared building weather consistent.
                Random random = new Random(Objects.hash(SEED, row.get("timestamp"), key));
                double noise = random.nextDouble() * 2.0 - 1.0;
                double prediction;
                if (base.equals("electricity_pricing")) prediction = future;
                else if (base.equals("outdoor_dry_bulb_temperature")) prediction = future + noise * TEMPERATURE_ERROR[h];
                else prediction = Math.max(0.0, future * (1.0 + noise * RELATIVE_ERROR[h]));
                if (base.equals("outdoor_relative_humidity")) prediction = Math.min(100.0, prediction);
                row.put(key, prediction);
                generated++;
            }
            fields.put(key, Map.of("generated", generated, "provided", steps - generated));
        }
        return fields;
    }

    public static Map<String,Object> policy() {
        Map<String,Object> policy = new LinkedHashMap<>();
        policy.put("method", "future_observation_plus_uniform_error");
        policy.put("purpose", "synthetic_research_forecasts_not_operational_predictions");
        policy.put("horizonsHours", List.of(6, 12, 24));
        policy.put("bufferHours", BUFFER_HOURS);
        policy.put("randomSeed", SEED);
        policy.put("randomAlgorithm", "java.util.Random keyed by seed, timestamp and field");
        policy.put("temperatureAbsoluteErrorC", List.of(0.3, 0.65, 1.35));
        policy.put("weatherRelativeError", List.of(0.025, 0.05, 0.1));
        policy.put("pricing", "future_observed_price_without_noise");
        policy.put("suppliedForecasts", "preserved; missing hourly values generated");
        policy.put("boundary", "24-hour source buffer; no circular wrapping");
        policy.put("parameters", "project research defaults, not verified original OL1 parameters");
        return policy;
    }
}
