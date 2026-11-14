package com.citylearn.building;

import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class SchemaEquipmentHeatingTest {
    @Test void electricHeatingKeepsItsNativeTypeAndParameters() {
        Map<String,Object> device=Map.of("type","citylearn.energy_model.ElectricHeater","autosize",false,
                "attributes",Map.of("nominal_power",6.9,"efficiency",0.95));
        assertEquals(device,SchemaEquipment.normalize(Map.of("heating_device",device)).get("heating_device"));
    }
    @Test void electricHeatingRejectsHeatPumpOnlyAttributesAndArbitraryClasses() {
        assertThrows(IllegalArgumentException.class,()->SchemaEquipment.normalize(Map.of("heating_device",Map.of(
                "type","citylearn.energy_model.ElectricHeater","attributes",Map.of("nominal_power",6.9,"target_heating_temperature",45)))));
        assertThrows(IllegalArgumentException.class,()->SchemaEquipment.normalize(Map.of("heating_device",Map.of(
                "type","custom.ElectricHeater","attributes",Map.of("nominal_power",6.9)))));
        assertThrows(IllegalArgumentException.class,()->SchemaEquipment.normalize(Map.of("cooling_device",Map.of(
                "type","citylearn.energy_model.ElectricHeater","attributes",Map.of("nominal_power",6.9)))));
    }
}
