package com.citylearn.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.citylearn.entity.UserPermission;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 用户权限关联 Mapper
 */
public interface UserPermissionMapper extends BaseMapper<UserPermission> {

    @Select("SELECT p.code FROM user_permission up " +
            "INNER JOIN permission p ON p.id = up.permission_id " +
            "WHERE up.user_id = #{userId} AND p.enabled = 1 " +
            "ORDER BY p.sort_order ASC, p.code ASC")
    List<String> selectPermissionCodesByUserId(@Param("userId") String userId);
}
