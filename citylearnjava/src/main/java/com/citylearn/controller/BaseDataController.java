package com.citylearn.controller;

import com.citylearn.common.Result;
import com.citylearn.entity.Building;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.param.BatteryMinSocConfigParam;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.param.PyFileParam;
import com.citylearn.param.PyTaskParam;
import com.citylearn.param.ResMarlConfigParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.service.BatteryMinSocConfigService;
import com.citylearn.service.CitylearnDatasetService;
import com.citylearn.vo.AlgorithmParamConfigVO;
import com.citylearn.vo.AlgorithmParamConfigSetDetailVO;
import com.citylearn.vo.AlgorithmParamConfigSetVO;
import com.citylearn.vo.CitylearnDatasetVO;
import com.citylearn.vo.ChescaBatteryConfigVO;
import com.citylearn.vo.ResMarlConfigVO;
import com.citylearn.vo.BuildingDataVO;
import com.citylearn.vo.DashboardSimulationDetailVO;
import com.citylearn.vo.DashboardSimulationVO;
import com.citylearn.vo.HomeEnergyFlowVO;
import com.citylearn.vo.HomeEnergyHourlyVO;
import com.citylearn.vo.KpisTransVO;
import com.citylearn.vo.KpisVO;
import com.citylearn.vo.PyFileVO;
import com.citylearn.vo.PyTaskDetailVO;
import com.citylearn.vo.PyTaskNoticeSummaryVO;
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

    @Resource
    private CitylearnDatasetService citylearnDatasetService;

    @RequestMapping(value = "/getList", method = RequestMethod.GET)
    public Result<List<BuildingDataVO>> getList(
            @RequestParam(name = "buildingId") String buildingId,
            @RequestParam(name = "hour", required = false) Integer hour,
            @RequestParam(name = "dayType", required = false) Integer dayType,
            @RequestParam(name = "date", required = false) String date,
            @RequestParam(name = "datasetSchema", required = false,
                    defaultValue = "citylearn_challenge_2023_phase_2_local_evaluation") String datasetSchema) {
        try {
            List<BuildingDataVO> list = baseDataService.getList(
                    buildingId, null, hour, dayType, datasetSchema, date);
            return Result.success(list);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 本地 CityLearn 数据集列表（MySQL citylearn_dataset），供原始数据 / 评估配置共用。
     */
    @RequestMapping(value = "/getDatasetList", method = RequestMethod.GET)
    public Result<List<CitylearnDatasetVO>> getDatasetList() {
        try {
            return Result.success(citylearnDatasetService.listEnabledDatasets());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
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

    /**
     * 代码编辑器「文件列表」。
     *
     * @param scriptType 可选：按脚本类型筛选（train 只训练 / eval 只评估 / both 训练+评估一体）。
     *                   不传或传 all 表示返回全部类型，与旧行为一致（向后兼容）。
     */
    @RequestMapping(value = "/getPyFileList",method = RequestMethod.GET)
    public Result<List<PyFileVO>> getPyFileList(
            @RequestParam(name = "scriptType", required = false) String scriptType){
        String createUser="admin";
        List<PyFileVO> list= baseDataService.getPyFileList(createUser, scriptType);
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

    @RequestMapping(value = "/deletePyTask", method = RequestMethod.POST)
    public Result<Void> deletePyTask(@RequestBody PyTaskParam pyTaskParam) {
        try {
            baseDataService.deletePyTask(pyTaskParam.getTaskId());
            return Result.success();
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

    /**
     * 首页能源分配：服务端按日预聚合。
     * mode=today 仅当日（首屏）；mode=history 截止 untilTs 的全部日期。
     */
    @RequestMapping(value = "/getHomeEnergyFlow", method = RequestMethod.GET)
    public Result<HomeEnergyFlowVO> getHomeEnergyFlow(
            @RequestParam(name = "taskId") String taskId,
            @RequestParam(name = "untilTs") String untilTs,
            @RequestParam(name = "datasetYear", required = false, defaultValue = "2026") Integer datasetYear,
            @RequestParam(name = "mode", required = false, defaultValue = "today") String mode) {
        try {
            return Result.success(baseDataService.getHomeEnergyFlow(taskId, untilTs, datasetYear, mode));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 首页能源分配「家庭」点击：返回指定日 / 范围的逐小时家庭耗电。
     */
    @RequestMapping(value = "/getHomeEnergyHourly", method = RequestMethod.GET)
    public Result<HomeEnergyHourlyVO> getHomeEnergyHourly(
            @RequestParam(name = "taskId") String taskId,
            @RequestParam(name = "day") String day,
            @RequestParam(name = "untilTs") String untilTs,
            @RequestParam(name = "scope", required = false, defaultValue = "community") String scope,
            @RequestParam(name = "datasetYear", required = false, defaultValue = "2026") Integer datasetYear) {
        try {
            return Result.success(baseDataService.getHomeEnergyHourly(taskId, day, scope, untilTs, datasetYear));
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
    /**
     * 执行「训练+评估」编排任务（任务管理页「执行」按钮）。
     *
     * <p>父任务转 0-执行中、训练子任务立刻开跑、评估子任务置 6-等待中；
     * 训练子任务跑完后由后台心跳自动接力启动评估，全部完成后父任务转 1-执行完成。
     */
    @RequestMapping(value = "/executePipelineTask", method = RequestMethod.POST)
    public Result<PyTaskVO> executePipelineTask(@RequestBody PyTaskParam pyTaskParam) {
        try {
            return Result.success(baseDataService.executePipelineTask(pyTaskParam.getTaskId()));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询编排任务的两个子任务（训练 / 评估，按训练在前返回），供「详情」展开的子表格使用。
     */
    @RequestMapping(value = "/getSubTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getSubTaskList(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getSubTaskList(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询所有代码的执行记录（按开始时间倒序），供「任务记录」菜单使用。
     * 比 getPyTaskList 多返回 scriptName（代码名称），不返回 output（列表页不需要）。
     */
    @RequestMapping(value = "/getAllPyTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getAllPyTaskList() {
        try {
            return Result.success(baseDataService.getAllPyTaskList());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 列出「可续训」的任务（P19-1）：任务目录下存在训练断点
     * （{@code checkpoints/multi_agent_resume/train_progress.json}）的任务。
     *
     * <p>供代码编辑器「续训」弹窗选择来源任务。返回 taskId / 脚本名 / 已训练轮数 /
     * 目标轮数 / 最差和 / 断点更新时间 / 不适曲线点数，按断点更新时间倒序。
     */
    @RequestMapping(value = "/getResumableTaskList", method = RequestMethod.GET)
    public Result<List<Map<String, Object>>> getResumableTaskList() {
        try {
            return Result.success(baseDataService.getResumableTaskList());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 列出「以往成功的训练任务」，供任务管理页评估卡选择「复用历史训练模型」。
     *
     * <p>只收 status=1-执行完成、且磁盘上确实有可用模型的任务；返回的 taskId 可直接填进
     * 评估卡的 {@code train-task-id}。选它时该任务只跑评估子任务（不再训练）。
     */
    @RequestMapping(value = "/getTrainModelTaskList", method = RequestMethod.GET)
    public Result<List<Map<String, Object>>> getTrainModelTaskList() {
        try {
            return Result.success(baseDataService.getTrainModelTaskList());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 读取指定任务的训练断点进度（P19-1）：含 {@code mid_eval_history} 不适曲线，
     * 供「续训」弹窗在选择来源任务后预览"将继承的曲线"。
     */
    @RequestMapping(value = "/getTaskTrainProgress", method = RequestMethod.GET)
    public Result<Map<String, Object>> getTaskTrainProgress(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getTaskTrainProgress(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 新建「训练 + 评估」编排任务（任务管理页「新建任务」按钮）。
     *
     * <p>只把两张卡片的配置落库：py_task.type=0，train_config / eval_config 各存一段 JSON。
     * **不执行任何脚本**，任务状态为 5-待执行；编排任务的执行与详情逻辑待后续补充。
     */
    @RequestMapping(value = "/createPipelineTask", method = RequestMethod.POST)
    public Result<PyTaskVO> createPipelineTask(@RequestBody PipelineTaskParam param) {
        try {
            return Result.success(baseDataService.createPipelineTask(param));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 编辑「训练 + 评估」编排任务：任务名称 + 两张卡片的全部配置。
     *
     * <p>仅允许 type=0 且状态为 5-待执行的任务，限制在服务端强制（不靠前端隐藏按钮）。
     */
    @RequestMapping(value = "/updatePipelineTask", method = RequestMethod.POST)
    public Result<PyTaskVO> updatePipelineTask(@RequestBody PipelineTaskParam param) {
        try {
            return Result.success(baseDataService.updatePipelineTask(param));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询编排任务详情（任务名称 + 两张卡片配置），供「编辑」弹窗回填。
     *
     * <p>列表接口不返回这两段 JSON（运行期间会被每 5 秒轮询），所以编辑时单独取一次。
     */
    @RequestMapping(value = "/getPyTaskDetail", method = RequestMethod.GET)
    public Result<PyTaskDetailVO> getPyTaskDetail(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getPyTaskDetail(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 算法参数定义目录（algorithm_param_config）。
     *
     * <p>两个使用方：
     * <ul>
     *   <li>代码编辑器「配置」弹窗 —— 不传 isMember，拿全量（组成员也要能挂到脚本上）；</li>
     *   <li>参数配置页「单独配置」页签 —— 传 isMember=0，只拿未加入配置组的参数。</li>
     * </ul>
     *
     * @param isMember 可选的配置组成员筛选：0=只看独立参数，1=只看组成员，不传=全部
     */
    @RequestMapping(value = "/getAlgorithmParamConfigList", method = RequestMethod.GET)
    public Result<List<AlgorithmParamConfigVO>> getAlgorithmParamConfigList(
            @RequestParam(name = "isMember", required = false) Integer isMember) {
        try {
            Boolean filter = isMember == null ? null : isMember != 0;
            return Result.success(baseDataService.listAlgorithmParamConfigs(filter));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 参数配置页：新增参数定义 */
    @RequestMapping(value = "/addAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<AlgorithmParamConfigVO> addAlgorithmParamConfig(
            @RequestBody AlgorithmParamConfigParam param) {
        try {
            return Result.success(baseDataService.addAlgorithmParamConfig(param));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 参数配置页：编辑参数定义（系统内置参数只允许改简介） */
    @RequestMapping(value = "/updateAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<Void> updateAlgorithmParamConfig(@RequestBody AlgorithmParamConfigParam param) {
        try {
            baseDataService.updateAlgorithmParamConfig(param);
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 参数配置页：删除参数定义（系统内置参数禁止删除） */
    @RequestMapping(value = "/deleteAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<Void> deleteAlgorithmParamConfig(@RequestBody AlgorithmParamConfigParam param) {
        try {
            baseDataService.deleteAlgorithmParamConfig(param == null ? null : param.getId());
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /* ==================== 参数配置页：配置组（algorithm_param_config_set） ==================== */

    /** 配置组列表（组名称 / 创建时间 / 简介 / 成员数） */
    @RequestMapping(value = "/getAlgorithmParamConfigSetList", method = RequestMethod.GET)
    public Result<List<AlgorithmParamConfigSetVO>> getAlgorithmParamConfigSetList() {
        try {
            return Result.success(baseDataService.listAlgorithmParamConfigSets());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 配置组详情：组信息 + 组内参数定义（点「详情」进入组内参数页） */
    @RequestMapping(value = "/getAlgorithmParamConfigSetDetail", method = RequestMethod.GET)
    public Result<AlgorithmParamConfigSetDetailVO> getAlgorithmParamConfigSetDetail(
            @RequestParam(name = "id") Integer id) {
        try {
            return Result.success(baseDataService.getAlgorithmParamConfigSetDetail(id));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 新增配置组 */
    @RequestMapping(value = "/addAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<AlgorithmParamConfigSetVO> addAlgorithmParamConfigSet(
            @RequestBody AlgorithmParamConfigSetParam param) {
        try {
            return Result.success(baseDataService.addAlgorithmParamConfigSet(param));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 编辑配置组（名称 / 简介 / 成员） */
    @RequestMapping(value = "/updateAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<Void> updateAlgorithmParamConfigSet(@RequestBody AlgorithmParamConfigSetParam param) {
        try {
            baseDataService.updateAlgorithmParamConfigSet(param);
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 删除配置组（组内参数会被重新计算 is_member） */
    @RequestMapping(value = "/deleteAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<Void> deleteAlgorithmParamConfigSet(@RequestBody AlgorithmParamConfigSetParam param) {
        try {
            baseDataService.deleteAlgorithmParamConfigSet(param == null ? null : param.getId());
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 保存某个脚本的算法配置（py_file.algorithm_config，JSON 数组字符串）。
     */
    @RequestMapping(value = "/savePyFileAlgorithmConfig", method = RequestMethod.POST)
    public Result<Void> savePyFileAlgorithmConfig(@RequestBody PyFileParam pyFileParam) {
        try {
            baseDataService.savePyFileAlgorithmConfig(
                    pyFileParam.getId(), pyFileParam.getAlgorithmConfig());
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 查询当前正在执行的任务列表（供前端「运行中任务」指示器高频轮询，任何页面都能用）。
     * 返回体不含 output，可以每几秒调一次。
     */
    @RequestMapping(value = "/getRunningPyTasks", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getRunningPyTasks() {
        try {
            return Result.success(baseDataService.getRunningPyTaskList());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 任务通知汇总：运行中任务 + 执行完但未读的数量（总数 + 按脚本聚合）。
     * 顶栏指示器与代码编辑器文件列表的未读红点共用这一个接口。
     */
    @RequestMapping(value = "/getPyTaskNoticeSummary", method = RequestMethod.GET)
    public Result<PyTaskNoticeSummaryVO> getPyTaskNoticeSummary() {
        try {
            return Result.success(baseDataService.getPyTaskNoticeSummary());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 把一条执行记录标记为已读（执行记录列表点击后调用）。
     */
    @RequestMapping(value = "/markPyTaskNotified", method = RequestMethod.POST)
    public Result<PyTaskVO> markPyTaskNotified(@RequestBody PyTaskParam pyTaskParam) {
        try {
            return Result.success(baseDataService.markPyTaskNotified(pyTaskParam.getTaskId()));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

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
     * 终止正在运行的任务（kill Python 进程），并将执行记录状态置为 3-运行终止。
     */
    @RequestMapping(value = "/stopPyTask", method = RequestMethod.POST)
    public Result<PyTaskVO> stopPyTask(@RequestBody PyTaskParam pyTaskParam) {
        try {
            return Result.success(baseDataService.stopPyTask(pyTaskParam.getTaskId()));
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
            config.setMinCoolPerCOverheat(param.getMinCoolPerCOverheat());
            config.setMinCoolPerCOutdoorGap(param.getMinCoolPerCOutdoorGap());
            config.setOutdoorGapDeadbandC(param.getOutdoorGapDeadbandC());
            config.setOutdoorFloorMaxOverheatC(param.getOutdoorFloorMaxOverheatC());
            config.setCoolingDemandFeedforwardFrac(param.getCoolingDemandFeedforwardFrac());
            config.setDemandFeedforwardOnlyWhenOverheat(param.getDemandFeedforwardOnlyWhenOverheat());
            config.setOutdoorFloorAllowWhenUnderSetpoint(param.getOutdoorFloorAllowWhenUnderSetpoint());
            config.setClearOpenLoopFloorWhenUnderSetpoint(param.getClearOpenLoopFloorWhenUnderSetpoint());
            config.setUseLaggedDynamicsIndoor(param.getUseLaggedDynamicsIndoor());
            config.setLaggedIndoorOnlyWhenHotter(param.getLaggedIndoorOnlyWhenHotter());
            config.setLaggedIndoorHotterMarginC(param.getLaggedIndoorHotterMarginC());
            config.setPostOutageSoftChargeEnabled(param.getPostOutageSoftChargeEnabled());
            config.setPostOutageRelaxSteps(param.getPostOutageRelaxSteps());
            config.setPostOutageWaiveMinSoc(param.getPostOutageWaiveMinSoc());
            config.setPostOutageMaxEleCharge(param.getPostOutageMaxEleCharge());
            config.setPostOutageForbidChargeWhenOverheat(param.getPostOutageForbidChargeWhenOverheat());
            config.setPostOutageOverheatC(param.getPostOutageOverheatC());
            config.setPostOutageTmpCapEnabled(param.getPostOutageTmpCapEnabled());
            config.setPostOutageTmpCapSteps(param.getPostOutageTmpCapSteps());
            config.setPostOutageTmpMaxStart(param.getPostOutageTmpMaxStart());
            config.setPostOutageTmpRamp(param.getPostOutageTmpRamp());
            config.setPostOutageTmpStagger(param.getPostOutageTmpStagger());
            config.setPriceAwareBatteryEnabled(param.getPriceAwareBatteryEnabled());
            config.setPriceHighQuantile(param.getPriceHighQuantile());
            config.setPriceLowQuantile(param.getPriceLowQuantile());
            config.setPriceHistoryMinSteps(param.getPriceHistoryMinSteps());
            config.setPriceHighSocThreshold(param.getPriceHighSocThreshold());
            config.setPriceHighForbidCharge(param.getPriceHighForbidCharge());
            config.setPriceHighForceDischarge(param.getPriceHighForceDischarge());
            config.setPriceHighDischargeEle(param.getPriceHighDischargeEle());
            config.setPriceMinReserveSoc(param.getPriceMinReserveSoc());
            config.setPriceGlobalReserveEnabled(param.getPriceGlobalReserveEnabled());
            config.setPriceLowTargetSoc(param.getPriceLowTargetSoc());
            config.setPriceLowChargeEle(param.getPriceLowChargeEle());
            config.setPriceLowSearchBoost(param.getPriceLowSearchBoost());
            config.setTau(param.getTau());
            config.setBalanceType(param.getBalanceType());
            config.setEvalSchema(param.getEvalSchema());
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
            config.setMultiAgentCheckpoint(param.getMultiAgentCheckpoint());
            config.setResidualAlpha(param.getResidualAlpha());
            config.setResidualActionMask(param.getResidualActionMask());
            config.setResmarlAfterSafety(param.getResmarlAfterSafety());
            config.setTrainSchema(param.getTrainSchema());
            config.setMultiAgentEvalSchema(param.getMultiAgentEvalSchema());
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