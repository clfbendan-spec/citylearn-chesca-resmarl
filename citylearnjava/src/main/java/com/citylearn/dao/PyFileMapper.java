package com.citylearn.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.citylearn.entity.PyFile;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * <p>
 *  Mapper 接口
 * </p>
 *
 * @author Your Name
 * @since 2025-09-02
 */
public interface PyFileMapper extends BaseMapper<PyFile> {
    @Select("SELECT * FROM py_file WHERE create_user = #{createUser} or if_system = 1")
    List<PyFile> getPyFileList(@Param("createUser")String createUser);
}
