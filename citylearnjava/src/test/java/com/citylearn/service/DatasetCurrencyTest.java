package com.citylearn.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import com.citylearn.config.FileResourceProperties;
import com.citylearn.dao.CitylearnDatasetMapper;
import com.citylearn.entity.CitylearnDataset;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class DatasetCurrencyTest {
    @TempDir Path directory;

    @Test void publicationCurrencyOverridesTheOriginalOnline1Currency() throws Exception {
        Path online = Files.createDirectory(directory.resolve("citylearn_challenge_2023_phase_2_online_evaluation_1"));
        Files.writeString(online.resolve("manifest.json"), "{\"building\":{\"currency\":\" cny \"}}");
        assertEquals("CNY", CitylearnDatasetService.readCurrency(online));
    }

    @Test void unknownDatasetDoesNotBecomeDollars() throws Exception {
        assertNull(CitylearnDatasetService.readCurrency(directory));
        Files.writeString(directory.resolve("manifest.json"), "{\"building\":{\"currency\":\"\"}}");
        assertNull(CitylearnDatasetService.readCurrency(directory));
    }

    @Test void officialOnline1UsesDollarsWithoutACommunityManifest() throws Exception {
        Path online = Files.createDirectory(directory.resolve("citylearn_challenge_2023_phase_2_online_evaluation_1"));
        assertEquals("USD", CitylearnDatasetService.readCurrency(online));
    }

    @Test void resolvesTaskDatasetAndFallsBackToItsOwnerForLegacyPublication() throws Exception {
        CitylearnDatasetService service = new CitylearnDatasetService();
        CitylearnDatasetMapper datasets = mock(CitylearnDatasetMapper.class);
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        FileResourceProperties files = new FileResourceProperties();
        files.setPythonFilePath(directory.toString());
        ReflectionTestUtils.setField(service, "citylearnDatasetMapper", datasets);
        ReflectionTestUtils.setField(service, "fileResourceProperties", files);
        ReflectionTestUtils.setField(service, "jdbc", jdbc);
        CitylearnDataset row = new CitylearnDataset();
        row.setSchemaKey("community_legacy"); row.setRelativePath("datasets/community_legacy");
        when(datasets.selectById("42")).thenReturn(row);
        when(datasets.selectOne(any())).thenReturn(row);
        Path published = Files.createDirectories(directory.resolve(row.getRelativePath()));
        Files.writeString(published.resolve("Building_1.csv"), "data");
        when(jdbc.query(anyString(), org.mockito.ArgumentMatchers.<org.springframework.jdbc.core.RowMapper<String>>any(), eq("community_legacy")))
                .thenReturn(List.of("CNY"));
        assertEquals("CNY", service.resolveCurrency("42"));
        Files.writeString(published.resolve("manifest.json"), "{\"building\":{\"currency\":\"EUR\"}}");
        assertEquals("EUR", service.resolveCurrency("42"));
    }
}
