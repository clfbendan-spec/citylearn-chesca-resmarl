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
@TableName("weather")
public class Weather implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableField("id")
    private Integer id;

    /**
     * 室外干球温度
     */
    @TableField("outdoor_dry_bulb_temperature")
    private BigDecimal outdoorDryBulbTemperature;

    /**
     * 室外相对湿度
     */
    @TableField("outdoor_relative_humidity")
    private BigDecimal outdoorRelativeHumidity;

    /**
     * 散射太阳辐照度
     */
    @TableField("diffuse_solar_irradiance")
    private BigDecimal diffuseSolarIrradiance;

    /**
     * 直接太阳辐照度
     */
    @TableField("direct_solar_irradiance")
    private BigDecimal directSolarIrradiance;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    @TableField("outdoor_dry_bulb_temperature_predicted_1")
    private BigDecimal outdoorDryBulbTemperaturePredicted1;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    @TableField("outdoor_dry_bulb_temperature_predicted_2")
    private BigDecimal outdoorDryBulbTemperaturePredicted2;

    /**
     * 室外干球温度 n 小时提前预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    @TableField("outdoor_dry_bulb_temperature_predicted_3")
    private BigDecimal outdoorDryBulbTemperaturePredicted3;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    @TableField("outdoor_relative_humidity_predicted_1")
    private BigDecimal outdoorRelativeHumidityPredicted1;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    @TableField("outdoor_relative_humidity_predicted_2")
    private BigDecimal outdoorRelativeHumidityPredicted2;

    /**
     * 未来 n 小时室外相对湿度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    @TableField("outdoor_relative_humidity_predicted_3")
    private BigDecimal outdoorRelativeHumidityPredicted3;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    @TableField("diffuse_solar_irradiance_predicted_1")
    private BigDecimal diffuseSolarIrradiancePredicted1;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    @TableField("diffuse_solar_irradiance_predicted_2")
    private BigDecimal diffuseSolarIrradiancePredicted2;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    @TableField("diffuse_solar_irradiance_predicted_3")
    private BigDecimal diffuseSolarIrradiancePredicted3;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 6 小时
     */
    @TableField("direct_solar_irradiance_predicted_1")
    private BigDecimal directSolarIrradiancePredicted1;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 12 小时
     */
    @TableField("direct_solar_irradiance_predicted_2")
    private BigDecimal directSolarIrradiancePredicted2;

    /**
     * 未来 n 小时漫射太阳辐照度预测
     * n 可为任意小时数，现有数据集通常为 24 小时
     */
    @TableField("direct_solar_irradiance_predicted_3")
    private BigDecimal directSolarIrradiancePredicted3;
}
