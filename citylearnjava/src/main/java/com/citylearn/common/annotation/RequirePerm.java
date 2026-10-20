package com.citylearn.common.annotation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 接口级权限声明。
 *
 * <p>标在 Controller 方法（或整个 Controller）上，由
 * {@code com.citylearn.config.PermissionInterceptor} 在请求进入时校验。
 *
 * <p><b>多个权限码之间是「任一满足」(OR)</b>：同一个接口被两个页面共用时需要它，
 * 例如 {@code /web/basedata/deletePyTask} 同时服务「代码编辑器-删除记录」与
 * 「任务管理-删除任务」两个按钮。
 *
 * <p><b>不标该注解 = 只要求登录，不校验权限</b>（所有读取类接口都是这样）。
 *
 * <p>权限码与 {@code permission.code} 一致，见 {@code com.citylearn.common.PermissionCodes}。
 */
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface RequirePerm {

    /** 需要的权限码；满足其中任意一个即放行 */
    String[] value();
}
