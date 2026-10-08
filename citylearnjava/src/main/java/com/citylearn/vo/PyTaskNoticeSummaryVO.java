package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 任务通知汇总：供顶栏「运行中 / 未读」指示器与代码编辑器文件列表的未读红点使用。
 *
 * <p>「未读」= status != 0（已结束）且 if_notified = 0。执行中的任务不计入未读。
 */
@Getter
@Setter
@ToString
public class PyTaskNoticeSummaryVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 运行中（status=0）的任务。
     * 前端用它的长度显示「运行中 N」，并用 taskId 的变化检测「哪个任务刚刚结束」以弹提示。
     * 不含 output，字段很少，可以高频轮询。
     */
    private List<PyTaskVO> runningTasks = new ArrayList<>();

    /** 执行完但未被查看（未读）的记录总数 */
    private int unreadCount;

    /** 同上，按脚本 id 聚合，供文件列表在对应文件旁显示未读数 */
    private Map<String, Integer> unreadByPyId = new HashMap<>();
}
