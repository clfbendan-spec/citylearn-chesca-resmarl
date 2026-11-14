package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.ResMarlConfigParam;
import com.citylearn.service.BatteryMinSocConfigService;
import com.citylearn.vo.ChescaBatteryConfigVO;
import com.citylearn.vo.ResMarlConfigVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;

/**
 * 电池 SOC 下限与 CHESCA-ResMARL 配置的读取、保存、恢复默认。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class BatteryConfigController {

    @Resource
    private BatteryMinSocConfigService batteryMinSocConfigService;

    /** 获取 CHESCA 电池 SOC 配置（小时下限 + 正常/停电上限） */
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
    @RequestMapping(value = "/getBatteryMinSocConfig", method = RequestMethod.GET)
    public Result<ChescaBatteryConfigVO> getBatteryMinSocConfig() {
        return Result.success(batteryMinSocConfigService.getConfig());
    }

    /** 保存 CHESCA 电池 SOC 配置 */
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
    @RequestMapping(value = "/saveBatteryMinSocConfig", method = RequestMethod.POST)
    public Result<String> saveBatteryMinSocConfig(@RequestBody ChescaBatteryConfigVO config) {
        batteryMinSocConfigService.saveConfig(config);
        return Result.success();
    }

    /** 获取 ResMARL 残差配置 */
    // 权限：menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_RES_MARL)
    @RequestMapping(value = "/getResMarlConfig", method = RequestMethod.GET)
    public Result<ResMarlConfigVO> getResMarlConfig() {
        return Result.success(batteryMinSocConfigService.getResMarlConfig());
    }

    /** 保存 ResMARL 残差配置到 algorithm_config */
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
    @RequestMapping(value = "/saveResMarlConfig", method = RequestMethod.POST)
    public Result<String> saveResMarlConfig(@RequestBody ResMarlConfigParam param) {
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
    }

    /** 恢复 ResMARL 默认配置（关闭，α=0） */
    // 权限：resMarlConfig:operate
    @RequirePerm(PermissionCodes.RES_MARL_OPERATE)
    @RequestMapping(value = "/resetResMarlConfig", method = RequestMethod.POST)
    public Result<ResMarlConfigVO> resetResMarlConfig() {
        ResMarlConfigVO defaults = batteryMinSocConfigService.getDefaultResMarlConfig();
        batteryMinSocConfigService.saveResMarlConfig(defaults);
        return Result.success(batteryMinSocConfigService.getResMarlConfig());
    }
}
