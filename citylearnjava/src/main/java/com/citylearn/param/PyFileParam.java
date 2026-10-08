package com.citylearn.param;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * <p>
 * 
 * </p>
 *
 * @author Your Name
 * @since 2025-09-02
 */
@Getter
@Setter
@ToString
public class PyFileParam implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * 主键
     */
    private String id;

    /**
     * 文件名
     */
    private String fileName;

    /**
     * 文件注释
     */
    private String description;


    /**
     * 代码
     */
    private String code;

    /**
     * 是否展示此文件对应结果
     */
    private Boolean ifShow;

    /**
     * 脚本类型：train=只训练 / eval=只评估 / both=训练+评估一体
     */
    private String scriptType;

    /**
     * 该脚本的算法配置（JSON 字符串），供 /savePyFileAlgorithmConfig 保存：
     * [{"id":1,"param_name":"train-schema","value":"1"}]
     */
    private String algorithmConfig;

    /**
     * 执行时是否断点续训（代码编辑器工具栏的「续训」开关）。
     *
     * <p>为 true 时后端给脚本追加 {@code --resume}：从 {@code checkpoints/multi_agent_resume}
     * 里的 checkpoint 接着训，且 {@code --train-epochs} 按「目标总轮数」解释。
     * 目前只有 {@code Multi-agent.py} 声明了该参数，其余脚本收到开关会忽略（只记警告，
     * 不传参），避免 "unrecognized arguments" 直接报错。
     */
    private Boolean resume;

    /**
     * 续训来源任务 ID（代码编辑器「续训」开关打开时，选择一个已执行完成的 task）。
     *
     * <p>非空时后端把 {@code outkpis/<resumeFromTaskId>/checkpoints/multi_agent_resume}
     * 整体复制到本次任务目录，再让脚本从本任务目录续训：
     * <ul>
     *   <li>源任务的训练快照保持不可变（可追溯、可对比）；</li>
     *   <li>断点里的 {@code train_progress.json}（已训练轮数 / 最差和 /
     *       {@code mid_eval_history} 不适曲线）一并继承，续训后曲线与早停判据基线连续；</li>
     *   <li>本任务断点自包含，之后还能从本任务继续续训。</li>
     * </ul>
     * 为空时退回旧行为：用脚本目录下固定的 {@code checkpoints/multi_agent_resume}。
     */
    private String resumeFromTaskId;

}
