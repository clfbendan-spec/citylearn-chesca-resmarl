-- ============================================================================
-- 把「CHESCA-ResMARL 配置」页其余各节的参数登记进算法参数目录，并按节建配置组
-- ----------------------------------------------------------------------------
-- 覆盖的小节（来源：BatteryMinSocConfig.vue）
--   冷机                  第 54~224 行   12 个参数
--   电力恢复时 TMP 功率帽   第 225~294 行   5 个参数
--   电力恢复后缓充         第 416~499 行   6 个参数
--   SOC 参数配置           第 299~415 行   3 个全局上限 + 1 个「小时下限」map
--   电价感知电池           第 500~679 行  13 个参数（上一批已登记，这里只改归属）
--   合计 40 个参数 → 5 个配置组
--
-- 三条统一口径
--   1. if_system = 0 —— 全部按「用户参数」处理。必须如此：系统内置参数不允许加入
--      配置组（见 BaseDataService.updateSetMembers），留在 1 就进不了组。
--   2. 开关（el-switch）→ value_type = bool；数字（el-input-number / el-slider）→ num。
--      bool 不使用 default_value（候选项只服务 单选/多选/map）。
--   3. 键名与 BatteryMinSocConfigService 的 KEY_* 常量、chesca_agent_config.json
--      的字段名逐字一致。
--
-- 「小时下限」的特殊处理
--   界面上的「选择时段 + 电池 SOC 下限」不是两个独立参数，而是同一个 24 项键值对
--   （min_soc_per_hour）。所以登记成一个 value_type = map 的参数：
--     key_alias   = 选择时段
--     value_alias = 电池 SOC 下限
--     default_value = 24 个小时的当前默认下限（与 algorithm_config.sql 一致）
--
-- 可重复执行：INSERT 带 WHERE NOT EXISTS；配置组的 members 每次重算覆盖，
--   保证参数清单变化后成员跟着变。is_member 由本脚本显式置 1（这 40 个都在组里）。
--
-- 执行顺序：先跑 algorithm_param_config_map_type.sql（加 key_alias/value_alias 两列）。
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_groups.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) 登记 27 个新参数（电价感知电池那 13 个上一批已有，不动定义）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `key_alias`, `value_alias`,
     `if_system`, `desc`, `create_time`)
SELECT * FROM (
    /* ---------- 冷机 ---------- */
    SELECT '冷机最大削减比例' AS `name`, 'TMP_max_reduction_percent' AS `param_name`,
           'num' AS `value_type`, NULL AS `default_value`, NULL AS `key_alias`, NULL AS `value_alias`,
           0 AS `if_system`,
           '减负荷时空调最多能被砍掉的比例（0~100）。0=保护舒适不砍空调；100=允许把空调几乎关停来保电网。' AS `desc`,
           NOW() AS `create_time`
    UNION ALL SELECT '过热保底系数', 'min_cool_per_c_overheat', 'num', NULL, NULL, NULL, 0,
           '室内比设定温度每高 1°C，至少按「系数 × 额定制冷功率」要电（0~2）。防止 PID 还没跟上时房间继续升温。', NOW()
    UNION ALL SELECT '室外保底系数', 'min_cool_per_c_outdoor_gap', 'num', NULL, NULL, NULL, 0,
           '按「室外温度 − 室内设定」额外抬一点制冷（0~1）。设为 0 则完全关闭室外保底。', NOW()
    UNION ALL SELECT '室外死区', 'outdoor_gap_deadband_c', 'num', NULL, NULL, NULL, 0,
           '只有「室外 − 设定」超过该死区才启用室外保底（°C，0~30），避免误开空调。', NOW()
    UNION ALL SELECT '室外保底最大过热阈值', 'outdoor_floor_max_overheat_c', 'num', NULL, NULL, NULL, 0,
           '仅当室内过热还「不太严重」（0 ≤ 过热 < 该值）时才叠加室外保底（°C，0~10），避免双重加码浪费电。', NOW()
    UNION ALL SELECT '冷负荷前馈比例', 'cooling_demand_feedforward_frac', 'num', NULL, NULL, NULL, 0,
           '至少按冷负荷的该比例要电（0~1），不等 PID 纠偏先按负荷预报预开一点空调。设为 0 关闭。', NOW()
    UNION ALL SELECT '前馈仅过热时启用', 'demand_feedforward_only_when_overheat', 'bool', NULL, NULL, NULL, 0,
           '开启：只有室内已经过热才用冷负荷前馈。关闭：室温刚贴设定时也能预开空调，舒适更稳但略费电。', NOW()
    UNION ALL SELECT '室外保底允许低于设定', 'outdoor_floor_allow_when_under_setpoint', 'bool', NULL, NULL, NULL, 0,
           '开启：即使室内比设定还凉一点，只要室外很热仍可按室外温差保底预冷；关闭：室内低于设定时不再加室外保底。', NOW()
    UNION ALL SELECT '低于设定清掉开环保底', 'clear_open_loop_floor_when_under_setpoint', 'bool', NULL, NULL, NULL, 0,
           '开启后：室内低于设定时清空室外保底与冷负荷前馈，只留 PID。', NOW()
    UNION ALL SELECT 'PID 使用滞后动力学室温', 'use_lagged_dynamics_indoor', 'bool', NULL, NULL, NULL, 0,
           '开启：PID 用「上一拍已落地」的室内温，与建筑动力学对齐，减少看错温度导致的震荡。', NOW()
    UNION ALL SELECT '仅当滞后室温更热时启用', 'lagged_indoor_only_when_hotter', 'bool', NULL, NULL, NULL, 0,
           '开启：只有滞后室温比最新观测更热、且温差超过裕度时才改用滞后温（偏保守防闷热）；关闭：总开关打开就始终用滞后温。', NOW()
    UNION ALL SELECT '滞后更热裕度', 'lagged_indoor_hotter_margin_c', 'num', NULL, NULL, NULL, 0,
           '滞后温要比最新观测至少高这么多才切换（°C，0~10），用来过滤噪声。', NOW()

    /* ---------- 电力恢复时 TMP 功率帽 ---------- */
    UNION ALL SELECT 'TMP 功率帽', 'post_outage_tmp_cap_enabled', 'bool', NULL, NULL, NULL, 0,
           '开启：电力恢复后一段时间内限制空调功率，避免三栋楼空调一步拉满造成的用电高峰；关闭：复电第一步即可满功率制冷。', NOW()
    UNION ALL SELECT 'TMP 功率帽窗口步数', 'post_outage_tmp_cap_steps', 'num', NULL, NULL, NULL, 0,
           '限制持续多少个仿真步（0~48）。例：4 步表示复电后约 4 小时内逐步放开。', NOW()
    UNION ALL SELECT '首步 TMP 上限', 'post_outage_tmp_max_start', 'num', NULL, NULL, NULL, 0,
           '电力恢复那一步允许的最大 TMP（0~1）。0.40 ≈ 最多开到满功率的 40%。', NOW()
    UNION ALL SELECT '线性爬升到满功率', 'post_outage_tmp_ramp', 'bool', NULL, NULL, NULL, 0,
           '开启：上限从「首步上限」线性升到 1.0；关闭：维持首步上限，结束限制步数才解除。', NOW()
    UNION ALL SELECT '分栋错峰', 'post_outage_tmp_stagger', 'bool', NULL, NULL, NULL, 0,
           '开启：Building0 先爬坡，其余各晚 1 步，避免三栋同时拉满。', NOW()

    /* ---------- 电力恢复后缓充 ---------- */
    UNION ALL SELECT '电力恢复后缓充', 'post_outage_soft_charge_enabled', 'bool', NULL, NULL, NULL, 0,
           '开启：复电后几步内限制每步充电量、过热时优先把电留给空调；关闭后下列缓充规则不生效。', NOW()
    UNION ALL SELECT '缓充窗口步数', 'post_outage_relax_steps', 'num', NULL, NULL, NULL, 0,
           '复电后连续多少步生效（含刚复电的第 0 步，0~48）。例：4 ≈ 复电后约 4 小时内按缓充规则。', NOW()
    UNION ALL SELECT '避免SOC强制充电', 'post_outage_waive_min_soc', 'bool', NULL, NULL, NULL, 0,
           '开启：不再强制把 SOC 充到该小时下限，避免用电高峰；关闭：仍按小时下限充电，峰值更大。', NOW()
    UNION ALL SELECT 'ELE 充电上限', 'post_outage_max_ele_charge', 'num', NULL, NULL, NULL, 0,
           '缓充窗口内每一步最多充多少（相对 SOC，0~1）。0.15 ≈ 每步最多充约 15% 电量。', NOW()
    UNION ALL SELECT '过热时禁止充电', 'post_outage_forbid_charge_when_overheat', 'bool', NULL, NULL, NULL, 0,
           '开启：室内过热超过阈值时强制 ELE≤0，把电力优先留给制冷。', NOW()
    UNION ALL SELECT '过热阈值', 'post_outage_overheat_c', 'num', NULL, NULL, NULL, 0,
           '室内比设定高出多少算过热、禁止充电（°C，0~20）。', NOW()

    /* ---------- SOC 参数配置 ---------- */
    UNION ALL SELECT '正常时段 SOC 上限', 'max_soc_normal', 'num', NULL, NULL, NULL, 0,
           '电网正常时电池最多充到多少（0~1）。例：0.99 几乎可充满，减少过充风险。', NOW()
    UNION ALL SELECT '停电时段 SOC 上限', 'max_soc_outage', 'num', NULL, NULL, NULL, 0,
           '停电期间允许的 SOC 上限（0~1），通常低于正常上限。', NOW()
    UNION ALL SELECT '停电 SOC 最大降幅', 'max_soc_reduction_in_outage', 'num', NULL, NULL, NULL, 0,
           '停电期间相对停电前允许下降多少电（0~1），限制「一口气把电放光」。', NOW()

    /* ---------- 小时下限：键值对（map）---------- */
    UNION ALL SELECT '小时下限', 'min_soc_per_hour', 'map',
           '[{"key":"0","value":"0.6"},{"key":"1","value":"0.65"},{"key":"2","value":"0.72"},{"key":"3","value":"0.78"},{"key":"4","value":"0.8"},{"key":"5","value":"0.85"},{"key":"6","value":"0.8"},{"key":"7","value":"0.75"},{"key":"8","value":"0.7"},{"key":"9","value":"0.6"},{"key":"10","value":"0.5"},{"key":"11","value":"0.6"},{"key":"12","value":"0.65"},{"key":"13","value":"0.65"},{"key":"14","value":"0.7"},{"key":"15","value":"0.7"},{"key":"16","value":"0.7"},{"key":"17","value":"0.65"},{"key":"18","value":"0.7"},{"key":"19","value":"0.6"},{"key":"20","value":"0.6"},{"key":"21","value":"0.6"},{"key":"22","value":"0.6"},{"key":"23","value":"0.55"}]',
           '选择时段', '电池 SOC 下限', 0,
           '24 个小时各自的电池 SOC 下限（0~1）。该小时电池「尽量不要低于」的电量；例：傍晚高峰设 0.7，算法会倾向提前充电、高峰时还能放电支援。', NOW()
) AS `t`
WHERE NOT EXISTS (
    SELECT 1 FROM `algorithm_param_config` `p` WHERE `p`.`param_name` = `t`.`param_name`
);

-- ---------------------------------------------------------------------------
-- 2) 电价感知电池那 13 个参数改为「非系统参数」，否则进不了配置组
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `if_system` = 0
WHERE `param_name` LIKE 'price\_%' AND `if_system` <> 0;

-- ---------------------------------------------------------------------------
-- 3) 建 5 个配置组（members 由 param_name 列表反查 id 算出来，不依赖自增 id）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '冷机',
       '空调开环保底与 PID 行为：最低制冷、前馈、滞后室温等',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('TMP_max_reduction_percent','min_cool_per_c_overheat','min_cool_per_c_outdoor_gap',
                       'outdoor_gap_deadband_c','outdoor_floor_max_overheat_c','cooling_demand_feedforward_frac',
                       'demand_feedforward_only_when_overheat','outdoor_floor_allow_when_under_setpoint',
                       'clear_open_loop_floor_when_under_setpoint','use_lagged_dynamics_indoor',
                       'lagged_indoor_only_when_hotter','lagged_indoor_hotter_margin_c')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '冷机');

INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '电力恢复时 TMP 功率帽',
       '复电瞬间限制空调功率，避免三栋同时拉满造成用电尖峰',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('post_outage_tmp_cap_enabled','post_outage_tmp_cap_steps',
                       'post_outage_tmp_max_start','post_outage_tmp_ramp','post_outage_tmp_stagger')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '电力恢复时 TMP 功率帽');

INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '电力恢复后缓充',
       '复电后限制充电速度、过热时把电优先留给制冷',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('post_outage_soft_charge_enabled','post_outage_relax_steps',
                       'post_outage_waive_min_soc','post_outage_max_ele_charge',
                       'post_outage_forbid_charge_when_overheat','post_outage_overheat_c')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '电力恢复后缓充');

INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), 'SOC 参数配置',
       '电池 SOC 全局上限，以及 24 小时的 SOC 下限（键值对）',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('max_soc_normal','max_soc_outage','max_soc_reduction_in_outage',
                       'min_soc_per_hour')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = 'SOC 参数配置');

INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '电价感知电池',
       '按电价分布判断贵/便宜：高价禁充强放、低价补电、韧性地板',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` LIKE 'price\_%'), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '电价感知电池');

-- 重算 members：参数清单若有增减，重跑本脚本即可同步（组本身不重复建）
UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` LIKE 'price\_%'), '[]')
WHERE `name` = '电价感知电池';

UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('max_soc_normal','max_soc_outage','max_soc_reduction_in_outage',
                    'min_soc_per_hour')), '[]')
WHERE `name` = 'SOC 参数配置';

UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('post_outage_soft_charge_enabled','post_outage_relax_steps',
                    'post_outage_waive_min_soc','post_outage_max_ele_charge',
                    'post_outage_forbid_charge_when_overheat','post_outage_overheat_c')), '[]')
WHERE `name` = '电力恢复后缓充';

UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('post_outage_tmp_cap_enabled','post_outage_tmp_cap_steps',
                    'post_outage_tmp_max_start','post_outage_tmp_ramp','post_outage_tmp_stagger')), '[]')
WHERE `name` = '电力恢复时 TMP 功率帽';

UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('TMP_max_reduction_percent','min_cool_per_c_overheat','min_cool_per_c_outdoor_gap',
                    'outdoor_gap_deadband_c','outdoor_floor_max_overheat_c','cooling_demand_feedforward_frac',
                    'demand_feedforward_only_when_overheat','outdoor_floor_allow_when_under_setpoint',
                    'clear_open_loop_floor_when_under_setpoint','use_lagged_dynamics_indoor',
                    'lagged_indoor_only_when_hotter','lagged_indoor_hotter_margin_c')), '[]')
WHERE `name` = '冷机';

-- ---------------------------------------------------------------------------
-- 4) 同步 is_member：这 40 个参数全部已在组里
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `is_member` = 1
WHERE `param_name` LIKE 'price\_%'
   OR `param_name` IN (
        'TMP_max_reduction_percent','min_cool_per_c_overheat','min_cool_per_c_outdoor_gap',
        'outdoor_gap_deadband_c','outdoor_floor_max_overheat_c','cooling_demand_feedforward_frac',
        'demand_feedforward_only_when_overheat','outdoor_floor_allow_when_under_setpoint',
        'clear_open_loop_floor_when_under_setpoint','use_lagged_dynamics_indoor',
        'lagged_indoor_only_when_hotter','lagged_indoor_hotter_margin_c',
        'post_outage_tmp_cap_enabled','post_outage_tmp_cap_steps','post_outage_tmp_max_start',
        'post_outage_tmp_ramp','post_outage_tmp_stagger',
        'post_outage_soft_charge_enabled','post_outage_relax_steps','post_outage_waive_min_soc',
        'post_outage_max_ele_charge','post_outage_forbid_charge_when_overheat','post_outage_overheat_c',
        'max_soc_normal','max_soc_outage','max_soc_reduction_in_outage','min_soc_per_hour'
   );

-- ---------------------------------------------------------------------------
-- 5) 校验
-- ---------------------------------------------------------------------------
SELECT `id`, `name`, `param_name`, `value_type`, `key_alias`, `value_alias`, `if_system`, `is_member`
FROM `algorithm_param_config`
ORDER BY `is_member` DESC, `id`;

SELECT `id`, `name`, `member_count` FROM (
    SELECT `id`, `name`,
           (LENGTH(`members`) - LENGTH(REPLACE(`members`, ',', '')) + 1) AS `member_count`
    FROM `algorithm_param_config_set`
) AS `t`
ORDER BY `id`;

SELECT `if_system`, `is_member`, COUNT(*) AS `cnt`
FROM `algorithm_param_config`
GROUP BY `if_system`, `is_member`
ORDER BY `if_system`, `is_member`;
