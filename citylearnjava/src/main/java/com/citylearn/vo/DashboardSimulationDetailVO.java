package com.citylearn.vo;

import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 仿真仪表盘单个分组的详细数据（KPI + 时序 CSV）
 */
@Getter
@Setter
@ToString
public class DashboardSimulationDetailVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private String groupName;

    private String pyId;

    private String taskId;

    /** exported_kpis.csv 文本 */
    private String kpisCsv;

    /** 结构化 KPI 行，供前端表格直接绑定 */
    private List<Map<String, String>> kpiRows = new ArrayList<>();

    /** 文件名 -> CSV 文本 */
    private Map<String, String> dataFiles = new LinkedHashMap<>();

    /** chesca_trace.csv 文本（CHESCA 决策链路 trace，供可解释可视化） */
    private String chescaTraceCsv;

    /** decision_trace.json 文本（按步聚合的决策推演日志） */
    private String decisionTraceJson;

    /** chesca_agent_config.json 文本（任务目录快照，含 ResMARL 参数） */
    private String agentConfigJson;

    /** 从 agentConfig 提炼的残差参数摘要，便于 KPI 对比标注 */
    private Map<String, Object> resmarlSummary = new LinkedHashMap<>();
}
