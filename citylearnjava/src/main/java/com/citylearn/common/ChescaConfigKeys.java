package com.citylearn.common;

/**
 * CHESCA 电池/削峰/电价配置项的落库键（{@code algorithm_config} 表的 id 列）。
 *
 * <p>从 {@code service/BatteryMinSocConfigService} 抽出：键名是对外契约（数据库里就是这些字符串，
 * Python 侧 {@code checa/agent.py} 也按同名读取），与配置读写逻辑无关，因此独立成常量类。</p>
 *
 * <p>⚠️ 改这里的值等于改数据库键，必须同时改库与 Python 侧，否则脚本静默取不到配置。</p>
 */
public final class ChescaConfigKeys {

    private ChescaConfigKeys() {
    }

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

    // P0-2：价格分位退化门控（默认 false ⇒ 逐位等于旧行为）
    public static final String KEY_PRICE_BAND_TIE_STRICT = "price_band_tie_strict";
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

    // ---- 片区尖峰削峰「结构层」（2026-10-11 P2 接入；与 checa/agent.py default_params 同源）----
    /** 削峰触发信号口径：net / ns_spike / district_spike */
    public static final String KEY_PEAK_TRIGGER_MODE = "peak_trigger_mode";

    /** 尖峰判据倍数（实测不可调负荷 > 该倍数 × 历史均值即触发） */
    public static final String KEY_NS_SPIKE_MULT = "ns_spike_mult";

    /** 削峰后回弹抑制窗口步数（0 = 关闭） */
    public static final String KEY_REBOUND_WINDOW = "rebound_window";

    /** 回弹窗口内制冷动作限幅系数（1.0 = 不限） */
    public static final String KEY_REBOUND_CAP = "rebound_cap";

    /** 触发步是否把各楼电池拉到最大放电 */
    public static final String KEY_PEAK_BATTERY_DISCHARGE_ENABLED = "peak_battery_discharge_enabled";

    /** 触发步电池 ELE 动作幅度（-1 = 单步最大放电） */
    public static final String KEY_PEAK_BATTERY_DISCHARGE_ELE = "peak_battery_discharge_ele";

    /** 是否用分级削峰替代 0/1 硬削 */
    public static final String KEY_PEAK_CUT_GRADED_ENABLED = "peak_cut_graded_enabled";

    /** 分级带宽下沿（r ≤ m_lo 不削） */
    public static final String KEY_PEAK_CUT_GRADED_M_LO = "peak_cut_graded_m_lo";

    /** 分级带宽上沿（r ≥ m_hi 满削，电池同此门槛满放） */
    public static final String KEY_PEAK_CUT_GRADED_M_HI = "peak_cut_graded_m_hi";

    // ---- 环境层「DHW 储能修复」开关（2026-10-15）----
    /** 是否修复上游 DHW 储能 bug（默认 false ⇒ 逐位等于上游 CityLearn） */
    public static final String KEY_DHW_STORAGE_FIX = "dhw_storage_fix";
}
