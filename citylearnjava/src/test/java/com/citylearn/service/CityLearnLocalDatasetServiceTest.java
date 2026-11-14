package com.citylearn.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.*;
import java.time.LocalDate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class CityLearnLocalDatasetServiceTest {
    @TempDir Path directory;

    @Test void usesExportedInstantsAndBuildingTimezoneInsteadOfInferringYearAndWeekday() throws Exception {
        Files.writeString(directory.resolve("Building_1.csv"),"month,hour,day_type\n11,1,2\n11,1,2\n");
        Path nested=Files.createDirectories(directory.resolve("building_1"));
        Files.writeString(nested.resolve("timestamps.csv"),"timestamp\n2020-11-09T16:00:00Z\n2099-11-09T16:00:00Z\n");
        Files.writeString(nested.resolve("manifest.json"),"{\"building\":{\"timezone\":\"Asia/Shanghai\"}}");
        CityLearnLocalDatasetService service=service();
        assertEquals(1,service.getBuildingRows("1","platform_test",null,null,null).size());
        assertEquals("2020-11-10",service.getBuildingRows("1","platform_test",null,null,null).get(0).getDate());
        assertEquals(1,service.getBuildingRows("1","platform_test",null,null,null,"2020-11-10").size());
    }

    @Test void retainsLegacyInferenceWhenDatasetHasNoTimestampFile() throws Exception {
        Files.writeString(directory.resolve("Building_1.csv"),"month,hour,day_type\n1,1,1\n");
        String date=service().getBuildingRows("1","legacy_test",null,null,null).get(0).getDate();
        assertEquals(LocalDate.now().getYear(),LocalDate.parse(date).getYear());
        assertEquals(1,LocalDate.parse(date).getDayOfWeek().getValue());
    }

    private CityLearnLocalDatasetService service() {
        CitylearnDatasetService resolver=mock(CitylearnDatasetService.class);
        when(resolver.resolveDatasetDir(anyString())).thenReturn(directory);
        CityLearnLocalDatasetService service=new CityLearnLocalDatasetService();
        ReflectionTestUtils.setField(service,"citylearnDatasetService",resolver);return service;
    }
}
