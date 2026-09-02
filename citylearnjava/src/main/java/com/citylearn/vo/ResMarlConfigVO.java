package com.citylearn.vo;

import lombok.Data;

/**
 * CHESCA-ResMARL 配置（CHESCA + Multi-Agent SAC 残差），对应 algorithm_config 表。
 */
@Data
public class ResMarlConfigVO {

    /** 是否启用 CHESCA-ResMARL */
    private Boolean resmarlEnabled;

    /** none | multi_agent */
    private String marlMode;

    /** Multi-Agent SAC 训练轮数 */
    private Integer multiAgentTrainEpochs;

    /** Multi-Agent 评估时是否 explore */
    private Boolean multiAgentExplore;

    /** 残差强度 α */
    private Double residualAlpha;

    /** 残差动作掩码 {dhw, ele, tmp} */
    private Object residualActionMask;

    /** 是否在 Safety 之后应用残差 */
    private Boolean resmarlAfterSafety;

    /** 是否启用训测 schema 分离（方案 A） */
    private Boolean schemaSplitEnabled;

    /** SAC 训练 schema */
    private String trainSchema;

    /** CHESCA 仿真/KPI schema */
    private String evalSchema;
}
