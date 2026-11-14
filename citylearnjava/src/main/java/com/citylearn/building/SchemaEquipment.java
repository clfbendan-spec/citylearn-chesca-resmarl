package com.citylearn.building;

import java.util.*;

/** Supported CityLearn equipment definitions; class names are deliberately restricted. */
public final class SchemaEquipment {
    public static final Map<String,String> TYPES = new LinkedHashMap<>();
    static {
        TYPES.put("electrical_storage", "Battery"); TYPES.put("pv", "PV");
        TYPES.put("cooling_device", "HeatPump"); TYPES.put("heating_device", "HeatPump");
        TYPES.put("dhw_device", "ElectricHeater");
        for (String key : List.of("cooling_storage", "heating_storage", "dhw_storage")) TYPES.put(key, "StorageTank");
    }
    private static final Set<String> STORAGE = Set.of("capacity", "efficiency", "loss_coefficient", "initial_soc");
    private SchemaEquipment() { }

    public static Map<String,Object> normalize(Object input) {
        if (!(input instanceof Map)) throw new IllegalArgumentException("devices 必须是设备配置对象");
        Map<?,?> devices = (Map<?,?>) input;
        Map<String,Object> output = new LinkedHashMap<>();
        for (Map.Entry<?,?> entry : devices.entrySet()) {
            String key = entry.getKey().toString();
            if (!TYPES.containsKey(key) || !(entry.getValue() instanceof Map)) throw new IllegalArgumentException("不支持的设备: " + key);
            Map<?,?> device = (Map<?,?>) entry.getValue();
            String equipmentType = TYPES.get(key);
            if (key.equals("heating_device") && "citylearn.energy_model.ElectricHeater".equals(device.get("type"))) equipmentType = "ElectricHeater";
            String type = "citylearn.energy_model." + equipmentType;
            if (!type.equals(device.get("type"))) throw new IllegalArgumentException("设备类型不匹配: " + key);
            if (!Set.of("type", "attributes", "autosize", "autosize_attributes").containsAll(device.keySet())) throw new IllegalArgumentException("未知设备配置: " + key);
            if (!(device.get("attributes") instanceof Map)) throw new IllegalArgumentException("缺少 attributes: " + key);
            if (device.containsKey("autosize") && !(device.get("autosize") instanceof Boolean)) throw new IllegalArgumentException("autosize 必须为布尔值");
            if (key.equals("pv") && Boolean.TRUE.equals(device.get("autosize"))) throw new IllegalArgumentException("光伏自动定容需要 EPW 气象文件，当前请设置 autosize=false 并填写 nominal_power");
            Map<?,?> attributes = (Map<?,?>) device.get("attributes");
            Set<String> allowed = new HashSet<>();
            switch (equipmentType) {
                case "Battery": allowed.addAll(STORAGE); allowed.addAll(List.of("nominal_power", "capacity_loss_coefficient", "depth_of_discharge", "power_efficiency_curve", "capacity_power_curve")); break;
                case "PV": allowed.add("nominal_power"); break;
                case "HeatPump": allowed.addAll(List.of("nominal_power", "efficiency", "target_cooling_temperature", "target_heating_temperature")); break;
                case "ElectricHeater": allowed.addAll(List.of("nominal_power", "efficiency")); break;
                case "StorageTank": allowed.addAll(STORAGE); allowed.addAll(List.of("max_input_power", "max_output_power")); break;
                default: throw new IllegalArgumentException("不支持的设备类型");
            }
            if (!allowed.containsAll(attributes.keySet())) throw new IllegalArgumentException("未知设备属性: " + key);
            for (Map.Entry<?,?> attribute : attributes.entrySet()) {
                String field = attribute.getKey().toString();
                if (field.endsWith("_curve")) { curve(attribute.getValue(), field); continue; }
                double number = number(attribute.getValue(), key + "." + field);
                double min = field.startsWith("target_") ? -100 : 0;
                double max = field.startsWith("target_") ? 150 : List.of("efficiency", "loss_coefficient", "capacity_loss_coefficient", "initial_soc", "depth_of_discharge").contains(field) ? 1 : 1e8;
                if (number < min || number > max || (List.of("efficiency", "depth_of_discharge").contains(field) && number == 0)) throw new IllegalArgumentException("设备参数超出范围: " + key + "." + field);
            }
            String required = key.endsWith("storage") ? "capacity" : "nominal_power";
            if (!attributes.containsKey(required)) throw new IllegalArgumentException("设备参数必填: " + key + "." + required);
            if (key.equals("electrical_storage") && (!attributes.containsKey("nominal_power") || number(attributes.get("capacity"), "capacity") <= 0 || number(attributes.get("nominal_power"), "nominal_power") <= 0)) throw new IllegalArgumentException("电池容量和额定功率必须大于 0");
            if (device.containsKey("autosize_attributes")) {
                if (!(device.get("autosize_attributes") instanceof Map)) throw new IllegalArgumentException("autosize_attributes 必须是对象");
                Map<?,?> sizing = (Map<?,?>)device.get("autosize_attributes");
                if (!Set.of("safety_factor").containsAll(sizing.keySet())) throw new IllegalArgumentException("仅支持 safety_factor 自动定容参数");
                if (sizing.containsKey("safety_factor") && number(sizing.get("safety_factor"), "safety_factor") <= 0) throw new IllegalArgumentException("safety_factor 必须大于 0");
            }
            output.put(key, new LinkedHashMap<>(device));
        }
        return output;
    }
    private static double number(Object value, String field) {
        if (!(value instanceof Number) || !Double.isFinite(((Number)value).doubleValue())) throw new IllegalArgumentException("设备参数必须是有限数值: " + field);
        return ((Number)value).doubleValue();
    }
    private static void curve(Object value, String field) {
        if (!(value instanceof List) || ((List<?>)value).size() < 2 || ((List<?>)value).size() > 100) throw new IllegalArgumentException("曲线需要 2–100 个 [x,y] 点: " + field);
        List<?> points = (List<?>)value;
        double previous = -1;
        for (Object point : points) {
            if (!(point instanceof List) || ((List<?>)point).size() != 2) throw new IllegalArgumentException("曲线点必须是 [x,y]");
            double x = number(((List<?>)point).get(0), field), y = number(((List<?>)point).get(1), field);
            if (x <= previous || x < 0 || x > 1 || y < 0 || y > 1 || (field.equals("power_efficiency_curve") && y == 0)) throw new IllegalArgumentException("曲线横坐标应递增且坐标须在有效范围内: " + field);
            previous = x;
        }
        if (number(((List<?>)points.get(0)).get(0), field) != 0 || previous != 1) throw new IllegalArgumentException("曲线横坐标必须覆盖 0–1: " + field);
    }
}
