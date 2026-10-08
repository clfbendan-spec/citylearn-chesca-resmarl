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

    /**
     * 脚本类型，用于代码编辑器页文件列表筛选：
     * train=只训练 / eval=只评估 / both=训练+评估一体
     */
    @TableField("script_type")
    private String scriptType;

    /**
     * 该脚本的算法配置（JSON 数组），由代码编辑器文件列表的「配置」按钮保存：
     * <pre>[{"id":1,"param_name":"train-schema","value":"1"}, ...]</pre>
     * <ul>
     *   <li>id —— algorithm_param_config.id，选了哪个参数</li>
     *   <li>param_name —— 参数别名（界面第二列右侧输入框的值；留空表示沿用原名）</li>
     *   <li>value —— 参数值；数据集类参数存 citylearn_dataset.id</li>
     * </ul>
     */
    @TableField("algorithm_config")
    private String algorithmConfig;
}
