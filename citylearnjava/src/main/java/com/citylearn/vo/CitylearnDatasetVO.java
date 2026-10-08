package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;

/**
 * 本地 CityLearn 数据集选项（原始数据 / ResMARL 配置共用）。
 */
@Getter
@Setter
@ToString
public class CitylearnDatasetVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private Integer id;
    /** 选择值 = schema 目录名 */
    private String schemaKey;
    private String displayName;
    /** 相对 python-file-path */
    private String relativePath;
    private Integer buildingCount;
    private Integer timeSteps;
    private Boolean chescaCompatible;
    private String description;
}
