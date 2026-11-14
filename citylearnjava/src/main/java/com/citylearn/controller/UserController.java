package com.citylearn.controller;

import com.citylearn.common.PageBean;
import com.citylearn.common.Result;
import com.citylearn.service.UserService;
import com.citylearn.vo.UserVO;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.servlet.http.HttpSession;

/**
 * 用户管理（仅超管）
 *
 * <p>权限不足由 {@code UserService.requireSuperAdmin} 抛 {@code ForbiddenException}，
 * 统一交给 {@code GlobalExceptionHandler} 转成 {@code code=403}，本类不再逐个 try/catch。</p>
 */
@RestController
@Api(value = "UserController", tags = {"用户管理"})
@RequestMapping("/web/user")
public class UserController {

    @Resource
    private UserService userService;

    @ApiOperation("分页查询用户")
    @RequestMapping(value = "/listPage", method = RequestMethod.GET)
    public Result<PageBean<UserVO>> listPage(@RequestParam(name = "username", required = false) String username,
                                             @RequestParam(name = "currentPage", required = false) Integer currentPage,
                                             @RequestParam(name = "pageSize", required = false) Integer pageSize,
                                             HttpSession session) {
        userService.requireSuperAdmin(session);
        return Result.success(userService.listPageUsers(username, currentPage, pageSize));
    }

    @ApiOperation("新增系统管理员")
    @RequestMapping(value = "/add", method = RequestMethod.POST)
    public Result<String> add(@RequestParam("username") String username,
                              @RequestParam("password") String password,
                              @RequestParam(name = "nickname", required = false) String nickname,
                              HttpSession session) {
        userService.requireSuperAdmin(session);
        userService.addAdmin(username, password, nickname);
        return Result.success();
    }

    @ApiOperation("编辑系统管理员（不含密码）")
    @RequestMapping(value = "/edit", method = RequestMethod.POST)
    public Result<String> edit(@RequestParam("id") String id,
                               @RequestParam(name = "username", required = false) String username,
                               @RequestParam(name = "nickname", required = false) String nickname,
                               HttpSession session) {
        userService.requireSuperAdmin(session);
        // 不接受 password：即使调用方传了也会被忽略，改密码统一走 /web/user/resetPassword
        userService.editAdmin(id, username, nickname);
        return Result.success();
    }

    @ApiOperation("删除系统管理员")
    @RequestMapping(value = "/delete", method = RequestMethod.POST)
    public Result<String> delete(@RequestParam("id") String id, HttpSession session) {
        userService.requireSuperAdmin(session);
        userService.deleteAdmin(id);
        return Result.success();
    }

    @ApiOperation("重置用户密码（仅超管）")
    @RequestMapping(value = "/resetPassword", method = RequestMethod.POST)
    public Result<String> resetPassword(@RequestParam("id") String id,
                                        @RequestParam("password") String password,
                                        HttpSession session) {
        userService.requireSuperAdmin(session);
        userService.resetPassword(id, password);
        return Result.success();
    }

    @ApiOperation("可分配权限树（来自 permission 表）")
    @RequestMapping(value = "/permissionTree", method = RequestMethod.GET)
    public Result<java.util.List<java.util.Map<String, Object>>> permissionTree(HttpSession session) {
        userService.requireSuperAdmin(session);
        return Result.success(userService.permissionTree());
    }

    @ApiOperation("查询指定用户已分配权限码（来自 user_permission 关联表）")
    @RequestMapping(value = "/getPermissions", method = RequestMethod.GET)
    public Result<java.util.List<String>> getPermissions(@RequestParam("id") String id, HttpSession session) {
        userService.requireSuperAdmin(session);
        return Result.success(userService.listUserPermissionCodes(id));
    }

    @ApiOperation("保存用户权限到关联表（仅超管，不可分配用户管理）")
    @RequestMapping(value = "/savePermissions", method = RequestMethod.POST)
    public Result<String> savePermissions(@RequestParam("id") String id,
                                          @RequestParam(name = "permissions", required = false) String permissionsJson,
                                          HttpSession session) {
        userService.requireSuperAdmin(session);
        java.util.List<String> permissions = new java.util.ArrayList<>();
        if (permissionsJson != null && !permissionsJson.trim().isEmpty()) {
            try {
                permissions = com.alibaba.fastjson.JSON.parseArray(permissionsJson, String.class);
            } catch (Exception e) {
                // 保持改造前的固定文案：不把 JSON 解析器的原始报错透给前端
                throw new IllegalArgumentException("权限数据格式错误");
            }
        }
        userService.savePermissions(id, permissions);
        return Result.success();
    }
}
