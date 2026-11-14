package com.citylearn.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.TypeReference;
import com.citylearn.dao.AlgorithmConfigMapper;
import com.citylearn.entity.AlgorithmConfig;
import com.citylearn.vo.ChescaBatteryConfigVO;
import com.citylearn.vo.ResMarlConfigVO;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.lang.reflect.Modifier;
import java.lang.reflect.Field;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;

import static com.citylearn.common.ChescaConfigDefaults.*;
import static com.citylearn.common.ChescaConfigKeys.*;

@Service
public class BatteryMinSocConfigService {


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
        vo.setPriceBandTieStrict(getBoolConfig(KEY_PRICE_BAND_TIE_STRICT, DEFAULT_PRICE_BAND_TIE_STRICT));
        vo.setTau(getIntConfig(KEY_TAU, DEFAULT_TAU));
        vo.setBalanceType(getStringConfig(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE));
        vo.setEvalSchema(getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        // 片区尖峰削峰「结构层」（2026-10-11 P2）
        vo.setPeakTriggerMode(getStringConfig(KEY_PEAK_TRIGGER_MODE, DEFAULT_PEAK_TRIGGER_MODE));
        vo.setNsSpikeMult(getNumberConfig(KEY_NS_SPIKE_MULT, DEFAULT_NS_SPIKE_MULT));
        vo.setReboundWindow(getIntConfig(KEY_REBOUND_WINDOW, DEFAULT_REBOUND_WINDOW));
        vo.setReboundCap(getNumberConfig(KEY_REBOUND_CAP, DEFAULT_REBOUND_CAP));
        vo.setPeakBatteryDischargeEnabled(getBoolConfig(KEY_PEAK_BATTERY_DISCHARGE_ENABLED, DEFAULT_PEAK_BATTERY_DISCHARGE_ENABLED));
        vo.setPeakBatteryDischargeEle(getNumberConfig(KEY_PEAK_BATTERY_DISCHARGE_ELE, DEFAULT_PEAK_BATTERY_DISCHARGE_ELE));
        vo.setPeakCutGradedEnabled(getBoolConfig(KEY_PEAK_CUT_GRADED_ENABLED, DEFAULT_PEAK_CUT_GRADED_ENABLED));
        vo.setPeakCutGradedMLo(getNumberConfig(KEY_PEAK_CUT_GRADED_M_LO, DEFAULT_PEAK_CUT_GRADED_M_LO));
        vo.setPeakCutGradedMHi(getNumberConfig(KEY_PEAK_CUT_GRADED_M_HI, DEFAULT_PEAK_CUT_GRADED_M_HI));
        return vo;
    }

    public Map<String, Double> getMinSocPerHour() {
        Map<String, Double> fromConfig = readMinSocJsonConfig();
        if (fromConfig != null && !fromConfig.isEmpty()) {
            return normalizeMinSocMap(fromConfig);
        }
        return getDefaultMinSocPerHour();
    }

    /**
     * 缺省值回填：VO 的任何字段未传（null）、空串、空 Map，一律回落到<b>当前生效值</b>。
     *
     * <p>用反射遍历字段而不是逐个 if，是因为存量代码里那 45 个显式 if 漏掉了削峰那批
     * 9 个字段（peak_trigger_mode / ns_spike_mult / rebound_window / rebound_cap /
     * peak_battery_discharge_* / peak_cut_graded_*），而它们的 writer 对 null 直接抛
     * 「缺少配置项」——前端漏传即 500。逐字段手写必然再次漏，所以改成结构性保证。</p>
     *
     * <p>回填源用 {@link #getConfig()}（库里现值）而不是出厂默认值，
     * 这样「未传」= 保持不变；若用出厂值，一次漏传就会把用户改过的其它配置悄悄重置。</p>
     */
    private void fillMissingWithDefaults(ChescaBatteryConfigVO config) {
        ChescaBatteryConfigVO defaults = getConfig();
        for (Field field : ChescaBatteryConfigVO.class.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers())) {
                continue;
            }
            try {
                field.setAccessible(true);
                Object current = field.get(config);
                boolean absent = current == null
                        || (current instanceof String && ((String) current).trim().isEmpty())
                        || (current instanceof Map && ((Map<?, ?>) current).isEmpty());
                if (absent) {
                    field.set(config, field.get(defaults));
                }
            } catch (IllegalAccessException e) {
                throw new IllegalStateException("配置缺省值回填失败: " + field.getName(), e);
            }
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void saveConfig(ChescaBatteryConfigVO config) {
        if (config == null) {
            throw new RuntimeException("配置不能为空");
        }
        // 未传（null / 空串 / 空 Map）的字段一律回落到默认值：全字段可选。
        fillMissingWithDefaults(config);
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
        upsertStringConfig(
                KEY_PRICE_BAND_TIE_STRICT,
                String.valueOf(Boolean.TRUE.equals(config.getPriceBandTieStrict())),
                "价格分位并列时按退化处理（关闭 = 旧行为）"
        );
        saveTauConfig(config.getTau());
        saveBalanceTypeConfig(config.getBalanceType());
        String evalSchema = config.getEvalSchema() == null ? "" : config.getEvalSchema().trim();
        if (evalSchema.isEmpty()) {
            evalSchema = DEFAULT_EVAL_SCHEMA;
        }
        upsertStringConfig(KEY_EVAL_SCHEMA, evalSchema, "CHESCA 仿真/KPI 评估 schema");
        // 片区尖峰削峰「结构层」（2026-10-11 P2）
        savePeakTriggerModeConfig(config.getPeakTriggerMode());
        saveNonNegConfig(KEY_NS_SPIKE_MULT, config.getNsSpikeMult(), 20.0, "尖峰判据倍数ns_spike_mult");
        saveReboundWindowConfig(config.getReboundWindow());
        saveNonNegConfig(KEY_REBOUND_CAP, config.getReboundCap(), 2.0, "回弹限幅系数rebound_cap");
        upsertStringConfig(
                KEY_PEAK_BATTERY_DISCHARGE_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPeakBatteryDischargeEnabled())),
                "触发步电池满放peak_battery_discharge_enabled"
        );
        saveSignedUnitConfig(KEY_PEAK_BATTERY_DISCHARGE_ELE, config.getPeakBatteryDischargeEle(),
                "满放ELE幅度peak_battery_discharge_ele");
        upsertStringConfig(
                KEY_PEAK_CUT_GRADED_ENABLED,
                String.valueOf(Boolean.TRUE.equals(config.getPeakCutGradedEnabled())),
                "分级削峰开关peak_cut_graded_enabled"
        );
        saveNonNegConfig(KEY_PEAK_CUT_GRADED_M_LO, config.getPeakCutGradedMLo(), 20.0, "分级带宽下沿peak_cut_graded_m_lo");
        saveNonNegConfig(KEY_PEAK_CUT_GRADED_M_HI, config.getPeakCutGradedMHi(), 20.0, "分级带宽上沿peak_cut_graded_m_hi");
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
        payload.put("price_band_tie_strict", config.getPriceBandTieStrict());
        payload.put("tau", config.getTau());
        payload.put("balance_type", config.getBalanceType());
        // 片区尖峰削峰「结构层」（2026-10-11 P2）：键名 = checa/agent.py 的 params 键名
        payload.put(KEY_PEAK_TRIGGER_MODE, config.getPeakTriggerMode());
        payload.put(KEY_NS_SPIKE_MULT, config.getNsSpikeMult());
        payload.put(KEY_REBOUND_WINDOW, config.getReboundWindow());
        payload.put(KEY_REBOUND_CAP, config.getReboundCap());
        payload.put(KEY_PEAK_BATTERY_DISCHARGE_ENABLED, config.getPeakBatteryDischargeEnabled());
        payload.put(KEY_PEAK_BATTERY_DISCHARGE_ELE, config.getPeakBatteryDischargeEle());
        payload.put(KEY_PEAK_CUT_GRADED_ENABLED, config.getPeakCutGradedEnabled());
        payload.put(KEY_PEAK_CUT_GRADED_M_LO, config.getPeakCutGradedMLo());
        payload.put(KEY_PEAK_CUT_GRADED_M_HI, config.getPeakCutGradedMHi());
        // 环境层「DHW 储能修复」开关（2026-10-15）：默认 false ⇒ 逐位等于上游 CityLearn。
        // 打开时 CHESCA.py / CHESCA_ResMARL.py 在环境构造前设 CITYLEARN_DHW_STORAGE_FIX=1。
        payload.put(KEY_DHW_STORAGE_FIX, getBoolConfig(KEY_DHW_STORAGE_FIX, DEFAULT_DHW_STORAGE_FIX));
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

    /**
     * 「首次建行」用的配置项清单：{@code key} / 落库类型 / 默认值 / 中文说明。
     *
     * <p>本方法原先是 285 行的手写 if——同一个配置项的 key、默认值、中文名在
     * {@code ensureScalarDefaults} / {@code getConfig} / {@code saveConfig} 三处各写一遍
     * （原先还有 {@code getDefaultConfig}，2026-10-20 随隐藏页一并删除），
     * 加一个参数要改 6~7 个地方，漏一处就是
     * 「写时对不上读」的静默错。收敛成一张表后，建行只遍历这张表。</p>
     */
    private void ensureScalarDefaults() {
        for (Spec spec : SCALAR_SPECS) {
            if (algorithmConfigMapper.selectById(spec.key) == null) {
                upsertConfig(spec.key, spec.value.apply(this), spec.type, spec.cn);
            }
        }
    }

    /** 一条配置项的建行元数据。{@code value} 用函数而非常量，是为兼容依赖其它配置项的项。 */
    private static final class Spec {
        final String key;
        final String type;
        final String cn;
        final java.util.function.Function<BatteryMinSocConfigService, String> value;

        private Spec(String key, String type, String cn,
                     java.util.function.Function<BatteryMinSocConfigService, String> value) {
            this.key = key;
            this.type = type;
            this.cn = cn;
            this.value = value;
        }

        static Spec num(String key, double v, String cn) {
            return new Spec(key, "number", cn, svc -> String.valueOf(v));
        }

        static Spec integer(String key, int v, String cn) {
            // ⚠️ 落库类型是 "number" 而不是 "int"：原 upsertIntConfig 一直写 number，
            // 库里 70 行也确实全是 number。改成 int 会让 Python 侧按 number 解析时对不上。
            return new Spec(key, "number", cn, svc -> String.valueOf(v));
        }

        static Spec bool(String key, boolean v, String cn) {
            return new Spec(key, "string", cn, svc -> String.valueOf(v));
        }

        static Spec str(String key, String v, String cn) {
            return new Spec(key, "string", cn, svc -> v);
        }

        static Spec raw(String key, String type, String v, String cn) {
            return new Spec(key, type, cn, svc -> v);
        }

        static Spec of(String key, String type,
                       java.util.function.Function<BatteryMinSocConfigService, String> f, String cn) {
            return new Spec(key, type, cn, f);
        }
    }

    private static final java.util.List<Spec> SCALAR_SPECS = buildScalarSpecs();

    private static java.util.List<Spec> buildScalarSpecs() {
        java.util.List<Spec> s = new java.util.ArrayList<>();
        s.add(Spec.num(KEY_MAX_SOC_NORMAL, DEFAULT_MAX_SOC_NORMAL, "正常时段电池SOC上限"));
        s.add(Spec.num(KEY_MAX_SOC_OUTAGE, DEFAULT_MAX_SOC_OUTAGE, "停电时段电池SOC上限"));
        s.add(Spec.num(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE, "停电时最大SOC降幅"));
        s.add(Spec.num(KEY_B_LOW, DEFAULT_B_LOW, "负荷平衡增负荷阈值系数B_low"));
        s.add(Spec.num(KEY_B_HIGH, DEFAULT_B_HIGH, "负荷平衡减负荷阈值系数B_high"));
        s.add(Spec.num(KEY_TMP_MAX_REDUCTION_PERCENT, DEFAULT_TMP_MAX_REDUCTION_PERCENT, "冷机最大削减比例TMP_max_reduction_percent"));
        s.add(Spec.num(KEY_MIN_COOL_PER_C_OVERHEAT, DEFAULT_MIN_COOL_PER_C_OVERHEAT, "过热最小制冷系数min_cool_per_c_overheat"));
        s.add(Spec.num(KEY_MIN_COOL_PER_C_OUTDOOR_GAP, DEFAULT_MIN_COOL_PER_C_OUTDOOR_GAP, "室外开环保底系数min_cool_per_c_outdoor_gap"));
        s.add(Spec.num(KEY_OUTDOOR_GAP_DEADBAND_C, DEFAULT_OUTDOOR_GAP_DEADBAND_C, "室外保底死区outdoor_gap_deadband_c"));
        s.add(Spec.num(KEY_OUTDOOR_FLOOR_MAX_OVERHEAT_C, DEFAULT_OUTDOOR_FLOOR_MAX_OVERHEAT_C, "室外保底最大过热阈值outdoor_floor_max_overheat_c"));
        s.add(Spec.num(KEY_COOLING_DEMAND_FEEDFORWARD_FRAC, DEFAULT_COOLING_DEMAND_FEEDFORWARD_FRAC, "冷负荷前馈比例cooling_demand_feedforward_frac"));
        s.add(Spec.bool(KEY_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT, DEFAULT_DEMAND_FEEDFORWARD_ONLY_WHEN_OVERHEAT, "冷负荷前馈仅过热时启用"));
        s.add(Spec.bool(KEY_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT, DEFAULT_OUTDOOR_FLOOR_ALLOW_WHEN_UNDER_SETPOINT, "室外保底允许低于设定时启用"));
        s.add(Spec.bool(KEY_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT, DEFAULT_CLEAR_OPEN_LOOP_FLOOR_WHEN_UNDER_SETPOINT, "低于设定时清掉开环保底"));
        s.add(Spec.bool(KEY_USE_LAGGED_DYNAMICS_INDOOR, DEFAULT_USE_LAGGED_DYNAMICS_INDOOR, "PID使用滞后动力学室温indoor[-2]"));
        s.add(Spec.bool(KEY_LAGGED_INDOOR_ONLY_WHEN_HOTTER, DEFAULT_LAGGED_INDOOR_ONLY_WHEN_HOTTER, "仅当滞后室温更热时启用"));
        s.add(Spec.num(KEY_LAGGED_INDOOR_HOTTER_MARGIN_C, DEFAULT_LAGGED_INDOOR_HOTTER_MARGIN_C, "滞后室温更热裕度lagged_indoor_hotter_margin_c"));
        s.add(Spec.bool(KEY_POST_OUTAGE_SOFT_CHARGE_ENABLED, DEFAULT_POST_OUTAGE_SOFT_CHARGE_ENABLED, "是否启用复电缓充"));
        s.add(Spec.integer(KEY_POST_OUTAGE_RELAX_STEPS, DEFAULT_POST_OUTAGE_RELAX_STEPS, "复电缓充窗口步数"));
        s.add(Spec.bool(KEY_POST_OUTAGE_WAIVE_MIN_SOC, DEFAULT_POST_OUTAGE_WAIVE_MIN_SOC, "复电窗口豁免小时min_soc硬充"));
        s.add(Spec.num(KEY_POST_OUTAGE_MAX_ELE_CHARGE, DEFAULT_POST_OUTAGE_MAX_ELE_CHARGE, "复电窗口ELE充电上限"));
        s.add(Spec.bool(KEY_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT, DEFAULT_POST_OUTAGE_FORBID_CHARGE_WHEN_OVERHEAT, "复电窗口过热时禁止充电"));
        s.add(Spec.num(KEY_POST_OUTAGE_OVERHEAT_C, DEFAULT_POST_OUTAGE_OVERHEAT_C, "复电缓充过热阈值"));
        s.add(Spec.bool(KEY_POST_OUTAGE_TMP_CAP_ENABLED, DEFAULT_POST_OUTAGE_TMP_CAP_ENABLED, "是否启用复电TMP帽/斜坡"));
        s.add(Spec.integer(KEY_POST_OUTAGE_TMP_CAP_STEPS, DEFAULT_POST_OUTAGE_TMP_CAP_STEPS, "复电TMP帽窗口步数"));
        s.add(Spec.num(KEY_POST_OUTAGE_TMP_MAX_START, DEFAULT_POST_OUTAGE_TMP_MAX_START, "复电首步TMP上限"));
        s.add(Spec.bool(KEY_POST_OUTAGE_TMP_RAMP, DEFAULT_POST_OUTAGE_TMP_RAMP, "复电TMP是否线性爬升"));
        s.add(Spec.bool(KEY_POST_OUTAGE_TMP_STAGGER, DEFAULT_POST_OUTAGE_TMP_STAGGER, "复电TMP分栋错峰"));
        s.add(Spec.bool(KEY_PRICE_AWARE_BATTERY_ENABLED, DEFAULT_PRICE_AWARE_BATTERY_ENABLED, "是否启用电价感知电池"));
        s.add(Spec.num(KEY_PRICE_HIGH_QUANTILE, DEFAULT_PRICE_HIGH_QUANTILE, "高价分位数"));
        s.add(Spec.num(KEY_PRICE_LOW_QUANTILE, DEFAULT_PRICE_LOW_QUANTILE, "低价分位数"));
        s.add(Spec.integer(KEY_PRICE_HISTORY_MIN_STEPS, DEFAULT_PRICE_HISTORY_MIN_STEPS, "电价历史最少样本步数"));
        s.add(Spec.num(KEY_PRICE_HIGH_SOC_THRESHOLD, DEFAULT_PRICE_HIGH_SOC_THRESHOLD, "高价强制放电SOC阈值"));
        s.add(Spec.bool(KEY_PRICE_HIGH_FORBID_CHARGE, DEFAULT_PRICE_HIGH_FORBID_CHARGE, "高价禁止充电"));
        s.add(Spec.bool(KEY_PRICE_HIGH_FORCE_DISCHARGE, DEFAULT_PRICE_HIGH_FORCE_DISCHARGE, "高价高SOC强制放电"));
        s.add(Spec.num(KEY_PRICE_HIGH_DISCHARGE_ELE, DEFAULT_PRICE_HIGH_DISCHARGE_ELE, "高价强制放电ELE幅度"));
        s.add(Spec.num(KEY_PRICE_MIN_RESERVE_SOC, DEFAULT_PRICE_MIN_RESERVE_SOC, "高价放电韧性地板SOC"));
        s.add(Spec.bool(KEY_PRICE_GLOBAL_RESERVE_ENABLED, DEFAULT_PRICE_GLOBAL_RESERVE_ENABLED, "全局韧性地板（非停电放电不可击穿）"));
        s.add(Spec.num(KEY_PRICE_LOW_TARGET_SOC, DEFAULT_PRICE_LOW_TARGET_SOC, "低价补电目标SOC"));
        s.add(Spec.num(KEY_PRICE_LOW_CHARGE_ELE, DEFAULT_PRICE_LOW_CHARGE_ELE, "低价补电ELE幅度"));
        s.add(Spec.bool(KEY_PRICE_LOW_SEARCH_BOOST, DEFAULT_PRICE_LOW_SEARCH_BOOST, "低价树搜索抬高SOC下限促补电"));
        s.add(Spec.bool(KEY_PRICE_BAND_TIE_STRICT, DEFAULT_PRICE_BAND_TIE_STRICT, "价格分位并列时按退化处理（关闭 = 旧行为）"));
        s.add(Spec.integer(KEY_TAU, DEFAULT_TAU, "预测优化步长tau"));
        s.add(Spec.str(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE, "电池树搜索适应度类型balance_type"));
        s.add(Spec.str(KEY_PEAK_TRIGGER_MODE, DEFAULT_PEAK_TRIGGER_MODE, "削峰触发信号口径peak_trigger_mode"));
        s.add(Spec.num(KEY_NS_SPIKE_MULT, DEFAULT_NS_SPIKE_MULT, "尖峰判据倍数ns_spike_mult"));
        s.add(Spec.integer(KEY_REBOUND_WINDOW, DEFAULT_REBOUND_WINDOW, "回弹抑制窗口rebound_window"));
        s.add(Spec.num(KEY_REBOUND_CAP, DEFAULT_REBOUND_CAP, "回弹限幅系数rebound_cap"));
        s.add(Spec.bool(KEY_PEAK_BATTERY_DISCHARGE_ENABLED, DEFAULT_PEAK_BATTERY_DISCHARGE_ENABLED, "触发步电池满放peak_battery_discharge_enabled"));
        s.add(Spec.num(KEY_PEAK_BATTERY_DISCHARGE_ELE, DEFAULT_PEAK_BATTERY_DISCHARGE_ELE, "满放ELE幅度peak_battery_discharge_ele"));
        s.add(Spec.bool(KEY_PEAK_CUT_GRADED_ENABLED, DEFAULT_PEAK_CUT_GRADED_ENABLED, "分级削峰开关peak_cut_graded_enabled"));
        s.add(Spec.num(KEY_PEAK_CUT_GRADED_M_LO, DEFAULT_PEAK_CUT_GRADED_M_LO, "分级带宽下沿peak_cut_graded_m_lo"));
        s.add(Spec.num(KEY_PEAK_CUT_GRADED_M_HI, DEFAULT_PEAK_CUT_GRADED_M_HI, "分级带宽上沿peak_cut_graded_m_hi"));
        s.add(Spec.bool(KEY_DHW_STORAGE_FIX, DEFAULT_DHW_STORAGE_FIX, "DHW 储能修复开关dhw_storage_fix"));
        s.add(Spec.bool(KEY_RESMARL_ENABLED, DEFAULT_RESMARL_ENABLED, "兼容字段：是否残差由入口脚本决定"));
        s.add(Spec.str(KEY_MARL_MODE, DEFAULT_MARL_MODE, "MARL 模式：none / multi_agent"));
        s.add(Spec.integer(KEY_MULTI_AGENT_TRAIN_EPOCHS, 0, "Multi-Agent SAC 训练轮数（仅 Multi-agent.py；评估侧已废弃）"));
        s.add(Spec.bool(KEY_MULTI_AGENT_EXPLORE, DEFAULT_MULTI_AGENT_EXPLORE, "Multi-Agent 评估时是否开启 explore"));
        s.add(Spec.str(KEY_MULTI_AGENT_CHECKPOINT, DEFAULT_MULTI_AGENT_CHECKPOINT, "预存 Multi-Agent SAC checkpoint（启用 ResMARL 时必填）"));
        s.add(Spec.num(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA, "CHESCA-ResMARL 残差强度α∈[0,1]"));
        s.add(Spec.bool(KEY_RESMARL_AFTER_SAFETY, DEFAULT_RESMARL_AFTER_SAFETY, "残差是否在安全审查之后施加"));
        s.add(Spec.str(KEY_SCHEMA_SPLIT_ENABLED, "true", "Multi-agent 训测 schema 是否分离（界面配置）"));
        s.add(Spec.str(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA, "Multi-agent.py 训练 schema"));
        s.add(Spec.str(KEY_MULTI_AGENT_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA, "Multi-agent.py 评估 schema"));
        s.add(Spec.str(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA, "CHESCA 仿真/KPI 评估 schema"));
        s.add(Spec.of(KEY_RESMARL_EVAL_SCHEMA, "string",
                svc -> svc.getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA), "CHESCA_ResMARL.py 仿真/KPI 评估 schema"));
        s.add(Spec.raw(KEY_RESIDUAL_ACTION_MASK, "json", DEFAULT_RESIDUAL_ACTION_MASK, "CHESCA-ResMARL 可修正动作维 mask"));
        return java.util.Collections.unmodifiableList(s);
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

    /** 削峰触发信号口径：只认 net / ns_spike / district_spike（2026-10-11 P2） */
    private void savePeakTriggerModeConfig(String mode) {
        if (mode == null || mode.trim().isEmpty()) {
            throw new RuntimeException("缺少配置项: " + KEY_PEAK_TRIGGER_MODE);
        }
        String normalized = mode.trim().toLowerCase();
        if (!"net".equals(normalized) && !"ns_spike".equals(normalized)
                && !"district_spike".equals(normalized)) {
            throw new RuntimeException(KEY_PEAK_TRIGGER_MODE + " 须为 net、ns_spike 或 district_spike");
        }
        upsertStringConfig(KEY_PEAK_TRIGGER_MODE, normalized, "削峰触发信号口径peak_trigger_mode");
    }

    /** 回弹抑制窗口：整数步数，0 = 关闭；上限 48（与 ches_config 的 clamp 一致） */
    private void saveReboundWindowConfig(Integer window) {
        if (window == null) {
            throw new RuntimeException("缺少配置项: " + KEY_REBOUND_WINDOW);
        }
        if (window < 0 || window > 48) {
            throw new RuntimeException(KEY_REBOUND_WINDOW + " 须在 0~48 之间");
        }
        upsertIntConfig(KEY_REBOUND_WINDOW, window, "回弹抑制窗口rebound_window");
    }

    /** 带符号单位区间 [-1, 1]：用于电池满放 ELE 动作（-1 = 单步最大放电） */
    private void saveSignedUnitConfig(String key, Double value, String description) {
        if (value == null) {
            throw new RuntimeException("缺少配置项: " + key);
        }
        if (value < -1.0 || value > 1.0) {
            throw new RuntimeException(key + " 须在 [-1, 1] 之间");
        }
        upsertNumberConfig(key, value, description);
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
