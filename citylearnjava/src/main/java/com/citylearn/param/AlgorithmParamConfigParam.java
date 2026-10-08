package com.citylearn.param;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * 「参数配置」页新增 / 编辑 algorithm_param_config 的入参。
 *
 * <p>编辑系统自带参数（if_system=1）时，服务端只取 {@link #desc} 生效，
 * 其余字段一律忽略。
 */
@Getter
@Setter
@ToString
public class AlgorithmParamConfigParam implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键；新增时为空 */
    private Integer id;

    /** 名称（如「训练数据集」） */
    private String name;

    /** 默认参数名（如 train-schema） */
    private String paramName;

    /**
     * 值类型：num=数字；text=文字；ratio=单选；multiple=多选；special=数据集（历史值）。
     * 空值按 text 处理。
     */
    private String valueType;

    /**
     * 单选 / 多选的可选项，以及 map 的键值对，JSON 数组字符串：
     * [{"key":"1","value":"方案一"}]。
     * 值类型不是 ratio / multiple / map 时忽略（落库为 NULL）。
     */
    private String defaultValue;

    /**
     * 值类型为 map 时「键」的别名（如「选择时段」）。
     * 值类型不是 map 时忽略（落库为 NULL）。
     */
    private String keyAlias;

    /** 值类型为 map 时「值」的别名（如「电池 SOC 下限」）。非 map 类型忽略。 */
    private String valueAlias;

    /** 参数简介 */
    private String desc;

    /**
     * 可选的「配置组 id」：在配置组详情页里新建参数时带上它，
     * 新增完成后直接把该参数加进这个组（members 追加 + is_member 置 1）。
     * 在「单独配置」页新建时留空即可。
     */
    private Integer setId;
}
