package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.PipelineTaskParam;
import com.citylearn.param.PyTaskParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.vo.PyTaskVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.List;

/**
 * 编排任务：训练+评估两卡片的创建、编辑、执行与子任务查询。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class PipelineTaskController {

    @Resource
    private BaseDataService baseDataService;

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
        return Result.success(baseDataService.createPipelineTask(param));
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
        return Result.success(baseDataService.updatePipelineTask(param));
    }

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
        return Result.success(baseDataService.executePipelineTask(pyTaskParam.getTaskId()));
    }

    /**
     * 查询编排任务的两个子任务（训练 / 评估，按训练在前返回），供「详情」展开的子表格使用。
     */
    // 权限：menu:taskList（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_TASK_LIST)
    @RequestMapping(value = "/getSubTaskList", method = RequestMethod.GET)
    public Result<List<PyTaskVO>> getSubTaskList(@RequestParam(name = "taskId") String taskId) {
        return Result.success(baseDataService.getSubTaskList(taskId));
    }
}
