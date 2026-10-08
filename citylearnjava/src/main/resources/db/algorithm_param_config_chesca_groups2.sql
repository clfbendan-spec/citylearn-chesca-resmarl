-- ============================================================================
-- 把 CHESCA 的「剩余参数」补齐进算法参数目录，并另建 2 个配置组
-- ----------------------------------------------------------------------------
-- 背景
--   代码编辑器「配置」弹窗按**配置组**挂参数（组来自 algorithm_param_config_set）。
--   CHESCA 目前已有 5 组 / 40 个参数（algorithm_param_config_chesca_groups.sql）：
--     冷机 12 · 电力恢复时 TMP 功率帽 5 · 电力恢复后缓充 6 · SOC 参数配置 4 · 电价感知电池 13
--   但 CHESCA.py 的 parse_args 还有 5 个参数没进组：
--     tau / balance_type / B_low / B_high  —— 已登记，但 if_system = 1（系统参数**不允许**入组 ✗）
--     eval_schema                          —— 完全没有登记 ✗（CHESCA.py 的评估数据集）
--
-- 本脚本做三件事
--   ① 登记 eval_schema（value_type = special：界面渲染成数据集下拉，库内存 citylearn_dataset.id）
--   ② 把 tau / balance_type / B_low / B_high 改成 if_system = 0（否则进不了组；
--      与 algorithm_param_config_chesca_groups.sql 里 price_* 那次改动同一处理）
--   ③ 新建 2 个配置组，并**重算全部 7 个 CHESCA 组**的 members
--
-- 分组口径（组别太肥会难用 ⇒ 每组的参数个数都控制在个位到十位数）
--   树搜索与负荷阈值   4：tau / balance_type / B_low / B_high
--   纯CHESCA 评估数据集 1：eval_schema
--   （+ 原有 5 组：冷机 12 / 电价 13 / 缓充 6 / TMP 帽 5 / SOC 4）
--   ⇒ 全库最大组 = 电价感知电池 13 个 ✓
--
-- 与命令行白名单的关系（重要）
--   配置弹窗里挂上的参数，执行时会翻成 `--参数名 值` 传给脚本；
--   只有 BaseDataService.ALGORITHM_CONFIG_CLI_WHITELIST 里登记过的名字才允许传
--   （见该处 "chesca.py" 那一份名单 —— 本脚本登记的 param_name 全部在其中 ✓）。
--   ⇒ param_name 必须与 CHESCA.py 的 argparse 选项**逐字一致**（这里都是下划线写法 ✓）。
--
-- 可重复执行：登记用 WHERE NOT EXISTS；组的 members 每次重算覆盖；
--   is_member 显式收敛成"这 45 个 = 1"。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_groups2.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- ① 登记 eval_schema（纯 CHESCA 的仿真/KPI 数据集；与 eval-schema 同型，但名字是下划线）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '纯CHESCA 评估数据集', 'eval_schema', 'special', NULL, 0,
       'CHESCA.py 仿真与 KPI 用的数据集（对应命令行 --eval_schema）。从已启用的数据集中选一个，'
       '库内存数据集 id；不选则用脚本默认。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'eval_schema');

-- ---------------------------------------------------------------------------
-- ② tau / balance_type / B_low / B_high 改为「非系统参数」，否则进不了配置组
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `if_system` = 0
WHERE `param_name` IN ('tau', 'balance_type', 'B_low', 'B_high')
  AND `if_system` <> 0;

-- ---------------------------------------------------------------------------
-- ③ 新建 2 个配置组（members 由 param_name 反查 id 算出，不依赖自增 id）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '树搜索与负荷阈值',
       '电池树搜索的预测步长与适应度口径，以及增/减负荷阈值系数',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('tau','balance_type','B_low','B_high')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '树搜索与负荷阈值');

INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '纯CHESCA 评估数据集',
       'CHESCA.py 跑仿真与统计 KPI 用的数据集',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` = 'eval_schema'), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '纯CHESCA 评估数据集');

-- ---------------------------------------------------------------------------
-- ④ 重算 7 个 CHESCA 组的 members（参数清单若有增减，重跑本脚本即可同步；组本身不重复建）
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('tau','balance_type','B_low','B_high')), '[]')
WHERE `name` = '树搜索与负荷阈值';

UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` = 'eval_schema'), '[]')
WHERE `name` = '纯CHESCA 评估数据集';

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
              WHERE `param_name` IN ('TMP_max_reduction_percent','min_cool_per_c_overheat',
                    'min_cool_per_c_outdoor_gap','outdoor_gap_deadband_c',
                    'outdoor_floor_max_overheat_c','cooling_demand_feedforward_frac',
                    'demand_feedforward_only_when_overheat','outdoor_floor_allow_when_under_setpoint',
                    'clear_open_loop_floor_when_under_setpoint','use_lagged_dynamics_indoor',
                    'lagged_indoor_only_when_hotter','lagged_indoor_hotter_margin_c')), '[]')
WHERE `name` = '冷机';

-- ---------------------------------------------------------------------------
-- ⑤ 同步 is_member：CHESCA 的 45 个参数全部在组里（40 个原有 + 本脚本新增 5 个）
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `is_member` = 1
WHERE `param_name` LIKE 'price\_%'
   OR `param_name` IN (
        'tau','balance_type','B_low','B_high','eval_schema',
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
-- ⑥ 校验
-- ---------------------------------------------------------------------------
-- 6.1 每组多少个成员（>13 会不好用，目前最大 = 电价感知电池 13）
SELECT `id`, `name`,
       (LENGTH(`members`) - LENGTH(REPLACE(`members`, ',', '')) + 1) AS `member_count`
FROM `algorithm_param_config_set`
ORDER BY `member_count` DESC, `id`;

-- 6.2 CHESCA 的 45 个参数是否都进组了（应全部 is_member = 1、if_system = 0）
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `is_member`
FROM `algorithm_param_config`
WHERE `param_name` IN ('tau','balance_type','B_low','B_high','eval_schema')
   OR `param_name` LIKE 'price\_%'
   OR `param_name` IN ('min_soc_per_hour','max_soc_normal','max_soc_outage',
        'max_soc_reduction_in_outage','TMP_max_reduction_percent')
ORDER BY `is_member`, `if_system`, `id`;

-- 6.3 有没有"登记了但没进任何组"的 CHESCA 参数（应返回 0 行）
SELECT `id`, `name`, `param_name`, `if_system`
FROM `algorithm_param_config`
WHERE `is_member` = 0
  AND (`param_name` LIKE 'price\_%'
       OR `param_name` IN ('tau','balance_type','B_low','B_high','eval_schema',
            'min_soc_per_hour','max_soc_normal','max_soc_outage','max_soc_reduction_in_outage',
            'TMP_max_reduction_percent','min_cool_per_c_overheat','min_cool_per_c_outdoor_gap',
            'outdoor_gap_deadband_c','outdoor_floor_max_overheat_c','cooling_demand_feedforward_frac',
            'demand_feedforward_only_when_overheat','outdoor_floor_allow_when_under_setpoint',
            'clear_open_loop_floor_when_under_setpoint','use_lagged_dynamics_indoor',
            'lagged_indoor_only_when_hotter','lagged_indoor_hotter_margin_c',
            'post_outage_tmp_cap_enabled','post_outage_tmp_cap_steps','post_outage_tmp_max_start',
            'post_outage_tmp_ramp','post_outage_tmp_stagger','post_outage_soft_charge_enabled',
            'post_outage_relax_steps','post_outage_waive_min_soc','post_outage_max_ele_charge',
            'post_outage_forbid_charge_when_overheat','post_outage_overheat_c'));
