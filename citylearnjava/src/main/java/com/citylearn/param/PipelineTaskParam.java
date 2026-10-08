package com.citylearn.param;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * 「新建任务」入参：训练卡 + 评估卡两张卡片的配置。
 *
 * <p>对应任务管理页「新建任务」弹窗（训练卡 → 评估卡，固定两步）。
 * 后端落库时写入 py_task 一行：type=0，两张卡片分别序列化进
 * train_config / eval_config 两个字段。
 */
@Getter
@Setter
@ToString
public class PipelineTaskParam implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 任务 ID。
     * 新建时为空（忽略）；编辑走 /updatePipelineTask 时必填。
     */
    private String taskId;

    /**
     * 任务名称（必填，最长 128 字符）。
     * 落在 py_task.task_name，任务管理页「任务名称」列对 type=0 就显示它。
     */
    private String taskName;

    /** 第一张卡：训练卡（必填） */
    private PipelineStepConfig trainConfig;

    /** 第二张卡：评估卡（必填） */
    private PipelineStepConfig evalConfig;
}
