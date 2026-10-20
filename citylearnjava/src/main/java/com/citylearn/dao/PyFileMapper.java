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
/**
 * 注意：本方法在 XML（resources/mappers/PyFileMapper.xml）里也定义了同名 statement。
 * MyBatis 只保留先加载的那一份，哪一份生效取决于加载顺序，很难靠阅读判断。
 * 因此这里与 XML 保持**逐字一致**的 SQL，改动时必须两处同时改，否则会出现
 * "改了 XML 却没生效"（或反之）的隐蔽问题。
 */
public interface PyFileMapper extends BaseMapper<PyFile> {

    /**
     * 代码编辑器「文件列表」：返回该用户可见的脚本，可选按脚本类型筛选。
     *
     * <p><b>不再按 if_show 过滤</b>：脚本级「展示/未展示」按钮已移除（展示语义只认
     * 执行记录的 {@code py_task.if_show}）。历史数据里仍有 if_show=0 的脚本（如
     * local_evaluation.py），若继续过滤会导致它们永久不可见且无入口恢复；
     * 新建脚本过去也默认写 if_show=0，会直接从列表消失。
     *
     * @param createUser 创建人（当前固定 admin）
     * @param scriptType 脚本类型 train / eval / both；传 null（或空串，由 Service 归一化）
     *                   表示不筛选。取值必须带 jdbcType，否则 MyBatis 在参数为 null 时
     *                   会抛 "JdbcType must be specified for all nullable parameters"。
     */
    @Select("SELECT * FROM py_file "
            + "WHERE (create_user = #{createUser} OR if_system = 1) "
            + "  AND (#{scriptType,jdbcType=VARCHAR} IS NULL "
            + "       OR script_type = #{scriptType,jdbcType=VARCHAR})")
    List<PyFile> getPyFileList(@Param("createUser") String createUser,
                               @Param("scriptType") String scriptType);
}
