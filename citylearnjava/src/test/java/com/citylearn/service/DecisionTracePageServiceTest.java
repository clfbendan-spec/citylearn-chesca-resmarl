package com.citylearn.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class DecisionTracePageServiceTest {
    @TempDir Path root;
    private final ObjectMapper mapper = new ObjectMapper();

    private void fixture() throws Exception {
        Files.writeString(root.resolve("decision_trace.json"),
                "{\"version\":2,\"algorithm\":\"Test\",\"steps\":["
                + "{\"episode\":1,\"step\":10,\"buildings\":[{\"building\":0},{\"building\":1}]},"
                + "{\"episode\":1,\"step\":11,\"buildings\":[{\"building\":0},{\"building\":1}]},"
                + "{\"episode\":2,\"step\":10,\"buildings\":[{\"building\":0},{\"building\":1}]}],"
                + "\"code_refs\":{\"rule\":\"keep metadata after steps\"}}");
        Files.writeString(root.resolve("chesca_trace.csv"),
                "\uFEFFepisode,step,building,decision_narrative\n"
                + "1,10,0,first\n1,10,1,other\n1,11,0,\"quoted, text\nsecond line\"\n"
                + "1,11,1,other\n2,10,0,last\n2,10,1,other\n");
    }

    @Test void pagesPreserveEpisodeIdentityMetadataAndQuotedCsv() throws Exception {
        fixture();
        var page = new DecisionTracePageService().read(root, root.resolve("decision_trace.json"),
                root.resolve("chesca_trace.csv"), 1, 1, 0);
        JsonNode trace = mapper.readTree((String) page.get("decisionTraceJson"));
        assertEquals(1, trace.get("steps").size());
        assertEquals(11, trace.at("/steps/0/step").asInt());
        assertEquals(1, trace.at("/steps/0/buildings").size());
        assertEquals(0, trace.at("/steps/0/buildings/0/building").asInt());
        assertEquals("keep metadata after steps", trace.at("/code_refs/rule").asText());
        String csv = (String) page.get("chescaTraceCsv");
        assertTrue(csv.contains("\"quoted, text\nsecond line\""));
        assertFalse(csv.contains("other"));
        Map<?, ?> meta = (Map<?, ?>) page.get("tracePage");
        assertEquals(3, meta.get("totalSteps"));
        assertEquals(1, meta.get("offset"));
        assertEquals(1, meta.get("returnedSteps"));
        assertEquals(java.util.List.of(Map.of("episode", 1, "step", 10),
                Map.of("episode", 1, "step", 11), Map.of("episode", 2, "step", 10)),
                meta.get("stepIndex"));
        var last = new DecisionTracePageService().read(root, root.resolve("decision_trace.json"),
                root.resolve("chesca_trace.csv"), 2, 1, null);
        assertEquals(2, mapper.readTree((String) last.get("decisionTraceJson")).at("/steps/0/episode").asInt());
        assertTrue(((String) last.get("chescaTraceCsv")).contains("last"));
        assertFalse(((String) last.get("chescaTraceCsv")).contains("first"));
    }

    @Test void legacyCsvOnlyCanBePagedWithoutReconstructingJson() throws Exception {
        fixture();
        Files.delete(root.resolve("decision_trace.json"));
        var page = new DecisionTracePageService().read(root, null, root.resolve("chesca_trace.csv"), 2, 2, null);
        assertEquals("", page.get("decisionTraceJson"));
        assertEquals(3, ((Map<?, ?>) page.get("tracePage")).get("totalSteps"));
        assertEquals(1, ((Map<?, ?>) page.get("tracePage")).get("returnedSteps"));
        assertEquals(3, ((java.util.List<?>) ((Map<?, ?>) page.get("tracePage")).get("stepIndex")).size());
        assertTrue(((String) page.get("chescaTraceCsv")).contains("last"));
        assertFalse(((String) page.get("chescaTraceCsv")).contains("first"));
        var databasePage = new DecisionTracePageService().readCsv(
                Files.readString(root.resolve("chesca_trace.csv")), 2, 2, null);
        assertEquals(page, databasePage);
    }

    @Test void outOfRangeIsEmptyAndInvalidRequestsAreRejected() throws Exception {
        fixture();
        var service = new DecisionTracePageService();
        var page = service.read(root, root.resolve("decision_trace.json"), null, 100, 24, null);
        assertEquals(0, mapper.readTree((String) page.get("decisionTraceJson")).get("steps").size());
        assertEquals(3, ((Map<?, ?>) page.get("tracePage")).get("totalSteps"));
        assertThrows(IllegalArgumentException.class, () -> service.read(root, null, null, -1, 24, null));
        assertThrows(IllegalArgumentException.class, () -> service.read(root, null, null, 0, 1000, null));
        Path outside = Files.createTempFile("outside-trace-", ".json");
        try {
            assertThrows(IllegalArgumentException.class, () -> service.read(root, outside, null, 0, 24, null));
        } finally { Files.deleteIfExists(outside); }
    }
}
