package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
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
    // 权限：menu:dataList / menu:codeEditor / menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_DATA_LIST, PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_RES_MARL})
    @RequestMapping(value = "/getDatasetList", method = RequestMethod.GET)
    public Result<List<CitylearnDatasetVO>> getDatasetList() {
        try {
            return Result.success(citylearnDatasetService.listEnabledDatasets());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getKpis",method = RequestMethod.GET)
    public Result<List<KpisTransVO>> getKpis(@RequestParam(name = "agentType")String agentType){
        List<KpisTransVO> list= baseDataService.getKpis(agentType);
        return Result.success(list);
    }


    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
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
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/getPyFileList",method = RequestMethod.GET)
    public Result<List<PyFileVO>> getPyFileList(
            @RequestParam(name = "scriptType", required = false) String scriptType){
        String createUser="admin";
        List<PyFileVO> list= baseDataService.getPyFileList(createUser, scriptType);
        return Result.success(list);
    }

    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyFile",method = RequestMethod.GET)
    public Result<String> getPyFile(@RequestParam(name = "id") String id){
        String content= baseDataService.getPyFile(id);
        return Result.success(content);
    }

    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
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

    // 权限：codeEditor:showRecord
    @RequirePerm(PermissionCodes.CODE_SHOW_RECORD)
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

    // 权限：codeEditor:renameRecord
    @RequirePerm(PermissionCodes.CODE_RENAME_RECORD)
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

    // 权限：codeEditor:deleteRecord 或 taskList:delete
    @RequirePerm({PermissionCodes.CODE_DELETE_RECORD, PermissionCodes.TASK_DELETE})
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

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getDashboardSimulations", method = RequestMethod.GET)
    public Result<List<DashboardSimulationVO>> getDashboardSimulations() {
        return Result.success(baseDataService.getDashboardSimulations());
    }

    // 权限：menu:home / menu:recDashboard（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_HOME, PermissionCodes.MENU_REC_DASHBOARD})
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
    // 权限：menu:home（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_HOME)
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
    // 权限：menu:home（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_HOME)
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

    // 权限：menu:recDashboard（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_REC_DASHBOARD)
    @RequestMapping(value = "/getPyFileKpiRows", method = RequestMethod.GET)
    public Result<List<Map<String, String>>> getPyFileKpiRows(@RequestParam(name = "pyId") String pyId) {
        return Result.success(baseDataService.getPyFileKpiRows(pyId));
    }

    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
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
    // 权限：codeEditor:run
    @RequirePerm(PermissionCodes.CODE_RUN)
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
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
    // 权限：taskList:run
    @RequirePerm(PermissionCodes.TASK_RUN)
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
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
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
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
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
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
     *
     * @param pyFileId 可选的训练脚本 id：只列由该脚本产出的训练记录
     *                 （编排任务里评估卡的「复用」下拉据此只显示左边所选训练脚本下的历史任务）；
     *                 不传则返回全部训练记录。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/getTrainModelTaskList", method = RequestMethod.GET)
    public Result<List<Map<String, Object>>> getTrainModelTaskList(
            @RequestParam(value = "pyFileId", required = false) String pyFileId) {
        try {
            return Result.success(baseDataService.getTrainModelTaskList(pyFileId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 读取指定任务的训练断点进度（P19-1）：含 {@code mid_eval_history} 不适曲线，
     * 供「续训」弹窗在选择来源任务后预览"将继承的曲线"。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
    // 权限：taskList:create
    @RequirePerm(PermissionCodes.TASK_CREATE)
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
    // 权限：taskList:edit
    @RequirePerm(PermissionCodes.TASK_EDIT)
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
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
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
    // 权限：menu:algorithmParam / menu:codeEditor（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_ALGORITHM_PARAM, PermissionCodes.MENU_CODE_EDITOR})
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
    // 权限：algorithmParam:itemCreate
    @RequirePerm(PermissionCodes.PARAM_ITEM_CREATE)
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
    // 权限：algorithmParam:itemEdit
    @RequirePerm(PermissionCodes.PARAM_ITEM_EDIT)
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
    // 权限：algorithmParam:itemDelete
    @RequirePerm(PermissionCodes.PARAM_ITEM_DELETE)
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
    // 权限：menu:algorithmParam / menu:codeEditor（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_ALGORITHM_PARAM, PermissionCodes.MENU_CODE_EDITOR})
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
    // 权限：menu:algorithmParam / menu:codeEditor（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_ALGORITHM_PARAM, PermissionCodes.MENU_CODE_EDITOR})
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
    // 权限：algorithmParam:setCreate
    @RequirePerm(PermissionCodes.PARAM_SET_CREATE)
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
    // 权限：algorithmParam:setEdit / setMoveIn / setMoveOut
    @RequirePerm({PermissionCodes.PARAM_SET_EDIT, PermissionCodes.PARAM_SET_MOVE_IN, PermissionCodes.PARAM_SET_MOVE_OUT})
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
    // 权限：algorithmParam:setDelete
    @RequirePerm(PermissionCodes.PARAM_SET_DELETE)
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
    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
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
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
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
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
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
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/markPyTaskNotified", method = RequestMethod.POST)
    public Result<PyTaskVO> markPyTaskNotified(@RequestBody PyTaskParam pyTaskParam) {
        try {
            return Result.success(baseDataService.markPyTaskNotified(pyTaskParam.getTaskId()));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /**
     * 一键把所有未读的执行记录标记为已读（顶栏「待查看」气泡里的「设为已读」按钮调用）。
     * 返回实际被标记的条数。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/markAllPyTaskNotified", method = RequestMethod.POST)
    public Result<Integer> markAllPyTaskNotified() {
        try {
            return Result.success(baseDataService.markAllPyTaskNotified());
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
    // 权限：codeEditor:run 或 taskList:run
    @RequirePerm({PermissionCodes.CODE_RUN, PermissionCodes.TASK_RUN})
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
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
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
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
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
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyTaskConsole", method = RequestMethod.GET)
    public Result<String> getPyTaskConsole(@RequestParam(name = "taskId") String taskId) {
        try {
            return Result.success(baseDataService.getConsoleInfo(taskId));
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    // 权限：codeEditor:deleteFile
    @RequirePerm(PermissionCodes.CODE_DELETE_FILE)
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
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
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
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
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
            config.setPriceBandTieStrict(param.getPriceBandTieStrict());
            config.setTau(param.getTau());
            config.setBalanceType(param.getBalanceType());
            config.setEvalSchema(param.getEvalSchema());
            // 片区尖峰削峰「结构层」（2026-10-11 P2）
            config.setPeakTriggerMode(param.getPeakTriggerMode());
            config.setNsSpikeMult(param.getNsSpikeMult());
            config.setReboundWindow(param.getReboundWindow());
            config.setReboundCap(param.getReboundCap());
            config.setPeakBatteryDischargeEnabled(param.getPeakBatteryDischargeEnabled());
            config.setPeakBatteryDischargeEle(param.getPeakBatteryDischargeEle());
            config.setPeakCutGradedEnabled(param.getPeakCutGradedEnabled());
            config.setPeakCutGradedMLo(param.getPeakCutGradedMLo());
            config.setPeakCutGradedMHi(param.getPeakCutGradedMHi());
            batteryMinSocConfigService.saveConfig(config);
            return Result.success();
        } catch (Exception e) {
            e.printStackTrace();
            return Result.fail(e.getMessage());
        }
    }

    /** 恢复 CHESCA 默认电池 SOC 配置 */
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
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
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
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
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
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
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
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
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
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
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
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