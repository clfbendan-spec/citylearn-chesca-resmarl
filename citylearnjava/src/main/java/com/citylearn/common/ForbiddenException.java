package com.citylearn.common;

/**
 * 访问被拒绝（HTTP 语义上对应 403，本项目沿用「HTTP 200 + {@code code=403}」的约定）。
 *
 * <p>存在的意义是把「权限不足」和「业务状态错误」分开。此前两者都用
 * {@link IllegalStateException} 表示，导致无法全局映射：{@code UserController} 需要把
 * 它转成 403，而 {@code BatteryMinSocConfigService} 的同类型异常必须是 500。</p>
 *
 * <p>由 {@link GlobalExceptionHandler} 统一处理为 {@code code=403}，Controller 不再逐个捕获。</p>
 */
public class ForbiddenException extends RuntimeException {

    public ForbiddenException(String message) {
        super(message);
    }
}
