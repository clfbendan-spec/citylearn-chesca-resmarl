package com.citylearn.common;

/**
 * HttpSession 中存放的键
 */
public final class SessionKeys {

    private SessionKeys() {
    }

    /** 当前登录用户（UserVO） */
    public static final String LOGIN_USER = "LOGIN_USER";

    /**
     * 当前登录用户拥有的权限码集合（{@code Set<String>}），登录时写入。
     *
     * <p>SUPER_ADMIN 写入的是全部启用权限码（等价「拥有全部」），
     * 拦截器仍会对其再做一次角色直通判断，避免权限表被误改后超管反而被锁。
     */
    public static final String LOGIN_PERMS = "LOGIN_PERMS";
}
