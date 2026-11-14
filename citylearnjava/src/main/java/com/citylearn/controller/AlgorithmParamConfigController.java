package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.AlgorithmParamConfigParam;
import com.citylearn.param.AlgorithmParamConfigSetParam;
import com.citylearn.service.AlgorithmParamConfigService;
import com.citylearn.vo.AlgorithmParamConfigVO;
import com.citylearn.vo.AlgorithmParamConfigSetDetailVO;
import com.citylearn.vo.AlgorithmParamConfigSetVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.List;

/**
 * 参数配置：参数目录与配置组的增删改查。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class AlgorithmParamConfigController {

    @Resource
    private AlgorithmParamConfigService algorithmParamConfigService;

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
        Boolean filter = isMember == null ? null : isMember != 0;
        return Result.success(algorithmParamConfigService.listAlgorithmParamConfigs(filter));
    }

    /** 参数配置页：新增参数定义 */
    // 权限：algorithmParam:itemCreate
    @RequirePerm(PermissionCodes.PARAM_ITEM_CREATE)
    @RequestMapping(value = "/addAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<AlgorithmParamConfigVO> addAlgorithmParamConfig(
            @RequestBody AlgorithmParamConfigParam param) {
        return Result.success(algorithmParamConfigService.addAlgorithmParamConfig(param));
    }

    /** 参数配置页：编辑参数定义（系统内置参数只允许改简介） */
    // 权限：algorithmParam:itemEdit
    @RequirePerm(PermissionCodes.PARAM_ITEM_EDIT)
    @RequestMapping(value = "/updateAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<Void> updateAlgorithmParamConfig(@RequestBody AlgorithmParamConfigParam param) {
        algorithmParamConfigService.updateAlgorithmParamConfig(param);
        return Result.success();
    }

    /** 参数配置页：删除参数定义（系统内置参数禁止删除） */
    // 权限：algorithmParam:itemDelete
    @RequirePerm(PermissionCodes.PARAM_ITEM_DELETE)
    @RequestMapping(value = "/deleteAlgorithmParamConfig", method = RequestMethod.POST)
    public Result<Void> deleteAlgorithmParamConfig(@RequestBody AlgorithmParamConfigParam param) {
        algorithmParamConfigService.deleteAlgorithmParamConfig(param == null ? null : param.getId());
        return Result.success();
    }

    /* ==================== 参数配置页：配置组（algorithm_param_config_set） ==================== */

    /** 配置组列表（组名称 / 创建时间 / 简介 / 成员数） */
    // 权限：menu:algorithmParam / menu:codeEditor（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_ALGORITHM_PARAM, PermissionCodes.MENU_CODE_EDITOR})
    @RequestMapping(value = "/getAlgorithmParamConfigSetList", method = RequestMethod.GET)
    public Result<List<AlgorithmParamConfigSetVO>> getAlgorithmParamConfigSetList() {
        return Result.success(algorithmParamConfigService.listAlgorithmParamConfigSets());
    }

    /** 配置组详情：组信息 + 组内参数定义（点「详情」进入组内参数页） */
    // 权限：menu:algorithmParam / menu:codeEditor（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_ALGORITHM_PARAM, PermissionCodes.MENU_CODE_EDITOR})
    @RequestMapping(value = "/getAlgorithmParamConfigSetDetail", method = RequestMethod.GET)
    public Result<AlgorithmParamConfigSetDetailVO> getAlgorithmParamConfigSetDetail(
            @RequestParam(name = "id") Integer id) {
        return Result.success(algorithmParamConfigService.getAlgorithmParamConfigSetDetail(id));
    }

    /** 新增配置组 */
    // 权限：algorithmParam:setCreate
    @RequirePerm(PermissionCodes.PARAM_SET_CREATE)
    @RequestMapping(value = "/addAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<AlgorithmParamConfigSetVO> addAlgorithmParamConfigSet(
            @RequestBody AlgorithmParamConfigSetParam param) {
        return Result.success(algorithmParamConfigService.addAlgorithmParamConfigSet(param));
    }

    /** 编辑配置组（名称 / 简介 / 成员） */
    // 权限：algorithmParam:setEdit / setMoveIn / setMoveOut
    @RequirePerm({PermissionCodes.PARAM_SET_EDIT, PermissionCodes.PARAM_SET_MOVE_IN, PermissionCodes.PARAM_SET_MOVE_OUT})
    @RequestMapping(value = "/updateAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<Void> updateAlgorithmParamConfigSet(@RequestBody AlgorithmParamConfigSetParam param) {
        algorithmParamConfigService.updateAlgorithmParamConfigSet(param);
        return Result.success();
    }

    /** 删除配置组（组内参数会被重新计算 is_member） */
    // 权限：algorithmParam:setDelete
    @RequirePerm(PermissionCodes.PARAM_SET_DELETE)
    @RequestMapping(value = "/deleteAlgorithmParamConfigSet", method = RequestMethod.POST)
    public Result<Void> deleteAlgorithmParamConfigSet(@RequestBody AlgorithmParamConfigSetParam param) {
        algorithmParamConfigService.deleteAlgorithmParamConfigSet(param == null ? null : param.getId());
        return Result.success();
    }
}
