package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.Date;

/**
 * 算法参数配置组（algorithm_param_config_set）。
 *
 * <p>把若干相关的参数定义聚成一组，参数配置页用页签区分「单独配置 / 配置组」。
 * 组成员存在 {@link #members}（{@code algorithm_param_config.id} 的 JSON 数组），
 * 同时在 {@link AlgorithmParamConfig#getIsMember()} 上冗余一份标记，
 * 让「单独配置」页能一句 SQL 过滤出来，不必反查每个组的 members。
 */
@Getter
@Setter
@ToString
@TableName("algorithm_param_config_set")
public class AlgorithmParamConfigSet implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键 */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /** 创建时间 */
    @TableField("create_time")
    private Date createTime;

    /** 组名称 */
    @TableField("name")
    private String name;

    /**
     * 简介。
     *
     * <p>⚠️ 列名 desc 是 MySQL 保留字，注解里必须带反引号 —— 否则 MyBatis-Plus 拼出的
     * SELECT 会变成 {@code ... ,desc FROM ...}，直接语法错误。
     */
    @TableField("`desc`")
    private String desc;

    /**
     * 组成员：{@code algorithm_param_config.id} 的 JSON 数组字符串，如 {@code [1,2,3]}。
     * 解析/序列化由 Service 负责，实体里保持原始文本。
     */
    @TableField("members")
    private String members;
}
