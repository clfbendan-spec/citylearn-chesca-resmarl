package com.citylearn.param;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * Python 执行任务参数
 */
@Getter
@Setter
@ToString
public class PyTaskParam implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 任务 ID */
    private String taskId;

    /** 是否在仿真仪表盘展示 */
    private Boolean ifShow;

    /** 仪表盘展示名称（可空；留空则用「代码名+时间」） */
    private String showName;
}
