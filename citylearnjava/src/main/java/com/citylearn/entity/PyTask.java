package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.util.Date;

/**
 * <p>
 * 
 * </p>
 *
 * @author Your Name
 * @since 2025-06-08
 */
@Getter
@Setter
@ToString
@TableName("py_task")
public class PyTask implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableId("id")
    private String id;

    /**
     *  python文件id
     */
    @TableField("py_id")
    private String pyId;

    /**
     *  执行状态(0执行中 1执行完成 2执行失败)
     */
    @TableField("status")
    private Integer status;


    /**
     *  删除标记
     */
    @TableField("if_delete")
    private Boolean ifDelete;

    /**
     * 是否在仿真仪表盘展示（仅执行成功任务有效；默认 false）
     */
    @TableField("if_show")
    private Boolean ifShow;

    /**
     * 仪表盘展示名称（有值时分组优先用此名称）
     */
    @TableField("show_name")
    private String showName;

    /**
     *  创建时间
     */
    @TableField("create_time")
    private Date createTime;

    /**
     *  更新时间
     */
    @TableField("update_time")
    private Date updateTime;
}
