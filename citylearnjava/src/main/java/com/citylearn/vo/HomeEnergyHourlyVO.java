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
 * 首页能源分配「家庭」点击：单日逐小时耗电序列。
 */
@Getter
@Setter
@ToString
public class HomeEnergyHourlyVO implements Serializable {

    private static final long serialVersionUID = 1L;

    private String taskId;
    private String groupName;
    /** YYYY-MM-DD（已映射到 datasetYear） */
    private String day;
    /** community | building_N */
    private String scope;
    private String untilTs;
    private Integer datasetYear;
    /** 当日累计家庭用电 kWh */
    private Double totalHome;

    /**
     * 按时序排列；每项含 ts / home / solarToHome / gridToHome / batteryToHome / nonShiftable / net
     */
    private List<Map<String, Object>> points = new ArrayList<>();
}
