package com.citylearn.building;

import org.junit.jupiter.api.Test;
import java.util.Map;
import java.sql.ResultSet;
import java.sql.Timestamp;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AssessmentComparisonVisibilityTest {
    @Test void hidesOnlyExplicitlyHiddenSuccessfulCases() {
        assertTrue(AssessmentDashboardService.isComparisonVisible(Map.of("status", "succeeded")));
        assertTrue(AssessmentDashboardService.isComparisonVisible(Map.of("status", "succeeded", "dashboard_hidden", false)));
        assertFalse(AssessmentDashboardService.isComparisonVisible(Map.of("status", "succeeded", "dashboard_hidden", true)));
        assertFalse(AssessmentDashboardService.isComparisonVisible(Map.of("status", "failed")));
    }

    @Test void listKeepsOtherAlgorithmsWhileHidingOneCase() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        ResultSet row = mock(ResultSet.class);
        when(row.getString("id")).thenReturn("12345678-1234-1234-1234-123456789012");
        when(row.getString("name")).thenReturn("Community");
        when(row.getTimestamp("create_time")).thenReturn(Timestamp.valueOf("2026-11-13 12:00:00"));
        when(row.getString("result_json")).thenReturn("{\"cases\":["
                + "{\"id\":\"chesca\",\"label\":\"CHESCA\",\"status\":\"succeeded\",\"dashboard_hidden\":true},"
                + "{\"id\":\"no_control\",\"label\":\"NoControl\",\"status\":\"succeeded\"}]}");
        doAnswer(call -> { ((RowCallbackHandler) call.getArgument(1)).processRow(row); return null; })
                .when(jdbc).query(anyString(), any(RowCallbackHandler.class));
        AssessmentDashboardService service = new AssessmentDashboardService();
        ReflectionTestUtils.setField(service, "jdbc", jdbc);
        ReflectionTestUtils.setField(service, "mapper", new ObjectMapper());
        var options = service.list();
        assertEquals(1, options.size());
        assertTrue(options.get(0).getTaskId().endsWith(":no_control"));
        assertEquals(2, service.list(false).size());
    }
}
