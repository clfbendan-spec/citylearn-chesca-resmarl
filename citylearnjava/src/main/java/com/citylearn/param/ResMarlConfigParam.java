package com.citylearn.param;

import lombok.Data;

/**
 * CHESCA-ResMARL 配置保存参数。
 */
@Data
public class ResMarlConfigParam {

    private Boolean resmarlEnabled;
    private String marlMode;
    private Integer multiAgentTrainEpochs;
    private Boolean multiAgentExplore;
    /** Multi-agent.py 的 RLlib checkpoint；非空则跳过现场训练 */
    private String multiAgentCheckpoint;
    private Double residualAlpha;
    private Object residualActionMask;
    private Boolean resmarlAfterSafety;
    /** Multi-agent.py 训练 schema */
    private String trainSchema;
    /** Multi-agent.py 评估 schema */
    private String multiAgentEvalSchema;
    /** CHESCA_ResMARL.py 仿真/KPI schema（resmarl_eval_schema） */
    private String evalSchema;
}
