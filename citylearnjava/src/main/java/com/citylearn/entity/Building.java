package com.citylearn.entity;

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
@TableName("building_1")
public class Building implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableField("id")
    private Integer id;

    /**
     *  月份
     */
    @TableField("month")
    private Integer month;

    /**
     *  一天中的小时数
     */
    @TableField("hour")
    private Integer hour;

    /**
     *  日期
     */
    @TableField("day_type")
    private Integer dayType;

    /**
     * 是否处于夏令时
     * 0表示建筑未因夏令时调整用电模式，1表示建筑可能受夏令时影响的时段。
     * 夏令时对
     */
        @TableField("daylight_savings_status")
    private Integer daylightSavingsStatus;

    /**
     *室内干球温度
     */
    @TableField("indoor_dry_bulb_temperature")
    private BigDecimal indoorDryBulbTemperature;

    /**
     * 平均未满足冷却设定点温差
     */
    @TableField("average_unmet_cooling_setpoint_difference")
    private BigDecimal averageUnmetCoolingSetpointDifference;

    /**
     * 室内相对湿度
     */
    @TableField("indoor_relative_humidity")
    private BigDecimal indoorRelativeHumidity;

    /**
     * 电器当前消耗电量（单位：千瓦时）
     */
    @TableField("non_shiftable_load")
    private BigDecimal nonShiftableLoad;

    /**
     * 供应建筑生活热水（DHW）的供热需求
     * 供热需求
     */
    @TableField("dhw_demand")
    private BigDecimal dhwDemand;

    /**
     * 用于建筑降温除湿的制冷能源需求
     * 制冷需求
     */
    @TableField("cooling_demand")
    private BigDecimal coolingDemand;

    /**
     * 供暖需求
     */
    @TableField("heating_demand")
    private BigDecimal heatingDemand;

    /**
     * 光伏发电量（单位：千瓦时）
     */
    @TableField("solar_generation")
    private BigDecimal solarGeneration;

    /**
     * 建筑内人员数量
     */
    @TableField("occupant_count")
    private Integer occupantCount;

    /**
     * 室内干球温度制冷设定点
     */
    @TableField("indoor_dry_bulb_temperature_cooling_set_point")
    private BigDecimal indoorDryBulbTemperatureCoolingSetPoint;

    /**
     * 室内干球温度制热设定点
     */
    @TableField("indoor_dry_bulb_temperature_heating_set_point")
    private BigDecimal indoorDryBulbTemperatureHeatingSetPoint;

    /**
     * 指定在每个时间步考虑制冷还是制热需求
     */
    @TableField("hvac_mode")
    private Integer hvacMode;
}
