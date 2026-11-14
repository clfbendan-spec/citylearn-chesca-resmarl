package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class NoControlScoreTest {
    @TempDir Path root;

    private Path writeEvidence(String task, JSONObject result) throws Exception {
        Path dir = Files.createDirectories(root.resolve(task));
        result.put("task_id", task);
        Map<String, Object> artifacts = new LinkedHashMap<>();
        for (var entry : Map.of("evaluation_result.json", result,
                "score_result.json", Map.of("status", "unavailable"),
                "decision_trace.json", Map.of("steps", new Object[0])).entrySet()) {
            byte[] bytes = JSON.toJSONBytes(entry.getValue());
            Files.write(dir.resolve(entry.getKey()), bytes);
            artifacts.put(entry.getKey(), Map.of("sha256", HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes))));
        }
        Files.writeString(dir.resolve("evaluation_manifest.json"), JSON.toJSONString(Map.of(
                "task_id", task, "algorithm", result.getString("algorithm"), "protocol", result.get("protocol"),
                "artifacts", artifacts, "artifact_status", "complete", "validation", Map.of("valid", true),
                "coverage", Map.of("terminated", true, "truncated", false, "expected_transitions", 1000, "recorded_transitions", 1000))));
        return dir;
    }

    @Test void dashboardFindsVerifiedBaselineWithoutAnAnchorAndRejectsChangedEvidence() throws Exception {
        var candidate = result(90, .06);
        candidate.put("algorithm", "District-MARL");
        Path task = writeEvidence("candidate", candidate);
        var service = new EvaluationAnalysisService();
        assertEquals("unavailable", ((Map<?, ?>) service.read(task, "candidate").get("nocontrolScore")).get("status"));
        Path base = writeEvidence("baseline", result(100, .06));
        assertEquals(10., (double) ((Map<?, ?>) service.read(task, "candidate").get("nocontrolScore")).get("score"), 1e-9);
        writeEvidence("duplicate", result(100, .06));
        assertEquals("available", ((Map<?, ?>) service.read(task, "candidate").get("nocontrolScore")).get("status"));
        writeEvidence("conflicting", result(110, .06));
        assertEquals("unavailable", ((Map<?, ?>) service.read(task, "candidate").get("nocontrolScore")).get("status"));
        Files.writeString(base.resolve("evaluation_result.json"), "{}");
        assertEquals("unavailable", service.read(base, "baseline").get("status"));
    }
    private JSONObject result(double bill, double discomfort) {
        JSONObject protocol = new JSONObject();
        for (String field : new String[]{"dataset_files_sha256", "equipment_sha256", "initial_state_sha256",
                "evaluator_version", "cost_definition", "warmup", "action_contract", "environment_step_order", "outage_model_sha256"})
            protocol.put(field, "fixed");
        protocol.put("building_ids", JSON.parseArray("[\"B1\"]"));
        protocol.put("simulation_window", JSON.parseArray("[0,1000]"));
        protocol.put("seconds_per_time_step", 3600);
        JSONObject out = new JSONObject();
        out.put("algorithm", "NoControl");
        out.put("task_id", "baseline");
        out.put("protocol", protocol);
        out.put("per_building", JSON.toJSON(Map.of("B1", Map.of("positive_bill", bill,
                "occupied_samples", 1000, "discomfort_proportion", discomfort))));
        return out;
    }

    @Test void savingsAndComfortImprovementIncreaseScore() {
        var baseline = result(100, .06);
        assertEquals(0., (double) NoControlScore.compute(baseline, baseline).get("score"), 1e-9);
        assertEquals(3., (double) NoControlScore.compute(result(102, .05), baseline).get("score"), 1e-9);
        assertEquals(10., (double) NoControlScore.compute(result(90, .06), baseline).get("score"), 1e-9);
        assertEquals(-10., (double) NoControlScore.compute(result(70, .11), baseline).get("score"), 1e-9);
    }

    @Test void comfortGateRemainsStrictEvenForPositiveScore() {
        var score = NoControlScore.compute(result(50, .10), result(100, .06));
        assertEquals(20., (double) score.get("score"), 1e-9);
        assertEquals(false, score.get("rankable"));
        assertEquals(false, score.get("comfort_qualified"));
    }

    @Test void piecewiseBoundariesStayContinuous() {
        assertEquals(3., NoControlScore.penalty(3));
        assertEquals(9., NoControlScore.penalty(5));
        assertEquals(24., NoControlScore.penalty(8));
        assertEquals(44., NoControlScore.penalty(10));
        assertThrows(IllegalArgumentException.class, () -> NoControlScore.penalty(101));
    }

    @Test void unknownOrMismatchedEvidenceNeverBecomesZero() {
        var baseline = result(100, .06);
        assertEquals("unavailable", NoControlScore.compute(result(50, .05), null).get("status"));
        assertEquals("unavailable", NoControlScore.compute(result(50, .05), result(0, .06)).get("status"));
        var current = result(50, .05);
        current.getJSONObject("per_building").getJSONObject("B1").put("occupied_samples", 0);
        assertEquals("unavailable", NoControlScore.compute(current, baseline).get("status"));
        current = result(50, .05);
        current.getJSONObject("protocol").put("initial_state_sha256", "changed");
        assertEquals("unavailable", NoControlScore.compute(current, baseline).get("status"));
        current = result(50, .05);
        current.getJSONObject("protocol").put("information_access", "forecast");
        assertEquals("available", NoControlScore.compute(current, baseline).get("status"));
    }

    @Test void districtUsesEqualBuildingWeightsRatherThanTotalBillRatio() {
        var baseline = result(100, .06);
        var current = result(90, .06);
        for (var item : new JSONObject[]{baseline, current}) {
            item.getJSONObject("protocol").put("building_ids", JSON.parseArray("[\"B1\",\"B2\"]"));
            item.getJSONObject("per_building").put("B2", JSON.toJSON(Map.of("positive_bill", 1000,
                    "occupied_samples", 1000, "discomfort_proportion", .06)));
        }
        assertEquals(5., (double) NoControlScore.compute(current, baseline).get("score"), 1e-9);
    }
}
