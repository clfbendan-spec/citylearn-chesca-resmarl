package com.citylearn.vo;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
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
public class CommunityBuildingVO implements Serializable {

    private static final long serialVersionUID = 1L;

    /**
     *  id
     */
    private String id;

    /**
     *  建筑名称
     */
    private String name;

    /**
     *  建筑信息
     */
    private String description;

    /**
     *  图片地址
     */
    private String imageUrl;

    /**
     *  创建时间
     */
    private Date createTime;

    /**
     *  更新时间
     */
    private Date updateTime;


}
