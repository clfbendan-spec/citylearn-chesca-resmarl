package com.citylearn.vo;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;

@Getter
@Setter
public class ChescaBatteryConfigVO implements Serializable {

    /** key 为小时字符串 "0"-"23"，value 为 SOC 下限（0~1） */
    private Map<String, Double> minSocPerHour = new LinkedHashMap<>();

    /** 正常时段电池 SOC 上限（0~1） */
    private Double maxSocNormal;

    /** 停电时段电池 SOC 上限（0~1） */
    private Double maxSocOutage;

    /** 停电时单次允许的最大 SOC 降幅（0~1） */
    private Double maxSocReductionInOutage;

    /** 负荷低于均值 − B_low×标准差 时触发增负荷 */
    @JsonProperty("bLow")
    private Double bLow;

    /** 负荷高于均值 + B_high×标准差 时触发减负荷 */
    @JsonProperty("bHigh")
    private Double bHigh;

    /** 负荷过高时冷机动作最大削减比例（0~1） */
    private Double tmpMaxReductionPercent;

    /** 预测/优化向前看的步数（1~3） */
    private Integer tau;

    /** 电池树搜索适应度函数类型（A/B/C） */
    private String balanceType;
}
