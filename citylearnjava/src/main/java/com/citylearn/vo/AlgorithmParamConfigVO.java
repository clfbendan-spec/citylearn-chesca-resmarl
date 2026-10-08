package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.Date;

/**
 * 算法参数定义（「参数配置」页表格 + 代码编辑器「配置」弹窗的下拉框数据源）。
 */
@Getter
@Setter
@ToString
public class AlgorithmParamConfigVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键：保存到 py_file.algorithm_config 里的 id */
    private Integer id;

    /** 名称（如「训练数据集」） */
    private String name;

    /** 默认参数名（如 train-schema）；界面第二列左边显示的原始参数名 */
    private String paramName;

    /** 是否系统自带（参数配置页打「系统」标识并禁止删除；系统参数仅可改简介） */
    private Boolean ifSystem;

    /**
     * 值类型：num=数字；text=文字；bool=布尔开关；ratio=单选；multiple=多选；
     * map=键值对（后三者的内容见 defaultValue，map 另有 keyAlias/valueAlias）；
     * special=特殊控件（数据集下拉）；null/空=普通文本输入框。
     * 前端据此决定「值」这一列渲染哪个控件。
     */
    private String valueType;

    /**
     * 单选(ratio) / 多选(multiple) 的候选项，以及 map 的键值对，均为 JSON 数组字符串：
     * [{"key":"1","value":"方案一"}]。其它值类型为 null。
     */
    private String defaultValue;

    /** 值类型为 map 时「键」的别名（如「选择时段」）；其它类型为 null */
    private String keyAlias;

    /** 值类型为 map 时「值」的别名（如「电池 SOC 下限」）；其它类型为 null */
    private String valueAlias;

    /** 参数简介（界面名称右侧小叹号悬浮显示 / 参数配置页的「简介」列） */
    private String desc;

    /** 创建时间（参数配置页的「创建时间」列） */
    private Date createTime;

    /**
     * 是否为配置组成员。
     * 「单独配置」页签只展示 false 的；组详情页展示该组的成员。
     */
    private Boolean isMember;
}
