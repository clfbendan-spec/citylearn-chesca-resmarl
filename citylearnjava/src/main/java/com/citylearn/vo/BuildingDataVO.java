package com.citylearn.vo;

import com.baomidou.mybatisplus.annotation.TableField;
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
 * @since 2025-06-08
 */
@Getter
@Setter
@ToString
public class BuildingDataVO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    private Integer id;

    /**
     *  建筑id
     */
    private String buildingId;

    /**
     *  月份
     */
    private Integer month;

    /**
     *  一天中的小时数
     */
    private Integer hour;

    /**
     *  日期
     */
    private Integer dayType;

    /**
     * 是否处于夏令时(1处于)
     */
    private Integer daylightSavingsStatus;

    /**
     *室内干球温度
     */
    private BigDecimal indoorDryBulbTemperature;

    /**
     * 平均未满足冷却设定点温差
     */
    private BigDecimal averageUnmetCoolingSetpointDifference;

    /**
     * 室内相对湿度
     */
    private BigDecimal indoorRelativeHumidity;

    /**
     * 电器当前消耗电量（单位：千瓦时）
     */
    private BigDecimal nonShiftableLoad;

    /**
     * 供应建筑生活热水（DHW）的供热需求
     * 供热需求
     */
    private BigDecimal dhwDemand;

    /**
     * 用于建筑降温除湿的制冷能源需求
     * 制冷需求
     */
    private BigDecimal coolingDemand;

    /**
     * 供暖需求
     */
    private BigDecimal heatingDemand;

    /**
     * 光伏发电量（单位：千瓦时）
     */
    private BigDecimal solarGeneration;

    /**
     * 建筑内人员数量
     */
    private Integer occupantCount;

    /**
     * 室内干球温度制冷设定点
     */
    private BigDecimal indoorDryBulbTemperatureCoolingSetPoint;

    /**
     * 室内干球温度制热设定点
     */
    private BigDecimal indoorDryBulbTemperatureHeatingSetPoint;

    /**
     * 指定在每个时间步考虑制冷还是制热需求
     */
    private Integer hvacMode;

    /**
     * 二氧化碳排放率
     */
    private BigDecimal carbonIntensity;

    /**
     * 单位电价[$/kWh]
     */
    private BigDecimal electricityPricing;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 1 或 6 小时
     */
    private BigDecimal electricityPricingPredicted1;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 2 或 12 小时
     */
    private BigDecimal electricityPricingPredicted2;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 3 或 24 小时
     */
    private BigDecimal electricityPricingPredicted3;

    /**
     * 室外干球温度
     */
    private BigDecimal outdoorDryBulbTemperature;

    /**
     * 室外相对湿度
     */
    private BigDecimal outdoorRelativeHumidity;

    /**
     * 散射太阳辐照度
     */
    private BigDecimal diffuseSolarIrradiance;

    /**
     * 直接太阳辐照度
     */
    private BigDecimal directSolarIrradiance;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    private BigDecimal outdoorDryBulbTemperaturePredicted1;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    private BigDecimal outdoorDryBulbTemperaturePredicted2;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    private BigDecimal outdoorDryBulbTemperaturePredicted3;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    private BigDecimal outdoorRelativeHumidityPredicted1;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    private BigDecimal outdoorRelativeHumidityPredicted2;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    private BigDecimal outdoorRelativeHumidityPredicted3;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    private BigDecimal diffuseSolarIrradiancePredicted1;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    private BigDecimal diffuseSolarIrradiancePredicted2;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    private BigDecimal diffuseSolarIrradiancePredicted3;

    /**
     * 未来 n 小时直射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    private BigDecimal directSolarIrradiancePredicted1;

    /**
     * 未来 n 小时直射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    private BigDecimal directSolarIrradiancePredicted2;

    /**
     * 未来 n 小时直射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    private BigDecimal directSolarIrradiancePredicted3;
}
