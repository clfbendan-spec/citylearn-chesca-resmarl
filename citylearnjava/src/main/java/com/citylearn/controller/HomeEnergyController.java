package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.service.HomeEnergyService;
import com.citylearn.vo.HomeEnergyFlowVO;
import com.citylearn.vo.HomeEnergyHourlyVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.io.IOException;

/**
 * 首页能源分配：按日预聚合与逐小时家庭耗电。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class HomeEnergyController {

    private static final Logger log = LoggerFactory.getLogger(HomeEnergyController.class);

    @Resource
    private HomeEnergyService homeEnergyService;

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
            return Result.success(homeEnergyService.getHomeEnergyFlow(taskId, untilTs, datasetYear, mode));
        } catch (IOException e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
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
            return Result.success(homeEnergyService.getHomeEnergyHourly(taskId, day, scope, untilTs, datasetYear));
        } catch (IOException e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
            return Result.fail(e.getMessage());
        }
    }
}
