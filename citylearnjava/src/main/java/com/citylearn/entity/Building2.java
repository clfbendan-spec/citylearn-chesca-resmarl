package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;

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
@TableName("building_2")
public class Building2 extends Building implements Serializable {

    private static final long serialVersionUID = 1L;

}
