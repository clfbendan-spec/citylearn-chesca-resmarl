package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.service.BaseDataService;
import com.citylearn.vo.BuildingDataVO;
import com.citylearn.vo.DashboardSimulationVO;
import com.citylearn.vo.KpisTransVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import com.citylearn.vo.DashboardSimulationDetailVO;
import java.io.IOException;
import java.util.*;

/**
 * 建筑数据与看板：原始数据、KPI、看板模拟明细、模型优选重算。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class DashboardController {

    private static final Logger log = LoggerFactory.getLogger(DashboardController.class);

    @Resource
    private BaseDataService baseDataService;
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private com.citylearn.building.AssessmentDashboardService assessmentDashboard;

    // 权限：menu:dataList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_DATA_LIST)
    @RequestMapping(value = "/getList", method = RequestMethod.GET)
    public Result<List<BuildingDataVO>> getList(
            @RequestParam(name = "buildingId") String buildingId,
            @RequestParam(name = "hour", required = false) Integer hour,
            @RequestParam(name = "dayType", required = false) Integer dayType,
            @RequestParam(name = "date", required = false) String date,
            @RequestParam(name = "datasetSchema", required = false,
                    defaultValue = "citylearn_challenge_2023_phase_2_local_evaluation") String datasetSchema) {
        List<BuildingDataVO> list = baseDataService.getList(
                buildingId, null, hour, dayType, datasetSchema, date);
        return Result.success(list);
    }

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getKpis",method = RequestMethod.GET)
    public Result<List<KpisTransVO>> getKpis(@RequestParam(name = "agentType")String agentType){
        List<KpisTransVO> list= baseDataService.getKpis(agentType);
        return Result.success(list);
    }

    // 权限：recDashboard:updateLearn（写操作码：会启动 Python 进程并回写 KPI）
    @RequirePerm(PermissionCodes.REC_UPDATE_LEARN)
    @RequestMapping(value = "/updateLearn", method = RequestMethod.GET)
    public Result<String> updateLearn(@RequestParam(name = "agentType") String agentType) {
        baseDataService.updateLearn(agentType);
        return Result.success();
    }

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getDashboardSimulations", method = RequestMethod.GET)
    public Result<List<DashboardSimulationVO>> getDashboardSimulations() {
        List<DashboardSimulationVO> result=baseDataService.getDashboardSimulations();
        result.addAll(assessmentDashboard.list());
        return Result.success(result);
    }

    // 权限：menu:home / menu:recDashboard（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_HOME, PermissionCodes.MENU_REC_DASHBOARD})
    @RequestMapping(value = "/getDashboardSimulationDetail", method = RequestMethod.GET)
    public Result<DashboardSimulationDetailVO> getDashboardSimulationDetail(
            @RequestParam(name = "taskId") String taskId) {
        return getDashboardSimulationDetail(taskId, false);
    }

    @RequirePerm({PermissionCodes.MENU_HOME, PermissionCodes.MENU_REC_DASHBOARD})
    @RequestMapping(value = "/getDashboardSimulationDetail", method = RequestMethod.GET, params = "pagedTrace")
    public Result<DashboardSimulationDetailVO> getDashboardSimulationDetail(
            @RequestParam(name = "taskId") String taskId,
            @RequestParam(name = "pagedTrace") boolean pagedTrace) {
        try {
            if(taskId.startsWith("community:")) return Result.success(assessmentDashboard.detail(taskId, pagedTrace));
            return Result.success(pagedTrace ? baseDataService.getDashboardSimulationDetail(taskId, true)
                    : baseDataService.getDashboardSimulationDetail(taskId));
        } catch (IOException e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
            return Result.fail(e.getMessage());
        }
    }

    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @GetMapping("/getDashboardTracePage")
    public Result<Map<String, Object>> getDashboardTracePage(
            @RequestParam(name = "taskId") String taskId,
            @RequestParam(name = "offset", defaultValue = "0") int offset,
            @RequestParam(name = "limit", defaultValue = "48") int limit,
            @RequestParam(name = "building", required = false) Integer building) {
        try {
            return Result.success(taskId.startsWith("community:")
                    ? assessmentDashboard.tracePage(taskId, offset, limit, building)
                    : baseDataService.getDashboardTracePage(taskId, offset, limit, building));
        } catch (IOException | IllegalArgumentException error) {
            return Result.fail(error.getMessage());
        }
    }

    private DashboardSimulationDetailVO communityDetail(String id, boolean includeHomeTrace) throws IOException {
        Map<String,Object> row=jdbc.queryForMap("SELECT r.id,r.config_json,r.result_json,c.name FROM community_assessment_run r JOIN managed_community c ON c.id=r.community_id WHERE r.id=? AND r.status='succeeded'",id);
        Map<String,Object> result=mapper.readValue(Objects.toString(row.get("result_json"),"{}"),Map.class);
        DashboardSimulationDetailVO vo=new DashboardSimulationDetailVO(); vo.setTaskId("community:"+id); vo.setPyId("community"); vo.setGroupName(row.get("name")+" · CHESCA");
        List<Map<String,String>> rows=new ArrayList<>();
        Object cases=result.get("cases"); if(cases instanceof List) for(Object item:(List<?>)cases) if(item instanceof Map){Map<?,?> c=(Map<?,?>)item; if(!"succeeded".equals(c.get("status")))continue; Map<?,?> m=(Map<?,?>)c.get("metrics"); String label=Objects.toString(c.get("label"),Objects.toString(c.get("id"),"")); Map<String,String> line=new LinkedHashMap<>(); line.put("algorithm",label+" · District"); line.put("cost_total",Objects.toString(m.get("cost_total"),"")); line.put("discomfort_proportion",Objects.toString(m.get("discomfort_proportion"),"")); line.put("score",Objects.toString(m.get("score"),"")); rows.add(line); Object buildings=m.get("buildings"); if(buildings instanceof List) for(Object b:(List<?>)buildings) if(b instanceof Map){Map<?,?> building=(Map<?,?>)b; Map<String,String> buildingLine=new LinkedHashMap<>(); buildingLine.put("algorithm",label+" · "+Objects.toString(building.get("name"),"Building")); buildingLine.put("cost_total",Objects.toString(building.get("cost_total"),"")); buildingLine.put("discomfort_proportion",Objects.toString(building.get("discomfort_proportion"),"")); buildingLine.put("score",Objects.toString(building.get("score"),"")); rows.add(buildingLine);}}
        vo.setKpiRows(rows); vo.setKpisCsv("algorithm,cost_total,discomfort_proportion,score\n"+rows.stream().map(x->x.get("algorithm")+","+x.get("cost_total")+","+x.get("discomfort_proportion")+","+x.get("score")).collect(java.util.stream.Collectors.joining("\n")));
        if(includeHomeTrace) {
            List<String> traces=jdbc.query("SELECT content FROM community_assessment_artifact WHERE run_id=? AND artifact_type='home_trace_csv'",(rs,n)->rs.getString(1),id);
            if(!traces.isEmpty()) {
                String trace=traces.get(0);
                vo.setChescaTraceCsv(trace);
                vo.getDataFiles().put("community_home_trace.csv",trace);
            }
        }
        return vo;
    }

    @RequirePerm(PermissionCodes.MENU_HOME)
    @RequestMapping(value = "/getLatestCommunityChescaHomeData", method = RequestMethod.GET)
    public Result<DashboardSimulationDetailVO> getLatestCommunityChescaHomeData() {
        List<String> ids=jdbc.query("SELECT r.id FROM community_assessment_run r JOIN community_assessment_artifact a ON a.run_id=r.id AND a.artifact_type='home_trace_csv' WHERE r.status='succeeded' ORDER BY r.create_time DESC,r.id DESC LIMIT 1",(rs,n)->rs.getString(1));
        if(ids.isEmpty()) return Result.success(null);
        try { return Result.success(communityDetail(ids.get(0),true)); }
        catch(IOException error) { log.error("读取首页 CHESCA 轨迹失败",error); return Result.fail(error.getMessage()); }
    }

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getPyFileKpiRows", method = RequestMethod.GET)
    public Result<List<Map<String, String>>> getPyFileKpiRows(@RequestParam(name = "pyId") String pyId) {
        return Result.success(baseDataService.getPyFileKpiRows(pyId));
    }
}
