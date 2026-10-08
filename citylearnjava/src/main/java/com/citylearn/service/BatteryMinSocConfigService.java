package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.TypeReference;
import com.citylearn.dao.AlgorithmConfigMapper;
import com.citylearn.entity.AlgorithmConfig;
import com.citylearn.vo.ChescaBatteryConfigVO;
import com.citylearn.vo.ResMarlConfigVO;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class BatteryMinSocConfigService {

    public static final String KEY_MIN_SOC_PER_HOUR = "min_soc_per_hour";
    public static final String KEY_MAX_SOC_NORMAL = "max_soc_normal";
    public static final String KEY_MAX_SOC_OUTAGE = "max_soc_outage";
    public static final String KEY_MAX_SOC_REDUCTION_IN_OUTAGE = "max_soc_reduction_in_outage";
    public static final String KEY_B_LOW = "b_low";
    public static final String KEY_B_HIGH = "b_high";
    public static final String KEY_TMP_MAX_REDUCTION_PERCENT = "tmp_max_reduction_percent";
    public static final String KEY_MIN_COOL_PER_C_OVERHEAT = "min_cool_per_c_overheat";
    public static final String KEY_MIN_COOL_PER_C_OUTDOOR_GAP = "min_cool_per_c_outdoor_gap";
    public static final String KEY_OUTDOOR_GAP_DEADBAND_C = "outdoor_gap_deadband_c";
    public static final String KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C = "outdoor_floor_max_overheat_c";
    public static final String KEY_COOLING_DEMAND_FEEDFORWARD_FRAC = "cooling_demand_feedforward_frac";
    public static final String KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT = "demand_feedforward_only_when_overheat";
    public static final String KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT = "outdoor_floor_allow_when_under_setpoint";
    public static final String KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT = "clear_open_loop_floor_when_under_setpoint";
    public static final String KEY_USE_LAGGED_DYNAMICS_INDOOR = "use_lagged_dynamics_indoor";
    public static final String KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER = "lagged_indoor_only_when_hotter";
    public static final String KEY_LAGGED_INDOOR_HOTTER_MARGIN_C = "lagged_indoor_hotter_margin_c";
    public static final String KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED = "post_outage_soft_charge_enabled";
    public static final String KEY_POST_OUTAGE_RELAX_STEPS = "post_outage_relax_steps";
    public static final String KEY_POST_OUTAGE_WAIVE_MIN_SOC = "post_outage_waive_min_soc";
    public static final String KEY_POST_OUTAGE_MAX_ELE_CHARGE = "post_outage_max_ele_charge";
    public static final String KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT = "post_outage_forbid_charge_when_overheat";
    public static final String KEY_POST_OUTAGE_OVERHEAT_C = "post_outage_overheat_c";
    public static final String KEY_POST_OUTAGE_TMP_CAP_ENABLED = "post_outage_tmp_cap_enabled";
    public static final String KEY_POST_OUTAGE_TMP_CAP_STEPS = "post_outage_tmp_cap_steps";
    public static final String KEY_POST_OUTAGE_TMP_MAX_START = "post_outage_tmp_max_start";
    public static final String KEY_POST_OUTAGE_TMP_RAMP = "post_outage_tmp_ramp";
    public static final String KEY_POST_OUTAGE_TMP_STAGGER = "post_outage_tmp_stagger";
    public static final String KEY_PRICE_AWARE_BATTERY_ENABLED = "price_aware_battery_enabled";
    public static final String KEY_PRICE_HIGH_QUANTILE = "price_high_quantile";
    public static final String KEY_PRICE_LOW_QUANTILE = "price_low_quantile";
    public static final String KEY_PRICE_HISTORY_MIN_STEPS = "price_history_min_steps";
    public static final String KEY_PRICE_HIGH_SOC_THRESHOLD = "price_high_soc_threshold";
    public static final String KEY_PRICE_HIGH_FORBID_CHARGE = "price_high_forbid_charge";
    public static final String KEY_PRICE_HIGH_FORCE_DISCHARGE = "price_high_force_discharge";
    public static final String KEY_PRICE_HIGH_DISCHARGE_ELE = "price_high_discharge_ele";
    public static final String KEY_PRICE_MIN_RESERVE_SOC = "price_min_reserve_soc";
    public static final String KEY_PRICE_GLOBAL_RESERVE_ENABLED = "price_global_reserve_enabled";
    public static final String KEY_PRICE_LOW_TARGET_SOC = "price_low_target_soc";
    public static final String KEY_PRICE_LOW_CHARGE_ELE = "price_low_charge_ele";
    public static final String KEY_PRICE_LOW_SEARCH_BOOST = "price_low_search_boost";
    public static final String KEY_TAU = "tau";
    public static final String KEY_BALANCE_TYPE = "balance_type";
    public static final String KEY_RESMARL_ENABLED = "resmarl_enabled";
    public static final String KEY_MARL_MODE = "marl_mode";
    public static final String KEY_MULTI_AGENT_TRAIN_EPOCHS = "multi_agent_train_epochs";
    public static final String KEY_MULTI_AGENT_EXPLORE = "multi_agent_explore";
    public static final String KEY_MULTI_AGENT_CHECKPOINT = "multi_agent_checkpoint";
    public static final String KEY_RESIDUAL_ALPHA = "residual_alpha";
    public static final String KEY_RESIDUAL_ACTION_MASK = "residual_action_mask";
    public static final String KEY_RESMARL_AFTER_SAFETY = "resmarl_after_safety";
    public static final String KEY_SCHEMA_SPLIT_ENABLED = "schema_split_enabled";
    public static final String KEY_TRAIN_SCHEMA = "train_schema";
    public static final String KEY_MULTI_AGENT_EVAL_SCHEMA = "multi_agent_eval_schema";
    public static final String KEY_EVAL_SCHEMA = "eval_schema";
    /** CHESCA_ResMARL.py 专用评估 schema（与 CHESCA.py 的 eval_schema 独立） */
    public static final String KEY_RESMARL_EVAL_SCHEMA = "resmarl_eval_schema";

    private static final double DEFAULT_MAX_SOC_NORMAL = 0.99;
    private static final double DEFAULT_MAX_SOC_OUTAGE = 0.87;
    private static final double DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE = 0.70;
    private static final double DEFAULT_B_LOW = 1.18;
    private static final double DEFAULT_B_HIGH = 1.0;
    private static final double DEFAULT_TMP_MAX_REDUCTION_PERCENT = 0.0;
    private static final double DEFAULT_MIN_COOL_PER_C_OVERHEAT = 0.12;
    private static final double DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP = 0.03;
    private static final double DEFAULT_OUTDOOR_GAP_DEADBAND_C = 5.0;
    private static final double DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C = 0.5;
    private static final double DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC = 0.10;
    private static final boolean DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT = false;
    private static final boolean DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT = true;
    private static final boolean DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT = false;
    private static final boolean DEFAULT_USE_LAGGED_DYNAMICS_INDOOR = true;
    private static final boolean DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER = false;
    private static final double DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C = 0.3;
    private static final boolean DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED = true;
    private static final int DEFAULT_POST_OUTAGE_RELAX_STEPS = 4;
    private static final boolean DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC = true;
    private static final double DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE = 0.15;
    private static final boolean DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT = true;
    private static final double DEFAULT_POST_OUTAGE_OVERHEAT_C = 0.5;
    private static final boolean DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED = true;
    private static final int DEFAULT_POST_OUTAGE_TMP_CAP_STEPS = 4;
    private static final double DEFAULT_POST_OUTAGE_TMP_MAX_START = 0.40;
    private static final boolean DEFAULT_POST_OUTAGE_TMP_RAMP = true;
    private static final boolean DEFAULT_POST_OUTAGE_TMP_STAGGER = true;
    private static final boolean DEFAULT_PRICE_AWARE_BATTERY_ENABLED = true;
    private static final double DEFAULT_PRICE_HIGH_QUANTILE = 0.75;
    private static final double DEFAULT_PRICE_LOW_QUANTILE = 0.25;
    private static final int DEFAULT_PRICE_HISTORY_MIN_STEPS = 48;
    private static final double DEFAULT_PRICE_HIGH_SOC_THRESHOLD = 0.70;
    private static final boolean DEFAULT_PRICE_HIGH_FORBID_CHARGE = true;
    private static final boolean DEFAULT_PRICE_HIGH_FORCE_DISCHARGE = true;
    private static final double DEFAULT_PRICE_HIGH_DISCHARGE_ELE = 0.15;
    private static final double DEFAULT_PRICE_MIN_RESERVE_SOC = 0.55;
    private static final boolean DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED = true;
    private static final double DEFAULT_PRICE_LOW_TARGET_SOC = 0.80;
    private static final double DEFAULT_PRICE_LOW_CHARGE_ELE = 0.25;
    private static final boolean DEFAULT_PRICE_LOW_SEARCH_BOOST = true;
    private static final int DEFAULT_TAU = 1;
    private static final String DEFAULT_BALANCE_TYPE = "C";
    private static final boolean DEFAULT_RESMARL_ENABLED = true;
    private static final String DEFAULT_MARL_MODE = "none";
    private static final int DEFAULT_MULTI_AGENT_TRAIN_EPOCHS = 20;
    private static final boolean DEFAULT_MULTI_AGENT_EXPLORE = false;
    private static final String DEFAULT_MULTI_AGENT_CHECKPOINT = "";
    private static final double DEFAULT_RESIDUAL_ALPHA = 0.0;
    private static final String DEFAULT_RESIDUAL_ACTION_MASK = "{\"dhw\":false,\"ele\":true,\"tmp\":false}";
    private static final boolean DEFAULT_RESMARL_AFTER_SAFETY = true;
    private static final boolean DEFAULT_SCHEMA_SPLIT_ENABLED = true;
    private static final String DEFAULT_TRAIN_SCHEMA = "citylearn_challenge_2023_phase_2_local_evaluation";
    private static final String DEFAULT_EVAL_SCHEMA = "citylearn_challenge_2023_phase_2_online_evaluation_1";

    private static final double[] DEFAULT_MIN_SOC = {
            0.60, 0.65, 0.72, 0.78, 0.80, 0.85,
            0.80, 0.75, 0.70, 0.60, 0.50, 0.60,
            0.65, 0.65, 0.70, 0.70, 0.70, 0.65,
            0.70, 0.60, 0.60, 0.60, 0.60, 0.55
    };

    @Resource
    private AlgorithmConfigMapper algorithmConfigMapper;

    public ChescaBatteryConfigVO getConfig() {
        ensureDefaults();
        ChescaBatteryConfigVO vo = new ChescaBatteryConfigVO();
        vo.setMinSocPerHour(getMinSocPerHour());
        vo.setMaxSocNormal(getNumberConfig(KEY_MAX_SOC_NORMAL, DEFAULT_MAX_SOC_NORMAL));
        vo.setMaxSocOutage(getNumberConfig(KEY_MAX_SOC_OUTAGE, DEFAULT_MAX_SOC_OUTAGE));
        vo.setMaxSocReductionInOutage(getNumberConfig(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE));
        vo.setBLow(getNumberConfig(KEY_B_LOW, DEFAULT_B_LOW));
        vo.setBHigh(getNumberConfig(KEY_B_HIGH, DEFAULT_B_HIGH));
        vo.setTmpMaxReductionPercent(getNumberConfig(KEY_TMP_MAX_REDUCTION_PERCENT, DEFAULT_TMP_MAX_REDUCTION_PERCENT));
        vo.setMinCoolPerCOverheat(getNumberConfig(KEY_MIN_COOL_PER_C_OVERHEAT, DEFAULT_MIN_COOL_PER_C_OVERHEAT));
        vo.setMinCoolPerCOutdoorGap(getNumberConfig(KEY_MIN_COOL_PER_C_OUTDOOR_GAP, DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP));
        vo.setOutdoorGapDeadbandC(getNumberConfig(KEY_OUTDOOR_GAP_DEADBAND_C, DEFAULT_OUTDOOR_GAP_DEADBAND_C));
        vo.setOutdoorFloorMaxOverheatC(getNumberConfig(KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C, DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C));
        vo.setCoolingDemandFeedforwardFrac(getNumberConfig(KEY_COOLING_DEMAND_FEEDFORWARD_FRAC, DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC));
        vo.setDemandFeedforwardOnlyWhenOverheat(getBoolConfig(KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT, DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT));
        vo.setOutdoorFloorAllowWhenUnderSetpoint(getBoolConfig(KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT, DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT));
        vo.setClearOpenLoopFloorWhenUnderSetpoint(getBoolConfig(KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT, DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT));
        vo.setUseLaggedDynamicsIndoor(getBoolConfig(KEY_USE_LAGGED_DYNAMICS_INDOOR, DEFAULT_USE_LAGGED_DYNAMICS_INDOOR));
        vo.setLaggedIndoorOnlyWhenHotter(getBoolConfig(KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER, DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER));
        vo.setLaggedIndoorHotterMarginC(getNumberConfig(KEY_LAGGED_INDOOR_HOTTER_MARGIN_C, DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C));
        vo.setPostOutageSoftChargeEnabled(getBoolConfig(KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED, DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED));
        vo.setPostOutageRelaxSteps(getIntConfig(KEY_POST_OUTAGE_RELAX_STEPS, DEFAULT_POST_OUTAGE_RELAX_STEPS));
        vo.setPostOutageWaiveMinSoc(getBoolConfig(KEY_POST_OUTAGE_WAIVE_MIN_SOC, DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC));
        vo.setPostOutageMaxEleCharge(getNumberConfig(KEY_POST_OUTAGE_MAX_ELE_CHARGE, DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE));
        vo.setPostOutageForbidChargeWhenOverheat(getBoolConfig(KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT, DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT));
        vo.setPostOutageOverheatC(getNumberConfig(KEY_POST_OUTAGE_OVERHEAT_C, DEFAULT_POST_OUTAGE_OVERHEAT_C));
        vo.setPostOutageTmpCapEnabled(getBoolConfig(KEY_POST_OUTAGE_TMP_CAP_ENABLED, DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED));
        vo.setPostOutageTmpCapSteps(getIntConfig(KEY_POST_OUTAGE_TMP_CAP_STEPS, DEFAULT_POST_OUTAGE_TMP_CAP_STEPS));
        vo.setPostOutageTmpMaxStart(getNumberConfig(KEY_POST_OUTAGE_TMP_MAX_START, DEFAULT_POST_OUTAGE_TMP_MAX_START));
        vo.setPostOutageTmpRamp(getBoolConfig(KEY_POST_OUTAGE_TMP_RAMP, DEFAULT_POST_OUTAGE_TMP_RAMP));
        vo.setPostOutageTmpStagger(getBoolConfig(KEY_POST_OUTAGE_TMP_STAGGER, DEFAULT_POST_OUTAGE_TMP_STAGGER));
        vo.setPriceAwareBatteryEnabled(getBoolConfig(KEY_PRICE_AWARE_BATTERY_ENABLED, DEFAULT_PRICE_AWARE_BATTERY_ENABLED));
        vo.setPriceHighQuantile(getNumberConfig(KEY_PRICE_HIGH_QUANTILE, DEFAULT_PRICE_HIGH_QUANTILE));
        vo.setPriceLowQuantile(getNumberConfig(KEY_PRICE_LOW_QUANTILE, DEFAULT_PRICE_LOW_QUANTILE));
        vo.setPriceHistoryMinSteps(getIntConfig(KEY_PRICE_HISTORY_MIN_STEPS, DEFAULT_PRICE_HISTORY_MIN_STEPS));
        vo.setPriceHighSocThreshold(getNumberConfig(KEY_PRICE_HIGH_SOC_THRESHOLD, DEFAULT_PRICE_HIGH_SOC_THRESHOLD));
        vo.setPriceHighForbidCharge(getBoolConfig(KEY_PRICE_HIGH_FORBID_CHARGE, DEFAULT_PRICE_HIGH_FORBID_CHARGE));
        vo.setPriceHighForceDischarge(getBoolConfig(KEY_PRICE_HIGH_FORCE_DISCHARGE, DEFAULT_PRICE_HIGH_FORCE_DISCHARGE));
        vo.setPriceHighDischargeEle(getNumberConfig(KEY_PRICE_HIGH_DISCHARGE_ELE, DEFAULT_PRICE_HIGH_DISCHARGE_ELE));
        vo.setPriceMinReserveSoc(getNumberConfig(KEY_PRICE_MIN_RESERVE_SOC, DEFAULT_PRICE_MIN_RESERVE_SOC));
        vo.setPriceGlobalReserveEnabled(getBoolConfig(KEY_PRICE_GLOBAL_RESERVE_ENABLED, DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED));
        vo.setPriceLowTargetSoc(getNumberConfig(KEY_PRICE_LOW_TARGET_SOC, DEFAULT_PRICE_LOW_TARGET_SOC));
        vo.setPriceLowChargeEle(getNumberConfig(KEY_PRICE_LOW_CHARGE_ELE, DEFAULT_PRICE_LOW_CHARGE_ELE));
        vo.setPriceLowSearchBoost(getBoolConfig(KEY_PRICE_LOW_SEARCH_BOOST, DEFAULT_PRICE_LOW_SEARCH_BOOST));
        vo.setTau(getIntConfig(KEY_TAU, DEFAULT_TAU));
        vo.setBalanceType(getStringConfig(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE));
        vo.setEvalSchema(getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        return vo;
    }

    public Map<String, Double> getMinSocPerHour() {
        Map<String, Double> fromConfig = readMinSocJsonConfig();
        if (fromConfig != null && !fromConfig.isEmpty()) {
            return normalizeMinSocMap(fromConfig);
        }
        return getDefaultMinSocPerHour();
    }

    public void saveConfig(ChescaBatteryConfigVO config) {
        if (config == null) {
            throw new RuntimeException("配置不能为空");
        }
        ChescaBatteryConfigVO defaults = getDefaultConfig();
        if (config.getMinSocPerHour() == null || config.getMinSocPerHour().isEmpty()) {
            config.setMinSocPerHour(defaults.getMinSocPerHour());
        }
        if (config.getMaxSocNormal() == null) {
            config.setMaxSocNormal(defaults.getMaxSocNormal());
        }
        if (config.getMaxSocOutage() == null) {
            config.setMaxSocOutage(defaults.getMaxSocOutage());
        }
        if (config.getMaxSocReductionInOutage() == null) {
            config.setMaxSocReductionInOutage(defaults.getMaxSocReductionInOutage());
        }
        if (config.getBLow() == null) {
            config.setBLow(defaults.getBLow());
        }
        if (config.getBHigh() == null) {
            config.setBHigh(defaults.getBHigh());
        }
        if (config.getTmpMaxReductionPercent() == null) {
            config.setTmpMaxReductionPercent(defaults.getTmpMaxReductionPercent());
        }
        if (config.getMinCoolPerCOverheat() == null) {
            config.setMinCoolPerCOverheat(defaults.getMinCoolPerCOverheat());
        }
        if (config.getMinCoolPerCOutdoorGap() == null) {
            config.setMinCoolPerCOutdoorGap(defaults.getMinCoolPerCOutdoorGap());
        }
        if (config.getOutdoorGapDeadbandC() == null) {
            config.setOutdoorGapDeadbandC(defaults.getOutdoorGapDeadbandC());
        }
        if (config.getOutdoorFloorMaxOverheatC() == null) {
            config.setOutdoorFloorMaxOverheatC(defaults.getOutdoorFloorMaxOverheatC());
        }
        if (config.getCoolingDemandFeedforwardFrac() == null) {
            config.setCoolingDemandFeedforwardFrac(defaults.getCoolingDemandFeedforwardFrac());
        }
        if (config.getDemandFeedforwardOnlyWhenOverheat() == null) {
            config.setDemandFeedforwardOnlyWhenOverheat(defaults.getDemandFeedforwardOnlyWhenOverheat());
        }
        if (config.getOutdoorFloorAllowWhenUnderSetpoint() == null) {
            config.setOutdoorFloorAllowWhenUnderSetpoint(defaults.getOutdoorFloorAllowWhenUnderSetpoint());
        }
        if (config.getClearOpenLoopFloorWhenUnderSetpoint() == null) {
            config.setClearOpenLoopFloorWhenUnderSetpoint(defaults.getClearOpenLoopFloorWhenUnderSetpoint());
        }
        if (config.getUseLaggedDynamicsIndoor() == null) {
            config.setUseLaggedDynamicsIndoor(defaults.getUseLaggedDynamicsIndoor());
        }
        if (config.getLaggedIndoorOnlyWhenHotter() == null) {
            config.setLaggedIndoorOnlyWhenHotter(defaults.getLaggedIndoorOnlyWhenHotter());
        }
        if (config.getLaggedIndoorHotterMarginC() == null) {
            config.setLaggedIndoorHotterMarginC(defaults.getLaggedIndoorHotterMarginC());
        }
        if (config.getPostOutageSoftChargeEnabled() == null) {
            config.setPostOutageSoftChargeEnabled(defaults.getPostOutageSoftChargeEnabled());
        }
        if (config.getPostOutageRelaxSteps() == null) {
            config.setPostOutageRelaxSteps(defaults.getPostOutageRelaxSteps());
        }
        if (config.getPostOutageWaiveMinSoc() == null) {
            config.setPostOutageWaiveMinSoc(defaults.getPostOutageWaiveMinSoc());
        }
        if (config.getPostOutageMaxEleCharge() == null) {
            config.setPostOutageMaxEleCharge(defaults.getPostOutageMaxEleCharge());
        }
        if (config.getPostOutageForbidChargeWhenOverheat() == null) {
            config.setPostOutageForbidChargeWhenOverheat(defaults.getPostOutageForbidChargeWhenOverheat());
        }
        if (config.getPostOutageOverheatC() == null) {
            config.setPostOutageOverheatC(defaults.getPostOutageOverheatC());
        }
        if (config.getPostOutageTmpCapEnabled() == null) {
            config.setPostOutageTmpCapEnabled(defaults.getPostOutageTmpCapEnabled());
        }
        if (config.getPostOutageTmpCapSteps() == null) {
            config.setPostOutageTmpCapSteps(defaults.getPostOutageTmpCapSteps());
        }
        if (config.getPostOutageTmpMaxStart() == null) {
            config.setPostOutageTmpMaxStart(defaults.getPostOutageTmpMaxStart());
        }
        if (config.getPostOutageTmpRamp() == null) {
            config.setPostOutageTmpRamp(defaults.getPostOutageTmpRamp());
        }
        if (config.getPostOutageTmpStagger() == null) {
            config.setPostOutageTmpStagger(defaults.getPostOutageTmpStagger());
        }
        if (config.getPriceAwareBatteryEnabled() == null) {
            config.setPriceAwareBatteryEnabled(defaults.getPriceAwareBatteryEnabled());
        }
        if (config.getPriceHighQuantile() == null) {
            config.setPriceHighQuantile(defaults.getPriceHighQuantile());
        }
        if (config.getPriceLowQuantile() == null) {
            config.setPriceLowQuantile(defaults.getPriceLowQuantile());
        }
        if (config.getPriceHistoryMinSteps() == null) {
            config.setPriceHistoryMinSteps(defaults.getPriceHistoryMinSteps());
        }
        if (config.getPriceHighSocThreshold() == null) {
            config.setPriceHighSocThreshold(defaults.getPriceHighSocThreshold());
        }
        if (config.getPriceHighForbidCharge() == null) {
            config.setPriceHighForbidCharge(defaults.getPriceHighForbidCharge());
        }
        if (config.getPriceHighForceDischarge() == null) {
            config.setPriceHighForceDischarge(defaults.getPriceHighForceDischarge());
        }
        if (config.getPriceHighDischargeEle() == null) {
            config.setPriceHighDischargeEle(defaults.getPriceHighDischargeEle());
        }
        if (config.getPriceMinReserveSoc() == null) {
            config.setPriceMinReserveSoc(defaults.getPriceMinReserveSoc());
        }
        if (config.getPriceGlobalReserveEnabled() == null) {
            config.setPriceGlobalReserveEnabled(defaults.getPriceGlobalReserveEnabled());
        }
        if (config.getPriceLowTargetSoc() == null) {
            config.setPriceLowTargetSoc(defaults.getPriceLowTargetSoc());
        }
        if (config.getPriceLowChargeEle() == null) {
            config.setPriceLowChargeEle(defaults.getPriceLowChargeEle());
        }
        if (config.getPriceLowSearchBoost() == null) {
            config.setPriceLowSearchBoost(defaults.getPriceLowSearchBoost());
        }
        if (config.getTau() == null) {
            config.setTau(defaults.getTau());
        }
        if (config.getBalanceType() == null || config.getBalanceType().isEmpty()) {
            config.setBalanceType(defaults.getBalanceType());
        }
        if (config.getEvalSchema() == null || config.getEvalSchema().trim().isEmpty()) {
            config.setEvalSchema(defaults.getEvalSchema());
        }
        saveMinSocPerHour(config.getMinSocPerHour());
        saveSocRatioConfig(KEY_MAX_SOC_NORMAL, config.getMaxSocNormal(), "正常时段电池SOC上限");
        saveSocRatioConfig(KEY_MAX_SOC_OUTAGE, config.getMaxSocOutage(), "停电时段电池SOC上限");
        saveSocRatioConfig(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, config.getMaxSocReductionInOutage(), "停电时最大SOC降幅");
        saveThresholdConfig(KEY_B_LOW, config.getBLow(), "负荷平衡增负荷阈值系数B_low");
        saveThresholdConfig(KEY_B_HIGH, config.getBHigh(), "负荷平衡减负荷阈值系数B_high");
        saveSocRatioConfig(KEY_TMP_MAX_REDUCTION_PERCENT, config.getTmpMaxReductionPercent(), "冷机最大削减比例TMP_max_reduction_percent");
        saveNonNegConfig(KEY_MIN_COOL_PER_C_OVERHEAT, config.getMinCoolPerCOverheat(), 2.0, "过热最小制冷系数min_cool_per_c_overheat");
        saveNonNegConfig(KEY_MIN_COOL_PER_C_OUTDOOR_GAP, config.getMinCoolPerCOutdoorGap(), 1.0, "室外开环保底系数min_cool_per_c_outdoor_gap");
        saveNonNegConfig(KEY_OUTDOOR_GAP_DEADBAND_C, config.getOutdoorGapDeadbandC(), 30.0, "室外保底死区outdoor_gap_deadband_c");
        saveNonNegConfig(KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C, config.getOutdoorFloorMaxOverheatC(), 10.0, "室外保底最大过热阈值outdoor_floor_max_overheat_c");
        saveSocRatioConfig(KEY_COOLING_DEMAND_FEEDFORWARD_FRAC, config.getCoolingDemandFeedforwardFrac(), "冷负荷前馈比例cooling_demand_feedforward_frac");
        upsertStringConfig(
                KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT,
                String.valueOf(Boolean.TRUE.equals(config.getDemandFeedforwardOnlyWhenOverheat())),
                "冷负荷前馈仅过热时启用"
        );
        upsertStringConfig(
                KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT,
                String.valueOf(Boolean.TRUE.equals(config.getOutdoorFloorAllowWhenUnderSetpoint())),
                "室外保底允许低于设定时启用"
        );
        upsertStringConfig(
                KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT,
                String.valueOf(Boolean.TRUE.equals(config.getClearOpenLoopFloorWhenUnderSetpoint())),
                "低于设定时清掉开环保底"
        );
        upsertStringConfig(
                KEY_USE_LAGGED_DYNAMICS_INDOOR,
                String.valueOf(Boolean.TRUE.equals(config.getUseLaggedDynamicsIndoor())),
                "PID使用滞后动力学室温indoor[-2]"
        );
        upsertStringConfig(
                KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER,
                String.valueOf(Boolean.TRUE.equals(config.getLaggedIndoorOnlyWhenHotter())),
                "仅当滞后室温更热时启用"
        );
        saveNonNegConfig(KEY_LAGGED_INDOOR_HOTTER_MARGIN_C, config.getLaggedIndoorHotterMarginC(), 10.0, "滞后室温更热裕度lagged_indoor_hotter_margin_c");
        upsertStringConfig(
                KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageSoftChargeEnabled())),
                "是否启用复电缓充"
        );
        int relaxSteps = config.getPostOutageRelaxSteps() == null
                ? DEFAULT_POST_OUTAGE_RELAX_STEPS
                : config.getPostOutageRelaxSteps();
        if (relaxSteps < 0 || relaxSteps > 48) {
            throw new RuntimeException("post_outage_relax_steps 须在 0~48 之间");
        }
        upsertIntConfig(KEY_POST_OUTAGE_RELAX_STEPS, relaxSteps, "复电缓充窗口步数");
        upsertStringConfig(
                KEY_POST_OUTAGE_WAIVE_MIN_SOC,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageWaiveMinSoc())),
                "复电窗口豁免小时min_soc硬充"
        );
        saveSocRatioConfig(KEY_POST_OUTAGE_MAX_ELE_CHARGE, config.getPostOutageMaxEleCharge(), "复电窗口ELE充电上限");
        upsertStringConfig(
                KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageForbidChargeWhenOverheat())),
                "复电窗口过热时禁止充电"
        );
        saveNonNegConfig(KEY_POST_OUTAGE_OVERHEAT_C, config.getPostOutageOverheatC(), 20.0, "复电缓充过热阈值post_outage_overheat_c");
        upsertStringConfig(
                KEY_POST_OUTAGE_TMP_CAP_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageTmpCapEnabled())),
                "是否启用复电TMP帽/斜坡"
        );
        int tmpCapSteps = config.getPostOutageTmpCapSteps() == null
                ? DEFAULT_POST_OUTAGE_TMP_CAP_STEPS
                : config.getPostOutageTmpCapSteps();
        if (tmpCapSteps < 0 || tmpCapSteps > 48) {
            throw new RuntimeException("post_outage_tmp_cap_steps 须在 0~48 之间");
        }
        upsertIntConfig(KEY_POST_OUTAGE_TMP_CAP_STEPS, tmpCapSteps, "复电TMP帽窗口步数");
        saveSocRatioConfig(KEY_POST_OUTAGE_TMP_MAX_START, config.getPostOutageTmpMaxStart(), "复电首步TMP上限");
        upsertStringConfig(
                KEY_POST_OUTAGE_TMP_RAMP,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageTmpRamp())),
                "复电TMP是否线性爬升"
        );
        upsertStringConfig(
                KEY_POST_OUTAGE_TMP_STAGGER,
                String.valueOf(Boolean.TRUE.equals(config.getPostOutageTmpStagger())),
                "复电TMP分栋错峰"
        );
        upsertStringConfig(
                KEY_PRICE_AWARE_BATTERY_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPriceAwareBatteryEnabled())),
                "是否启用电价感知电池"
        );
        saveNonNegConfig(KEY_PRICE_HIGH_QUANTILE, config.getPriceHighQuantile(), 0.99, "高价分位数");
        saveNonNegConfig(KEY_PRICE_LOW_QUANTILE, config.getPriceLowQuantile(), 0.5, "低价分位数");
        int priceHistMin = config.getPriceHistoryMinSteps() == null
                ? DEFAULT_PRICE_HISTORY_MIN_STEPS
                : config.getPriceHistoryMinSteps();
        if (priceHistMin < 8 || priceHistMin > 720) {
            throw new RuntimeException("price_history_min_steps 须在 8~720 之间");
        }
        upsertIntConfig(KEY_PRICE_HISTORY_MIN_STEPS, priceHistMin, "电价历史最少样本步数");
        saveSocRatioConfig(KEY_PRICE_HIGH_SOC_THRESHOLD, config.getPriceHighSocThreshold(), "高价强制放电SOC阈值");
        upsertStringConfig(
                KEY_PRICE_HIGH_FORBID_CHARGE,
                String.valueOf(Boolean.TRUE.equals(config.getPriceHighForbidCharge())),
                "高价禁止充电"
        );
        upsertStringConfig(
                KEY_PRICE_HIGH_FORCE_DISCHARGE,
                String.valueOf(Boolean.TRUE.equals(config.getPriceHighForceDischarge())),
                "高价高SOC强制放电"
        );
        saveSocRatioConfig(KEY_PRICE_HIGH_DISCHARGE_ELE, config.getPriceHighDischargeEle(), "高价强制放电ELE幅度");
        saveSocRatioConfig(KEY_PRICE_MIN_RESERVE_SOC, config.getPriceMinReserveSoc(), "高价放电韧性地板SOC");
        upsertStringConfig(
                KEY_PRICE_GLOBAL_RESERVE_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPriceGlobalReserveEnabled())),
                "全局韧性地板（非停电放电不可击穿）"
        );
        saveSocRatioConfig(KEY_PRICE_LOW_TARGET_SOC, config.getPriceLowTargetSoc(), "低价补电目标SOC");
        saveSocRatioConfig(KEY_PRICE_LOW_CHARGE_ELE, config.getPriceLowChargeEle(), "低价补电ELE幅度");
        upsertStringConfig(
                KEY_PRICE_LOW_SEARCH_BOOST,
                String.valueOf(Boolean.TRUE.equals(config.getPriceLowSearchBoost())),
                "低价树搜索抬高SOC下限促补电"
        );
        saveTauConfig(config.getTau());
        saveBalanceTypeConfig(config.getBalanceType());
        String evalSchema = config.getEvalSchema() == null ? "" : config.getEvalSchema().trim();
        if (evalSchema.isEmpty()) {
            evalSchema = DEFAULT_EVAL_SCHEMA;
        }
        upsertStringConfig(KEY_EVAL_SCHEMA, evalSchema, "CHESCA 仿真/KPI 评估 schema");
    }

    public void saveMinSocPerHour(Map<String, Double> config) {
        if (config == null || config.isEmpty()) {
            throw new RuntimeException("小时 SOC 下限配置不能为空");
        }
        Map<String, Double> normalized = normalizeMinSocMap(config);
        for (int h = 0; h < 24; h++) {
            String key = String.valueOf(h);
            Double value = normalized.get(key);
            if (value == null) {
                throw new RuntimeException("缺少小时 " + h + " 的配置");
            }
            if (value < 0 || value > 1) {
                throw new RuntimeException("小时 " + h + " 的 SOC 下限须在 0~1 之间");
            }
        }
        upsertJsonConfig(KEY_MIN_SOC_PER_HOUR, normalized, "24小时电池SOC下限");
    }

    public ChescaBatteryConfigVO getDefaultConfig() {
        ChescaBatteryConfigVO vo = new ChescaBatteryConfigVO();
        vo.setMinSocPerHour(getDefaultMinSocPerHour());
        vo.setMaxSocNormal(DEFAULT_MAX_SOC_NORMAL);
        vo.setMaxSocOutage(DEFAULT_MAX_SOC_OUTAGE);
        vo.setMaxSocReductionInOutage(DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE);
        vo.setBLow(DEFAULT_B_LOW);
        vo.setBHigh(DEFAULT_B_HIGH);
        vo.setTmpMaxReductionPercent(DEFAULT_TMP_MAX_REDUCTION_PERCENT);
        vo.setMinCoolPerCOverheat(DEFAULT_MIN_COOL_PER_C_OVERHEAT);
        vo.setMinCoolPerCOutdoorGap(DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP);
        vo.setOutdoorGapDeadbandC(DEFAULT_OUTDOOR_GAP_DEADBAND_C);
        vo.setOutdoorFloorMaxOverheatC(DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C);
        vo.setCoolingDemandFeedforwardFrac(DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC);
        vo.setDemandFeedforwardOnlyWhenOverheat(DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT);
        vo.setOutdoorFloorAllowWhenUnderSetpoint(DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT);
        vo.setClearOpenLoopFloorWhenUnderSetpoint(DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT);
        vo.setUseLaggedDynamicsIndoor(DEFAULT_USE_LAGGED_DYNAMICS_INDOOR);
        vo.setLaggedIndoorOnlyWhenHotter(DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER);
        vo.setLaggedIndoorHotterMarginC(DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C);
        vo.setPostOutageSoftChargeEnabled(DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED);
        vo.setPostOutageRelaxSteps(DEFAULT_POST_OUTAGE_RELAX_STEPS);
        vo.setPostOutageWaiveMinSoc(DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC);
        vo.setPostOutageMaxEleCharge(DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE);
        vo.setPostOutageForbidChargeWhenOverheat(DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT);
        vo.setPostOutageOverheatC(DEFAULT_POST_OUTAGE_OVERHEAT_C);
        vo.setPostOutageTmpCapEnabled(DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED);
        vo.setPostOutageTmpCapSteps(DEFAULT_POST_OUTAGE_TMP_CAP_STEPS);
        vo.setPostOutageTmpMaxStart(DEFAULT_POST_OUTAGE_TMP_MAX_START);
        vo.setPostOutageTmpRamp(DEFAULT_POST_OUTAGE_TMP_RAMP);
        vo.setPostOutageTmpStagger(DEFAULT_POST_OUTAGE_TMP_STAGGER);
        vo.setPriceAwareBatteryEnabled(DEFAULT_PRICE_AWARE_BATTERY_ENABLED);
        vo.setPriceHighQuantile(DEFAULT_PRICE_HIGH_QUANTILE);
        vo.setPriceLowQuantile(DEFAULT_PRICE_LOW_QUANTILE);
        vo.setPriceHistoryMinSteps(DEFAULT_PRICE_HISTORY_MIN_STEPS);
        vo.setPriceHighSocThreshold(DEFAULT_PRICE_HIGH_SOC_THRESHOLD);
        vo.setPriceHighForbidCharge(DEFAULT_PRICE_HIGH_FORBID_CHARGE);
        vo.setPriceHighForceDischarge(DEFAULT_PRICE_HIGH_FORCE_DISCHARGE);
        vo.setPriceHighDischargeEle(DEFAULT_PRICE_HIGH_DISCHARGE_ELE);
        vo.setPriceMinReserveSoc(DEFAULT_PRICE_MIN_RESERVE_SOC);
        vo.setPriceGlobalReserveEnabled(DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED);
        vo.setPriceLowTargetSoc(DEFAULT_PRICE_LOW_TARGET_SOC);
        vo.setPriceLowChargeEle(DEFAULT_PRICE_LOW_CHARGE_ELE);
        vo.setPriceLowSearchBoost(DEFAULT_PRICE_LOW_SEARCH_BOOST);
        vo.setTau(DEFAULT_TAU);
        vo.setBalanceType(DEFAULT_BALANCE_TYPE);
        vo.setEvalSchema(DEFAULT_EVAL_SCHEMA);
        return vo;
    }

    /** 获取 CHESCA-ResMARL 配置 */
    public ResMarlConfigVO getResMarlConfig() {
        ensureDefaults();
        ResMarlConfigVO vo = new ResMarlConfigVO();
        // 兼容字段：配置页已去掉开关，固定返回 true（实际是否残差由入口脚本决定）
        vo.setResmarlEnabled(true);
        vo.setMarlMode("multi_agent");
        vo.setMultiAgentTrainEpochs(getIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, DEFAULT_MULTI_AGENT_TRAIN_EPOCHS));
        vo.setMultiAgentExplore(getBoolConfig(KEY_MULTI_AGENT_EXPLORE, DEFAULT_MULTI_AGENT_EXPLORE));
        vo.setMultiAgentCheckpoint(getStringConfig(KEY_MULTI_AGENT_CHECKPOINT, DEFAULT_MULTI_AGENT_CHECKPOINT));
        vo.setResidualAlpha(getNumberConfig(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA));
        vo.setResidualActionMask(getResidualActionMask());
        vo.setResmarlAfterSafety(getBoolConfig(KEY_RESMARL_AFTER_SAFETY, DEFAULT_RESMARL_AFTER_SAFETY));
        vo.setTrainSchema(getStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA));
        vo.setMultiAgentEvalSchema(getStringConfig(KEY_MULTI_AGENT_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        // 残差评估集：优先 resmarl_eval_schema；旧库无该键时回退 eval_schema
        vo.setEvalSchema(getStringConfig(
                KEY_RESMARL_EVAL_SCHEMA,
                getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA)));
        return vo;
    }

    /** 保存 CHESCA-ResMARL 配置到 algorithm_config */
    public void saveResMarlConfig(ResMarlConfigVO config) {
        if (config == null) {
            throw new RuntimeException("配置不能为空");
        }
        boolean enabled = true;
        String marlMode = "multi_agent";

        Integer trainEpochs = config.getMultiAgentTrainEpochs();
        if (trainEpochs == null) {
            trainEpochs = 0;
        }
        String checkpoint = config.getMultiAgentCheckpoint();
        if (checkpoint == null) {
            checkpoint = DEFAULT_MULTI_AGENT_CHECKPOINT;
        } else {
            checkpoint = checkpoint.trim();
        }
        // 入口脚本决定是否残差；空 checkpoint 允许保存（恢复默认），运行 CHESCA_ResMARL.py 时再校验
        if (trainEpochs < 0 || trainEpochs > 500) {
            throw new RuntimeException("multi_agent_train_epochs 须在 [0, 500] 之间（评估侧已不再使用，仅兼容旧配置）");
        }
        boolean explore = config.getMultiAgentExplore() != null
                ? config.getMultiAgentExplore()
                : DEFAULT_MULTI_AGENT_EXPLORE;

        Double alpha = config.getResidualAlpha();
        if (alpha == null) {
            alpha = DEFAULT_RESIDUAL_ALPHA;
        }
        if (alpha < 0 || alpha > 1) {
            throw new RuntimeException("residual_alpha 须在 [0, 1] 之间");
        }
        Map<String, Boolean> mask = normalizeResidualActionMaskFromObject(config.getResidualActionMask());
        boolean afterSafety = config.getResmarlAfterSafety() != null
                ? config.getResmarlAfterSafety()
                : DEFAULT_RESMARL_AFTER_SAFETY;
        String resmarlEvalSchema = config.getEvalSchema();
        if (resmarlEvalSchema == null || resmarlEvalSchema.trim().isEmpty()) {
            resmarlEvalSchema = getStringConfig(
                    KEY_RESMARL_EVAL_SCHEMA,
                    getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        } else {
            resmarlEvalSchema = resmarlEvalSchema.trim();
        }
        String trainSchema = config.getTrainSchema();
        if (trainSchema == null || trainSchema.trim().isEmpty()) {
            trainSchema = DEFAULT_TRAIN_SCHEMA;
        } else {
            trainSchema = trainSchema.trim();
        }
        String multiAgentEvalSchema = config.getMultiAgentEvalSchema();
        if (multiAgentEvalSchema == null || multiAgentEvalSchema.trim().isEmpty()) {
            multiAgentEvalSchema = DEFAULT_EVAL_SCHEMA;
        } else {
            multiAgentEvalSchema = multiAgentEvalSchema.trim();
        }

        upsertStringConfig(KEY_RESMARL_ENABLED, String.valueOf(enabled), "兼容字段：是否启用由入口脚本决定，配置页固定 true");
        upsertStringConfig(KEY_MARL_MODE, marlMode, "MARL 模式：none / multi_agent（实际由入口脚本覆盖）");
        upsertIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, trainEpochs, "Multi-Agent SAC 训练轮数（仅 Multi-agent.py；评估侧已废弃）");
        upsertStringConfig(KEY_MULTI_AGENT_EXPLORE, String.valueOf(explore), "Multi-Agent 评估时是否开启 explore");
        upsertStringConfig(KEY_MULTI_AGENT_CHECKPOINT, checkpoint, "预存 Multi-Agent SAC checkpoint（CHESCA_ResMARL.py 必填）");
        upsertNumberConfig(KEY_RESIDUAL_ALPHA, alpha, "CHESCA-ResMARL 残差强度α∈[0,1]");
        upsertConfig(KEY_RESIDUAL_ACTION_MASK, JSON.toJSONString(mask), "json", "CHESCA-ResMARL 可修正动作维 mask");
        upsertStringConfig(KEY_RESMARL_AFTER_SAFETY, String.valueOf(afterSafety), "残差是否在安全审查之后施加");
        upsertStringConfig(KEY_SCHEMA_SPLIT_ENABLED, "true", "Multi-agent 训测 schema 是否分离（界面配置）");
        upsertStringConfig(KEY_TRAIN_SCHEMA, trainSchema, "Multi-agent.py 训练 schema");
        upsertStringConfig(KEY_MULTI_AGENT_EVAL_SCHEMA, multiAgentEvalSchema, "Multi-agent.py 评估 schema");
        // 仅更新 ResMARL 评估集，不覆盖 CHESCA.py 的 eval_schema
        upsertStringConfig(KEY_RESMARL_EVAL_SCHEMA, resmarlEvalSchema, "CHESCA_ResMARL.py 仿真/KPI 评估 schema");
    }

    public ResMarlConfigVO getDefaultResMarlConfig() {
        ResMarlConfigVO vo = new ResMarlConfigVO();
        vo.setResmarlEnabled(true);
        vo.setMarlMode("multi_agent");
        vo.setMultiAgentTrainEpochs(0);
        vo.setMultiAgentExplore(DEFAULT_MULTI_AGENT_EXPLORE);
        vo.setMultiAgentCheckpoint(DEFAULT_MULTI_AGENT_CHECKPOINT);
        vo.setResidualAlpha(DEFAULT_RESIDUAL_ALPHA);
        vo.setResidualActionMask(defaultResidualActionMask());
        vo.setResmarlAfterSafety(DEFAULT_RESMARL_AFTER_SAFETY);
        vo.setTrainSchema(DEFAULT_TRAIN_SCHEMA);
        vo.setMultiAgentEvalSchema(DEFAULT_EVAL_SCHEMA);
        vo.setEvalSchema(DEFAULT_EVAL_SCHEMA);
        return vo;
    }

    private String normalizeMarlMode(String mode) {
        if (mode == null || mode.trim().isEmpty()) {
            return DEFAULT_MARL_MODE;
        }
        String normalized = mode.trim().toLowerCase();
        if (!"none".equals(normalized) && !"multi_agent".equals(normalized)) {
            if ("central_residual".equals(normalized)) {
                return "multi_agent";
            }
            throw new RuntimeException("marl_mode 须为 none / multi_agent");
        }
        return normalized;
    }

    /** 读取 marl_mode；resmarl_enabled=true 且库中为空/none 时推断为 multi_agent（兼容旧数据） */
    private String resolveMarlModeForDisplay(boolean resmarlEnabled) {
        String stored = getStringConfig(KEY_MARL_MODE, DEFAULT_MARL_MODE);
        if (stored == null || stored.isEmpty()) {
            stored = DEFAULT_MARL_MODE;
        }
        stored = stored.trim().toLowerCase();
        if (!resmarlEnabled) {
            return "none";
        }
        if ("none".equals(stored) || stored.isEmpty()) {
            return "multi_agent";
        }
        if ("multi_agent".equals(stored)) {
            return stored;
        }
        if ("central_residual".equals(stored)) {
            return "multi_agent";
        }
        return "multi_agent";
    }

    /** 写入 chesca_agent_config.json 时解析 marl_mode（与 Python _resolve_marl_mode 一致） */
    private String resolveMarlModeForTaskJson(boolean resmarlEnabled) {
        String stored = getStringConfig(KEY_MARL_MODE, DEFAULT_MARL_MODE);
        if (stored != null && !stored.trim().isEmpty() && !"none".equalsIgnoreCase(stored.trim())) {
            return normalizeMarlMode(stored);
        }
        if (resmarlEnabled) {
            return "multi_agent";
        }
        return "none";
    }

    private Map<String, Boolean> defaultResidualActionMask() {
        Map<String, Boolean> mask = new LinkedHashMap<>();
        mask.put("dhw", false);
        mask.put("ele", true);
        mask.put("tmp", false);
        return mask;
    }

    private Map<String, Boolean> normalizeResidualActionMask(Map<String, Boolean> source) {
        Map<String, Boolean> mask = defaultResidualActionMask();
        if (source == null) {
            return mask;
        }
        if (source.containsKey("dhw") && source.get("dhw") != null) {
            mask.put("dhw", source.get("dhw"));
        }
        if (source.containsKey("ele") && source.get("ele") != null) {
            mask.put("ele", source.get("ele"));
        }
        if (source.containsKey("tmp") && source.get("tmp") != null) {
            mask.put("tmp", source.get("tmp"));
        }
        return mask;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Boolean> normalizeResidualActionMaskFromObject(Object source) {
        if (source == null) {
            return defaultResidualActionMask();
        }
        if (source instanceof Map) {
            Map<String, Object> raw = (Map<String, Object>) source;
            Map<String, Boolean> converted = new LinkedHashMap<>();
            for (Map.Entry<String, Object> e : raw.entrySet()) {
                if (e.getValue() instanceof Boolean) {
                    converted.put(e.getKey(), (Boolean) e.getValue());
                } else if (e.getValue() != null) {
                    converted.put(e.getKey(), Boolean.parseBoolean(String.valueOf(e.getValue())));
                }
            }
            return normalizeResidualActionMask(converted);
        }
        return defaultResidualActionMask();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Boolean> getResidualActionMask() {
        AlgorithmConfig row = algorithmConfigMapper.selectById(KEY_RESIDUAL_ACTION_MASK);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return defaultResidualActionMask();
        }
        try {
            Map<String, Object> parsed = JSON.parseObject(row.getConfigValue(), Map.class);
            Map<String, Boolean> converted = new LinkedHashMap<>();
            if (parsed != null) {
                for (Map.Entry<String, Object> e : parsed.entrySet()) {
                    if (e.getValue() instanceof Boolean) {
                        converted.put(e.getKey(), (Boolean) e.getValue());
                    } else if (e.getValue() != null) {
                        converted.put(e.getKey(), Boolean.parseBoolean(String.valueOf(e.getValue())));
                    }
                }
            }
            return normalizeResidualActionMask(converted);
        } catch (Exception e) {
            return defaultResidualActionMask();
        }
    }

    public Map<String, Double> getDefaultMinSocPerHour() {
        Map<String, Double> defaults = new LinkedHashMap<>();
        for (int h = 0; h < 24; h++) {
            defaults.put(String.valueOf(h), DEFAULT_MIN_SOC[h]);
        }
        return defaults;
    }

    /** 将当前配置写入任务目录，供 Python --min-soc-config 读取（默认 CHESCA.py 评估集） */
    public String writeConfigJsonToTaskDir(String taskOutputDir) throws IOException {
        return writeConfigJsonToTaskDir(taskOutputDir, false);
    }

    /**
     * 将当前配置写入任务目录。
     * @param forResMarlEntry true 时 payload.eval_schema 使用残差配置的 resmarl_eval_schema（供 CHESCA_ResMARL.py）
     */
    public String writeConfigJsonToTaskDir(String taskOutputDir, boolean forResMarlEntry) throws IOException {
        ChescaBatteryConfigVO config = getConfig();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put(KEY_MIN_SOC_PER_HOUR, config.getMinSocPerHour());
        payload.put(KEY_MAX_SOC_NORMAL, config.getMaxSocNormal());
        payload.put(KEY_MAX_SOC_OUTAGE, config.getMaxSocOutage());
        payload.put(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, config.getMaxSocReductionInOutage());
        payload.put("B_low", config.getBLow());
        payload.put("B_high", config.getBHigh());
        payload.put("TMP_max_reduction_percent", config.getTmpMaxReductionPercent());
        payload.put("min_cool_per_c_overheat", config.getMinCoolPerCOverheat());
        payload.put("min_cool_per_c_outdoor_gap", config.getMinCoolPerCOutdoorGap());
        payload.put("outdoor_gap_deadband_c", config.getOutdoorGapDeadbandC());
        payload.put("outdoor_floor_max_overheat_c", config.getOutdoorFloorMaxOverheatC());
        payload.put("cooling_demand_feedforward_frac", config.getCoolingDemandFeedforwardFrac());
        payload.put("demand_feedforward_only_when_overheat", config.getDemandFeedforwardOnlyWhenOverheat());
        payload.put("outdoor_floor_allow_when_under_setpoint", config.getOutdoorFloorAllowWhenUnderSetpoint());
        payload.put("clear_open_loop_floor_when_under_setpoint", config.getClearOpenLoopFloorWhenUnderSetpoint());
        payload.put("use_lagged_dynamics_indoor", config.getUseLaggedDynamicsIndoor());
        payload.put("lagged_indoor_only_when_hotter", config.getLaggedIndoorOnlyWhenHotter());
        payload.put("lagged_indoor_hotter_margin_c", config.getLaggedIndoorHotterMarginC());
        payload.put("post_outage_soft_charge_enabled", config.getPostOutageSoftChargeEnabled());
        payload.put("post_outage_relax_steps", config.getPostOutageRelaxSteps());
        payload.put("post_outage_waive_min_soc", config.getPostOutageWaiveMinSoc());
        payload.put("post_outage_max_ele_charge", config.getPostOutageMaxEleCharge());
        payload.put("post_outage_forbid_charge_when_overheat", config.getPostOutageForbidChargeWhenOverheat());
        payload.put("post_outage_overheat_c", config.getPostOutageOverheatC());
        payload.put("post_outage_tmp_cap_enabled", config.getPostOutageTmpCapEnabled());
        payload.put("post_outage_tmp_cap_steps", config.getPostOutageTmpCapSteps());
        payload.put("post_outage_tmp_max_start", config.getPostOutageTmpMaxStart());
        payload.put("post_outage_tmp_ramp", config.getPostOutageTmpRamp());
        payload.put("post_outage_tmp_stagger", config.getPostOutageTmpStagger());
        payload.put("price_aware_battery_enabled", config.getPriceAwareBatteryEnabled());
        payload.put("price_high_quantile", config.getPriceHighQuantile());
        payload.put("price_low_quantile", config.getPriceLowQuantile());
        payload.put("price_history_min_steps", config.getPriceHistoryMinSteps());
        payload.put("price_high_soc_threshold", config.getPriceHighSocThreshold());
        payload.put("price_high_forbid_charge", config.getPriceHighForbidCharge());
        payload.put("price_high_force_discharge", config.getPriceHighForceDischarge());
        payload.put("price_high_discharge_ele", config.getPriceHighDischargeEle());
        payload.put("price_min_reserve_soc", config.getPriceMinReserveSoc());
        payload.put("price_global_reserve_enabled", config.getPriceGlobalReserveEnabled());
        payload.put("price_low_target_soc", config.getPriceLowTargetSoc());
        payload.put("price_low_charge_ele", config.getPriceLowChargeEle());
        payload.put("price_low_search_boost", config.getPriceLowSearchBoost());
        payload.put("tau", config.getTau());
        payload.put("balance_type", config.getBalanceType());
        // 是否启用残差由入口脚本决定，不再读库中的 resmarl_enabled 开关
        payload.put(KEY_RESMARL_ENABLED, forResMarlEntry);
        payload.put(KEY_MARL_MODE, forResMarlEntry ? "multi_agent" : "none");
        payload.put(KEY_MULTI_AGENT_TRAIN_EPOCHS, getIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, DEFAULT_MULTI_AGENT_TRAIN_EPOCHS));
        payload.put(KEY_MULTI_AGENT_EXPLORE, getBoolConfig(KEY_MULTI_AGENT_EXPLORE, DEFAULT_MULTI_AGENT_EXPLORE));
        payload.put(KEY_MULTI_AGENT_CHECKPOINT, getStringConfig(KEY_MULTI_AGENT_CHECKPOINT, DEFAULT_MULTI_AGENT_CHECKPOINT));
        payload.put(KEY_RESIDUAL_ALPHA, getNumberConfig(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA));
        payload.put(KEY_RESIDUAL_ACTION_MASK, getJsonObjectConfig(KEY_RESIDUAL_ACTION_MASK, DEFAULT_RESIDUAL_ACTION_MASK));
        payload.put(KEY_RESMARL_AFTER_SAFETY, getBoolConfig(KEY_RESMARL_AFTER_SAFETY, DEFAULT_RESMARL_AFTER_SAFETY));
        payload.put(KEY_TRAIN_SCHEMA, getStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA));
        payload.put(KEY_MULTI_AGENT_EVAL_SCHEMA, getStringConfig(KEY_MULTI_AGENT_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        String chescaEvalSchema = getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA);
        String resmarlEvalSchema = getStringConfig(KEY_RESMARL_EVAL_SCHEMA, chescaEvalSchema);
        payload.put(KEY_RESMARL_EVAL_SCHEMA, resmarlEvalSchema);
        // CHESCA.py 读 eval_schema；ResMARL 入口写入残差页配置的评估集
        payload.put(KEY_EVAL_SCHEMA, forResMarlEntry ? resmarlEvalSchema : chescaEvalSchema);

        Path path = Paths.get(taskOutputDir, "chesca_agent_config.json");
        Files.createDirectories(path.getParent());
        Files.write(path, JSON.toJSONString(payload).getBytes(StandardCharsets.UTF_8));
        return path.toAbsolutePath().toString();
    }

    private void ensureDefaults() {
        if (algorithmConfigMapper.selectById(KEY_MIN_SOC_PER_HOUR) == null) {
            upsertJsonConfig(KEY_MIN_SOC_PER_HOUR, getDefaultMinSocPerHour(), "24小时电池SOC下限");
        }
        ensureScalarDefaults();
    }

    private void ensureScalarDefaults() {
        if (algorithmConfigMapper.selectById(KEY_MAX_SOC_NORMAL) == null) {
            upsertNumberConfig(KEY_MAX_SOC_NORMAL, DEFAULT_MAX_SOC_NORMAL, "正常时段电池SOC上限");
        }
        if (algorithmConfigMapper.selectById(KEY_MAX_SOC_OUTAGE) == null) {
            upsertNumberConfig(KEY_MAX_SOC_OUTAGE, DEFAULT_MAX_SOC_OUTAGE, "停电时段电池SOC上限");
        }
        if (algorithmConfigMapper.selectById(KEY_MAX_SOC_REDUCTION_IN_OUTAGE) == null) {
            upsertNumberConfig(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE, "停电时最大SOC降幅");
        }
        if (algorithmConfigMapper.selectById(KEY_B_LOW) == null) {
            upsertNumberConfig(KEY_B_LOW, DEFAULT_B_LOW, "负荷平衡增负荷阈值系数B_low");
        }
        if (algorithmConfigMapper.selectById(KEY_B_HIGH) == null) {
            upsertNumberConfig(KEY_B_HIGH, DEFAULT_B_HIGH, "负荷平衡减负荷阈值系数B_high");
        }
        if (algorithmConfigMapper.selectById(KEY_TMP_MAX_REDUCTION_PERCENT) == null) {
            upsertNumberConfig(KEY_TMP_MAX_REDUCTION_PERCENT, DEFAULT_TMP_MAX_REDUCTION_PERCENT, "冷机最大削减比例TMP_max_reduction_percent");
        }
        if (algorithmConfigMapper.selectById(KEY_MIN_COOL_PER_C_OVERHEAT) == null) {
            upsertNumberConfig(KEY_MIN_COOL_PER_C_OVERHEAT, DEFAULT_MIN_COOL_PER_C_OVERHEAT, "过热最小制冷系数min_cool_per_c_overheat");
        }
        if (algorithmConfigMapper.selectById(KEY_MIN_COOL_PER_C_OUTDOOR_GAP) == null) {
            upsertNumberConfig(KEY_MIN_COOL_PER_C_OUTDOOR_GAP, DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP, "室外开环保底系数min_cool_per_c_outdoor_gap");
        }
        if (algorithmConfigMapper.selectById(KEY_OUTDOOR_GAP_DEADBAND_C) == null) {
            upsertNumberConfig(KEY_OUTDOOR_GAP_DEADBAND_C, DEFAULT_OUTDOOR_GAP_DEADBAND_C, "室外保底死区outdoor_gap_deadband_c");
        }
        if (algorithmConfigMapper.selectById(KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C) == null) {
            upsertNumberConfig(KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C, DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C, "室外保底最大过热阈值outdoor_floor_max_overheat_c");
        }
        if (algorithmConfigMapper.selectById(KEY_COOLING_DEMAND_FEEDFORWARD_FRAC) == null) {
            upsertNumberConfig(KEY_COOLING_DEMAND_FEEDFORWARD_FRAC, DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC, "冷负荷前馈比例cooling_demand_feedforward_frac");
        }
        if (algorithmConfigMapper.selectById(KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT) == null) {
            upsertStringConfig(
                    KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT,
                    String.valueOf(DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT),
                    "冷负荷前馈仅过热时启用"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT) == null) {
            upsertStringConfig(
                    KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT,
                    String.valueOf(DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT),
                    "室外保底允许低于设定时启用"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT) == null) {
            upsertStringConfig(
                    KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT,
                    String.valueOf(DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT),
                    "低于设定时清掉开环保底"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_USE_LAGGED_DYNAMICS_INDOOR) == null) {
            upsertStringConfig(
                    KEY_USE_LAGGED_DYNAMICS_INDOOR,
                    String.valueOf(DEFAULT_USE_LAGGED_DYNAMICS_INDOOR),
                    "PID使用滞后动力学室温indoor[-2]"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER) == null) {
            upsertStringConfig(
                    KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER,
                    String.valueOf(DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER),
                    "仅当滞后室温更热时启用"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_LAGGED_INDOOR_HOTTER_MARGIN_C) == null) {
            upsertNumberConfig(KEY_LAGGED_INDOOR_HOTTER_MARGIN_C, DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C, "滞后室温更热裕度lagged_indoor_hotter_margin_c");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED,
                    String.valueOf(DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED),
                    "是否启用复电缓充"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_RELAX_STEPS) == null) {
            upsertIntConfig(KEY_POST_OUTAGE_RELAX_STEPS, DEFAULT_POST_OUTAGE_RELAX_STEPS, "复电缓充窗口步数");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_WAIVE_MIN_SOC) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_WAIVE_MIN_SOC,
                    String.valueOf(DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC),
                    "复电窗口豁免小时min_soc硬充"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_MAX_ELE_CHARGE) == null) {
            upsertNumberConfig(KEY_POST_OUTAGE_MAX_ELE_CHARGE, DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE, "复电窗口ELE充电上限");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT,
                    String.valueOf(DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT),
                    "复电窗口过热时禁止充电"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_OVERHEAT_C) == null) {
            upsertNumberConfig(KEY_POST_OUTAGE_OVERHEAT_C, DEFAULT_POST_OUTAGE_OVERHEAT_C, "复电缓充过热阈值");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_TMP_CAP_ENABLED) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_TMP_CAP_ENABLED,
                    String.valueOf(DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED),
                    "是否启用复电TMP帽/斜坡"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_TMP_CAP_STEPS) == null) {
            upsertIntConfig(KEY_POST_OUTAGE_TMP_CAP_STEPS, DEFAULT_POST_OUTAGE_TMP_CAP_STEPS, "复电TMP帽窗口步数");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_TMP_MAX_START) == null) {
            upsertNumberConfig(KEY_POST_OUTAGE_TMP_MAX_START, DEFAULT_POST_OUTAGE_TMP_MAX_START, "复电首步TMP上限");
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_TMP_RAMP) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_TMP_RAMP,
                    String.valueOf(DEFAULT_POST_OUTAGE_TMP_RAMP),
                    "复电TMP是否线性爬升"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_POST_OUTAGE_TMP_STAGGER) == null) {
            upsertStringConfig(
                    KEY_POST_OUTAGE_TMP_STAGGER,
                    String.valueOf(DEFAULT_POST_OUTAGE_TMP_STAGGER),
                    "复电TMP分栋错峰"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_AWARE_BATTERY_ENABLED) == null) {
            upsertStringConfig(
                    KEY_PRICE_AWARE_BATTERY_ENABLED,
                    String.valueOf(DEFAULT_PRICE_AWARE_BATTERY_ENABLED),
                    "是否启用电价感知电池"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HIGH_QUANTILE) == null) {
            upsertNumberConfig(KEY_PRICE_HIGH_QUANTILE, DEFAULT_PRICE_HIGH_QUANTILE, "高价分位数");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_LOW_QUANTILE) == null) {
            upsertNumberConfig(KEY_PRICE_LOW_QUANTILE, DEFAULT_PRICE_LOW_QUANTILE, "低价分位数");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HISTORY_MIN_STEPS) == null) {
            upsertIntConfig(KEY_PRICE_HISTORY_MIN_STEPS, DEFAULT_PRICE_HISTORY_MIN_STEPS, "电价历史最少样本步数");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HIGH_SOC_THRESHOLD) == null) {
            upsertNumberConfig(KEY_PRICE_HIGH_SOC_THRESHOLD, DEFAULT_PRICE_HIGH_SOC_THRESHOLD, "高价强制放电SOC阈值");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HIGH_FORBID_CHARGE) == null) {
            upsertStringConfig(
                    KEY_PRICE_HIGH_FORBID_CHARGE,
                    String.valueOf(DEFAULT_PRICE_HIGH_FORBID_CHARGE),
                    "高价禁止充电"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HIGH_FORCE_DISCHARGE) == null) {
            upsertStringConfig(
                    KEY_PRICE_HIGH_FORCE_DISCHARGE,
                    String.valueOf(DEFAULT_PRICE_HIGH_FORCE_DISCHARGE),
                    "高价高SOC强制放电"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_HIGH_DISCHARGE_ELE) == null) {
            upsertNumberConfig(KEY_PRICE_HIGH_DISCHARGE_ELE, DEFAULT_PRICE_HIGH_DISCHARGE_ELE, "高价强制放电ELE幅度");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_MIN_RESERVE_SOC) == null) {
            upsertNumberConfig(KEY_PRICE_MIN_RESERVE_SOC, DEFAULT_PRICE_MIN_RESERVE_SOC, "高价放电韧性地板SOC");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_GLOBAL_RESERVE_ENABLED) == null) {
            upsertStringConfig(
                    KEY_PRICE_GLOBAL_RESERVE_ENABLED,
                    String.valueOf(DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED),
                    "全局韧性地板（非停电放电不可击穿）"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_LOW_TARGET_SOC) == null) {
            upsertNumberConfig(KEY_PRICE_LOW_TARGET_SOC, DEFAULT_PRICE_LOW_TARGET_SOC, "低价补电目标SOC");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_LOW_CHARGE_ELE) == null) {
            upsertNumberConfig(KEY_PRICE_LOW_CHARGE_ELE, DEFAULT_PRICE_LOW_CHARGE_ELE, "低价补电ELE幅度");
        }
        if (algorithmConfigMapper.selectById(KEY_PRICE_LOW_SEARCH_BOOST) == null) {
            upsertStringConfig(
                    KEY_PRICE_LOW_SEARCH_BOOST,
                    String.valueOf(DEFAULT_PRICE_LOW_SEARCH_BOOST),
                    "低价树搜索抬高SOC下限促补电"
            );
        }
        if (algorithmConfigMapper.selectById(KEY_TAU) == null) {
            upsertIntConfig(KEY_TAU, DEFAULT_TAU, "预测优化步长tau");
        }
        if (algorithmConfigMapper.selectById(KEY_BALANCE_TYPE) == null) {
            upsertStringConfig(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE, "电池树搜索适应度类型balance_type");
        }
        if (algorithmConfigMapper.selectById(KEY_RESMARL_ENABLED) == null) {
            upsertStringConfig(KEY_RESMARL_ENABLED, String.valueOf(DEFAULT_RESMARL_ENABLED), "兼容字段：是否残差由入口脚本决定");
        }
        if (algorithmConfigMapper.selectById(KEY_MARL_MODE) == null) {
            upsertStringConfig(KEY_MARL_MODE, DEFAULT_MARL_MODE, "MARL 模式：none / multi_agent");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_TRAIN_EPOCHS) == null) {
            upsertIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, 0, "Multi-Agent SAC 训练轮数（仅 Multi-agent.py；评估侧已废弃）");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_EXPLORE) == null) {
            upsertStringConfig(KEY_MULTI_AGENT_EXPLORE, String.valueOf(DEFAULT_MULTI_AGENT_EXPLORE), "Multi-Agent 评估时是否开启 explore");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_CHECKPOINT) == null) {
            upsertStringConfig(KEY_MULTI_AGENT_CHECKPOINT, DEFAULT_MULTI_AGENT_CHECKPOINT, "预存 Multi-Agent SAC checkpoint（启用 ResMARL 时必填）");
        }
        if (algorithmConfigMapper.selectById(KEY_RESIDUAL_ALPHA) == null) {
            upsertNumberConfig(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA, "CHESCA-ResMARL 残差强度α∈[0,1]");
        }
        if (algorithmConfigMapper.selectById(KEY_RESIDUAL_ACTION_MASK) == null) {
            upsertConfig(KEY_RESIDUAL_ACTION_MASK, DEFAULT_RESIDUAL_ACTION_MASK, "json", "CHESCA-ResMARL 可修正动作维 mask");
        }
        if (algorithmConfigMapper.selectById(KEY_RESMARL_AFTER_SAFETY) == null) {
            upsertStringConfig(KEY_RESMARL_AFTER_SAFETY, String.valueOf(DEFAULT_RESMARL_AFTER_SAFETY), "残差是否在安全审查之后施加");
        }
        if (algorithmConfigMapper.selectById(KEY_SCHEMA_SPLIT_ENABLED) == null) {
            upsertStringConfig(KEY_SCHEMA_SPLIT_ENABLED, "true", "Multi-agent 训测 schema 是否分离（界面配置）");
        }
        if (algorithmConfigMapper.selectById(KEY_TRAIN_SCHEMA) == null) {
            upsertStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA, "Multi-agent.py 训练 schema");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_EVAL_SCHEMA) == null) {
            upsertStringConfig(KEY_MULTI_AGENT_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA, "Multi-agent.py 评估 schema");
        }
        if (algorithmConfigMapper.selectById(KEY_EVAL_SCHEMA) == null) {
            upsertStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA, "CHESCA 仿真/KPI 评估 schema");
        }
        if (algorithmConfigMapper.selectById(KEY_RESMARL_EVAL_SCHEMA) == null) {
            upsertStringConfig(
                    KEY_RESMARL_EVAL_SCHEMA,
                    getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA),
                    "CHESCA_ResMARL.py 仿真/KPI 评估 schema");
        }
    }

    private Map<String, Double> readMinSocJsonConfig() {
        AlgorithmConfig row = algorithmConfigMapper.selectById(KEY_MIN_SOC_PER_HOUR);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return null;
        }
        Map<String, Double> parsed = JSON.parseObject(row.getConfigValue(), new TypeReference<Map<String, Double>>() {});
        return parsed == null ? null : normalizeMinSocMap(parsed);
    }

    private Map<String, Double> normalizeMinSocMap(Map<String, Double> source) {
        Map<String, Double> result = new LinkedHashMap<>();
        for (int h = 0; h < 24; h++) {
            result.put(String.valueOf(h), DEFAULT_MIN_SOC[h]);
        }
        if (source != null) {
            for (Map.Entry<String, Double> entry : source.entrySet()) {
                try {
                    int hour = Integer.parseInt(entry.getKey());
                    if (hour >= 0 && hour < 24 && entry.getValue() != null) {
                        result.put(String.valueOf(hour), entry.getValue());
                    }
                } catch (NumberFormatException ignored) {
                    // skip invalid key
                }
            }
        }
        return result;
    }

    private double getNumberConfig(String key, double defaultValue) {
        AlgorithmConfig row = algorithmConfigMapper.selectById(key);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return defaultValue;
        }
        try {
            return Double.parseDouble(row.getConfigValue());
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    private String getStringConfig(String key, String defaultValue) {
        AlgorithmConfig row = algorithmConfigMapper.selectById(key);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return defaultValue;
        }
        return row.getConfigValue().trim();
    }

    private boolean getBoolConfig(String key, boolean defaultValue) {
        AlgorithmConfig row = algorithmConfigMapper.selectById(key);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return defaultValue;
        }
        String v = row.getConfigValue().trim().toLowerCase();
        if ("1".equals(v) || "true".equals(v) || "yes".equals(v) || "on".equals(v)) {
            return true;
        }
        if ("0".equals(v) || "false".equals(v) || "no".equals(v) || "off".equals(v)) {
            return false;
        }
        return defaultValue;
    }

    private Object getJsonObjectConfig(String key, String defaultJson) {
        AlgorithmConfig row = algorithmConfigMapper.selectById(key);
        String raw = (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty())
                ? defaultJson
                : row.getConfigValue();
        try {
            return JSON.parse(raw);
        } catch (Exception e) {
            return JSON.parse(defaultJson);
        }
    }

    private int getIntConfig(String key, int defaultValue) {
        AlgorithmConfig row = algorithmConfigMapper.selectById(key);
        if (row == null || row.getConfigValue() == null || row.getConfigValue().isEmpty()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(row.getConfigValue().trim());
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    private void saveSocRatioConfig(String key, Double value, String description) {
        if (value == null) {
            throw new RuntimeException("缺少配置项: " + key);
        }
        if (value < 0 || value > 1) {
            throw new RuntimeException(key + " 须在 0~1 之间");
        }
        upsertNumberConfig(key, value, description);
    }

    private void saveThresholdConfig(String key, Double value, String description) {
        if (value == null) {
            throw new RuntimeException("缺少配置项: " + key);
        }
        if (value <= 0 || value > 20) {
            throw new RuntimeException(key + " 须在 (0, 20] 之间");
        }
        upsertNumberConfig(key, value, description);
    }

    private void saveNonNegConfig(String key, Double value, double maxValue, String description) {
        if (value == null) {
            throw new RuntimeException("缺少配置项: " + key);
        }
        if (value < 0 || value > maxValue) {
            throw new RuntimeException(key + " 须在 [0, " + maxValue + "] 之间");
        }
        upsertNumberConfig(key, value, description);
    }

    private void saveTauConfig(Integer tau) {
        if (tau == null) {
            throw new RuntimeException("缺少配置项: " + KEY_TAU);
        }
        if (tau < 1 || tau > 3) {
            throw new RuntimeException(KEY_TAU + " 须为 1、2 或 3");
        }
        upsertIntConfig(KEY_TAU, tau, "预测优化步长tau");
    }

    private void saveBalanceTypeConfig(String balanceType) {
        if (balanceType == null || balanceType.isEmpty()) {
            throw new RuntimeException("缺少配置项: " + KEY_BALANCE_TYPE);
        }
        String normalized = balanceType.trim().toUpperCase();
        if (!"A".equals(normalized) && !"B".equals(normalized) && !"C".equals(normalized)) {
            throw new RuntimeException(KEY_BALANCE_TYPE + " 须为 A、B 或 C");
        }
        upsertStringConfig(KEY_BALANCE_TYPE, normalized, "电池树搜索适应度类型balance_type");
    }

    private void upsertNumberConfig(String key, double value, String description) {
        upsertConfig(key, String.valueOf(value), "number", description);
    }

    private void upsertIntConfig(String key, int value, String description) {
        upsertConfig(key, String.valueOf(value), "number", description);
    }

    private void upsertStringConfig(String key, String value, String description) {
        upsertConfig(key, value, "string", description);
    }

    private void upsertJsonConfig(String key, Map<String, Double> value, String description) {
        upsertConfig(key, JSON.toJSONString(value), "json", description);
    }

    private void upsertConfig(String key, String value, String valueType, String description) {
        Date now = new Date();
        AlgorithmConfig existing = algorithmConfigMapper.selectById(key);
        if (existing != null) {
            existing.setConfigValue(value);
            existing.setValueType(valueType);
            existing.setDescription(description);
            existing.setUpdateTime(now);
            algorithmConfigMapper.updateById(existing);
        } else {
            AlgorithmConfig row = new AlgorithmConfig();
            row.setConfigKey(key);
            row.setConfigValue(value);
            row.setValueType(valueType);
            row.setDescription(description);
            row.setUpdateTime(now);
            algorithmConfigMapper.insert(row);
        }
    }
}
