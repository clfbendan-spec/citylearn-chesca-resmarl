package com.citylearn.controller;

import com.citylearn.common.Result;
import com.citylearn.entity.Building;
import com.citylearn.param.BatteryMinSocConfigParam;
import com.citylearn.param.PyFileParam;
import com.citylearn.param.PyTaskParam;
import com.citylearn.param.ResMarlConfigParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.service.BatteryMinSocConfigService;
import com.citylearn.vo.ChescaBatteryConfigVO;
import com.citylearn.vo.ResMarlConfigVO;
import com.citylearn.vo.BuildingDataVO;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import com.citylearn.vo.KpisTransVO;
import com.citylearn.vo.KpisVO;
import com.citylearn.vo.PyFileVO;
import com.citylearn.vo.PyTaskScriptVO;
import com.citylearn.vo.PyTaskVO;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * @author  chenglifu
 */
@RestController
@RequestMapping("/web/basedata")
public class BaseDataController {

    @Resource
    private BaseDataService baseDataService;

    @Resource
    private BatteryMinSocConfigService batteryMinSocConfigService;

    @RequestMapping(value = "/getList",method = RequestMethod.GET)
    public Result<List<BuildingDataVO>> getList(@RequestParam(name = "buildingId")String buildingId,
                                                @RequestParam(name = "month",required = false)Integer month,
                                                @RequestParam(name = "hour",required = false)Integer hour,
                                                @RequestParam(name = "dayType",required = false)Integer dayType){
        List<BuildingDataVO> list= baseDataService.getList(buildingId,month,hour,dayType);
        return Result.success(list);
    }

    @RequestMapping(value = "/getKpis",method = RequestMethod.GET)
    public Result<List<KpisTransVO>> getKpis(@RequestParam(name = "agentType")String agentType){
        List<KpisTransVO> list= baseDataService.getKpis(agentType);
        return Result.success(list);
    }


    @RequestMapping(value = "/updateLearn", method = RequestMethod.GET)
    public Result<String> updateLearn(@RequestParam(name = "agentType") String agentType) {
        baseDataService.updateLearn(agentType);
        return Result.success();
    }

    @RequestMapping(value = "/getPyFileList",method = RequestMethod.GET)
    public Result<List<PyFileVO>> getPyFileList(){
        String createUser="admin";
        List<PyFileVO> list= baseDataService.getPyFileList(createUser);
        return Result.success(list);
    }

    @RequestMapping(value = "/getPyFile",method = RequestMethod.GET)
    public Result<String> getPyFile(@RequestParam(name = "id") String id){
        String content= baseDataService.getPyFile(id);
        return Result.success(content);
    }

    @RequestMapping(value = "/savePyFile",method = RequestMethod.POST)
    public Result<String> savePyFile(@RequestBody PyFileParam pyFileParam){
        try {
            baseDataService.savePyFile(pyFileParam);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
        return Result.success();
    }

    @RequestMapping(value = "/updatePyFileIfShow", method = RequestMethod.POST)
    public Result<PyFileVO> updatePyFileIfShow(@RequestBody PyFileParam pyFileParam) {
        try {
            PyFileVO vo = baseDataService.updatePyFileIfShow(pyFileParam.getId(), pyFileParam.getIfShow());
            return Result.success(vo);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    @RequestMapping(value = "/updatePyTaskIfShow", method = RequestMethod.POST)
    public Result<PyTaskVO> updatePyTaskIfShow(@RequestBody PyTaskParam pyTaskParam) {
        try {
            PyTaskVO vo = baseDataService.updatePyTaskIfShow(pyTaskParam.getTaskId(), pyTaskParam.getIfShow());
            return Result.success(vo);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    @RequestMapping(value = "/updatePyTaskShowName", method = RequestMethod.POST)
    public Result<PyTaskVO> updatePyTaskShowName(@RequestBody PyTaskParam pyTaskParam) {
        try {
            PyTaskVO vo = baseDataService.updatePyTaskShowName(pyTaskParam.getTaskId(), pyTaskParam.getShowName());
            return Result.success(vo);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    @RequestMapping(value = "/getDashboardSimulations", method = RequestMethod.GET)
    public Result<List<DashboardSimulationVO>> getDashboardSimulations() {
        return Result.success(baseDataService.getDashboardSimulations());
    }

    @RequestMapping(value = "/getDashboardSimulationDetail", method = RequestMethod.GET)
    public Result<DashboardSimulationDetailVO> getDashboardSimulationDetail(
            @RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getDashboardSimulationDetail(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    @RequestMapping(value = "/getPyFileKpiRows", method = RequestMethod.GET)
    public Result<List<Map<String, String>>> getPyFileKpiRows(@RequestParam(name = "pyId") String pyId) {
        return Result.success(baseDataService.getPyFileKpiRows(pyId));
    }

    @RequestMapping(value = "/addPyFile",method = RequestMethod.POST)
    public Result<PyFileVO> addPyFile(){
        PyFileVO pyFileVO= null;
        try {
            pyFileVO = baseDataService.addPyFile();
            return Result.success(pyFileVO);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }

    }

    /**
     * 异步执行 Python 脚本，立即返回 taskId，前端轮询 getPyTaskResult 获取结果。
     */
    @RequestMapping(value = "/runPyFile", method = RequestMethod.POST)
    public Result<PyTaskVO> runPyFile(@RequestBody PyFileParam pyFileParam) {
        try {
            PyTaskVO task = baseDataService.runPyFile(pyFileParam);
            return Result.success(task);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询指定 py 文件的任务记录列表（按创建时间倒序）。
     */
    @RequestMapping(value = "/getPyTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getPyTaskList(@RequestParam(name = "pyId") String pyId) {
        try {
            return Result.success(baseDataService.getPyTaskList(pyId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 读取任务输出目录中的 Python 脚本内容。
     */
    @RequestMapping(value = "/getPyTaskScript", method = RequestMethod.GET)
    public Result<PyTaskScriptVO> getPyTaskScript(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getPyTaskScript(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询指定 py 文件是否有执行中的任务；无则 data 为 null。
     */
    @RequestMapping(value = "/getRunningPyTask", method = RequestMethod.GET)
    public Result<PyTaskVO> getRunningPyTask(@RequestParam(name = "pyId") String pyId) {
        try {
            return Result.success(baseDataService.getRunningPyTask(pyId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询 Python 异步任务状态与结果（status: 0执行中 1完成 2失败）。
     */
    @RequestMapping(value = "/getPyTaskResult", method = RequestMethod.GET)
    public Result<PyTaskVO> getPyTaskResult(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getPyTaskResult(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询任务控制台输出（高频轮询，仅含 status + output）。
     */
    @RequestMapping(value = "/getPyTaskOutput", method = RequestMethod.GET)
    public Result<PyTaskVO> getPyTaskOutput(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getPyTaskOutput(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 增量获取任务控制台输出（执行过程中轮询，结束后返回 null）。
     */
    @RequestMapping(value = "/getPyTaskConsole", method = RequestMethod.GET)
    public Result<String> getPyTaskConsole(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getConsoleInfo(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    @RequestMapping(value = "/deletePyFile",method = RequestMethod.POST)
    public Result<PyFileVO> deletePyFile(@RequestBody PyFileParam pyFileParam){
        try {
            baseDataService.deletePyFile(pyFileParam);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
        return Result.success();
    }

    /** 获取 CHESCA 电池 SOC 配置（小时下限 + 正常/停电上限） */
    @RequestMapping(value = "/getBatteryMinSocConfig", method = RequestMethod.GET)
    public Result<ChescaBatteryConfigVO> getBatteryMinSocConfig() {
        try {
            return Result.success(batteryMinSocConfigService.getConfig());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 保存 CHESCA 电池 SOC 配置 */
    @RequestMapping(value = "/saveBatteryMinSocConfig", method = RequestMethod.POST)
    public Result<String> saveBatteryMinSocConfig(@RequestBody BatteryMinSocConfigParam param) {
        try {
            ChescaBatteryConfigVO config = new ChescaBatteryConfigVO();
            config.setMinSocPerHour(param.getMinSocPerHour());
            config.setMaxSocNormal(param.getMaxSocNormal());
            config.setMaxSocOutage(param.getMaxSocOutage());
            config.setMaxSocReductionInOutage(param.getMaxSocReductionInOutage());
            config.setBLow(param.getBLow());
            config.setBHigh(param.getBHigh());
            config.setTmpMaxReductionPercent(param.getTmpMaxReductionPercent());
            config.setTau(param.getTau());
            config.setBalanceType(param.getBalanceType());
            batteryMinSocConfigService.saveConfig(config);
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 恢复 CHESCA 默认电池 SOC 配置 */
    @RequestMapping(value = "/resetBatteryMinSocConfig", method = RequestMethod.POST)
    public Result<ChescaBatteryConfigVO> resetBatteryMinSocConfig() {
        try {
            ChescaBatteryConfigVO defaults = batteryMinSocConfigService.getDefaultConfig();
            batteryMinSocConfigService.saveConfig(defaults);
            return Result.success(batteryMinSocConfigService.getConfig());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 获取 ResMARL 残差配置 */
    @RequestMapping(value = "/getResMarlConfig", method = RequestMethod.GET)
    public Result<ResMarlConfigVO> getResMarlConfig() {
        try {
            return Result.success(batteryMinSocConfigService.getResMarlConfig());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 保存 ResMARL 残差配置到 algorithm_config */
    @RequestMapping(value = "/saveResMarlConfig", method = RequestMethod.POST)
    public Result<String> saveResMarlConfig(@RequestBody ResMarlConfigParam param) {
        try {
            ResMarlConfigVO config = new ResMarlConfigVO();
            config.setResmarlEnabled(param.getResmarlEnabled());
            config.setMarlMode(param.getMarlMode());
            config.setMultiAgentTrainEpochs(param.getMultiAgentTrainEpochs());
            config.setMultiAgentExplore(param.getMultiAgentExplore());
            config.setResidualAlpha(param.getResidualAlpha());
            config.setResidualActionMask(param.getResidualActionMask());
            config.setResmarlAfterSafety(param.getResmarlAfterSafety());
            config.setSchemaSplitEnabled(param.getSchemaSplitEnabled());
            config.setTrainSchema(param.getTrainSchema());
            config.setEvalSchema(param.getEvalSchema());
            batteryMinSocConfigService.saveResMarlConfig(config);
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 恢复 ResMARL 默认配置（关闭，α=0） */
    @RequestMapping(value = "/resetResMarlConfig", method = RequestMethod.POST)
    public Result<ResMarlConfigVO> resetResMarlConfig() {
        try {
            ResMarlConfigVO defaults = batteryMinSocConfigService.getDefaultResMarlConfig();
            batteryMinSocConfigService.saveResMarlConfig(defaults);
            return Result.success(batteryMinSocConfigService.getResMarlConfig());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** α 扫描 registry 列表（ablation_results/registry/index.json） */
    @RequestMapping(value = "/getAlphaSweepRuns", method = RequestMethod.GET)
    public Result<List<Map<String, Object>>> getAlphaSweepRuns() {
        try {
            return Result.success(baseDataService.listAlphaSweepRuns());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** α 扫描详情（含各 α 点 District KPI，供看板曲线） */
    @RequestMapping(value = "/getAlphaSweepDetail", method = RequestMethod.GET)
    public Result<Map<String, Object>> getAlphaSweepDetail(@RequestParam(name = "runId") String runId) {
        try {
            return Result.success(baseDataService.getAlphaSweepDetail(runId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }
}