package com.citylearn.building;

import com.citylearn.controller.DashboardController;
import com.citylearn.vo.DashboardSimulationDetailVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.boot.test.mock.mockito.MockBean;
import com.citylearn.service.BaseDataService;
import static org.mockito.Mockito.when;
import java.util.Map;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class DashboardAssessmentTest {
    @Autowired DashboardController dashboard;
    @Autowired CommunityManagementService communities;
    @Autowired JdbcTemplate jdbc;
    @Autowired HomeEvaluationService evaluations;
    @Autowired HomeSourceService home;
    @MockBean BaseDataService base;

    @Test void communityDetailReturnsSavedTraceInsteadOfKpiOnly() {
        when(base.getDashboardSimulations(false)).thenReturn(java.util.List.of());
        long community=((Number)communities.save(null, Map.of("name","Dashboard regression","timezone","UTC","currency","CNY","timestampKind","assigned")).get("id")).longValue();
        String id=UUID.randomUUID().toString();
        jdbc.update("INSERT INTO community_assessment_run(id,community_id,release_id,status,stage,config_json,result_json) VALUES (?,?,?,'succeeded','completed','{}',?)",id,community,UUID.randomUUID().toString(),"{\"cases\":[{\"id\":\"chesca\",\"label\":\"CHESCA\",\"status\":\"succeeded\",\"metrics\":{}}]}");
        String trace="episode,step,building,action_ele_final,decision_narrative\n1,0,0,0.2,Recorded decision\n";
        jdbc.update("INSERT INTO community_assessment_artifact(run_id,artifact_type,content) VALUES (?,?,?)",id,"home_trace_csv",trace);
        DashboardSimulationDetailVO detail=dashboard.getDashboardSimulationDetail("community:"+id).getData();
        assertNotNull(detail);
        assertEquals("CNY", detail.getCurrency());
        assertEquals(trace,detail.getChescaTraceCsv());
        assertEquals("cost_total",detail.getKpiRows().get(0).get("KPI"));
        String key="community:"+id+":chesca";
        assertTrue(evaluations.options().stream().anyMatch(item->key.equals(item.getTaskId())));
        try { evaluations.select(key); } catch(java.io.IOException e) { fail(e); }
        assertEquals(key,evaluations.selected());
        assertEquals("evaluation",home.snapshot(null,null,null).get("mode"));
        try { assertEquals(key,evaluations.current().getTaskId()); } catch(java.io.IOException e) { fail(e); }
        assertThrows(IllegalArgumentException.class,()->evaluations.select("community:"+id+":missing"));
        home.select(null);
        assertNull(evaluations.selected());
    }
}
