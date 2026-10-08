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

    /**
     * 关联的 Python 文件名（如 Multi-agent-train.py）。
     * 仅「任务记录」列表接口（getAllPyTaskList）填充，单文件的任务列表不需要。
     */
    private String scriptName;

    /**
     * 任务类型：0=训练+评估编排任务（任务管理页「新建任务」创建）；
     * 1=代码编辑器直接执行的简易任务（含全部历史数据，也包含编排任务拆出的子任务）。
     * 前端据此区分列表展示：0 显示「训练+评估」标签。
     */
    private Integer type;

    /**
     * 是否为编排任务拆出的子任务（py_task.is_subtask）。
     *
     * <p>任务管理页主列表不展示子任务（只在父任务详情展开的子表格里显示）；
     * 代码编辑器「记录」列表会把它们列出来，并打上「子任务」标识。
     */
    private Boolean isSubtask;

    /**
     * 任务名称，仅 type=0（编排任务）有值。
     *
     * <p>任务管理页「任务名称」列的取值规则：
     * <ul>
     *   <li>type=0 → 本字段（py_task.task_name）</li>
     *   <li>type=1 → scriptName（py_file.file_name 代码名称）</li>
     * </ul>
     */
    private String taskName;

    /** 0-执行中 1-成功 2-失败 3-运行终止（用户手动终止）4-已中断（后端服务重启）5-待执行（编排任务创建后尚未执行） */
    private Integer status;

    /** 状态描述 */
    private String statusDesc;

    /** 是否在仿真仪表盘展示（默认 false / 未展示） */
    private Boolean ifShow;

    /** 仪表盘展示名称（可选） */
    private String showName;

    /**
     * 是否已提醒/已读：false 未读（执行完成后尚未被查看）。
     * 仅 status != 0 时代表「未读」；前端据此给记录打未读标记、并累计文件/顶栏的未读数。
     */
    private Boolean ifNotified;

    /** 脚本标准输出（执行完成后从 output.log 读取） */
    private String output;

    /** 失败时的错误信息 */
    private String errorMessage;

    /** 执行成功后的 KPI（仅 status=1 时填充） */
    private List<KpisTransVO> kpis;

    private Date createTime;

    private Date updateTime;

    /**
     * 编排任务（type=0）在评估卡里选的「复用历史训练任务」id：非空表示**本次不训练**，
     * 只跑评估子任务、用该历史任务训练出的模型；为空/null 表示按老逻辑先训练再评估。
     *
     * <p>仅 {@code getAllPyTaskList} 填充（任务管理页要用它写执行确认文案与列表标签）。
     */
    private String reuseTrainTaskId;

    /** 任务类型：训练+评估编排任务（任务管理页「新建任务」创建） */
    public static final int TASK_TYPE_PIPELINE = 0;

    /** 任务类型：代码编辑器直接执行的简易任务（含全部历史数据） */
    public static final int TASK_TYPE_SIMPLE = 1;

    /**
     * 待执行：编排任务（type=0）创建后的初始状态。
     * 刻意不复用 0（执行中）——否则会一直显示「执行中」、被顶栏计入运行中任务，
     * 还会在后端重启对账（reconcileInterruptedTasks 只查 status=0）时被误判成「已中断」。
     */
    public static final int TASK_STATUS_PENDING = 5;

    /**
     * 等待中：编排任务的子任务专用状态。
     *
     * <p>「执行」编排任务时，训练子任务立刻变 0-执行中，评估子任务先置本状态；
     * 训练子任务跑完后由后台心跳把它改成 0-执行中并真正拉起评估脚本。
     * 与 5-待执行 的区别：5 是「人工还没点执行」，6 是「已排上队、等前置子任务」。
     */
    public static final int TASK_STATUS_WAITING = 6;

    /** 子任务 id 后缀：训练子任务 */
    public static final String SUB_TASK_SUFFIX_TRAIN = "-train";

    /** 子任务 id 后缀：评估子任务 */
    public static final String SUB_TASK_SUFFIX_EVAL = "-eval";

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
        if (status == 3) {
            return "运行终止";
        }
        if (status == 4) {
            return "已中断";
        }
        if (status == TASK_STATUS_PENDING) {
            return "待执行";
        }
        if (status == TASK_STATUS_WAITING) {
            return "等待中";
        }
        return "未知";
    }

    /**
     * 是否为「已结束」状态（执行完成 1 / 执行失败 2 / 运行终止 3 / 已中断 4）。
     * 0-执行中、5-待执行、6-等待中 都不算已结束：前两个还没开始/正在跑，最后一个在排队。
     * 只有已结束的任务才有结果可查看，才能参与「未读 / 待查看」统计。
     */
    public static boolean isFinished(Integer status) {
        return status != null && status != 0
                && status != TASK_STATUS_PENDING && status != TASK_STATUS_WAITING;
    }

    /** 生成子任务 id：父任务 id + 后缀（-train / -eval）。 */
    public static String subTaskIdOf(String parentTaskId, String suffix) {
        return parentTaskId == null ? null : parentTaskId + suffix;
    }

    /**
     * 从任务 id 反推父任务 id：以 -train / -eval 结尾的子任务返回其前缀，其它任务返回 null。
     *
     * <p>父子关系刻意只用 id 约定表达（不加 parent_id 列）：编排任务的子任务永远由
     * 本服务按 {@link #subTaskIdOf} 生成，后缀固定且父 id 是 uuid，不会与普通任务 id 冲突。
     */
    public static String parentTaskIdOf(String taskId) {
        if (taskId == null) {
            return null;
        }
        if (taskId.endsWith(SUB_TASK_SUFFIX_TRAIN)) {
            return taskId.substring(0, taskId.length() - SUB_TASK_SUFFIX_TRAIN.length());
        }
        if (taskId.endsWith(SUB_TASK_SUFFIX_EVAL)) {
            return taskId.substring(0, taskId.length() - SUB_TASK_SUFFIX_EVAL.length());
        }
        return null;
    }

    /** 是否为训练子任务（按 id 后缀判断）。 */
    public static boolean isTrainSubTask(String taskId) {
        return taskId != null && taskId.endsWith(SUB_TASK_SUFFIX_TRAIN);
    }

    /** 是否为评估子任务（按 id 后缀判断）。 */
    public static boolean isEvalSubTask(String taskId) {
        return taskId != null && taskId.endsWith(SUB_TASK_SUFFIX_EVAL);
    }
}
