package com.citylearn.common;

/**
 * 用户角色常量
 */
public final class UserRoles {

    private UserRoles() {
    }

    /** 超级管理员：可用户管理 */
    public static final String SUPER_ADMIN = "SUPER_ADMIN";

    /** 系统管理员：可使用系统，不可管理用户 */
    public static final String ADMIN = "ADMIN";
}
