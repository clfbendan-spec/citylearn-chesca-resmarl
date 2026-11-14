package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.PyFileParam;
import com.citylearn.param.PyTaskParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.vo.PyTaskDetailVO;
import com.citylearn.vo.PyTaskScriptVO;
import com.citylearn.vo.PyTaskVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.List;
import java.util.Map;

/**
 * 单脚本任务：执行、查询、日志/控制台、终止、续训、展示名与删除。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class PyTaskController {

    @Resource
    private BaseDataService baseDataService;

    /**
     * 异步执行 Python 脚本，立即返回 taskId，前端轮询 getPyTaskResult 获取结果。
     */
    // 权限：codeEditor:run
    @RequirePerm(PermissionCodes.CODE_RUN)
    @RequestMapping(value = "/runPyFile", method = RequestMethod.POST)
    public Result<PyTaskVO> runPyFile(@RequestBody PyFileParam pyFileParam) {
        PyTaskVO task = baseDataService.runPyFile(pyFileParam);
        return Result.success(task);
    }

    /**
     * 查询指定 py 文件的任务记录列表（按创建时间倒序）。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getPyTaskList(@RequestParam(name = "pyId") String pyId) {
        return Result.success(baseDataService.getPyTaskList(pyId));
    }

    /**
     * 读取任务输出目录中的 Python 脚本内容。
     */

    /**
     * 查询所有代码的执行记录（按开始时间倒序），供「任务记录」菜单使用。
     * 比 getPyTaskList 多返回 scriptName（代码名称），不返回 output（列表页不需要）。
     */
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
    @RequestMapping(value = "/getAllPyTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getAllPyTaskList() {
        return Result.success(baseDataService.getAllPyTaskList());
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
        return Result.success(baseDataService.getPyTaskDetail(taskId));
    }

    /**
     * 查询 Python 异步任务状态与结果（status: 0执行中 1完成 2失败）。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/getPyTaskResult", method = RequestMethod.GET)
    public Result<PyTaskVO> getPyTaskResult(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getPyTaskResult(taskId));
    }

    /**
     * 查询任务控制台输出（高频轮询，仅含 status + output）。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyTaskOutput", method = RequestMethod.GET)
    public Result<PyTaskVO> getPyTaskOutput(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getPyTaskOutput(taskId));
    }

    /**
     * 增量获取任务控制台输出（执行过程中轮询，结束后返回 null）。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyTaskConsole", method = RequestMethod.GET)
    public Result<String> getPyTaskConsole(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getConsoleInfo(taskId));
    }

    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyTaskScript", method = RequestMethod.GET)
    public Result<PyTaskScriptVO> getPyTaskScript(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getPyTaskScript(taskId));
    }

    /**
     * 终止正在运行的任务（kill Python 进程），并将执行记录状态置为 3-运行终止。
     */
    // 权限：codeEditor:run 或 taskList:run
    @RequirePerm({PermissionCodes.CODE_RUN, PermissionCodes.TASK_RUN})
    @RequestMapping(value = "/stopPyTask", method = RequestMethod.POST)
    public Result<PyTaskVO> stopPyTask(@RequestBody PyTaskParam pyTaskParam) {
        return Result.success(baseDataService.stopPyTask(pyTaskParam.getTaskId()));
    }

    /**
     * 查询指定 py 文件是否有执行中的任务；无则 data 为 null。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getRunningPyTask", method = RequestMethod.GET)
    public Result<PyTaskVO> getRunningPyTask(@RequestParam(name = "pyId") String pyId) {
        return Result.success(baseDataService.getRunningPyTask(pyId));
    }

    /**
     * 查询当前正在执行的任务列表（供前端「运行中任务」指示器高频轮询，任何页面都能用）。
     * 返回体不含 output，可以每几秒调一次。
     */
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
    @RequestMapping(value = "/getRunningPyTasks", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getRunningPyTasks() {
        return Result.success(baseDataService.getRunningPyTaskList());
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
        return Result.success(baseDataService.getResumableTaskList());
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
        return Result.success(baseDataService.getTrainModelTaskList(pyFileId));
    }

    /**
     * 读取指定任务的训练断点进度（P19-1）：含 {@code mid_eval_history} 不适曲线，
     * 供「续训」弹窗在选择来源任务后预览"将继承的曲线"。
     */
    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getTaskTrainProgress", method = RequestMethod.GET)
    public Result<Map<String, Object>> getTaskTrainProgress(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getTaskTrainProgress(taskId));
    }

    // 权限：codeEditor:showRecord
    @RequirePerm(PermissionCodes.CODE_SHOW_RECORD)
    @RequestMapping(value = "/updatePyTaskIfShow", method = RequestMethod.POST)
    public Result<PyTaskVO> updatePyTaskIfShow(@RequestBody PyTaskParam pyTaskParam) {
        PyTaskVO vo = baseDataService.updatePyTaskIfShow(pyTaskParam.getTaskId(), pyTaskParam.getIfShow());
        return Result.success(vo);
    }

    // 权限：codeEditor:renameRecord
    @RequirePerm(PermissionCodes.CODE_RENAME_RECORD)
    @RequestMapping(value = "/updatePyTaskShowName", method = RequestMethod.POST)
    public Result<PyTaskVO> updatePyTaskShowName(@RequestBody PyTaskParam pyTaskParam) {
        PyTaskVO vo = baseDataService.updatePyTaskShowName(pyTaskParam.getTaskId(), pyTaskParam.getShowName());
        return Result.success(vo);
    }

    // 权限：codeEditor:deleteRecord 或 taskList:delete
    @RequirePerm({PermissionCodes.CODE_DELETE_RECORD, PermissionCodes.TASK_DELETE})
    @RequestMapping(value = "/deletePyTask", method = RequestMethod.POST)
    public Result<Void> deletePyTask(@RequestBody PyTaskParam pyTaskParam) {
        baseDataService.deletePyTask(pyTaskParam.getTaskId());
        return Result.success();
    }
}
