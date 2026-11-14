package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class EvaluationAnalysisServiceTest {
    @TempDir Path root;

    private Map<String, Object> fixture() throws Exception {
        Map<String, Object> protocol = Map.of("building_ids", new String[]{"B1"}, "simulation_window", new int[]{0, 2});
        Map<String, Object> result = Map.of("task_id", "owned-eval", "protocol", protocol,
                "per_building", Map.of("B1", Map.of("cost_total", .8, "discomfort_proportion", .04)));
        Map<String, Object> score = Map.of("status", "unavailable", "reason_codes", new String[]{"missing_anchor"});
        Map<String, Object> advice = Map.of("markdown", "Local evidence", "evidence", Map.of("task_id", "owned-eval"));
        Map<String, Object> trace = Map.of("steps", new Object[]{
                Map.of("step", 0, "terminated", false), Map.of("step", 1, "terminated", true)});
        Map<String, Object> artifacts = new LinkedHashMap<>();
        for (var entry : Map.of("evaluation_result.json", result, "score_result.json", score,
                "ai_analysis_bundle.json", advice, "decision_trace.json", trace).entrySet()) {
            byte[] bytes = JSON.toJSONBytes(entry.getValue());
            Files.write(root.resolve(entry.getKey()), bytes);
            artifacts.put(entry.getKey(), Map.of("sha256",
                    HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)), "bytes", bytes.length));
        }
        Map<String, Object> manifest = new LinkedHashMap<>(Map.of("task_id", "owned-eval",
                "protocol", protocol, "artifacts", artifacts, "artifact_status", "complete",
                "validation", Map.of("valid", true),
                "coverage", Map.of("terminated", true, "truncated", false,
                        "expected_transitions", 2, "recorded_transitions", 2)));
        Files.writeString(root.resolve("evaluation_manifest.json"), JSON.toJSONString(manifest));
        return manifest;
    }

    @Test void legacyRecordsStayExplicitlyUnavailable() throws Exception {
        var analysis = new EvaluationAnalysisService().read(root, "legacy");
        assertEquals("unavailable", analysis.get("status"));
        assertEquals("missing_evaluation_manifest", analysis.get("reason"));
        assertFalse(analysis.containsKey("score"));
    }

    @Test void verifiedTaskEvidenceIsReturnedWithoutInventingAnAnchor() throws Exception {
        fixture();
        var analysis = new EvaluationAnalysisService().read(root, "owned-eval");
        assertEquals("available", analysis.get("status"));
        Map<?, ?> score = (Map<?, ?>) analysis.get("score");
        assertEquals("unavailable", score.get("status"));
        assertNull(score.get("score"));
        assertTrue(((Map<?, ?>) analysis.get("result")).containsKey("per_building"));
        assertEquals("Local evidence", ((Map<?, ?>) analysis.get("advice")).get("markdown"));
    }

    @Test void changedOrCrossTaskEvidenceIsNeverPresentedAsVerified() throws Exception {
        fixture();
        assertEquals("task_identity_mismatch", new EvaluationAnalysisService().read(root, "another-eval").get("reason"));
        Files.writeString(root.resolve("score_result.json"), "{\"status\":\"available\",\"score\":-999}");
        assertEquals("artifact_hash_mismatch:score_result.json",
                new EvaluationAnalysisService().read(root, "owned-eval").get("reason"));
    }

    @Test void indexedNestedDecisionTraceIsVerifiedAndAccepted() throws Exception {
        var manifest = fixture();
        var artifacts = (Map<String, Object>) manifest.get("artifacts");
        var traceIndex = artifacts.remove("decision_trace.json");
        Files.createDirectories(root.resolve("kpis"));
        Files.move(root.resolve("decision_trace.json"), root.resolve("kpis/decision_trace.json"));
        artifacts.put("kpis/decision_trace.json", traceIndex);
        Files.writeString(root.resolve("evaluation_manifest.json"), JSON.toJSONString(manifest));

        var service = new EvaluationAnalysisService();
        var analysis = service.read(root, "owned-eval");
        assertEquals("available", analysis.get("status"), analysis.toString());
        assertTrue(analysis.containsKey("result"));
        Files.writeString(root.resolve("kpis/decision_trace.json"), "{\"steps\":[]}");
        assertEquals("artifact_hash_mismatch:kpis/decision_trace.json",
                service.read(root, "owned-eval").get("reason"));
    }

    @Test void externalPathsAreRejected() throws Exception {
        var manifest = fixture();
        ((Map<String, Object>) manifest.get("artifacts")).put("../score_result.json", Map.of("sha256", "x"));
        Files.writeString(root.resolve("evaluation_manifest.json"), JSON.toJSONString(manifest));
        assertEquals("unsafe_artifact_path", new EvaluationAnalysisService().read(root, "owned-eval").get("reason"));
    }

    @Test void incompleteEvaluationCannotExposeAComputedScore() throws Exception {
        for (String problem : new String[]{"status", "validation", "coverage", "missing_trace"}) {
            var manifest = fixture();
            if (problem.equals("status")) manifest.put("artifact_status", "incomplete");
            if (problem.equals("validation")) manifest.put("validation", Map.of("valid", false));
            if (problem.equals("coverage")) manifest.put("coverage", Map.of("terminated", false));
            if (problem.equals("missing_trace"))
                ((Map<String, Object>) manifest.get("artifacts")).remove("decision_trace.json");
            Files.writeString(root.resolve("evaluation_manifest.json"), JSON.toJSONString(manifest));
            var analysis = new EvaluationAnalysisService().read(root, "owned-eval");
            assertEquals("unavailable", analysis.get("status"), problem);
            assertEquals("incomplete_evaluation_evidence", analysis.get("reason"), problem);
            assertFalse(analysis.containsKey("score"), problem);
        }
    }
}
