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
     *  执行状态(0执行中 1执行完成 2执行失败 3运行终止-用户手动终止 4已中断 5待执行)
     */
    @TableField("status")
    private Integer status;

    /**
     * 任务名称：type=0（训练+评估编排任务）的名称，由用户在「新建任务」时填写、待执行时可修改；
     * type=1（代码编辑器直接执行的简易任务）不用此列，其名称一律取 py_file.file_name。
     *
     * <p>与 show_name 的区别：show_name 是「仿真仪表盘展示名称」，
     * 只在 if_show=1 的执行成功任务上用于分组命名，与任务本身的名字无关。
     */
    @TableField("task_name")
    private String taskName;


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
     * 是否已提醒/已读：false 未读（执行完成后尚未被查看） true 已读。
     * 仅在 status != 0（已结束）时作为「未读」计数；新任务插入时为 false。
     */
    @TableField("if_notified")
    private Boolean ifNotified;

    /**
     * 任务类型：0=训练+评估编排任务（任务管理页「新建任务」创建）；
     * 1=代码编辑器直接执行的简易任务（含全部历史数据）。
     * 建表默认值为 1，历史数据由 db/py_task_pipeline_task.sql 回填。
     */
    @TableField("type")
    private Integer type;

    /**
     * 是否子任务：true = 编排任务（type=0）拆出的训练/评估子任务。
     *
     * <p>子任务自身也是 py_task 的一行，id 为 {@code <父任务id>-train} / {@code <父任务id>-eval}，
     * 由「执行」自动串联（训练跑完接着跑评估）。任务管理页主列表不展示它们
     * （只在其父任务详情展开的子表格里显示）；代码编辑器记录列表会带「子任务」标识展示。
     */
    @TableField("is_subtask")
    private Boolean isSubtask;

    /**
     * 本任务的脚本配置（JSON 字符串，卡片结构）：替代原来的 train_config / eval_config。
     *
     * <p>内容形如 {@code {"datasetId":1,"schemaKey":"...","pyId":"9","scriptName":"...",
     * "trainEpochs":360,"trainBatchSize":1024,"config":"[...]"}}；其中内层 config 是
     * 该任务专用的脚本配置（与 py_file.algorithm_config 同格式，不回写脚本文件），
     * 执行时由它翻译成命令行参数（为空则沿用脚本文件自身的配置）。
     *
     * <p>父任务（type=0、is_subtask=false）不持有配置 —— 两张卡的配置分别落在
     * {@code -train} / {@code -eval} 两个子任务上。
     */
    @TableField("config")
    private String config;

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
