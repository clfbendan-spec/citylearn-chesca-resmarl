package com.citylearn.common;

/**
 * CHESCA 电池/削峰/电价配置项的出厂默认值。
 *
 * <p>从 {@code service/BatteryMinSocConfigService} 抽出，与 {@link ChescaConfigKeys} 一一对应
 * （{@code KEY_X} ↔ {@code DEFAULT_X}）。改这里会改变「首次建行」和「字段缺省回填」的结果，
 * 属于会影响仿真行为的改动，需重新跑 KPI 回归。</p>
 */
public final class ChescaConfigDefaults {

    private ChescaConfigDefaults() {
    }

    public static final double DEFAULT_MAX_SOC_NORMAL = 0.99;
    public static final double DEFAULT_MAX_SOC_OUTAGE = 0.87;
    public static final double DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE = 0.70;
    public static final double DEFAULT_B_LOW = 1.18;
    public static final double DEFAULT_B_HIGH = 1.0;
    public static final double DEFAULT_TMP_MAX_REDUCTION_PERCENT = 0.0;
    public static final double DEFAULT_MIN_COOL_PER_C_OVERHEAT = 0.12;
    public static final double DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP = 0.03;
    public static final double DEFAULT_OUTDOOR_GAP_DEADBAND_C = 5.0;
    public static final double DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C = 0.5;
    public static final double DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC = 0.10;
    public static final boolean DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT = false;
    public static final boolean DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT = true;
    public static final boolean DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT = false;
    public static final boolean DEFAULT_USE_LAGGED_DYNAMICS_INDOOR = true;
    public static final boolean DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER = false;
    public static final double DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C = 0.3;
    public static final boolean DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED = true;
    public static final int DEFAULT_POST_OUTAGE_RELAX_STEPS = 4;
    public static final boolean DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC = true;
    public static final double DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE = 0.15;
    public static final boolean DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT = true;
    public static final double DEFAULT_POST_OUTAGE_OVERHEAT_C = 0.5;
    public static final boolean DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED = true;
    public static final int DEFAULT_POST_OUTAGE_TMP_CAP_STEPS = 4;
    public static final double DEFAULT_POST_OUTAGE_TMP_MAX_START = 0.40;
    public static final boolean DEFAULT_POST_OUTAGE_TMP_RAMP = true;
    public static final boolean DEFAULT_POST_OUTAGE_TMP_STAGGER = true;
    public static final boolean DEFAULT_PRICE_AWARE_BATTERY_ENABLED = true;
    public static final double DEFAULT_PRICE_HIGH_QUANTILE = 0.75;
    public static final double DEFAULT_PRICE_LOW_QUANTILE = 0.25;
    public static final int DEFAULT_PRICE_HISTORY_MIN_STEPS = 48;
    public static final double DEFAULT_PRICE_HIGH_SOC_THRESHOLD = 0.70;
    public static final boolean DEFAULT_PRICE_HIGH_FORBID_CHARGE = true;
    public static final boolean DEFAULT_PRICE_HIGH_FORCE_DISCHARGE = true;
    public static final double DEFAULT_PRICE_HIGH_DISCHARGE_ELE = 0.15;
    public static final double DEFAULT_PRICE_MIN_RESERVE_SOC = 0.55;
    public static final boolean DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED = true;
    public static final double DEFAULT_PRICE_LOW_TARGET_SOC = 0.80;
    public static final double DEFAULT_PRICE_LOW_CHARGE_ELE = 0.25;
    public static final boolean DEFAULT_PRICE_LOW_SEARCH_BOOST = true;

    // P0-2：价格分位退化门控，默认关（零侵入）
    public static final boolean DEFAULT_PRICE_BAND_TIE_STRICT = false;
    public static final int DEFAULT_TAU = 1;
    public static final String DEFAULT_BALANCE_TYPE = "C";
    public static final boolean DEFAULT_RESMARL_ENABLED = true;
    public static final String DEFAULT_MARL_MODE = "none";
    public static final int DEFAULT_MULTI_AGENT_TRAIN_EPOCHS = 20;
    public static final boolean DEFAULT_MULTI_AGENT_EXPLORE = false;
    public static final String DEFAULT_MULTI_AGENT_CHECKPOINT = "";
    public static final double DEFAULT_RESIDUAL_ALPHA = 0.0;
    public static final String DEFAULT_RESIDUAL_ACTION_MASK = "{\"dhw\":false,\"ele\":true,\"tmp\":false}";

    /** 2026-10-09：默认值与 Python 侧（utils/ches_config.py 的 DEFAULTS / argparse）对齐为 false */
    public static final boolean DEFAULT_RESMARL_AFTER_SAFETY = false;
    public static final boolean DEFAULT_SCHEMA_SPLIT_ENABLED = true;
    public static final String DEFAULT_TRAIN_SCHEMA = "citylearn_challenge_2023_phase_2_local_evaluation";
    public static final String DEFAULT_EVAL_SCHEMA = "citylearn_challenge_2023_phase_2_online_evaluation_1";

    // ---- 片区尖峰削峰「结构层」默认值（逐字对齐 checa/agent.py default_params）----
    public static final String DEFAULT_PEAK_TRIGGER_MODE = "net";
    public static final double DEFAULT_NS_SPIKE_MULT = 3.0;
    public static final int DEFAULT_REBOUND_WINDOW = 0;
    public static final double DEFAULT_REBOUND_CAP = 1.0;
    public static final boolean DEFAULT_PEAK_BATTERY_DISCHARGE_ENABLED = false;
    public static final double DEFAULT_PEAK_BATTERY_DISCHARGE_ELE = -1.0;
    public static final boolean DEFAULT_PEAK_CUT_GRADED_ENABLED = false;
    public static final double DEFAULT_PEAK_CUT_GRADED_M_LO = 5.0;
    public static final double DEFAULT_PEAK_CUT_GRADED_M_HI = 6.0;

    // 环境层「DHW 储能修复」默认关 ⇒ 逐位等于上游 CityLearn
    public static final boolean DEFAULT_DHW_STORAGE_FIX = false;
}
