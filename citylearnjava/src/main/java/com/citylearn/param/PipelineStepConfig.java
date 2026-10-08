package com.citylearn.param;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * 编排任务单张卡片的配置（训练卡 / 评估卡共用）。
 *
 * <p>前端「新建任务」弹窗里两张卡片各自提交一个本对象，后端校验后序列化成
 * JSON 字符串，分别写入 py_task.train_config / py_task.eval_config。
 *
 * <p>同时保存 id / schemaKey 与名称快照（datasetName、scriptName）：
 * id 与 schemaKey 是配置的事实来源，名称只是写入时刻的展示快照 ——
 * 这样任务列表即使不联表也能显示"当时选了什么"，
 * 且数据集/脚本后来改名或删除也不会让历史配置变得不可读。
 */
@Getter
@Setter
@ToString
public class PipelineStepConfig implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** citylearn_dataset.id（下拉选中项） */
    private Integer datasetId;

    /** 数据集 schema 目录名（真正传给 python 脚本的值） */
    private String schemaKey;

    /** 数据集展示名快照（如「2023 local（3栋·720步）」） */
    private String datasetName;

    /** py_file.id（下拉选中项：训练卡只允许 train 类型，评估卡只允许 eval 类型） */
    private String pyId;

    /** 脚本名快照（如 Multi-agent-train.py） */
    private String scriptName;

    /** 训练轮数（仅训练卡使用，评估卡为 null） */
    private Integer trainEpochs;

    /** 训练批大小（仅训练卡使用，评估卡为 null） */
    private Integer trainBatchSize;

    /**
     * 本任务专用的脚本配置（JSON 字符串，与 py_file.algorithm_config 的格式完全一致：
     * 新格式为分组数组 [{"type":"alone","params":[...]},{"type":"set","set_id":1,"params":[...]}]）。
     *
     * <p>语义：任务级覆盖，**不回写脚本文件**。点「配置」按钮时先把脚本文件自己的配置
     * 带出来，用户改完只落在这里；为空表示沿用脚本文件自身的配置。
     */
    private String config;
}
