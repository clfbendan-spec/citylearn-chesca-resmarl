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
@TableName("pricing")
public class Pricing implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableField("id")
    private Integer id;

    /**
     * 单位电价[$/kWh]
     */
    @TableField("electricity_pricing")
    private BigDecimal electricityPricing;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 1 或 6 小时
     */
    @TableField("electricity_pricing_predicted_1")
    private BigDecimal electricityPricingPredicted1;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 2 或 12 小时
     */
    @TableField("electricity_pricing_predicted_2")
    private BigDecimal electricityPricingPredicted2;

    /**
     * n 小时电价预测
     * 在现有数据集中通常为 3 或 24 小时
     */
    @TableField("electricity_pricing_predicted_3")
    private BigDecimal electricityPricingPredicted3;
}
