package com.citylearn.vo;

import com.citylearn.param.PipelineStepConfig;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;

/**
 * 编排任务（py_task.type=0）详情：任务基本信息 + 两张卡片的配置。
 *
 * <p>列表接口（getAllPyTaskList）刻意不返回 train_config / eval_config ——
 * 那个接口在任务运行期间会被每 5 秒轮询一次，没必要每条都带上两段 JSON。
 * 只有点「编辑」时才通过 /getPyTaskDetail 单独取一次。
 *
 * <p>库里存的是 JSON 字符串，这里在服务层反序列化成结构化的
 * {@link PipelineStepConfig}，前端拿到就是可直接绑定到表单的对象。
 */
@Getter
@Setter
@ToString
public class PyTaskDetailVO implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /** 任务 ID */
    private String taskId;

    /** 任务名称（type=0 时来自 py_task.task_name） */
    private String taskName;

    /** 任务类型：0=编排任务，1=简易任务 */
    private Integer type;

    /** 任务状态，见 PyTaskVO.statusDescOf */
    private Integer status;

    /** 训练卡配置；非编排任务或未填写时为 null */
    private PipelineStepConfig trainConfig;

    /** 评估卡配置；非编排任务或未填写时为 null */
    private PipelineStepConfig evalConfig;
}
