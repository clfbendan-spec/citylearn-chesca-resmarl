package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * <p>
 * 
 * </p>
 *
 * @author Your Name
 * @since 2025-06-14
 */
@Getter
@Setter
@ToString
@TableName("kpis")
public class Kpis implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("name")
    private String name;

    @TableField("agent_type")
    private String agentType;

    /**
     * 全时段峰值平均值
     */
    @TableField("all_time_peak_average")
    private BigDecimal allTimePeakAverage;

    /**
     * 年度标准化未满足能源总量
     */
    @TableField("annual_normalized_unserved_energy_total")
    private BigDecimal annualNormalizedUnservedEnergyTotal;

    /**
     * 碳排放总量
     */
    @TableField("carbon_emissions_total")
    private BigDecimal carbonEmissionsTotal;

    /**
     * 总成本
     */
    @TableField("cost_total")
    private BigDecimal costTotal;

    /**
     * 日平均(1-负荷率)
     */
    @TableField("daily_one_minus_load_factor_average")
    private BigDecimal dailyOneMinusLoadFactorAverage;

    /**
     * 日峰值平均值
     */
    @TableField("daily_peak_average")
    private BigDecimal dailyPeakAverage;

    /**
     * 低温不适温差平均值
     */
    @TableField("discomfort_cold_delta_average")
    private BigDecimal discomfortColdDeltaAverage;

    /**
     * 低温不适温差最大值
     */
    @TableField("discomfort_cold_delta_maximum")
    private BigDecimal discomfortColdDeltaMaximum;

    /**
     * 低温不适温差最小值
     */
    @TableField("discomfort_cold_delta_minimum")
    private BigDecimal discomfortColdDeltaMinimum;

    /**
     * 低温不适比例
     */
    @TableField("discomfort_cold_proportion")
    private BigDecimal discomfortColdProportion;

    /**
     * 高温不适温差平均值
     */
    @TableField("discomfort_hot_delta_average")
    private BigDecimal discomfortHotDeltaAverage;

    /**
     * 高温不适温差最大值
     */
    @TableField("discomfort_hot_delta_maximum")
    private BigDecimal discomfortHotDeltaMaximum;

    /**
     * 高温不适温差最小值
     */
    @TableField("discomfort_hot_delta_minimum")
    private BigDecimal discomfortHotDeltaMinimum;

    /**
     * 高温不适比例
     */
    @TableField("discomfort_hot_proportion")
    private BigDecimal discomfortHotProportion;

    /**
     * 不适比例
     */
    @TableField("discomfort_proportion")
    private BigDecimal discomfortProportion;

    /**
     * 电量消耗总量
     */
    @TableField("electricity_consumption_total")
    private BigDecimal electricityConsumptionTotal;

    /**
     * 月平均(1-负荷率)
     */
    @TableField("monthly_one_minus_load_factor_average")
    private BigDecimal monthlyOneMinusLoadFactorAverage;

    /**
     * 热弹性不足比例
     */
    @TableField("one_minus_thermal_resilience_proportion")
    private BigDecimal oneMinusThermalResilienceProportion;

    /**
     * 停电未满足能源总量
     */
    @TableField("power_outage_normalized_unserved_energy_total")
    private BigDecimal powerOutageNormalizedUnservedEnergyTotal;

    /**
     * 负荷爬坡率
     */
    @TableField("ramping_average")
    private BigDecimal rampingAverage;

    /**
     * 零净能耗达标率
     */
    @TableField("zero_net_energy")
    private BigDecimal zeroNetEnergy;
}
