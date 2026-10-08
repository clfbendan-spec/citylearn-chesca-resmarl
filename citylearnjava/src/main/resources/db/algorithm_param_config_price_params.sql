-- ============================================================================
-- 把「CHESCA-ResMARL 配置 → 电价感知电池」整节的 13 个参数登记进算法参数目录
-- （algorithm_param_config）
-- ----------------------------------------------------------------------------
-- 字段来源：BatteryMinSocConfig.vue 的「电价感知电池」小节（第 500~679 行）
-- 键名口径：与 BatteryMinSocConfigService 的 KEY_PRICE_* 常量、以及
--           chesca_agent_config.json 的字段名完全一致
--
-- 登记内容（value_type 的映射规则见文末说明）
--   name                    param_name                      value_type   默认值
--   电价感知                 price_aware_battery_enabled     ratio        开启
--   高价分位数               price_high_quantile             num          0.75
--   低价分位数               price_low_quantile              num          0.25
--   电价历史最少步数         price_history_min_steps         num          48
--   高价禁止充电             price_high_forbid_charge        ratio        开启
--   高价强制放电             price_high_force_discharge      ratio        开启
--   高价强放 SOC 阈值        price_high_soc_threshold        num          0.70
--   强制放电幅度             price_high_discharge_ele        num          0.15
--   全局韧性地板             price_global_reserve_enabled    ratio        开启
--   韧性地板 SOC             price_min_reserve_soc           num          0.55
--   低价补电目标 SOC         price_low_target_soc            num          0.80
--   低价补电幅度             price_low_charge_ele            num          0.25
--   低价树搜索促补电         price_low_search_boost          ratio        开启
--
-- 说明
--   · 开关类（el-switch）统一按「单选」登记，候选项固定为 开启/关闭，
--     对应 key 是字符串 "true" / "false"（与 JSON 布尔值一一对应，下游 str 比较即可）。
--   · 数字类（el-input-number）按「数字」登记，只允许输入数字。
--   · if_system = 1（系统预置）：参数配置页打「系统」标识，只能改简介、不能删。
--   · 只登记「参数定义」，不写 algorithm_config 里的取值 —— 那 13 个值仍由
--     「CHESCA-ResMARL 配置」页维护，两边互不影响。
--   · 可重复执行：用 派生表 + WHERE NOT EXISTS 一次插入多行，已存在的 param_name
--     会被跳过；已存在的行不会被覆盖（想改定义请走「参数配置」页）。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_price_params.sql
-- ============================================================================

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT * FROM (
    SELECT '电价感知' AS `name`, 'price_aware_battery_enabled' AS `param_name`,
           'ratio' AS `value_type`,
           '[{"key":"true","value":"开启"},{"key":"false","value":"关闭"}]' AS `default_value`,
           1 AS `if_system`,
           '是否启用电价感知电池：用最近一段时间的电价分布判断「现在贵不贵」，贵则少充、便宜则多充电。关闭后下方高/低价规则不生效（韧性地板若单独开启仍可能约束放电）。' AS `desc`,
           NOW() AS `create_time`
    UNION ALL SELECT '高价分位数', 'price_high_quantile', 'num', NULL, 1,
           '高价分位数（0.5~0.99）：电价高于该分位视为「高价」，默认 0.75。', NOW()
    UNION ALL SELECT '低价分位数', 'price_low_quantile', 'num', NULL, 1,
           '低价分位数（0.01~0.5）：电价低于该分位视为「低价」，默认 0.25。', NOW()
    UNION ALL SELECT '电价历史最少步数', 'price_history_min_steps', 'num', NULL, 1,
           '电价历史最少样本步数（8~720）：历史样本不足该步数时不做分位数判断，默认 48。', NOW()
    UNION ALL SELECT '高价禁止充电', 'price_high_forbid_charge', 'ratio',
           '[{"key":"true","value":"开启"},{"key":"false","value":"关闭"}]', 1,
           '开启后高价时段禁止充电（ELE≤0），避免电价高时还充电。默认开启。', NOW()
    UNION ALL SELECT '高价强制放电', 'price_high_force_discharge', 'ratio',
           '[{"key":"true","value":"开启"},{"key":"false","value":"关闭"}]', 1,
           '开启后在高价且 SOC 够高时主动放电，用电池电顶替买电，降低电费与净负荷。默认开启。', NOW()
    UNION ALL SELECT '高价强放 SOC 阈值', 'price_high_soc_threshold', 'num', NULL, 1,
           '高价强制放电的 SOC 阈值（0~1）：SOC 高于该值才触发强制放电，默认 0.70。', NOW()
    UNION ALL SELECT '强制放电幅度', 'price_high_discharge_ele', 'num', NULL, 1,
           '高价强制放电的 ELE 幅度（0~1）：单次放电削减的用电比例，默认 0.15。', NOW()
    UNION ALL SELECT '全局韧性地板', 'price_global_reserve_enabled', 'ratio',
           '[{"key":"true","value":"开启"},{"key":"false","value":"关闭"}]', 1,
           '开启后中/高/低价放电都受韧性地板约束，树搜索的 SOC 下限也会抬到地板以上；关闭则中价放电不起效。默认开启。', NOW()
    UNION ALL SELECT '韧性地板 SOC', 'price_min_reserve_soc', 'num', NULL, 1,
           '高价放电的韧性地板 SOC（0~1）：放电不得击穿该下限，默认 0.55。', NOW()
    UNION ALL SELECT '低价补电目标 SOC', 'price_low_target_soc', 'num', NULL, 1,
           '低价时补电的目标 SOC（0~1），默认 0.80。', NOW()
    UNION ALL SELECT '低价补电幅度', 'price_low_charge_ele', 'num', NULL, 1,
           '低价补电的 ELE 幅度（0~1）：单次补电抬升的用电比例，默认 0.25。', NOW()
    UNION ALL SELECT '低价树搜索促补电', 'price_low_search_boost', 'ratio',
           '[{"key":"true","value":"开启"},{"key":"false","value":"关闭"}]', 1,
           '开启后低价时抬高树搜索的 SOC 下限，促使一步充到「当前 SOC + 补电幅度」，让搜索更积极抓住便宜电。默认开启。', NOW()
) AS `t`
WHERE NOT EXISTS (
    SELECT 1 FROM `algorithm_param_config` `p` WHERE `p`.`param_name` = `t`.`param_name`
);

-- 校验：确认这一节的 13 个参数都已登记
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`
FROM `algorithm_param_config`
WHERE `param_name` LIKE 'price\_%'
ORDER BY `id`;

-- 总量校验
SELECT COUNT(*) AS `total`, SUM(`if_system`) AS `system_count` FROM `algorithm_param_config`;
