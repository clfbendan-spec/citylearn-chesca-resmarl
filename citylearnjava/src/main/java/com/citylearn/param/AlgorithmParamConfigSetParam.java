package com.citylearn.param;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.List;

/**
 * 「配置组」新增 / 编辑的入参。
 */
@Getter
@Setter
@ToString
public class AlgorithmParamConfigSetParam implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键；新增时为空 */
    private Integer id;

    /** 组名称 */
    private String name;

    /** 简介 */
    private String desc;

    /**
     * 组成员：algorithm_param_config.id 列表。
     * 后端会据此重写 members 字段，并同步这些参数的 is_member 标记
     * （被移出组的参数会重新算一遍，仍属于其它组则保持 1）。
     */
    private List<Integer> memberIds;
}
