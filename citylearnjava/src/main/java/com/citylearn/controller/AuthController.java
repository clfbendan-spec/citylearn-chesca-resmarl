package com.citylearn.controller;

import com.citylearn.common.Result;
import com.citylearn.service.UserService;
import com.citylearn.vo.UserVO;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.servlet.http.HttpSession;

/**
 * 登录认证（Session）
 */
@RestController
@Api(value = "AuthController", tags = {"登录认证"})
@RequestMapping("/web/auth")
public class AuthController {

    @Resource
    private UserService userService;

    @ApiOperation("登录")
    @RequestMapping(value = "/login", method = RequestMethod.POST)
    public Result<UserVO> login(@RequestParam("username") String username,
                                @RequestParam("password") String password,
                                HttpSession session) {
        try {
            UserVO user = userService.login(username, password, session);
            return Result.success(user);
        } catch (IllegalArgumentException e) {
            return Result.fail(e.getMessage());
        }
    }

    @ApiOperation("退出登录")
    @RequestMapping(value = "/logout", method = RequestMethod.POST)
    public Result<String> logout(HttpSession session) {
        userService.logout(session);
        return Result.success();
    }

    @ApiOperation("当前登录用户")
    @RequestMapping(value = "/current", method = RequestMethod.GET)
    public Result<UserVO> current(HttpSession session) {
        UserVO user = userService.currentUser(session);
        if (user == null) {
            Result<UserVO> result = Result.fail("未登录");
            result.setCode(401);
            return result;
        }
        return Result.success(user);
    }
}
