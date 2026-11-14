package com.citylearn.building;

import com.citylearn.service.BaseDataService;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class HomeEvaluationValidityTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final BaseDataService base = mock(BaseDataService.class);
    private final AssessmentDashboardService assessments = mock(AssessmentDashboardService.class);
    private final HomeEvaluationService evaluations = new HomeEvaluationService();
    private final HomeSourceService home = new HomeSourceService();

    HomeEvaluationValidityTest() {
        ReflectionTestUtils.setField(evaluations, "jdbc", jdbc);
        ReflectionTestUtils.setField(evaluations, "base", base);
        ReflectionTestUtils.setField(evaluations, "assessments", assessments);
        ReflectionTestUtils.setField(home, "jdbc", jdbc);
        ReflectionTestUtils.setField(home, "evaluations", evaluations);
        CommunityManagementService communities = mock(CommunityManagementService.class);
        when(communities.list()).thenReturn(List.of());
        ReflectionTestUtils.setField(home, "communities", communities);
        when(jdbc.queryForObject("SELECT community_id FROM home_source_setting WHERE id=1", Long.class))
                .thenReturn(null);
        when(base.getDashboardSimulations(false)).thenReturn(List.of());
        when(assessments.list()).thenReturn(List.of());
    }

    @Test void deletedSelectionStaysExplicitlyInvalidWithoutSubstitutingAnotherTask() throws Exception {
        when(jdbc.queryForObject("SELECT task_id FROM home_evaluation_setting WHERE id=1", String.class))
                .thenReturn("deleted-eval");
        DashboardSimulationVO other = new DashboardSimulationVO();
        other.setTaskId("other-eval");
        when(base.getDashboardSimulations(false)).thenReturn(List.of(other));
        Map<String,Object> source = home.source();
        assertEquals("invalid", source.get("mode"));
        assertEquals(false, source.get("valid"));
        assertEquals("deleted-eval", source.get("taskId"));
        assertTrue(source.get("message").toString().contains("重新选择"));
        Map<String,Object> snapshot = home.snapshot(null, null, null);
        assertEquals("invalid", snapshot.get("mode"));
        assertNull(snapshot.get("current"));
        assertEquals(List.of(), snapshot.get("samples"));
        assertThrows(IllegalArgumentException.class, evaluations::current);
        verify(base, never()).getDashboardSimulationDetail(anyString());
        verify(jdbc, never()).update(anyString(), any(Object[].class));
    }

    @Test void hiddenButUndeletedSelectionRemainsUsable() throws Exception {
        when(jdbc.queryForObject("SELECT task_id FROM home_evaluation_setting WHERE id=1", String.class))
                .thenReturn("hidden-eval");
        DashboardSimulationVO hidden = new DashboardSimulationVO();
        hidden.setTaskId("hidden-eval");
        // false lists all successful evaluations, independent of display toggles.
        when(base.getDashboardSimulations(false)).thenReturn(List.of(hidden));
        DashboardSimulationDetailVO detail = new DashboardSimulationDetailVO();
        detail.setTaskId("hidden-eval");
        when(base.getDashboardSimulationDetail("hidden-eval")).thenReturn(detail);
        assertEquals("evaluation", home.source().get("mode"));
        assertEquals(true, home.source().get("valid"));
        assertEquals("hidden-eval", evaluations.current().getTaskId());
    }

    @Test void missingCommunityCaseIsInvalidAndEmptySelectionStillMeansDefault() {
        when(jdbc.queryForObject("SELECT task_id FROM home_evaluation_setting WHERE id=1", String.class))
                .thenReturn("community:missing:chesca");
        assertEquals("invalid", home.source().get("mode"));
        when(jdbc.queryForObject("SELECT task_id FROM home_evaluation_setting WHERE id=1", String.class))
                .thenReturn(null);
        assertEquals("default", home.source().get("mode"));
        assertEquals(true, home.source().get("valid"));
    }
}
