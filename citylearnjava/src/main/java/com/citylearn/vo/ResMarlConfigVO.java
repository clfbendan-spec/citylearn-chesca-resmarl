package com.citylearn.vo;

import lombok.Data;

/**
 * CHESCA-ResMARL 配置（CHESCA + Multi-Agent SAC 残差），对应 algorithm_config 表。
 */
@Data
public class ResMarlConfigVO {

    /** 是否启用 CHESCA-ResMARL（兼容字段；配置页已去掉开关，实际由入口脚本决定） */
    private Boolean resmarlEnabled;

    /** none | multi_agent */
    private String marlMode;

    /** Multi-Agent SAC 训练轮数 */
    private Integer multiAgentTrainEpochs;

    /** Multi-Agent 评估时是否 explore */
    private Boolean multiAgentExplore;

    /**
     * Multi-agent.py 保存的 RLlib checkpoint 路径。
     * 非空时 CHESCA-ResMARL 加载该模型并跳过现场训练。
     */
    private String multiAgentCheckpoint;

    /** 残差强度 α */
    private Double residualAlpha;

    /** 残差动作掩码 {dhw, ele, tmp} */
    private Object residualActionMask;

    /** 是否在 Safety 之后应用残差 */
    private Boolean resmarlAfterSafety;

    /** Multi-agent.py 训练 schema */
    private String trainSchema;

    /** Multi-agent.py 评估 schema */
    private String multiAgentEvalSchema;

    /** CHESCA_ResMARL.py 仿真/KPI schema（resmarl_eval_schema，与 CHESCA.py 的 eval_schema 独立） */
    private String evalSchema;
}
