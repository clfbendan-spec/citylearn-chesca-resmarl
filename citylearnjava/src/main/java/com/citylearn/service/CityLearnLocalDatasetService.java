package com.citylearn.service;

import com.citylearn.vo.BuildingDataVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.io.BufferedReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * 从 CityLearn 本地 schema 目录读取 Building / weather / pricing / carbon_intensity CSV，
 * 封装为 {@link BuildingDataVO}。默认 schema：2023 phase2 local evaluation。
 */
@Slf4j
@Service
public class CityLearnLocalDatasetService {

    public static final String DEFAULT_SCHEMA = "citylearn_challenge_2023_phase_2_local_evaluation";

    @Resource
    private CitylearnDatasetService citylearnDatasetService;

    /** schema|buildingKey -> rows */
    private final ConcurrentHashMap<String, List<BuildingDataVO>> cache = new ConcurrentHashMap<>();

    public List<BuildingDataVO> getBuildingRows(String buildingId, String schemaName,
                                                Integer month, Integer hour, Integer dayType,
                                                String date) {
        String schema = (schemaName == null || schemaName.trim().isEmpty())
                ? DEFAULT_SCHEMA
                : schemaName.trim();
        String buildingKey = normalizeBuildingKey(buildingId);
        String cacheKey = schema + "|" + buildingKey;

        List<BuildingDataVO> all = cache.computeIfAbsent(cacheKey, k -> {
            try {
                return loadBuildingJoined(schema, buildingKey);
            } catch (IOException e) {
                log.error("加载本地数据集失败 schema={} building={}", schema, buildingKey, e);
                throw new RuntimeException("加载本地数据集失败: " + e.getMessage(), e);
            }
        });

        // 先按墙钟当前整点截断并写入 date，再套用筛选条件
        String dateKey = (date == null || date.trim().isEmpty()) ? null : date.trim();
        List<BuildingDataVO> untilNow = filterNotAfterNow(all);

        return untilNow.stream()
                .filter(row -> month == null || month.equals(row.getMonth()))
                .filter(row -> hour == null || hour.equals(row.getHour()))
                .filter(row -> dayType == null || dayType.equals(row.getDayType()))
                .filter(row -> dateKey == null || dateKey.equals(row.getDate()))
                .collect(Collectors.toList());
    }

    /** 兼容旧调用 */
    public List<BuildingDataVO> getBuildingRows(String buildingId, String schemaName,
                                                Integer month, Integer hour, Integer dayType) {
        return getBuildingRows(buildingId, schemaName, month, hour, dayType, null);
    }

    /**
     * 按 CSV 时序推算每行时刻，只保留 ≤ 当前墙钟整点 的行，并写入 date（YYYY-MM-DD）。
     * CityLearn Hour∈[1,24] 映射为当日 0–23 点；Day Type∈[1,7] 对齐周一–周日。
     */
    private List<BuildingDataVO> filterNotAfterNow(List<BuildingDataVO> all) {
        if (all == null || all.isEmpty()) {
            return all;
        }
        LocalDateTime until = LocalDateTime.now().withMinute(0).withSecond(0).withNano(0);
        LocalDateTime cursor = null;
        List<BuildingDataVO> out = new ArrayList<>();
        for (BuildingDataVO row : all) {
            cursor = nextRowDateTime(cursor, row, until);
            if (cursor == null) {
                continue;
            }
            if (cursor.isAfter(until)) {
                break;
            }
            row.setDate(cursor.toLocalDate().toString());
            out.add(row);
        }
        return out;
    }

    private static LocalDateTime nextRowDateTime(LocalDateTime cursor, BuildingDataVO row, LocalDateTime until) {
        if (cursor != null) {
            return cursor.plusHours(1);
        }
        Integer month = row.getMonth();
        Integer hour = row.getHour();
        if (month == null || month < 1 || month > 12 || hour == null) {
            return null;
        }
        int clockHour = cityLearnHourToClock(hour);
        Integer dayType = row.getDayType();
        int year = until.getYear();
        LocalDateTime start = resolveStartDateTime(year, month, dayType, clockHour);
        // 若按今年推算已晚于当前时刻，则改用去年（跨年演示）
        if (start != null && start.isAfter(until)) {
            start = resolveStartDateTime(year - 1, month, dayType, clockHour);
        }
        return start;
    }

    private static LocalDateTime resolveStartDateTime(int year, int month, Integer dayType, int clockHour) {
        LocalDate day = LocalDate.of(year, month, 1);
        if (dayType != null && dayType >= 1 && dayType <= 7) {
            DayOfWeek target = DayOfWeek.of(dayType);
            int guard = 0;
            while (day.getDayOfWeek() != target && guard < 7) {
                day = day.plusDays(1);
                guard++;
            }
        }
        return LocalDateTime.of(day, LocalTime.of(clockHour, 0));
    }

    /** CityLearn hour 1–24 → 时钟 0–23（1=00:00 … 24=23:00） */
    private static int cityLearnHourToClock(int hour) {
        int h = Math.max(1, Math.min(24, hour));
        return h - 1;
    }

    public void clearCache() {
        cache.clear();
    }

    private List<BuildingDataVO> loadBuildingJoined(String schema, String buildingKey) throws IOException {
        Path schemaDir = citylearnDatasetService.resolveDatasetDir(schema);
        Path buildingFile = schemaDir.resolve(buildingFileName(buildingKey));
        Path weatherFile = schemaDir.resolve("weather.csv");
        Path pricingFile = schemaDir.resolve("pricing.csv");
        Path carbonFile = schemaDir.resolve("carbon_intensity.csv");

        if (!Files.isRegularFile(buildingFile)) {
            throw new IOException("找不到建筑文件: " + buildingFile);
        }

        List<Map<String, String>> buildingRows = readCsvMaps(buildingFile);
        List<Map<String, String>> weatherRows = Files.isRegularFile(weatherFile)
                ? readCsvMaps(weatherFile) : Collections.emptyList();
        List<Map<String, String>> pricingRows = Files.isRegularFile(pricingFile)
                ? readCsvMaps(pricingFile) : Collections.emptyList();
        List<Map<String, String>> carbonRows = Files.isRegularFile(carbonFile)
                ? readCsvMaps(carbonFile) : Collections.emptyList();

        List<BuildingDataVO> out = new ArrayList<>(buildingRows.size());
        for (int i = 0; i < buildingRows.size(); i++) {
            Map<String, String> b = buildingRows.get(i);
            Map<String, String> w = i < weatherRows.size() ? weatherRows.get(i) : Collections.emptyMap();
            Map<String, String> p = i < pricingRows.size() ? pricingRows.get(i) : Collections.emptyMap();
            Map<String, String> c = i < carbonRows.size() ? carbonRows.get(i) : Collections.emptyMap();
            out.add(toVo(buildingKey, i + 1, b, w, p, c));
        }
        log.info("已加载本地数据集 schema={} building={} rows={} dir={}",
                schema, buildingKey, out.size(), schemaDir);
        return out;
    }

    private BuildingDataVO toVo(String buildingKey, int id,
                                Map<String, String> b,
                                Map<String, String> w,
                                Map<String, String> p,
                                Map<String, String> c) {
        BuildingDataVO vo = new BuildingDataVO();
        vo.setId(id);
        vo.setBuildingId(buildingKey);

        vo.setMonth(asInt(first(b, "Month", "month")));
        vo.setHour(asInt(first(b, "Hour", "hour")));
        vo.setDayType(asInt(first(b, "Day Type", "day_type", "DayType")));
        vo.setDaylightSavingsStatus(asInt(first(b,
                "Daylight Savings Status", "daylight_savings_status")));

        vo.setIndoorDryBulbTemperature(asDec(first(b,
                "Indoor Temperature (C)", "indoor_dry_bulb_temperature")));
        vo.setAverageUnmetCoolingSetpointDifference(asDec(first(b,
                "Average Unmet Cooling Setpoint Difference (C)",
                "average_unmet_cooling_setpoint_difference")));
        vo.setIndoorRelativeHumidity(asDec(first(b,
                "Indoor Relative Humidity (%)", "indoor_relative_humidity")));
        vo.setNonShiftableLoad(asDec(first(b,
                "Equipment Electric Power (kWh)",
                "non_shiftable_load",
                "Non-shiftable Load")));
        vo.setDhwDemand(asDec(first(b, "DHW Heating (kWh)", "dhw_demand")));
        vo.setCoolingDemand(asDec(first(b, "Cooling Load (kWh)", "cooling_demand")));
        vo.setHeatingDemand(asDec(first(b, "Heating Load (kWh)", "heating_demand")));
        vo.setSolarGeneration(asDec(first(b,
                "Solar Generation (W/kW)", "solar_generation")));
        vo.setOccupantCount(asInt(first(b, "Occupant Count (people)", "occupant_count")));

        BigDecimal setPoint = asDec(first(b,
                "Temperature Set Point (C)",
                "indoor_dry_bulb_temperature_cooling_set_point",
                "indoor_dry_bulb_temperature_set_point"));
        BigDecimal coolSp = asDec(first(b, "indoor_dry_bulb_temperature_cooling_set_point"));
        BigDecimal heatSp = asDec(first(b, "indoor_dry_bulb_temperature_heating_set_point"));
        vo.setIndoorDryBulbTemperatureCoolingSetPoint(coolSp != null ? coolSp : setPoint);
        vo.setIndoorDryBulbTemperatureHeatingSetPoint(heatSp != null ? heatSp : setPoint);
        vo.setHvacMode(asInt(first(b, "HVAC Mode (Off/Cooling/Heating)", "hvac_mode")));

        vo.setCarbonIntensity(asDec(first(c, "kg_CO2/kWh", "carbon_intensity")));

        vo.setElectricityPricing(asDec(first(p,
                "Electricity Pricing [$/kWh]", "electricity_pricing")));
        vo.setElectricityPricingPredicted1(asDec(first(p,
                "6h Prediction Electricity Pricing [$/kWh]",
                "electricity_pricing_predicted_6h")));
        vo.setElectricityPricingPredicted2(asDec(first(p,
                "12h Prediction Electricity Pricing [$/kWh]",
                "electricity_pricing_predicted_12h")));
        vo.setElectricityPricingPredicted3(asDec(first(p,
                "24h Prediction Electricity Pricing [$/kWh]",
                "electricity_pricing_predicted_24h")));

        vo.setOutdoorDryBulbTemperature(asDec(first(w,
                "Outdoor Drybulb Temperature (C)", "outdoor_dry_bulb_temperature")));
        vo.setOutdoorRelativeHumidity(asDec(first(w,
                "Outdoor Relative Humidity (%)", "outdoor_relative_humidity")));
        vo.setDiffuseSolarIrradiance(asDec(first(w,
                "Diffuse Solar Radiation (W/m2)", "diffuse_solar_irradiance")));
        vo.setDirectSolarIrradiance(asDec(first(w,
                "Direct Solar Radiation (W/m2)", "direct_solar_irradiance")));

        vo.setOutdoorDryBulbTemperaturePredicted1(asDec(first(w,
                "6h Outdoor Drybulb Temperature (C)",
                "outdoor_dry_bulb_temperature_predicted_6h")));
        vo.setOutdoorDryBulbTemperaturePredicted2(asDec(first(w,
                "12h Outdoor Drybulb Temperature (C)",
                "outdoor_dry_bulb_temperature_predicted_12h")));
        vo.setOutdoorDryBulbTemperaturePredicted3(asDec(first(w,
                "24h Outdoor Drybulb Temperature (C)",
                "outdoor_dry_bulb_temperature_predicted_24h")));

        vo.setOutdoorRelativeHumidityPredicted1(asDec(first(w,
                "6h Outdoor Relative Humidity (%)",
                "outdoor_relative_humidity_predicted_6h")));
        vo.setOutdoorRelativeHumidityPredicted2(asDec(first(w,
                "12h Outdoor Relative Humidity (%)",
                "outdoor_relative_humidity_predicted_12h")));
        vo.setOutdoorRelativeHumidityPredicted3(asDec(first(w,
                "24h Outdoor Relative Humidity (%)",
                "outdoor_relative_humidity_predicted_24h")));

        vo.setDiffuseSolarIrradiancePredicted1(asDec(first(w,
                "6h Diffuse Solar Radiation (W/m2)",
                "diffuse_solar_irradiance_predicted_6h")));
        vo.setDiffuseSolarIrradiancePredicted2(asDec(first(w,
                "12h Diffuse Solar Radiation (W/m2)",
                "diffuse_solar_irradiance_predicted_12h")));
        vo.setDiffuseSolarIrradiancePredicted3(asDec(first(w,
                "24h Diffuse Solar Radiation (W/m2)",
                "diffuse_solar_irradiance_predicted_24h")));

        vo.setDirectSolarIrradiancePredicted1(asDec(first(w,
                "6h Direct Solar Radiation (W/m2)",
                "direct_solar_irradiance_predicted_6h")));
        vo.setDirectSolarIrradiancePredicted2(asDec(first(w,
                "12h Direct Solar Radiation (W/m2)",
                "direct_solar_irradiance_predicted_12h")));
        vo.setDirectSolarIrradiancePredicted3(asDec(first(w,
                "24h Direct Solar Radiation (W/m2)",
                "direct_solar_irradiance_predicted_24h")));

        return vo;
    }

    private static String normalizeBuildingKey(String buildingId) {
        if (buildingId == null || buildingId.trim().isEmpty()) {
            return "building1";
        }
        String s = buildingId.trim().toLowerCase(Locale.ROOT).replace("-", "").replace("_", "");
        if (s.equals("building1") || s.equals("b1") || s.equals("1")) return "building1";
        if (s.equals("building2") || s.equals("b2") || s.equals("2")) return "building2";
        if (s.equals("building3") || s.equals("b3") || s.equals("3")) return "building3";
        // building_1 风格
        String raw = buildingId.trim().toLowerCase(Locale.ROOT);
        if (raw.matches("building[_]?\\d+")) {
            String n = raw.replaceAll("\\D+", "");
            return "building" + n;
        }
        return "building1";
    }

    private static String buildingFileName(String buildingKey) {
        // building1 -> Building_1.csv
        String n = buildingKey.replaceAll("\\D+", "");
        return "Building_" + n + ".csv";
    }

    private static List<Map<String, String>> readCsvMaps(Path file) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                return Collections.emptyList();
            }
            if (headerLine.startsWith("\uFEFF")) {
                headerLine = headerLine.substring(1);
            }
            String[] headers = splitCsvLine(headerLine);
            List<Map<String, String>> rows = new ArrayList<>();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] cols = splitCsvLine(line);
                Map<String, String> map = new LinkedHashMap<>();
                for (int i = 0; i < headers.length; i++) {
                    String key = headers[i] == null ? "" : headers[i].trim();
                    String val = i < cols.length ? cols[i].trim() : "";
                    map.put(key, val);
                }
                rows.add(map);
            }
            return rows;
        }
    }

    private static String[] splitCsvLine(String line) {
        // 数据集表头不含引号逗号嵌套，简单 split 即可
        return line.split(",", -1);
    }

    private static String first(Map<String, String> row, String... keys) {
        if (row == null || row.isEmpty()) return null;
        for (String key : keys) {
            if (row.containsKey(key)) {
                String v = row.get(key);
                if (v != null && !v.isEmpty()) return v;
            }
        }
        // 忽略大小写兜底
        Map<String, String> lower = new HashMap<>();
        for (Map.Entry<String, String> e : row.entrySet()) {
            if (e.getKey() != null) {
                lower.put(e.getKey().toLowerCase(Locale.ROOT), e.getValue());
            }
        }
        for (String key : keys) {
            String v = lower.get(key.toLowerCase(Locale.ROOT));
            if (v != null && !v.isEmpty()) return v;
        }
        return null;
    }

    private static Integer asInt(String s) {
        if (s == null || s.trim().isEmpty()) return null;
        try {
            return (int) Math.round(Double.parseDouble(s.trim()));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static BigDecimal asDec(String s) {
        if (s == null || s.trim().isEmpty()) return null;
        try {
            return new BigDecimal(s.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
