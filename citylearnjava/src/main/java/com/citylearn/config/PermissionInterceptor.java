package com.citylearn.config;

import com.alibaba.fastjson.JSON;
import com.citylearn.common.Result;
import com.citylearn.common.SessionKeys;
import com.citylearn.common.UserRoles;
import com.citylearn.common.annotation.RequirePerm;
import com.citylearn.vo.UserVO;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.http.HttpSession;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * 接口级权限拦截：读 {@link RequirePerm} 注解，用 session 里的权限码集合判断。
 *
 * <p>执行顺序在 {@link LoginInterceptor} 之后（见 WebMvcConfig 的 order）：
 * <ul>
 *   <li>没标 {@code @RequirePerm} 的接口（读取类）只要求登录，这里直接放行；</li>
 *   <li>标了的接口：SUPER_ADMIN 直通；其他人要求 session 权限集合里至少命中一个码；</li>
 *   <li>注解里的多个码是 OR 语义（同一接口被多个页面共用时用得上）。</li>
 * </ul>
 *
 * <p><b>权限何时生效</b>：权限码集合在登录时写进 session；{@code /web/auth/current}
 * （前端进入页面/刷新都会调用）也会重新写入。因此管理员改完某人的权限后，
 * 对方**刷新页面即可生效**，不必重新登录。
 */
@Component
public class PermissionInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws Exception {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }
        if (!(handler instanceof HandlerMethod)) {
            // 静态资源 / 错误页等：登录拦截已处理，这里不参与鉴权
            return true;
        }
        HandlerMethod handlerMethod = (HandlerMethod) handler;
        RequirePerm required = handlerMethod.getMethodAnnotation(RequirePerm.class);
        if (required == null) {
            required = handlerMethod.getBeanType().getAnnotation(RequirePerm.class);
        }
        if (required == null || required.value() == null || required.value().length == 0) {
            return true;
        }

        HttpSession session = request.getSession(false);
        UserVO user = null;
        if (session != null) {
            Object attr = session.getAttribute(SessionKeys.LOGIN_USER);
            if (attr instanceof UserVO) {
                user = (UserVO) attr;
            }
        }
        if (user == null) {
            writeJson(response, 401, "未登录或登录已过期");
            return false;
        }
        // 超管直通：等价「拥有全部权限」，且不依赖 permission 表是否被误改
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            return true;
        }

        Set<String> owned = readSessionPerms(session);
        for (String code : required.value()) {
            if (owned.contains(code)) {
                return true;
            }
        }
        writeJson(response, 403, "无权限访问该接口（需要权限：" + String.join(" / ", required.value()) + "）");
        return false;
    }

    /** session 里的权限码集合；取不到时返回空集合（等价无任何权限） */
    private Set<String> readSessionPerms(HttpSession session) {
        if (session == null) {
            return Collections.emptySet();
        }
        Object attr = session.getAttribute(SessionKeys.LOGIN_PERMS);
        if (attr instanceof Collection) {
            Set<String> set = new LinkedHashSet<>();
            for (Object item : (Collection<?>) attr) {
                if (item != null) {
                    set.add(String.valueOf(item));
                }
            }
            return set;
        }
        // 兜底：老 session（本次升级前登录的）没有 LOGIN_PERMS，退回 UserVO.permissions
        Object userAttr = session.getAttribute(SessionKeys.LOGIN_USER);
        if (userAttr instanceof UserVO) {
            UserVO vo = (UserVO) userAttr;
            if (vo.getPermissions() != null) {
                return new LinkedHashSet<>(vo.getPermissions());
            }
        }
        return Collections.emptySet();
    }

    private void writeJson(HttpServletResponse response, int code, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        Result<String> result = Result.fail(message);
        result.setCode(code);
        response.getWriter().write(JSON.toJSONString(result));
    }
}
