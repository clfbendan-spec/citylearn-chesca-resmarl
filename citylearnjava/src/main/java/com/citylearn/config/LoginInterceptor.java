package com.citylearn.config;

import com.alibaba.fastjson.JSON;
import com.citylearn.common.Result;
import com.citylearn.common.SessionKeys;
import com.citylearn.vo.UserVO;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.http.HttpSession;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * 登录拦截：未登录禁止访问业务接口
 */
@Component
public class LoginInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }
        HttpSession session = request.getSession(false);
        if (session != null) {
            Object attr = session.getAttribute(SessionKeys.LOGIN_USER);
            if (attr instanceof UserVO) {
                return true;
            }
        }
        writeUnauthorized(response);
        return false;
    }

    private void writeUnauthorized(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        Result<String> result = Result.fail("未登录或登录已过期");
        result.setCode(401);
        response.getWriter().write(JSON.toJSONString(result));
    }
}
