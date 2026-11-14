package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.PyTaskParam;
import com.citylearn.service.BaseDataService;
import com.citylearn.vo.PyTaskNoticeSummaryVO;
import com.citylearn.vo.PyTaskVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;

/**
 * 任务完成通知：未读汇总与已读标记。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class PyTaskNoticeController {

    @Resource
    private BaseDataService baseDataService;

    /**
     * 任务通知汇总：运行中任务 + 执行完但未读的数量（总数 + 按脚本聚合）。
     * 顶栏指示器与代码编辑器文件列表的未读红点共用这一个接口。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/getPyTaskNoticeSummary", method = RequestMethod.GET)
    public Result<PyTaskNoticeSummaryVO> getPyTaskNoticeSummary() {
        return Result.success(baseDataService.getPyTaskNoticeSummary());
    }

    /**
     * 把一条执行记录标记为已读（执行记录列表点击后调用）。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/markPyTaskNotified", method = RequestMethod.POST)
    public Result<PyTaskVO> markPyTaskNotified(@RequestBody PyTaskParam pyTaskParam) {
        return Result.success(baseDataService.markPyTaskNotified(pyTaskParam.getTaskId()));
    }

    /**
     * 一键把所有未读的执行记录标记为已读（顶栏「待查看」气泡里的「设为已读」按钮调用）。
     * 返回实际被标记的条数。
     */
    // 权限：menu:codeEditor / menu:taskList（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_TASK_LIST})
    @RequestMapping(value = "/markAllPyTaskNotified", method = RequestMethod.POST)
    public Result<Integer> markAllPyTaskNotified() {
        return Result.success(baseDataService.markAllPyTaskNotified());
    }
}
