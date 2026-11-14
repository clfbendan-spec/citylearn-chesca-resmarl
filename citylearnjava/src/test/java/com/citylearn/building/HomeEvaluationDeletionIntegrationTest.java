package com.citylearn.building;

import com.citylearn.service.BaseDataService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class HomeEvaluationDeletionIntegrationTest {
    @Autowired JdbcTemplate jdbc;
    @Autowired BaseDataService base;
    @Autowired HomeEvaluationService evaluations;
    @Autowired HomeSourceService home;

    @Test void selectedEvaluationSurvivesHidingButDeletionInvalidatesHomeAndBothReaders() throws Exception {
        String file = UUID.randomUUID().toString();
        String task = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO py_file(id,file_name,script_type) VALUES (?,'Home fixture.py','eval')", file);
        jdbc.update("INSERT INTO py_task(id,py_id,status,if_delete,if_show) VALUES (?,?,1,0,1)", task, file);
        evaluations.select(task);
        assertEquals(task, evaluations.current().getTaskId());
        base.updatePyTaskIfShow(task, false);
        assertEquals("evaluation", home.source().get("mode"));
        assertEquals(task, evaluations.current().getTaskId());
        base.deletePyTask(task);
        assertEquals(task, evaluations.selected(), "Keep the unavailable identity, not another result");
        assertEquals("invalid", home.source().get("mode"));
        assertEquals(false, home.source().get("valid"));
        assertNull(home.snapshot(null, null, null).get("current"));
        assertThrows(IllegalArgumentException.class, evaluations::current);
        assertThrows(IllegalArgumentException.class, () -> base.getDashboardSimulationDetail(task));
        assertThrows(IllegalArgumentException.class, () -> base.getDashboardTracePage(task, 0, 48, null));
    }
}
