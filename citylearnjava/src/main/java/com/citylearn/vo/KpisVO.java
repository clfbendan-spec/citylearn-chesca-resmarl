package com.citylearn.vo;

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
public class KpisVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;

    private String name;

    private String agentType;

    /**
     * 全时段峰值平均值
     */
    private BigDecimal allTimePeakAverage;

    /**
     * 年度标准化未满足能源总量
     */
    private BigDecimal annualNormalizedUnservedEnergyTotal;

    /**
     * 碳排放总量
     */
    private BigDecimal carbonEmissionsTotal;

    /**
     * 总成本
     */
    private BigDecimal costTotal;

    /**
     * 日平均(1-负荷率)
     */
    private BigDecimal dailyOneMinusLoadFactorAverage;

    /**
     * 日峰值平均值
     */
    private BigDecimal dailyPeakAverage;

    /**
     * 低温不适温差平均值
     */
    private BigDecimal discomfortColdDeltaAverage;

    /**
     * 低温不适温差最大值
     */
    private BigDecimal discomfortColdDeltaMaximum;

    /**
     * 低温不适温差最小值
     */
    private BigDecimal discomfortColdDeltaMinimum;

    /**
     * 低温不适比例
     */
    private BigDecimal discomfortColdProportion;

    /**
     * 高温不适温差平均值
     */
    private BigDecimal discomfortHotDeltaAverage;

    /**
     * 高温不适温差最大值
     */
    private BigDecimal discomfortHotDeltaMaximum;

    /**
     * 高温不适温差最小值
     */
    private BigDecimal discomfortHotDeltaMinimum;

    /**
     * 高温不适比例
     */
    private BigDecimal discomfortHotProportion;

    /**
     * 不适比例
     */
    private BigDecimal discomfortProportion;

    /**
     * 电量消耗总量
     */
    private BigDecimal electricityConsumptionTotal;

    /**
     * 月平均(1-负荷率)
     */
    private BigDecimal monthlyOneMinusLoadFactorAverage;

    /**
     * 热弹性不足比例
     */
    private BigDecimal oneMinusThermalResilienceProportion;

    /**
     * 停电未满足能源总量
     */
    private BigDecimal powerOutageNormalizedUnservedEnergyTotal;

    /**
     * 负荷爬坡率
     */
    private BigDecimal rampingAverage;

    /**
     * 零净能耗达标率
     */
    private BigDecimal zeroNetEnergy;
}
