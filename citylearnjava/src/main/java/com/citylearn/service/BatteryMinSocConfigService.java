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
    public static final String KEY_TAU = "tau";
    public static final String KEY_BALANCE_TYPE = "balance_type";
    public static final String KEY_RESMARL_ENABLED = "resmarl_enabled";
    public static final String KEY_MARL_MODE = "marl_mode";
    public static final String KEY_MULTI_AGENT_TRAIN_EPOCHS = "multi_agent_train_epochs";
    public static final String KEY_MULTI_AGENT_EXPLORE = "multi_agent_explore";
    public static final String KEY_RESIDUAL_ALPHA = "residual_alpha";
    public static final String KEY_RESIDUAL_ACTION_MASK = "residual_action_mask";
    public static final String KEY_RESMARL_AFTER_SAFETY = "resmarl_after_safety";
    public static final String KEY_SCHEMA_SPLIT_ENABLED = "schema_split_enabled";
    public static final String KEY_TRAIN_SCHEMA = "train_schema";
    public static final String KEY_EVAL_SCHEMA = "eval_schema";

    private static final double DEFAULT_MAX_SOC_NORMAL = 0.99;
    private static final double DEFAULT_MAX_SOC_OUTAGE = 0.87;
    private static final double DEFAULT_MAX_SOC_REDUCTION_IN_OUTAGE = 0.70;
    private static final double DEFAULT_B_LOW = 1.18;
    private static final double DEFAULT_B_HIGH = 1.0;
    private static final double DEFAULT_TMP_MAX_REDUCTION_PERCENT = 0.0;
    private static final int DEFAULT_TAU = 1;
    private static final String DEFAULT_BALANCE_TYPE = "C";
    private static final boolean DEFAULT_RESMARL_ENABLED = false;
    private static final String DEFAULT_MARL_MODE = "none";
    private static final int DEFAULT_MULTI_AGENT_TRAIN_EPOCHS = 20;
    private static final boolean DEFAULT_MULTI_AGENT_EXPLORE = false;
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
        vo.setTau(getIntConfig(KEY_TAU, DEFAULT_TAU));
        vo.setBalanceType(getStringConfig(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE));
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
        if (config.getTau() == null) {
            config.setTau(defaults.getTau());
        }
        if (config.getBalanceType() == null || config.getBalanceType().isEmpty()) {
            config.setBalanceType(defaults.getBalanceType());
        }
        saveMinSocPerHour(config.getMinSocPerHour());
        saveSocRatioConfig(KEY_MAX_SOC_NORMAL, config.getMaxSocNormal(), "正常时段电池SOC上限");
        saveSocRatioConfig(KEY_MAX_SOC_OUTAGE, config.getMaxSocOutage(), "停电时段电池SOC上限");
        saveSocRatioConfig(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, config.getMaxSocReductionInOutage(), "停电时最大SOC降幅");
        saveThresholdConfig(KEY_B_LOW, config.getBLow(), "负荷平衡增负荷阈值系数B_low");
        saveThresholdConfig(KEY_B_HIGH, config.getBHigh(), "负荷平衡减负荷阈值系数B_high");
        saveSocRatioConfig(KEY_TMP_MAX_REDUCTION_PERCENT, config.getTmpMaxReductionPercent(), "冷机最大削减比例TMP_max_reduction_percent");
        saveTauConfig(config.getTau());
        saveBalanceTypeConfig(config.getBalanceType());
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
        vo.setTau(DEFAULT_TAU);
        vo.setBalanceType(DEFAULT_BALANCE_TYPE);
        return vo;
    }

    /** 获取 CHESCA-ResMARL 配置 */
    public ResMarlConfigVO getResMarlConfig() {
        ensureDefaults();
        ResMarlConfigVO vo = new ResMarlConfigVO();
        boolean enabled = getBoolConfig(KEY_RESMARL_ENABLED, DEFAULT_RESMARL_ENABLED);
        vo.setResmarlEnabled(enabled);
        vo.setMarlMode(resolveMarlModeForDisplay(enabled));
        vo.setMultiAgentTrainEpochs(getIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, DEFAULT_MULTI_AGENT_TRAIN_EPOCHS));
        vo.setMultiAgentExplore(getBoolConfig(KEY_MULTI_AGENT_EXPLORE, DEFAULT_MULTI_AGENT_EXPLORE));
        vo.setResidualAlpha(getNumberConfig(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA));
        vo.setResidualActionMask(getResidualActionMask());
        vo.setResmarlAfterSafety(getBoolConfig(KEY_RESMARL_AFTER_SAFETY, DEFAULT_RESMARL_AFTER_SAFETY));
        vo.setSchemaSplitEnabled(getBoolConfig(KEY_SCHEMA_SPLIT_ENABLED, DEFAULT_SCHEMA_SPLIT_ENABLED));
        vo.setTrainSchema(getStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA));
        vo.setEvalSchema(getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));
        return vo;
    }

    /** 保存 CHESCA-ResMARL 配置到 algorithm_config */
    public void saveResMarlConfig(ResMarlConfigVO config) {
        if (config == null) {
            throw new RuntimeException("配置不能为空");
        }
        boolean enabled = config.getResmarlEnabled() != null
                ? config.getResmarlEnabled()
                : DEFAULT_RESMARL_ENABLED;
        String marlMode = normalizeMarlMode(config.getMarlMode());
        if (!enabled) {
            marlMode = "none";
        } else if ("none".equals(marlMode)) {
            marlMode = "multi_agent";
        }

        Integer trainEpochs = config.getMultiAgentTrainEpochs();
        if (trainEpochs == null) {
            trainEpochs = DEFAULT_MULTI_AGENT_TRAIN_EPOCHS;
        }
        if (trainEpochs < 1 || trainEpochs > 500) {
            throw new RuntimeException("multi_agent_train_epochs 须在 [1, 500] 之间");
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
        boolean schemaSplit = config.getSchemaSplitEnabled() != null
                ? config.getSchemaSplitEnabled()
                : DEFAULT_SCHEMA_SPLIT_ENABLED;
        String trainSchema = config.getTrainSchema();
        if (trainSchema == null || trainSchema.trim().isEmpty()) {
            trainSchema = DEFAULT_TRAIN_SCHEMA;
        } else {
            trainSchema = trainSchema.trim();
        }
        String evalSchema = config.getEvalSchema();
        if (evalSchema == null || evalSchema.trim().isEmpty()) {
            evalSchema = DEFAULT_EVAL_SCHEMA;
        } else {
            evalSchema = evalSchema.trim();
        }

        upsertStringConfig(KEY_RESMARL_ENABLED, String.valueOf(enabled), "是否启用 CHESCA-ResMARL");
        upsertStringConfig(KEY_MARL_MODE, marlMode, "MARL 模式：none / multi_agent");
        upsertIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, trainEpochs, "Multi-Agent SAC 训练轮数");
        upsertStringConfig(KEY_MULTI_AGENT_EXPLORE, String.valueOf(explore), "Multi-Agent 评估时是否开启 explore");
        upsertNumberConfig(KEY_RESIDUAL_ALPHA, alpha, "CHESCA-ResMARL 残差强度α∈[0,1]");
        upsertConfig(KEY_RESIDUAL_ACTION_MASK, JSON.toJSONString(mask), "json", "CHESCA-ResMARL 可修正动作维 mask");
        upsertStringConfig(KEY_RESMARL_AFTER_SAFETY, String.valueOf(afterSafety), "残差是否在安全审查之后施加");
        upsertStringConfig(KEY_SCHEMA_SPLIT_ENABLED, String.valueOf(schemaSplit), "是否启用训测 schema 分离（方案 A）");
        upsertStringConfig(KEY_TRAIN_SCHEMA, trainSchema, "Multi-Agent SAC 训练 schema");
        upsertStringConfig(KEY_EVAL_SCHEMA, evalSchema, "CHESCA 仿真/KPI 评估 schema");
    }

    public ResMarlConfigVO getDefaultResMarlConfig() {
        ResMarlConfigVO vo = new ResMarlConfigVO();
        vo.setResmarlEnabled(DEFAULT_RESMARL_ENABLED);
        vo.setMarlMode(DEFAULT_MARL_MODE);
        vo.setMultiAgentTrainEpochs(DEFAULT_MULTI_AGENT_TRAIN_EPOCHS);
        vo.setMultiAgentExplore(DEFAULT_MULTI_AGENT_EXPLORE);
        vo.setResidualAlpha(DEFAULT_RESIDUAL_ALPHA);
        vo.setResidualActionMask(defaultResidualActionMask());
        vo.setResmarlAfterSafety(DEFAULT_RESMARL_AFTER_SAFETY);
        vo.setSchemaSplitEnabled(DEFAULT_SCHEMA_SPLIT_ENABLED);
        vo.setTrainSchema(DEFAULT_TRAIN_SCHEMA);
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

    /** 将当前配置写入任务目录，供 Python --min-soc-config 读取 */
    public String writeConfigJsonToTaskDir(String taskOutputDir) throws IOException {
        ChescaBatteryConfigVO config = getConfig();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put(KEY_MIN_SOC_PER_HOUR, config.getMinSocPerHour());
        payload.put(KEY_MAX_SOC_NORMAL, config.getMaxSocNormal());
        payload.put(KEY_MAX_SOC_OUTAGE, config.getMaxSocOutage());
        payload.put(KEY_MAX_SOC_REDUCTION_IN_OUTAGE, config.getMaxSocReductionInOutage());
        payload.put("B_low", config.getBLow());
        payload.put("B_high", config.getBHigh());
        payload.put("TMP_max_reduction_percent", config.getTmpMaxReductionPercent());
        payload.put("tau", config.getTau());
        payload.put("balance_type", config.getBalanceType());
        // CHESCA-ResMARL：从 algorithm_config 读取
        boolean resmarlEnabled = getBoolConfig(KEY_RESMARL_ENABLED, DEFAULT_RESMARL_ENABLED);
        String marlMode = resolveMarlModeForTaskJson(resmarlEnabled);
        payload.put(KEY_RESMARL_ENABLED, resmarlEnabled);
        payload.put(KEY_MARL_MODE, marlMode);
        payload.put(KEY_MULTI_AGENT_TRAIN_EPOCHS, getIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, DEFAULT_MULTI_AGENT_TRAIN_EPOCHS));
        payload.put(KEY_MULTI_AGENT_EXPLORE, getBoolConfig(KEY_MULTI_AGENT_EXPLORE, DEFAULT_MULTI_AGENT_EXPLORE));
        payload.put(KEY_RESIDUAL_ALPHA, getNumberConfig(KEY_RESIDUAL_ALPHA, DEFAULT_RESIDUAL_ALPHA));
        payload.put(KEY_RESIDUAL_ACTION_MASK, getJsonObjectConfig(KEY_RESIDUAL_ACTION_MASK, DEFAULT_RESIDUAL_ACTION_MASK));
        payload.put(KEY_RESMARL_AFTER_SAFETY, getBoolConfig(KEY_RESMARL_AFTER_SAFETY, DEFAULT_RESMARL_AFTER_SAFETY));
        payload.put(KEY_SCHEMA_SPLIT_ENABLED, getBoolConfig(KEY_SCHEMA_SPLIT_ENABLED, DEFAULT_SCHEMA_SPLIT_ENABLED));
        payload.put(KEY_TRAIN_SCHEMA, getStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA));
        payload.put(KEY_EVAL_SCHEMA, getStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA));

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
        if (algorithmConfigMapper.selectById(KEY_TAU) == null) {
            upsertIntConfig(KEY_TAU, DEFAULT_TAU, "预测优化步长tau");
        }
        if (algorithmConfigMapper.selectById(KEY_BALANCE_TYPE) == null) {
            upsertStringConfig(KEY_BALANCE_TYPE, DEFAULT_BALANCE_TYPE, "电池树搜索适应度类型balance_type");
        }
        if (algorithmConfigMapper.selectById(KEY_RESMARL_ENABLED) == null) {
            upsertStringConfig(KEY_RESMARL_ENABLED, String.valueOf(DEFAULT_RESMARL_ENABLED), "是否启用 CHESCA-ResMARL");
        }
        if (algorithmConfigMapper.selectById(KEY_MARL_MODE) == null) {
            upsertStringConfig(KEY_MARL_MODE, DEFAULT_MARL_MODE, "MARL 模式：none / multi_agent");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_TRAIN_EPOCHS) == null) {
            upsertIntConfig(KEY_MULTI_AGENT_TRAIN_EPOCHS, DEFAULT_MULTI_AGENT_TRAIN_EPOCHS, "Multi-Agent SAC 训练轮数");
        }
        if (algorithmConfigMapper.selectById(KEY_MULTI_AGENT_EXPLORE) == null) {
            upsertStringConfig(KEY_MULTI_AGENT_EXPLORE, String.valueOf(DEFAULT_MULTI_AGENT_EXPLORE), "Multi-Agent 评估时是否开启 explore");
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
            upsertStringConfig(KEY_SCHEMA_SPLIT_ENABLED, String.valueOf(DEFAULT_SCHEMA_SPLIT_ENABLED), "是否启用训测 schema 分离（方案 A）");
        }
        if (algorithmConfigMapper.selectById(KEY_TRAIN_SCHEMA) == null) {
            upsertStringConfig(KEY_TRAIN_SCHEMA, DEFAULT_TRAIN_SCHEMA, "Multi-Agent SAC 训练 schema");
        }
        if (algorithmConfigMapper.selectById(KEY_EVAL_SCHEMA) == null) {
            upsertStringConfig(KEY_EVAL_SCHEMA, DEFAULT_EVAL_SCHEMA, "CHESCA 仿真/KPI 评估 schema");
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
