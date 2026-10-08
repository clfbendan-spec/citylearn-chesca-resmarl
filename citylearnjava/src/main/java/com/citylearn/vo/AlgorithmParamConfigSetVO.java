package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.Date;
import java.util.List;

/**
 * 配置组（算法参数配置组）—— 供「配置组」页签的列表使用。
 */
@Getter
@Setter
@ToString
public class AlgorithmParamConfigSetVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键 */
    private Integer id;

    /** 创建时间 */
    private Date createTime;

    /** 组名称 */
    private String name;

    /** 简介 */
    private String desc;

    /** 组成员 id 列表（algorithm_param_config.id），按组内顺序 */
    private List<Integer> memberIds;

    /** 组成员个数，列表页直接展示，省得前端再算一遍 */
    private Integer memberCount;
}
