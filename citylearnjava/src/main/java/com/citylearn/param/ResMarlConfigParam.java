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
    private Double residualAlpha;
    private Object residualActionMask;
    private Boolean resmarlAfterSafety;
    private Boolean schemaSplitEnabled;
    private String trainSchema;
    private String evalSchema;
}
