package com.citylearn.service;

import com.alibaba.fastjson.JSONObject;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Dashboard score; historical training scores and rewards remain unchanged. */
public final class NoControlScore {
    private NoControlScore() {}
    private static final List<String> PHYSICAL_FIELDS = List.of(
            "dataset_files_sha256", "simulation_window", "seconds_per_time_step", "building_ids",
            "equipment_sha256", "initial_state_sha256", "evaluator_version", "cost_definition",
            "warmup", "action_contract", "environment_step_order", "outage_model_sha256");

    public static boolean comparable(JSONObject a, JSONObject b) {
        if (a == null || b == null) return false;
        return PHYSICAL_FIELDS.stream().allMatch(field -> a.get(field) != null
                && !"".equals(a.get(field)) && Objects.equals(a.get(field), b.get(field)));
    }

    public static Map<String, Object> unavailable(String reason) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", "unavailable");
        out.put("score", null);
        out.put("reason_codes", List.of(reason));
        out.put("formula_version", "nocontrol-cash-higher-v1");
        return out;
    }

    public static double penalty(double d) {
        if (!Double.isFinite(d) || d < 0 || d > 100) throw new IllegalArgumentException("invalid_discomfort");
        return Math.min(d, 3) + 3 * Math.min(Math.max(d - 3, 0), 2)
                + 5 * Math.min(Math.max(d - 5, 0), 3) + 10 * Math.max(d - 8, 0);
    }

    private static double number(JSONObject row, String key) {
        Object raw = row.get(key);
        if (!(raw instanceof Number)) throw new IllegalArgumentException("missing_or_invalid_metric:" + key);
        double value = ((Number) raw).doubleValue();
        if (!Double.isFinite(value) || value < 0) throw new IllegalArgumentException("missing_or_invalid_metric:" + key);
        return value;
    }

    public static Map<String, Object> compute(JSONObject result, JSONObject baseline) {
        if (baseline == null) return unavailable("missing_independent_nocontrol");
        try {
            if (!"NoControl".equals(baseline.getString("algorithm"))) return unavailable("reference_is_not_nocontrol");
            if (!comparable(result.getJSONObject("protocol"), baseline.getJSONObject("protocol")))
                return unavailable("incomparable_baseline_protocol");
            var names = result.getJSONObject("protocol").getJSONArray("building_ids").toJavaList(String.class);
            var current = result.getJSONObject("per_building");
            var reference = baseline.getJSONObject("per_building");
            if (names.isEmpty() || new java.util.HashSet<>(names).size() != names.size()
                    || !current.keySet().equals(new java.util.HashSet<>(names)) || !reference.keySet().equals(current.keySet()))
                return unavailable("incomparable_buildings");
            Map<String, Object> rows = new LinkedHashMap<>();
            double total = 0;
            boolean qualified = true;
            for (String name : names) {
                JSONObject row = current.getJSONObject(name), base = reference.getJSONObject(name);
                double count = number(row, "occupied_samples"), baseCount = number(base, "occupied_samples");
                if (count <= 0 || baseCount <= 0 || count != Math.rint(count) || baseCount != Math.rint(baseCount))
                    return unavailable("missing_occupied_samples:" + name);
                if (count != baseCount) return unavailable("incomparable_occupied_samples:" + name);
                double bill = number(row, "positive_bill"), baseBill = number(base, "positive_bill");
                if (baseBill == 0) return unavailable("zero_nocontrol_bill:" + name);
                double d = number(row, "discomfort_proportion"), d0 = number(base, "discomfort_proportion");
                double p = penalty(100 * d), p0 = penalty(100 * d0);
                double cost = 100 * (1 - bill / baseBill), comfort = p0 - p, score = cost + comfort;
                if (!Double.isFinite(score)) return unavailable("nonfinite_score");
                Map<String, Object> detail = new LinkedHashMap<>();
                detail.put("positive_bill", bill);
                detail.put("baseline_positive_bill", baseBill);
                detail.put("discomfort_proportion", d);
                detail.put("baseline_discomfort_proportion", d0);
                detail.put("penalty", p);
                detail.put("baseline_penalty", p0);
                detail.put("cost_term", cost);
                detail.put("comfort_term", comfort);
                detail.put("score", score);
                detail.put("comfort_qualified", d < .10);
                rows.put(name, detail);
                total += score / names.size();
                qualified &= d < .10;
            }
            if (!Double.isFinite(total)) return unavailable("nonfinite_score");
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("status", "available");
            out.put("formula_version", "nocontrol-cash-higher-v1");
            out.put("score", total);
            out.put("higher_is_better", true);
            out.put("alpha", 1);
            out.put("reference_id", baseline.getString("task_id"));
            out.put("comfort_qualified", qualified);
            out.put("rankable", qualified);
            out.put("reason_codes", qualified ? List.of() : List.of("comfort_gate_failed"));
            out.put("per_building", rows);
            return out;
        } catch (IllegalArgumentException | NullPointerException | ClassCastException e) {
            return unavailable(e instanceof IllegalArgumentException ? e.getMessage() : "malformed_evidence");
        }
    }
}
