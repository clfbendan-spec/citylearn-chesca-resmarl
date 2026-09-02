package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Date;

/**
 * <p>
 * 
 * </p>
 *
 * @author Your Name
 * @since 2025-09-02
 */
@Getter
@Setter
@ToString
@TableName("py_file")
public class PyFile implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 主键
     */
    @TableId("id")
    private String id;

    /**
     * 文件名
     */
    @TableField("file_name")
    private String fileName;

    /**
     * 文件注释
     */
    @TableField("description")
    private String description;

    /**
     * 是否为系统默认文件
     */
    @TableField("if_system")
    private Boolean ifSystem;

    /**
     * 创建时间
     */
    @TableField("create_time")
    private Date createTime;

    /**
     * 创建人用户名
     */
    @TableField("create_user")
    private String createUser;

    /**
     * 是否展示此文件对应结果
     */
    @TableField("if_show")
    private Boolean ifShow;
}
