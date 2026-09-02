package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

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
@TableName("community_building")
public class CommunityBuilding implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    @TableId("id")
    private String id;

    /**
     *  建筑名称
     */
    @TableField("name")
    private String name;

    /**
     *  建筑信息
     */
    @TableField("description")
    private String description;

    /**
     *  图片地址
     */
    @TableField("image_url")
    private String imageUrl;

    /**
     *  删除标记
     */
    @TableField("if_delete")
    private Boolean ifDelete;

    /**
     *  创建时间
     */
    @TableField("create_time")
    private Date createTime;

    /**
     *  更新时间
     */
    @TableField("update_time")
    private Date updateTime;


}
