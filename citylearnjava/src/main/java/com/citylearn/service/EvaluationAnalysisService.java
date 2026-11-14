package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

/** Verified task evidence with a separate NoControl dashboard score. */
public class EvaluationAnalysisService {
    private static final long MAX_JSON_BYTES = 4L * 1024 * 1024;
    private static final long MAX_ARTIFACT_BYTES = 512L * 1024 * 1024;

    public Map<String, Object> read(Path taskRoot, String taskId) {
        Map<String, Object> analysis = readEvidence(taskRoot, taskId);
        if (!"available".equals(analysis.get("status"))) return analysis;
        JSONObject result = (JSONObject) analysis.get("result");
        if ("NoControl".equals(result.getString("algorithm"))
                && "NoControl".equals(((JSONObject) analysis.get("manifest")).getString("algorithm"))) {
            analysis.put("nocontrolScore", NoControlScore.compute(result, result));
            return analysis;
        }
        JSONObject baseline = null;
        try (var children = Files.list(taskRoot.toAbsolutePath().normalize().getParent())) {
            for (Path candidate : children.filter(Files::isDirectory).sorted().toList()) {
                Path file = candidate.resolve("evaluation_result.json");
                if (!Files.isRegularFile(file)) continue;
                try {
                    JSONObject possible = readJson(file);
                    if (!"NoControl".equals(possible.getString("algorithm"))
                            || !NoControlScore.comparable(result.getJSONObject("protocol"), possible.getJSONObject("protocol"))) continue;
                    Map<String, Object> evidence = readEvidence(candidate, possible.getString("task_id"));
                    if (!"available".equals(evidence.get("status"))
                            || !"NoControl".equals(((JSONObject) evidence.get("manifest")).getString("algorithm"))) continue;
                    if (baseline != null) {
                        if (baseline.getJSONObject("per_building").equals(
                                ((JSONObject) evidence.get("result")).getJSONObject("per_building"))) continue;
                        analysis.put("nocontrolScore", NoControlScore.unavailable("multiple_matching_nocontrol"));
                        return analysis;
                    }
                    baseline = (JSONObject) evidence.get("result");
                } catch (IOException | RuntimeException ignored) {
                    // Unreadable sibling evidence is not a usable baseline.
                }
            }
            analysis.put("nocontrolScore", NoControlScore.compute(result, baseline));
        } catch (IOException | RuntimeException e) {
            analysis.put("nocontrolScore", NoControlScore.unavailable("unreadable_nocontrol_evidence"));
        }
        return analysis;
    }

    private Map<String, Object> readEvidence(Path taskRoot, String taskId) {
        try {
            Path root = taskRoot.toAbsolutePath().normalize();
            Path manifestPath = root.resolve("evaluation_manifest.json");
            if (!Files.isRegularFile(manifestPath)) return unavailable("missing_evaluation_manifest");
            JSONObject manifest = readJson(manifestPath);
            if (!taskId.equals(manifest.getString("task_id"))) return unavailable("task_identity_mismatch");
            JSONObject artifacts = manifest.getJSONObject("artifacts");
            if (artifacts == null) return unavailable("missing_artifact_index");
            // Validate all indexed bytes, including the trace, before displaying a
            // completeness claim from the producer. Symlinks may not escape the task.
            Path realRoot = root.toRealPath();
            long total = 0;
            for (String name : artifacts.keySet()) {
                Path relative = Path.of(name);
                Path path = root.resolve(relative).normalize();
                if (relative.isAbsolute() || !path.startsWith(root) || name.contains(".."))
                    return unavailable("unsafe_artifact_path");
                if (!Files.isRegularFile(path)) return unavailable("missing_artifact:" + name);
                if (!path.toRealPath().startsWith(realRoot)) return unavailable("unsafe_artifact_path");
                total += Files.size(path);
                if (total > MAX_ARTIFACT_BYTES) return unavailable("artifact_verification_size_limit");
                if (!hash(path).equals(artifacts.getJSONObject(name).getString("sha256")))
                    return unavailable("artifact_hash_mismatch:" + name);
            }
            if (!artifacts.containsKey("evaluation_result.json") || !artifacts.containsKey("score_result.json"))
                return unavailable("missing_analysis_artifacts");
            JSONObject validation = manifest.getJSONObject("validation");
            JSONObject coverage = manifest.getJSONObject("coverage");
            Long expected = coverage == null ? null : coverage.getLong("expected_transitions");
            Long recorded = coverage == null ? null : coverage.getLong("recorded_transitions");
            // Producers may place the verified trace in kpis/. Only indexed,
            // hash-checked paths from the loop above can satisfy this gate.
            boolean hasDecisionTrace = artifacts.keySet().stream().anyMatch(
                    name -> "decision_trace.json".equals(Path.of(name).getFileName().toString()));
            if (!"complete".equals(manifest.getString("artifact_status"))
                    || validation == null || !Boolean.TRUE.equals(validation.getBoolean("valid"))
                    || coverage == null || !Boolean.TRUE.equals(coverage.getBoolean("terminated"))
                    || !Boolean.FALSE.equals(coverage.getBoolean("truncated"))
                    || expected == null || expected <= 0 || !expected.equals(recorded)
                    || !hasDecisionTrace)
                return unavailable("incomplete_evaluation_evidence");
            JSONObject result = readJson(root.resolve("evaluation_result.json"));
            if (!taskId.equals(result.getString("task_id"))) return unavailable("task_identity_mismatch");
            if (!manifest.getJSONObject("protocol").equals(result.getJSONObject("protocol")))
                return unavailable("result_protocol_mismatch");
            Map<String, Object> analysis = new LinkedHashMap<>();
            analysis.put("status", "available");
            analysis.put("manifest", manifest);
            analysis.put("result", result);
            analysis.put("score", readJson(root.resolve("score_result.json")));
            if (artifacts.containsKey("headroom_result.json"))
                analysis.put("headroom", readJson(root.resolve("headroom_result.json")));
            if (artifacts.containsKey("ai_analysis_bundle.json")) {
                JSONObject advice = readJson(root.resolve("ai_analysis_bundle.json"));
                if (!taskId.equals(advice.getJSONObject("evidence").getString("task_id")))
                    return unavailable("advice_task_identity_mismatch");
                analysis.put("advice", advice);
            }
            return analysis;
        } catch (IOException | RuntimeException exception) {
            return unavailable("unreadable_evaluation_evidence");
        }
    }

    private JSONObject readJson(Path path) throws IOException {
        if (Files.size(path) > MAX_JSON_BYTES) throw new IOException("analysis JSON exceeds limit");
        return JSON.parseObject(Files.readString(path));
    }

    private String hash(Path path) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var stream = Files.newInputStream(path)) {
                byte[] bytes = new byte[64 * 1024];
                int count;
                while ((count = stream.read(bytes)) != -1) digest.update(bytes, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private Map<String, Object> unavailable(String reason) {
        return Map.of("status", "unavailable", "reason", reason);
    }
}
