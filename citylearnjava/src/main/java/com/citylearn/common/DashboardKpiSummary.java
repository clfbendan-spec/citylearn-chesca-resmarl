package com.citylearn.common;

import com.citylearn.vo.DashboardSimulationVO;
import java.util.Map;

/** Community-level values only; missing metrics are never inferred from buildings. */
public final class DashboardKpiSummary {
    private DashboardKpiSummary() {}

    public static void apply(DashboardSimulationVO target, Map<?, ?> metrics) {
        target.setDiscomfortProportion(number(metrics.get("discomfort_proportion")));
        target.setCostTotal(number(metrics.get("cost_total")));
    }

    private static Double number(Object raw) {
        if (raw == null || raw.toString().isBlank()) return null;
        try {
            double value = Double.parseDouble(raw.toString().trim());
            return Double.isFinite(value) ? value : null;
        } catch (NumberFormatException ignored) {
            return null;
        }
    }
}
