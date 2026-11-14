package com.citylearn.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常兜底。
 *
 * <p>等价替换各 Controller 原先逐方法重复的模板：</p>
 * <pre>
 * try { ... } catch (Exception e) { e.printStackTrace(); return Result.fail(e.getMessage()); }
 * </pre>
 * <p>差别只有两处，都是改善：异常堆栈进入日志框架（可检索、带时间戳），而不是打到标准错误。</p>
 *
 * <p><b>刻意保持</b> {@code code=500} 且不标注 {@code @ResponseStatus}，即 HTTP 仍为 200，
 * 与改造前业务异常响应逐字一致；前端 axios 拦截器只读 {@code body.code}，不受影响。</p>
 *
 * <p><b>权限语义走专用异常</b>：{@link ForbiddenException} 由下面的 handler 映射为 {@code code=403}。
 * 之所以不把 {@code IllegalStateException} 直接映射成 403，是因为 {@code BatteryMinSocConfigService}
 * 也用同类型表示业务状态错误，那是 500 而非 403。类型分开，全局映射才安全。</p>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * 权限不足。保持 HTTP 200 + {@code code=403}，与改造前 Controller 逐个 catch 时一致，
     * 前端 axios 拦截器据此弹「无权限」提示。
     */
    @ExceptionHandler(ForbiddenException.class)
    public Result<Void> handleForbidden(ForbiddenException e) {
        log.warn("拒绝访问: {}", e.getMessage());
        Result<Void> result = Result.fail(e.getMessage());
        result.setCode(403);
        return result;
    }

    @ExceptionHandler(Exception.class)
    public Result<Void> handleException(Exception e) {
        log.error("请求处理失败: {}", e.getMessage(), e);
        return Result.fail(e.getMessage());
    }
}
