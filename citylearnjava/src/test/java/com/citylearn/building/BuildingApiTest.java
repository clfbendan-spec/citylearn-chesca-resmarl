package com.citylearn.building;

import com.citylearn.common.SessionKeys;
import com.citylearn.vo.UserVO;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BuildingApiTest {
    @Autowired MockMvc mvc;
    MockHttpSession reader() {
        UserVO user = new UserVO();
        user.setRole("USER");
        user.setPermissions(List.of("menu:buildingManagement"));
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionKeys.LOGIN_USER, user);
        session.setAttribute(SessionKeys.LOGIN_PERMS, user.getPermissions());
        return session;
    }
    @Test void readPermissionDoesNotGrantWritesAndDevicesNeedTheirOwnToken() throws Exception {
        mvc.perform(get("/web/buildings")).andExpect(jsonPath("$.code").value(401));
        mvc.perform(get("/web/buildings").session(reader())).andExpect(status().isOk()).andExpect(jsonPath("$.code").value(0));
        mvc.perform(post("/web/buildings").session(reader()).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(403));
        mvc.perform(post("/web/buildings/community-datasets").session(reader()).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(403));
        mvc.perform(get("/web/buildings/community-datasets/sources").session(reader()))
                .andExpect(jsonPath("$.code").value(0));
        mvc.perform(post("/web/buildings/999999/delete").session(reader()))
                .andExpect(jsonPath("$.code").value(403));
        mvc.perform(post("/web/buildings/999999/versions/not-a-version/delete").session(reader()))
                .andExpect(jsonPath("$.code").value(403));
        mvc.perform(post("/ingest/v1/buildings/999999/measurements")
                .contentType("application/json").content("{\"rows\":[]}")).andExpect(status().isUnauthorized());
        mvc.perform(get("/web/buildings/999999/experiments").session(reader()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.code").value(500));
    }
    @Test void buildingPublicationIsRetiredWithoutCreatingAnArtifact() throws Exception {
        MockHttpSession session=reader();
        session.setAttribute(SessionKeys.LOGIN_PERMS,List.of("menu:buildingManagement","building:write"));
        mvc.perform(post("/web/buildings/999999/versions").session(session).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(500))
                .andExpect(jsonPath("$.message").value("建筑级数据集发布已取消，请在社区管理的数据集发布中统一选择建筑和时间范围"));
        mvc.perform(post("/web/buildings/999999/versions/preview").session(session).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(500))
                .andExpect(jsonPath("$.message").value("建筑级数据集发布已取消，请在社区管理的数据集发布中统一选择建筑和时间范围"));
        mvc.perform(post("/web/buildings/community-datasets").session(session).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(500))
                .andExpect(jsonPath("$.message").value("旧社区发布入口已停用，请在社区管理的数据集发布中统一选择建筑和时间范围"));
        mvc.perform(post("/web/buildings/community-datasets/preview").session(session).contentType("application/json").content("{}"))
                .andExpect(jsonPath("$.code").value(500))
                .andExpect(jsonPath("$.message").value("旧社区发布入口已停用，请在社区管理的数据集发布中统一选择建筑和时间范围"));
    }
}
