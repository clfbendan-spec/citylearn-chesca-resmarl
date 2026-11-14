package com.citylearn.building;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class CommunityForecastGeneratorTest {
    List<Map<String,Object>> measurements() {
        List<Map<String,Object>> rows=new ArrayList<>();
        for(int i=0;i<28;i++) rows.add(new LinkedHashMap<>(Map.of(
                "timestamp",Instant.parse("2026-01-01T00:00:00Z").plusSeconds(i*3600L).toString(),
                "outdoor_dry_bulb_temperature",10.0+i,"outdoor_relative_humidity",100.0,
                "direct_solar_irradiance",0.0,"diffuse_solar_irradiance",500.0,"electricity_pricing",i/10.0)));
        return rows;
    }
    @Test void predictionsStayWithinErrorBoundsAndDoNotWrapAtTheEnd() {
        List<Map<String,Object>> rows=measurements();
        new CommunityForecastGenerator().generate(rows,4);
        assertEquals(2.7,(double)rows.get(3).get("electricity_pricing_predicted_3"),1e-12);
        for(int i=0;i<4;i++) for(int horizon=1;horizon<=3;horizon++) {
            assertEquals(0.0,rows.get(i).get("direct_solar_irradiance_predicted_"+horizon));
            double humidity=(double)rows.get(i).get("outdoor_relative_humidity_predicted_"+horizon);
            assertTrue(humidity>=90 && humidity<=100);
        }
        List<Map<String,Object>> repeated=measurements();
        new CommunityForecastGenerator().generate(repeated,4);
        assertEquals(rows,repeated);
        List<Map<String,Object>> cropped=new ArrayList<>(measurements().subList(2,28));
        new CommunityForecastGenerator().generate(cropped,2);
        assertEquals(rows.get(2),cropped.get(0));
        assertThrows(IllegalArgumentException.class,()->new CommunityForecastGenerator().generate(measurements().subList(0,25),2));
    }
}
