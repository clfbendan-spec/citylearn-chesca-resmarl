package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.service.AlphaSweepService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.io.IOException;
import java.util.List;
import java.util.Map;

/**
 * α 扫描：运行列表与详情曲线。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class AlphaSweepController {

    private static final Logger log = LoggerFactory.getLogger(AlphaSweepController.class);

    @Resource
    private AlphaSweepService alphaSweepService;

    /** α 扫描 registry 列表（ablation_results/registry/index.json） */
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
    @RequestMapping(value = "/getAlphaSweepRuns", method = RequestMethod.GET)
    public Result<List<Map<String, Object>>> getAlphaSweepRuns() {
        return Result.success(alphaSweepService.listAlphaSweepRuns());
    }

    /** α 扫描详情（含各 α 点 District KPI，供看板曲线） */
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
    @RequestMapping(value = "/getAlphaSweepDetail", method = RequestMethod.GET)
    public Result<Map<String, Object>> getAlphaSweepDetail(@RequestParam(name = "runId") String runId) {
        try {
            return Result.success(alphaSweepService.getAlphaSweepDetail(runId));
        } catch (IOException e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
            return Result.fail(e.getMessage());
        }
    }
}
