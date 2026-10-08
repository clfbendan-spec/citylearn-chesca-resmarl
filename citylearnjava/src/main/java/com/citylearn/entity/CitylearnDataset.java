package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.util.Date;

@Getter
@Setter
@ToString
@TableName("citylearn_dataset")
public class CitylearnDataset implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    @TableField("schema_key")
    private String schemaKey;

    @TableField("display_name")
    private String displayName;

    @TableField("relative_path")
    private String relativePath;

    @TableField("building_count")
    private Integer buildingCount;

    @TableField("time_steps")
    private Integer timeSteps;

    @TableField("chesca_compatible")
    private Integer chescaCompatible;

    @TableField("enabled")
    private Integer enabled;

    @TableField("sort_order")
    private Integer sortOrder;

    @TableField("description")
    private String description;

    @TableField("create_time")
    private Date createTime;

    @TableField("update_time")
    private Date updateTime;
}
