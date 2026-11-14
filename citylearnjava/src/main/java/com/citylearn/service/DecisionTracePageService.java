package com.citylearn.service;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVPrinter;
import org.apache.commons.csv.CSVRecord;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringWriter;
import java.io.StringReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/** Reads one bounded page without materializing the full decision history. */
public class DecisionTracePageService {
    public static final int DEFAULT_LIMIT = 48;
    private final ObjectMapper mapper = new ObjectMapper();

    public Map<String, Object> read(Path root, Path json, Path csv,
                                    int offset, int limit, Integer building) throws IOException {
        return read(root, json, csv, null, offset, limit, building);
    }

    /** Legacy community records stored the CSV as one database text value. */
    public Map<String, Object> readCsv(String csv, int offset, int limit, Integer building) throws IOException {
        return read(null, null, null, csv, offset, limit, building);
    }

    private Map<String, Object> read(Path root, Path json, Path csv, String legacyCsv,
                                     int offset, int limit, Integer building) throws IOException {
        if (offset < 0 || limit < 1 || limit > 168 || (building != null && building < 0))
            throw new IllegalArgumentException("日志分页参数无效：offset>=0，limit为1到168，building>=0");
        json = checked(root, json);
        csv = checked(root, csv);
        ObjectNode trace = mapper.createObjectNode();
        ArrayNode steps = trace.putArray("steps");
        Set<String> selected = new LinkedHashSet<>();
        int total = 0;
        List<Map<String, Integer>> stepIndex = new ArrayList<>();
        if (json != null) {
            // Skip unselected subtrees at the parser level. An 80MB trace should
            // cost a small page of heap, not an 80MB String plus a full JSON tree.
            try (JsonParser parser = mapper.getFactory().createParser(json.toFile())) {
                if (parser.nextToken() != JsonToken.START_OBJECT) throw new IOException("决策日志不是JSON对象");
                boolean foundSteps = false;
                while (parser.nextToken() != JsonToken.END_OBJECT) {
                    if (parser.currentToken() != JsonToken.FIELD_NAME) throw new IOException("决策日志格式无效");
                    String field = parser.currentName();
                    parser.nextToken();
                    if (!"steps".equals(field)) {
                        trace.set(field, mapper.readTree(parser));
                    } else {
                        if (foundSteps || parser.currentToken() != JsonToken.START_ARRAY)
                            throw new IOException("决策日志steps格式无效");
                        foundSteps = true;
                        while (parser.nextToken() != JsonToken.END_ARRAY) {
                            if (parser.currentToken() != JsonToken.START_OBJECT)
                                throw new IOException("决策日志步骤无效");
                            if (total >= offset && total - offset < limit) {
                                ObjectNode step = mapper.readTree(parser);
                                stepIndex.add(Map.of("episode", step.path("episode").asInt(1), "step", step.path("step").asInt()));
                                selected.add(key(step.path("episode").asText("1"), step.path("step").asText()));
                                if (building != null && step.path("buildings").isArray()) {
                                    ArrayNode filtered = mapper.createArrayNode();
                                    for (JsonNode entry : step.path("buildings"))
                                        if (entry.path("building").asInt(-1) == building) filtered.add(entry);
                                    step.set("buildings", filtered);
                                }
                                steps.add(step);
                            } else {
                                int episode = 1, number = total;
                                while (parser.nextToken() != JsonToken.END_OBJECT) {
                                    String name = parser.currentName();
                                    parser.nextToken();
                                    if ("episode".equals(name)) episode = parser.getValueAsInt(1);
                                    else if ("step".equals(name)) number = parser.getValueAsInt(total);
                                    else parser.skipChildren();
                                }
                                stepIndex.add(Map.of("episode", episode, "step", number));
                            }
                            total++;
                        }
                    }
                }
                if (!foundSteps) throw new IOException("决策日志缺少steps");
            }
        }
        String csvText = "";
        if (csv != null || (legacyCsv != null && !legacyCsv.isBlank())) {
            try (BufferedReader reader = csv != null ? Files.newBufferedReader(csv, StandardCharsets.UTF_8)
                    : new BufferedReader(new StringReader(legacyCsv))) {
                reader.mark(1);
                if (reader.read() != '\uFEFF') reader.reset();
                try (CSVParser parser = CSVFormat.DEFAULT.builder().setHeader()
                        .setSkipHeaderRecord(true).build().parse(reader)) {
                    if (!parser.getHeaderMap().containsKey("step"))
                        throw new IOException("决策CSV缺少step列");
                    Set<String> seen = new LinkedHashSet<>();
                    StringWriter output = new StringWriter();
                    try (CSVPrinter printer = new CSVPrinter(output, CSVFormat.DEFAULT.builder()
                            .setHeader(parser.getHeaderNames().toArray(new String[0])).build())) {
                        for (CSVRecord row : parser) {
                            String id = key(row.isMapped("episode") ? row.get("episode") : "1", row.get("step"));
                            if (json == null && seen.add(id) && seen.size() - 1 >= offset
                                    && seen.size() - 1 - offset < limit) selected.add(id);
                            if (!selected.contains(id)) continue;
                            if (building != null && (!row.isMapped("building")
                                    || new BigDecimal(row.get("building")).intValueExact() != building)) continue;
                            printer.printRecord(row);
                        }
                    }
                    csvText = output.toString();
                    if (json == null) {
                        total = seen.size();
                        for (String id : seen) {
                            String[] parts = id.split(":");
                            stepIndex.add(Map.of("episode", Integer.parseInt(parts[0]), "step", Integer.parseInt(parts[1])));
                        }
                    }
                }
            } catch (IllegalArgumentException | ArithmeticException error) {
                throw new IOException("决策CSV格式无效", error);
            }
        }
        Map<String, Object> page = new LinkedHashMap<>();
        page.put("offset", offset);
        page.put("limit", limit);
        page.put("totalSteps", total);
        page.put("returnedSteps", json == null ? selected.size() : steps.size());
        page.put("firstStep", selected.isEmpty() ? null : Integer.valueOf(selected.iterator().next().split(":")[1]));
        String last = selected.isEmpty() ? null : new ArrayList<>(selected).get(selected.size() - 1);
        page.put("lastStep", last == null ? null : Integer.valueOf(last.split(":")[1]));
        page.put("building", building);
        page.put("stepIndex", stepIndex);
        return Map.of("decisionTraceJson", json == null ? "" : mapper.writeValueAsString(trace),
                "chescaTraceCsv", csvText, "tracePage", page);
    }

    private String key(String episode, String step) throws IOException {
        try {
            return new BigDecimal(episode).intValueExact() + ":" + new BigDecimal(step).intValueExact();
        } catch (NumberFormatException | ArithmeticException error) {
            throw new IOException("日志episode/step必须为整数", error);
        }
    }

    private Path checked(Path root, Path path) throws IOException {
        if (path == null || !Files.isRegularFile(path)) return null;
        if (!path.toRealPath().startsWith(root.toRealPath()))
            throw new IllegalArgumentException("日志路径超出当前任务目录");
        return path;
    }
}
