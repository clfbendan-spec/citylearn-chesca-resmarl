package com.citylearn.service;

import com.citylearn.common.DashboardKpiSummary;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.PyFileMapper;
import com.citylearn.dao.PyTaskMapper;
import com.citylearn.entity.PyFile;
import com.citylearn.entity.PyTask;
import com.citylearn.vo.DashboardSimulationVO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class DashboardSelectionSummaryTest {
    @TempDir Path output;

    @Test void listReadsTaskDistrictMetricsWithoutLoadingTrace() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTaskMapper tasks = mock(PyTaskMapper.class);
        PyFileMapper files = mock(PyFileMapper.class);
        PyTask task = new PyTask(); task.setId("selection"); task.setPyId("rules");
        task.setCreateTime(new java.util.Date(0));
        PyFile file = new PyFile(); file.setId("rules"); file.setFileName("CHESCA");
        when(tasks.selectList(any())).thenReturn(List.of(task));
        when(files.selectById("rules")).thenReturn(file);
        FileResourceProperties properties = new FileResourceProperties();
        properties.setOutFilePath(output.toString());
        ReflectionTestUtils.setField(service, "pyTaskMapper", tasks);
        ReflectionTestUtils.setField(service, "pyFileMapper", files);
        ReflectionTestUtils.setField(service, "fileResourceProperties", properties);
        Path directory = Files.createDirectories(output.resolve("outkpis/selection"));
        Path csv = directory.resolve("exported_kpis.csv");
        Files.writeString(csv, "KPI,Building_1,District\ncost_total,9,0.75\ndiscomfort_proportion,0.9,0.04\n");
        Files.writeString(directory.resolve("decision_trace.json"), "invalid trace must not be parsed");
        DashboardSimulationVO row = service.getDashboardSimulations().get(0);
        assertEquals(.75, row.getCostTotal());
        assertEquals(.04, row.getDiscomfortProportion());
        assertEquals("CHESCA", row.getRecordName());
        assertNotEquals(row.getGroupName(), row.getRecordName());
        task.setShowName("Custom 2026-11-13 experiment");
        Files.delete(csv);
        row = service.getDashboardSimulations().get(0);
        assertNull(row.getCostTotal());
        assertNull(row.getDiscomfortProportion());
        assertEquals("Custom 2026-11-13 experiment", row.getRecordName());
    }

    @Test void zeroIsPreservedAndInvalidMetricsStayMissing() {
        DashboardSimulationVO row = new DashboardSimulationVO();
        DashboardKpiSummary.apply(row, Map.of("cost_total", 0, "discomfort_proportion", "0.035"));
        assertEquals(0.0, row.getCostTotal());
        assertEquals(.035, row.getDiscomfortProportion());
        DashboardKpiSummary.apply(row, Map.of("cost_total", "NaN", "discomfort_proportion", "bad"));
        assertNull(row.getCostTotal());
        assertNull(row.getDiscomfortProportion());
    }

    @Test void datasetUsesSavedEvaluationBeforeTaskCardAndNeverUsesTrainingSchema() throws Exception {
        BaseDataService service = new BaseDataService();
        PyTask task = new PyTask(); task.setId("dataset");
        task.setConfig("{\"config\":\"[{\\\"param_name\\\":\\\"train-schema\\\",\\\"value\\\":\\\"local\\\"},{\\\"param_name\\\":\\\"eval-schema\\\",\\\"value\\\":\\\"2\\\"}]\"}");
        Map<String,String> names = Map.of("2", "Online1", "actual", "Saved evaluation");
        assertEquals("Online1", ReflectionTestUtils.invokeMethod(service, "dashboardEvaluationDataset", task, output, output, names));
        Files.writeString(output.resolve("evaluation_manifest.json"), "{\"resolved_parameters\":{\"schema\":\"E:/datasets/actual/schema.json\"}}");
        assertEquals("Saved evaluation", ReflectionTestUtils.invokeMethod(service, "dashboardEvaluationDataset", task, output, output, names));
        Files.delete(output.resolve("evaluation_manifest.json"));
        task.setConfig("{\"config\":\"[{\\\"param_name\\\":\\\"train-schema\\\",\\\"value\\\":\\\"local\\\"}]\"}");
        assertNull(ReflectionTestUtils.invokeMethod(service, "dashboardEvaluationDataset", task, output, output, names));
        assertEquals("actual", BaseDataService.dashboardDatasetKey("E:\\datasets\\actual\\schema.json"));
    }
}
