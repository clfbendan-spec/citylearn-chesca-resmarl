package com.citylearn.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.Date;

/**
 * 算法参数定义（可选参数目录）。
 *
 * <p>代码编辑器里选中 train / eval 脚本后点「配置」，可从这里挑参数挂到脚本上。
 * 目前预置三条系统数据：训练数据集(train-schema)、评估数据集(eval-schema)、
 * 训练轮数(train-epochs)。
 *
 * <p>注意与 {@link AlgorithmConfig} 区分：后者是 CHESCA / ResMARL 的算法参数
 * <b>取值</b>库（键值表 algorithm_config，config_key 主键）；本类对应的是
 * <b>参数定义目录</b>（algorithm_param_config，id 主键）。两张表用途与结构都不同。
 */
@Getter
@Setter
@ToString
@TableName("algorithm_param_config")
public class AlgorithmParamConfig implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 主键 */
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    /** 创建时间 */
    @TableField("create_time")
    private Date createTime;

    /** 名称（界面显示，如「训练数据集」） */
    @TableField("name")
    private String name;

    /** 参数名（如 train-schema） */
    @TableField("param_name")
    private String paramName;

    /** 是否系统自带：true=系统预置，false=用户新增 */
    @TableField("if_system")
    private Boolean ifSystem;

    /**
     * 是否为配置组成员：true=出现在某个配置组的 members 里，false=独立参数。
     *
     * <p>这是 members 的冗余标记列 —— 只为让「单独配置」页一句 SQL 过滤出独立参数，
     * 不必反查所有组的 members。由 Service 在写配置组时同步维护。
     */
    @TableField("is_member")
    private Boolean isMember;

    /**
     * 值类型，决定界面「值」这一列渲染成什么控件。
     *
     * <ul>
     *   <li>{@code num} —— 只允许输入数字的输入框（当前：训练轮数 train-epochs）</li>
     *   <li>{@code text} —— 普通文本输入框（等价于历史上的 null/空）</li>
     *   <li>{@code bool} —— 开关（当前：电价感知电池那 5 个开关类参数），
     *       存进配置的是 JSON 布尔值 true / false</li>
     *   <li>{@code ratio} —— 单选下拉，候选项取自 {@link #defaultValue}</li>
     *   <li>{@code multiple} —— 多选下拉，候选项取自 {@link #defaultValue}</li>
     *   <li>{@code map} —— 键值对（一组 key/value），同样存在 {@link #defaultValue}；
     *       键与值的显示名由 {@link #keyAlias} / {@link #valueAlias} 描述
     *       （当前：小时下限 min_soc_per_hour，键=选择时段、值=电池 SOC 下限）</li>
     *   <li>{@code special} —— 特殊值，不是自由文本（当前：两个数据集参数，
     *       渲染成数据集下拉，值存 citylearn_dataset.id；历史值，仅在参数配置页保留可选项）</li>
     *   <li>null / 空 —— 普通文本输入框</li>
     * </ul>
     */
    @TableField("value_type")
    private String valueType;

    /**
     * 单选(ratio) / 多选(multiple) 的候选项，以及 map 的键值对，均为 JSON 数组：
     * <pre>[{"key":"1","value":"方案一"},{"key":"2","value":"方案二"}]</pre>
     * key = 存进 py_file.algorithm_config 的真实取值；value = 界面显示文字。
     * 其它值类型（num / text / bool / special）时为 null。
     */
    @TableField("default_value")
    private String defaultValue;

    /**
     * 值类型为 map 时「键」的别名（如「选择时段」），让界面不必显示生硬的 key。
     * 其它类型为 null。
     */
    @TableField("key_alias")
    private String keyAlias;

    /** 值类型为 map 时「值」的别名（如「电池 SOC 下限」）。其它类型为 null。 */
    @TableField("value_alias")
    private String valueAlias;

    /**
     * 参数简介：界面在名称右侧显示一个小叹号，悬浮时显示这段文字。
     *
     * <p>⚠️ 列名 desc 是 MySQL 保留字，注解里必须带反引号 —— 否则
     * MyBatis-Plus 拼出的 SELECT 会变成 {@code ... ,desc FROM ...}，直接语法错误。
     */
    @TableField("`desc`")
    private String desc;
}
