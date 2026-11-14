package com.citylearn.building;

import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;

/** Canonical measurements use interval energy, not instantaneous meter power. */
public class MeasurementContract {
    public static final Map<String, Map<String, Object>> FIELDS = new LinkedHashMap<>();
    public static final Set<String> ENERGY = Set.of("non_shiftable_load", "cooling_demand", "heating_demand", "dhw_demand");
    public static final Set<String> CATEGORY = Set.of("month", "hour", "day_type", "daylight_savings_status", "hvac_mode");
    public static final Set<String> REQUIRED;
    static {
        field("non_shiftable_load", "不可移峰用电", "kWh", 0, 1e8);
        field("cooling_demand", "制冷需求", "kWh", 0, 1e8);
        field("heating_demand", "供热需求", "kWh", 0, 1e8);
        field("dhw_demand", "生活热水需求", "kWh", 0, 1e8);
        field("solar_generation", "单位装机光伏输出", "W/kW", 0, 2000);
        field("indoor_dry_bulb_temperature", "室内温度", "C", -60, 80);
        field("indoor_relative_humidity", "室内相对湿度", "%", 0, 100);
        field("occupant_count", "占用人数", "person", 0, 1e6);
        field("indoor_dry_bulb_temperature_cooling_set_point", "制冷设定温度", "C", -60, 80);
        field("indoor_dry_bulb_temperature_heating_set_point", "供热设定温度", "C", -60, 80);
        field("outdoor_dry_bulb_temperature", "室外温度", "C", -90, 80);
        field("outdoor_relative_humidity", "室外相对湿度", "%", 0, 100);
        field("diffuse_solar_irradiance", "散射辐照度", "W/m2", 0, 2000);
        field("direct_solar_irradiance", "直射辐照度", "W/m2", 0, 2000);
        field("electricity_pricing", "购电电价", "currency/kWh", -100, 10000);
        field("carbon_intensity", "电网碳强度", "kgCO2/kWh", 0, 100);
        REQUIRED = Collections.unmodifiableSet(new LinkedHashSet<>(FIELDS.keySet()));
        field("month", "月份", "category", 1, 12);
        field("hour", "小时（1–24）", "category", 1, 24);
        field("day_type", "星期/特殊日（1–7周一至周日，8特殊日）", "category", 1, 8);
        field("daylight_savings_status", "夏令时状态", "category", 0, 1);
        field("hvac_mode", "空调模式（0关闭、1制冷、2供热、3自动）", "category", 0, 3);
        field("average_unmet_cooling_setpoint_difference", "平均制冷设定温差", "C", -200, 200);
        for (String base : List.of("outdoor_dry_bulb_temperature", "outdoor_relative_humidity", "diffuse_solar_irradiance", "direct_solar_irradiance", "electricity_pricing")) {
            Map<String,Object> definition = FIELDS.get(base);
            for (int i=1;i<=3;i++) {
                int hours = new int[]{6,12,24}[i-1];
                String key=base+"_predicted_"+i;
                field(key, definition.get("label")+" · "+hours+"小时预测", definition.get("unit").toString(),
                        ((Number)definition.get("min")).doubleValue(), ((Number)definition.get("max")).doubleValue());
                FIELDS.get(key).put("forecastHours", hours);
            }
        }
    }
    private static void field(String key, String label, String unit, double min, double max) {
        FIELDS.put(key, new LinkedHashMap<>(Map.of("key", key, "label", label, "unit", unit, "min", min, "max", max,
                "required", FIELDS.size()<16, "aggregation", CATEGORY.contains(key)?"constant":ENERGY.contains(key)?"sum":"mean")));
    }

    public Instant timestamp(Object value, ZoneId zone) {
        if (value == null) throw new IllegalArgumentException("缺少 timestamp");
        String text = value.toString().trim().replace(' ', 'T');
        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (java.time.format.DateTimeParseException ignored) {
            try {
                LocalDateTime local = LocalDateTime.parse(text);
                List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
                if (offsets.size() != 1) throw new IllegalArgumentException("夏令时时间有歧义或不存在，请携带 UTC 偏移: " + text);
                return local.toInstant(offsets.get(0));
            } catch (java.time.format.DateTimeParseException e) {
                throw new IllegalArgumentException("无效时间戳，请使用 ISO 8601: " + text);
            }
        }
    }

    public Map<String, Object> normalize(Map<String, Object> raw, ZoneId zone, int interval,
                                          Map<String, String> mapping, Map<String, String> units) {
        if (!List.of(60, 300, 900, 1800, 3600).contains(interval)) throw new IllegalArgumentException("不支持的采样周期");
        for (String key : mapping.keySet()) {
            if (!key.equals("timestamp") && !FIELDS.containsKey(key)) throw new IllegalArgumentException("未知映射字段: " + key);
        }
        Instant instant = timestamp(raw.get(mapping.getOrDefault("timestamp", "timestamp")), zone);
        if (instant.getNano() != 0 || Math.floorMod(instant.getEpochSecond(), interval) != 0)
            throw new IllegalArgumentException("时间戳必须对齐采样周期: " + instant);
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("timestamp", instant.toString());
        for (Map.Entry<String, Map<String, Object>> field : FIELDS.entrySet()) {
            String key = field.getKey();
            Object value = raw.get(mapping.getOrDefault(key, key));
            if (value == null || value.toString().trim().isEmpty()) continue;
            double number;
            try { number = Double.parseDouble(value.toString().trim()); }
            catch (NumberFormatException e) { throw new IllegalArgumentException("字段不是数值: " + key); }
            String unit = units.getOrDefault(key, field.getValue().get("unit").toString());
            if (ENERGY.contains(key)) {
                if ("kW".equals(unit)) number *= interval / 3600.0;
                else if ("W".equals(unit)) number *= interval / 3600000.0;
                else if ("Wh".equals(unit)) number /= 1000.0;
                else if (!"kWh".equals(unit)) throw new IllegalArgumentException("不支持的能量单位: " + key + "=" + unit);
            } else if ("carbon_intensity".equals(key) && "gCO2/kWh".equals(unit)) {
                number /= 1000.0;
            } else if (!field.getValue().get("unit").equals(unit)) {
                throw new IllegalArgumentException("单位不匹配: " + key + "=" + unit);
            }
            double min = ((Number) field.getValue().get("min")).doubleValue();
            double max = ((Number) field.getValue().get("max")).doubleValue();
            if (!Double.isFinite(number) || number < min || number > max)
                throw new IllegalArgumentException("字段超出范围: " + key);
            if (CATEGORY.contains(key) && number != Math.rint(number)) throw new IllegalArgumentException("分类字段必须为整数: " + key);
            row.put(key, number == 0 ? 0.0 : number);
        }
        if (row.size() == 1) throw new IllegalArgumentException("至少需要一个有效测量字段");
        return row;
    }

    public List<Map<String, Object>> hourly(List<Map<String, Object>> rows, ZoneId zone, int interval) {
        if (rows.isEmpty()) throw new IllegalArgumentException("所选区间没有数据");
        Map<Instant, List<Map<String, Object>>> buckets = new TreeMap<>();
        Instant previous = null;
        for (Map<String, Object> row : rows) {
            Instant instant = timestamp(row.get("timestamp"), zone);
            if (previous != null && !previous.plusSeconds(interval).equals(instant))
                throw new IllegalArgumentException("存在缺口或重复时间: " + previous + " → " + instant);
            previous = instant;
            for (String field : REQUIRED) {
                if (!(row.get(field) instanceof Number)) throw new IllegalArgumentException("发布所需字段缺失: " + field + " @ " + instant);
            }
            Instant hour = instant.atZone(zone).truncatedTo(ChronoUnit.HOURS).toInstant();
            buckets.computeIfAbsent(hour, key -> new ArrayList<>()).add(row);
        }
        List<Map<String, Object>> hourly = new ArrayList<>();
        Set<String> present = new LinkedHashSet<>(REQUIRED);
        for (String field:FIELDS.keySet()) {
            long count=rows.stream().filter(row->row.containsKey(field)).count();
            if (count>0 && count!=rows.size()) throw new IllegalArgumentException("可选字段在所选时段存在缺失: "+field);
            if (count>0) present.add(field);
        }
        for (Map.Entry<Instant, List<Map<String, Object>>> bucket : buckets.entrySet()) {
            List<Map<String, Object>> samples = bucket.getValue();
            if (samples.size() != 3600 / interval || !samples.get(0).get("timestamp").equals(bucket.getKey().toString()))
                throw new IllegalArgumentException("小时采样不完整: " + bucket.getKey());
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("timestamp", bucket.getKey().toString());
            for (String field : present) {
                if (CATEGORY.contains(field)) {
                    double value=((Number)samples.get(0).get(field)).doubleValue();
                    if (samples.stream().anyMatch(s->((Number)s.get(field)).doubleValue()!=value))
                        throw new IllegalArgumentException("小时内分类字段不一致: "+field+" @ "+bucket.getKey());
                    row.put(field,value); continue;
                }
                double sum = samples.stream().mapToDouble(s -> ((Number) s.get(field)).doubleValue()).sum();
                row.put(field, ENERGY.contains(field) ? sum : sum / samples.size());
            }
            hourly.add(row);
        }
        if (hourly.size() < 2) throw new IllegalArgumentException("至少需要两个完整小时");
        return hourly;
    }
}
