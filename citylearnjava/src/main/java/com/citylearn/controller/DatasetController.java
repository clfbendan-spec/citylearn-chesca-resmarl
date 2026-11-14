package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.service.CitylearnDatasetService;
import com.citylearn.vo.CitylearnDatasetVO;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.util.List;

/**
 * 本地 CityLearn 数据集列表。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class DatasetController {

    @Resource
    private CitylearnDatasetService citylearnDatasetService;

    /**
     * 本地 CityLearn 数据集列表（MySQL citylearn_dataset），供原始数据 / 评估配置共用。
     */
    // 权限：menu:dataList / menu:codeEditor / menu:resMarlConfig（读接口，按菜单权限）
    @RequirePerm({PermissionCodes.MENU_DATA_LIST, PermissionCodes.MENU_CODE_EDITOR, PermissionCodes.MENU_RES_MARL})
    @RequestMapping(value = "/getDatasetList", method = RequestMethod.GET)
    public Result<List<CitylearnDatasetVO>> getDatasetList() {
        return Result.success(citylearnDatasetService.listEnabledDatasets());
    }
}
