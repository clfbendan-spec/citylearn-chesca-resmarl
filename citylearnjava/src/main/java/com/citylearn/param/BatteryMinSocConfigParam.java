package com.citylearn.param;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;

@Getter
@Setter
public class BatteryMinSocConfigParam implements Serializable {

    /** key 为 hour 字符串 "0"-"23"，value 为 SOC 下限（0~1） */
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

    /** 过热时最小制冷系数（相对额定功率 / °C） */
    private Double minCoolPerCOverheat;

    /** 室外开环保底系数（相对额定功率 / °C）；0=关闭 */
    private Double minCoolPerCOutdoorGap;

    /** 室外相对设定的死区 (°C)，超过才启用室外保底 */
    private Double outdoorGapDeadbandC;

    /** 仅当过热低于该值 (°C) 时启用室外保底 */
    private Double outdoorFloorMaxOverheatC;

    /** 冷负荷前馈比例（0~1）；0=关闭 */
    private Double coolingDemandFeedforwardFrac;

    /** 冷负荷前馈是否仅在过热时启用 */
    private Boolean demandFeedforwardOnlyWhenOverheat;

    /** 室外保底是否允许在室温低于设定时启用 */
    private Boolean outdoorFloorAllowWhenUnderSetpoint;

    /** 室温低于设定时是否清掉一切开环保底（旧行为） */
    private Boolean clearOpenLoopFloorWhenUnderSetpoint;

    /** PID 是否使用上一拍已落地的动力学室温 indoor[-2] */
    private Boolean useLaggedDynamicsIndoor;

    /** 仅当 [-2] 明显更热时才用滞后室温 */
    private Boolean laggedIndoorOnlyWhenHotter;

    /** 滞后室温「更热」判定裕度 (°C) */
    private Double laggedIndoorHotterMarginC;

    /** 是否启用复电缓充（抑制强充尖峰） */
    private Boolean postOutageSoftChargeEnabled;

    /** 复电后缓充窗口步数 */
    private Integer postOutageRelaxSteps;

    /** 复电窗口内是否豁免小时 min_soc 硬充约束 */
    private Boolean postOutageWaiveMinSoc;

    /** 复电窗口内 ELE 充电上限（SOC 比例，0~1） */
    private Double postOutageMaxEleCharge;

    /** 复电窗口内过热时是否禁止充电 */
    private Boolean postOutageForbidChargeWhenOverheat;

    /** 过热禁止充电阈值 (°C) */
    private Double postOutageOverheatC;

    /** 是否启用复电 TMP 帽/斜坡 */
    private Boolean postOutageTmpCapEnabled;

    /** 复电 TMP 帽窗口步数 */
    private Integer postOutageTmpCapSteps;

    /** 复电首步 TMP 上限（0~1） */
    private Double postOutageTmpMaxStart;

    /** 是否从起始帽线性爬升到 1.0 */
    private Boolean postOutageTmpRamp;

    /** 是否分栋错峰制冷 */
    private Boolean postOutageTmpStagger;

    /** 是否启用电价感知电池策略 */
    private Boolean priceAwareBatteryEnabled;

    /** 高价分位数阈值（如 0.75） */
    private Double priceHighQuantile;

    /** 低价分位数阈值（如 0.25） */
    private Double priceLowQuantile;

    /** 电价历史最少样本步数 */
    private Integer priceHistoryMinSteps;

    /** 高价强制放电的 SOC 阈值（0~1） */
    private Double priceHighSocThreshold;

    /** 高价时段是否禁止充电 */
    private Boolean priceHighForbidCharge;

    /** 高价且 SOC 达阈值时是否强制放电 */
    private Boolean priceHighForceDischarge;

    /** 高价强制放电 ELE 幅度（0~1） */
    private Double priceHighDischargeEle;

    /** 高价放电韧性地板 SOC（0~1），强放不得低于此值 */
    private Double priceMinReserveSoc;

    /** 是否全局启用韧性地板（非停电放电均不可击穿） */
    private Boolean priceGlobalReserveEnabled;

    /** 低价补电目标 SOC（0~1） */
    private Double priceLowTargetSoc;

    /** 低价补电 ELE 幅度（0~1） */
    private Double priceLowChargeEle;

    /** 低价时是否抬高树搜索 SOC 下限以促使补电 */
    private Boolean priceLowSearchBoost;

    /** 预测/优化向前看的步数（1~3） */
    private Integer tau;

    /** 电池树搜索适应度函数类型（A/B/C） */
    private String balanceType;

    /** CHESCA 仿真/KPI 评估数据集 schema */
    private String evalSchema;
}
