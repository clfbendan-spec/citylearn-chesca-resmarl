package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * 配置组详情 —— 供「点详情进入组内参数页」使用。
 *
 * <p>比列表 VO 多一个 {@link #members}：组内参数定义的完整信息（按组内顺序），
 * 前端拿到即可直接渲染表格，不必再按 id 逐条查。
 */
@Getter
@Setter
@ToString
public class AlgorithmParamConfigSetDetailVO implements Serializable {

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

    /** 组内参数定义（按组内顺序；已被删除的 id 会被跳过） */
    private List<AlgorithmParamConfigVO> members = new ArrayList<>();
}
