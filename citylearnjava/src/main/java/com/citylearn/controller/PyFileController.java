package com.citylearn.controller;

import com.citylearn.common.PermissionCodes;
import com.citylearn.common.Result;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.param.PyFileParam;
import com.citylearn.service.PyFileService;
import com.citylearn.vo.PyFileVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;
import java.io.IOException;
import java.util.List;

/**
 * 代码编辑器「脚本文件」：文件列表、正文读写、新建、改名/简介、删除、算法配置保存。
 *
 * <p>由原 BaseDataController 按功能域拆出；类级路径保持 /web/basedata 不变，
 * 以免前端调用地址变化。</p>
 */
@RestController
@RequestMapping("/web/basedata")
public class PyFileController {

    private static final Logger log = LoggerFactory.getLogger(PyFileController.class);

    @Resource
    private PyFileService pyFileService;

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
        List<PyFileVO> list= pyFileService.getPyFileList(createUser, scriptType);
        return Result.success(list);
    }

    // 权限：menu:codeEditor（读接口，按菜单权限）
    @RequirePerm(PermissionCodes.MENU_CODE_EDITOR)
    @RequestMapping(value = "/getPyFile",method = RequestMethod.GET)
    public Result<String> getPyFile(@RequestParam(name = "id") String id){
        String content= pyFileService.getPyFile(id);
        return Result.success(content);
    }

    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
    @RequestMapping(value = "/addPyFile",method = RequestMethod.POST)
    public Result<PyFileVO> addPyFile(){
        PyFileVO pyFileVO= null;
        try {
            pyFileVO = pyFileService.addPyFile();
            return Result.success(pyFileVO);
        } catch (IOException e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
            return Result.fail(e.getMessage());
        }

    }

    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
    @RequestMapping(value = "/savePyFile",method = RequestMethod.POST)
    public Result<String> savePyFile(@RequestBody PyFileParam pyFileParam){
        try {
            pyFileService.savePyFile(pyFileParam);
            return Result.success();
        } catch (Exception e) {
            log.error("请求处理失败: {}", e.getMessage(), e);
            return Result.fail(e.getMessage());
        }
    }

    // 权限：codeEditor:deleteFile
    @RequirePerm(PermissionCodes.CODE_DELETE_FILE)
    @RequestMapping(value = "/deletePyFile",method = RequestMethod.POST)
    public Result<PyFileVO> deletePyFile(@RequestBody PyFileParam pyFileParam){
        pyFileService.deletePyFile(pyFileParam);
        return Result.success();
    }

    /**
     * 保存某个脚本的算法配置（py_file.algorithm_config，JSON 数组字符串）。
     */
    // 权限：codeEditor:save
    @RequirePerm(PermissionCodes.CODE_SAVE)
    @RequestMapping(value = "/savePyFileAlgorithmConfig", method = RequestMethod.POST)
    public Result<Void> savePyFileAlgorithmConfig(@RequestBody PyFileParam pyFileParam) {
        pyFileService.savePyFileAlgorithmConfig(
                pyFileParam.getId(), pyFileParam.getAlgorithmConfig());
        return Result.success();
    }
}
