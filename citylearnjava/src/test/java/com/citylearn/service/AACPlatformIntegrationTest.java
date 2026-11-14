package com.citylearn.service;

import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.PyFileMapper;
import com.citylearn.entity.PyFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AACPlatformIntegrationTest {
    @TempDir Path root;
    @Test void editorReadsTheConfiguredPythonRoot() throws Exception {
        Files.writeString(root.resolve("AACMADRL_train.py"), "# platform entry\n");
        FileResourceProperties config = new FileResourceProperties();
        config.setPythonFilePath(root.toString());
        PyFileMapper mapper = mock(PyFileMapper.class);
        PyFile file = new PyFile(); file.setFileName("AACMADRL_train.py");
        when(mapper.selectById("aac")).thenReturn(file);
        PyFileService service = new PyFileService();
        ReflectionTestUtils.setField(service, "pyFileMapper", mapper);
        ReflectionTestUtils.setField(service, "fileResourceProperties", config);
        assertEquals("# platform entry\n", service.getPyFile("aac"));
        file.setFileName("../outside.py");
        assertThrows(IllegalArgumentException.class, () -> service.getPyFile("aac"));
    }
    @Test void modelReadinessRequiresBothManifestAndWeights() throws Exception {
        Files.writeString(root.resolve("model_manifest.json"),
                "{\"algorithm\":\"AACMADRL\",\"checkpoint\":\"model.pt\"}");
        assertEquals(false, ReflectionTestUtils.invokeMethod(BaseDataService.class, "isUsableCheckpointDir", root));
        Files.write(root.resolve("model.pt"), new byte[]{1});
        assertEquals(true, ReflectionTestUtils.invokeMethod(BaseDataService.class, "isUsableCheckpointDir", root));
    }
}
