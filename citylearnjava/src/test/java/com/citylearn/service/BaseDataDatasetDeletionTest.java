package com.citylearn.service;

import com.citylearn.dao.CitylearnDatasetMapper;
import com.citylearn.entity.AlgorithmParamConfig;
import com.citylearn.entity.CitylearnDataset;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class BaseDataDatasetDeletionTest {
    @Test void storedDatasetIdsAndSchemaNamesRejectDisabledEntries() {
        CitylearnDatasetMapper mapper = mock(CitylearnDatasetMapper.class);
        CitylearnDataset dataset = new CitylearnDataset();
        dataset.setId(123); dataset.setSchemaKey("building_deleted"); dataset.setEnabled(0);
        when(mapper.selectById(123)).thenReturn(dataset);
        when(mapper.selectOne(any())).thenReturn(dataset);
        BaseDataService service = new BaseDataService();
        ReflectionTestUtils.setField(service, "citylearnDatasetMapper", mapper);
        AlgorithmParamConfig definition = new AlgorithmParamConfig();
        definition.setValueType("special");
        assertThrows(IllegalArgumentException.class, () -> ReflectionTestUtils.invokeMethod(service, "resolveAlgorithmConfigValue", definition, 123));
        assertThrows(IllegalArgumentException.class, () -> ReflectionTestUtils.invokeMethod(service, "resolveAlgorithmConfigValue", definition, "building_deleted"));
        dataset.setEnabled(1);
        assertEquals("building_deleted", ReflectionTestUtils.invokeMethod(service, "resolveAlgorithmConfigValue", definition, 123));
        assertEquals("building_deleted", ReflectionTestUtils.invokeMethod(service, "resolveAlgorithmConfigValue", definition, "building_deleted"));
    }
}
