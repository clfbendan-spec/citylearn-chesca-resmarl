package com.citylearn.building;

import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class CommunityManagementContractTest {
    @Test void exposesSharedRowsAndScopedTokenAuthentication() throws Exception {
        Class<?> type = Class.forName("com.citylearn.building.CommunityManagementService");
        assertEquals(Map.class, type.getMethod("get", long.class, boolean.class).getReturnType());
        assertEquals(List.class, type.getMethod("rows", long.class, String.class, String.class).getReturnType());
        assertEquals(boolean.class, type.getMethod("authenticate", long.class, String.class).getReturnType());
    }
}
