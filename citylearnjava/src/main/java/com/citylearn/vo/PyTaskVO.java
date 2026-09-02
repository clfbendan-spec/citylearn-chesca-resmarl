package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.Date;
import java.util.List;

/**
 * Python 异步任务状态与结果
 */
@Getter
@Setter
@ToString
public class PyTaskVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 任务 ID */
    private String taskId;

    /** 关联的 Python 文件 ID */
    private String pyId;

    /** 0-执行中 1-成功 2-失败 */
    private Integer status;

    /** 状态描述 */
    private String statusDesc;

    /** 是否在仿真仪表盘展示（默认 false / 未展示） */
    private Boolean ifShow;

    /** 仪表盘展示名称（可选） */
    private String showName;

    /** 脚本标准输出（执行完成后从 output.log 读取） */
    private String output;

    /** 失败时的错误信息 */
    private String errorMessage;

    /** 执行成功后的 KPI（仅 status=1 时填充） */
    private List<KpisTransVO> kpis;

    private Date createTime;

    private Date updateTime;

    public static String statusDescOf(Integer status) {
        if (status == null) {
            return "未知";
        }
        if (status == 0) {
            return "执行中";
        }
        if (status == 1) {
            return "执行完成";
        }
        if (status == 2) {
            return "执行失败";
        }
        return "未知";
    }
}
