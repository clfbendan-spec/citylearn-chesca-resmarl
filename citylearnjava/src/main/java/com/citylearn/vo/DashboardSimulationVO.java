package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.util.Date;

/**
 * 仿真仪表盘可选分组（执行完成且 ifShow=1 的代码记录）
 */
@Getter
@Setter
@ToString
public class DashboardSimulationVO implements Serializable {

    private static final long serialVersionUID = 1L;

    /** 分组名称（代码名 + 记录时间） */
    private String groupName;

    private String pyId;

    private String taskId;

    private String fileName;

    private Date taskCreateTime;
}
