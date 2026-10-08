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
 * 首页能源分配：服务端按日预聚合后的轻量结果（避免下发全年 CSV）。
 */
@Getter
@Setter
@ToString
public class HomeEnergyFlowVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private String taskId;
    private String groupName;
    /** today | history */
    private String mode;
    /** 截止时刻（含），已映射到 datasetYear */
    private String untilTs;
    private Integer datasetYear;

    private List<String> days = new ArrayList<>();
    private List<String> buildings = new ArrayList<>();

    /**
     * day(YYYY-MM-DD) -> scope(community|building_N) -> metric -> value
     */
    private Map<String, Map<String, Map<String, Double>>> flows = new LinkedHashMap<>();
}
