package com.citylearn.param;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;

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
public class PyFileParam implements Serializable {

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
     * 代码
     */
    private String code;

    /**
     * 是否展示此文件对应结果
     */
    private Boolean ifShow;

}
