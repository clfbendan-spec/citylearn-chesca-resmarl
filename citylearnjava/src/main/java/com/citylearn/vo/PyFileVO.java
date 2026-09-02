package com.citylearn.vo;

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
public class PyFileVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 主键
     */
    private String id;

    /**
     * 文件名
     */
    private String fileName;


    /**
     * 文件注释
     */
    private String description;

    /**
     * 是否为系统默认文件
     */
    private Boolean ifSystem;

    /**
     * 创建时间
     */
    private Date createTime;

    /**
     * 创建人用户名
     */
    private String createUser;

    /**
     * 是否展示此文件对应结果
     */
    private Boolean ifShow;
}
