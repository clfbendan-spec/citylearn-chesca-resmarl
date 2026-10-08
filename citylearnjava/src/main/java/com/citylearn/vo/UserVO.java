package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * 用户信息（不含密码）
 */
@Getter
@Setter
@ToString
public class UserVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private String id;
    private String username;
    private String nickname;
    private String role;
    /** 已分配权限码（超管为全部可分配权限） */
    private List<String> permissions = new ArrayList<>();
    private Date createTime;
    private Date updateTime;
}
