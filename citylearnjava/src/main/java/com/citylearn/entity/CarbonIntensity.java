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
@TableName("carbon_intensity")
public class CarbonIntensity implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableField("id")
    private Integer id;

    /**
     * 二氧化碳排放率
     */
    @TableField("carbon_intensity")
    private BigDecimal carbonIntensity;
}
