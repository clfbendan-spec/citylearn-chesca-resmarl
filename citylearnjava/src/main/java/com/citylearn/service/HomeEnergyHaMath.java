package com.citylearn.service;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * 对齐前端 energyFlowAggregate.js 的 HA 分摊与日累计。
 */
final class HomeEnergyHaMath {

    private HomeEnergyHaMath() {
    }

    static Map<String, Double> emptyFlow() {
        Map<String, Double> m = new HashMap<>();
        m.put("pv", 0d);
        m.put("gridIn", 0d);
        m.put("gridOut", 0d);
        m.put("batIn", 0d);
        m.put("batOut", 0d);
        m.put("home", 0d);
        m.put("nonShiftable", 0d);
        m.put("otherLoad", 0d);
        m.put("net", 0d);
        m.put("solarToHome", 0d);
        m.put("solarToGrid", 0d);
        m.put("solarToBattery", 0d);
        m.put("gridToHome", 0d);
        m.put("gridToBattery", 0d);
        m.put("batteryToHome", 0d);
        m.put("batteryToGrid", 0d);
        return m;
    }

    static void addHour(Map<String, Double> acc, double pvH, double gridInH, double gridOutH,
                        double batInH, double batOutH, double loadH) {
        acc.put("pv", acc.get("pv") + pvH);
        acc.put("gridIn", acc.get("gridIn") + gridInH);
        acc.put("gridOut", acc.get("gridOut") + gridOutH);
        acc.put("batIn", acc.get("batIn") + batInH);
        acc.put("batOut", acc.get("batOut") + batOutH);
        acc.put("nonShiftable", acc.get("nonShiftable") + loadH);

        Map<String, Double> step = computeHaConsumption(pvH, gridInH, gridOutH, batInH, batOutH);
        for (Map.Entry<String, Double> e : step.entrySet()) {
            acc.put(e.getKey(), acc.getOrDefault(e.getKey(), 0d) + e.getValue());
        }
    }

    static Map<String, Double> finalizeFlow(Map<String, Double> acc) {
        double home = acc.getOrDefault("home", 0d);
        double nonShiftable = acc.getOrDefault("nonShiftable", 0d);
        double otherLoad = home - nonShiftable;
        if (otherLoad < 0.05) {
            otherLoad = 0;
        }
        double loadShown = Math.min(nonShiftable, home);
        if (loadShown + otherLoad > home && home > 0) {
            otherLoad = Math.max(home - loadShown, 0);
        }
        Map<String, Double> out = new HashMap<>();
        for (Map.Entry<String, Double> e : acc.entrySet()) {
            out.put(e.getKey(), round3(e.getValue()));
        }
        out.put("nonShiftable", round3(loadShown));
        out.put("otherLoad", round3(otherLoad));
        out.put("home", round3(home));
        double gridIn = acc.getOrDefault("gridIn", 0d);
        double gridOut = acc.getOrDefault("gridOut", 0d);
        out.put("net", round3(gridIn - gridOut));
        return out;
    }

    static Map<String, Double> computeHaConsumption(double solar, double fromGrid, double toGrid,
                                                    double toBattery, double fromBattery) {
        double to_grid = Math.max(toGrid, 0);
        double to_battery = Math.max(toBattery, 0);
        double pv = Math.max(solar, 0);
        double from_grid = Math.max(fromGrid, 0);
        double from_battery = Math.max(fromBattery, 0);

        double used_total = from_grid + pv + from_battery - to_grid - to_battery;
        double used_total_remaining = Math.max(used_total, 0);
        double grid_to_battery = 0;

        double excessGridToBattery = Math.max(0, Math.min(to_battery, from_grid - used_total_remaining));
        grid_to_battery += excessGridToBattery;
        to_battery -= excessGridToBattery;
        from_grid -= excessGridToBattery;

        double solar_to_battery = Math.min(pv, to_battery);
        to_battery -= solar_to_battery;
        pv -= solar_to_battery;

        double solar_to_grid = Math.min(pv, to_grid);
        to_grid -= solar_to_grid;
        pv -= solar_to_grid;

        double battery_to_grid = Math.min(from_battery, to_grid);
        from_battery -= battery_to_grid;

        double grid_to_battery_2 = Math.min(from_grid, to_battery);
        grid_to_battery += grid_to_battery_2;
        from_grid -= grid_to_battery_2;

        double used_solar = Math.min(used_total_remaining, pv);
        used_total_remaining -= used_solar;

        double used_battery = Math.min(from_battery, used_total_remaining);
        used_total_remaining -= used_battery;

        double used_grid = Math.min(used_total_remaining, from_grid);

        Map<String, Double> m = new HashMap<>();
        m.put("solarToHome", used_solar);
        m.put("solarToGrid", solar_to_grid);
        m.put("solarToBattery", solar_to_battery);
        m.put("gridToHome", used_grid);
        m.put("gridToBattery", grid_to_battery);
        m.put("batteryToHome", used_battery);
        m.put("batteryToGrid", battery_to_grid);
        m.put("home", Math.max(used_total, 0));
        return m;
    }

    static double round3(double x) {
        return Math.round(x * 1000d) / 1000d;
    }

    static double parseDouble(String s) {
        if (s == null || s.isEmpty()) {
            return 0;
        }
        try {
            return Double.parseDouble(s.trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    static String normalizeTs(String ts, int datasetYear) {
        if (ts == null || ts.isEmpty()) {
            return "";
        }
        String s = ts.trim().replace('T', ' ');
        if (s.length() >= 19) {
            s = s.substring(0, 19);
        } else if (s.length() >= 16) {
            s = s.substring(0, 16) + ":00";
        } else if (s.length() >= 10) {
            s = s.substring(0, 10) + " 00:00:00";
        }
        if (s.length() >= 10) {
            return datasetYear + s.substring(4);
        }
        return s;
    }

    static String dayKey(String normalizedTs) {
        if (normalizedTs == null || normalizedTs.length() < 10) {
            return null;
        }
        return normalizedTs.substring(0, 10);
    }

    static boolean headerMatches(String header, String... keys) {
        if (header == null) {
            return false;
        }
        String h = header.toLowerCase(Locale.ROOT);
        for (String k : keys) {
            if (h.equals(k.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }
}
