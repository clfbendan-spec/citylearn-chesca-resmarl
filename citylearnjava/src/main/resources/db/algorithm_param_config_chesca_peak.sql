-- ============================================================================
-- 把「片区尖峰削峰」结构层的 9 个参数登记进算法参数目录，并单独成组
-- ----------------------------------------------------------------------------
-- 背景（2026-10-11 · P2）
--   CHESCA 的削峰由「净负荷阈值」演进为「片区实测不可调负荷尖峰触发 + 电池让路 + 分级削峰」，
--   checa/agent.py 的 default_params 因此新增 9 个键。它们此前只能改源码或直接传命令行，
--   配置页 / 代码编辑器「配置」弹窗里看不到 ⇒ 本脚本把它登记进参数目录并单独成组。
--
-- 登记内容（name / param_name / value_type / 默认）
--   削峰触发信号口径        peak_trigger_mode              ratio  net|ns_spike|district_spike
--   尖峰判据倍数            ns_spike_mult                  num    3.0
--   回弹抑制窗口            rebound_window                 num    0
--   回弹限幅系数            rebound_cap                    num    1.0
--   触发步电池满放          peak_battery_discharge_enabled bool   false
--   满放 ELE 幅度           peak_battery_discharge_ele     num    -1.0
--   分级削峰开关            peak_cut_graded_enabled        bool   false
--   分级带宽下沿            peak_cut_graded_m_lo           num    5.0
--   分级带宽上沿            peak_cut_graded_m_hi           num    6.0
--
-- 口径与 checa/agent.py 的 default_params、utils/ches_config.py 的 DEFAULTS **逐字一致**
--   ⇒ 只改注释 / 登记定义，不改变任何默认行为。
--   ⚠️ peak_trigger_mode / ns_spike_mult 是「触发信号」本身；其余 7 个都是
--      peak_trigger_mode='district_spike' 的**修饰开关**（其它模式下静默 no-op）。
--
-- 推荐部署值（见《CHESCA-P0官方口径定论.md》）——本脚本**只登记定义与默认值**，
--   推荐值请在配置页按需改：
--     peak_trigger_mode = district_spike · ns_spike_mult = 6.0 · TMP_max_reduction_percent = 1.0
--     peak_battery_discharge_enabled = true · price_aware_battery_enabled = false
--     peak_cut_graded_enabled = true · peak_cut_graded_m_lo = 5.0 · peak_cut_graded_m_hi = 6.0
--
-- 说明
--   · if_system = 1（系统预置）：参数配置页里打「系统」标识，只能改简介、不能删。
--   · param_name 用**下划线**写法（= chesca_agent_config.json 的字段名 = CHESCA.py 的 --选项名）。
--   · ratio 的 key 一律是字符串（"net" 而非裸标识符），否则下拉框选不中。
--   · 可重复执行：登记用 WHERE NOT EXISTS；组的 members 每次重算覆盖。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_peak.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- ① 削峰触发信号口径（单选）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '削峰触发信号口径', 'peak_trigger_mode', 'ratio',
       '[{"key":"net","value":"net — 预测净负荷超阈值（旧行为）"},{"key":"ns_spike","value":"ns_spike — 单栋实测不可调负荷尖峰"},{"key":"district_spike","value":"district_spike — 片区实测不可调负荷尖峰（推荐）"}]',
       1,
       '决定「什么时候削峰」：net=预测净负荷超自身历史均值+B_high×σ（旧口径，实测已退化）；'
       'ns_spike=某栋当步实测不可调负荷 > ns_spike_mult×其历史均值；'
       'district_spike=全片区当步不可调负荷之和 > ns_spike_mult×其历史均值（推荐）。'
       '后两种是纯因果、无前瞻的判据；下面 7 个修饰参数只在 district_spike 下生效。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_trigger_mode');

-- ---------------------------------------------------------------------------
-- ② 尖峰判据倍数（num）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '尖峰判据倍数', 'ns_spike_mult', 'num', NULL, 1,
       '尖峰判据的倍数门槛：实测不可调负荷 > 该倍数 × 历史均值即触发削峰。'
       '默认 3.0；本数据集经 P0 重标定后推荐 6.0（只削真尖峰，舒适代价最小）。倍数越大越少触发。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'ns_spike_mult');

-- ---------------------------------------------------------------------------
-- ③ 回弹抑制窗口 / 限幅系数（num ×2）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '回弹抑制窗口', 'rebound_window', 'num', NULL, 1,
       '削峰触发步之后的多少步内，把制冷动作压到「触发前基准 × rebound_cap」，'
       '抑制控制器把开度补回造成的过冷超调。默认 0 = 关闭本机制（与旧行为逐位一致）。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'rebound_window');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '回弹限幅系数', 'rebound_cap', 'num', NULL, 1,
       '回弹抑制窗口内制冷动作相对「触发步削峰前动作」的限幅系数（0~2，默认 1.0 = 不限幅）。'
       '仅当 rebound_window > 0 时生效。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'rebound_cap');

-- ---------------------------------------------------------------------------
-- ④ 触发步电池满放（bool + num）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '触发步电池满放', 'peak_battery_discharge_enabled', 'bool', NULL, 1,
       'district_spike 触发步是否把所有楼的电池 ELE 动作拉到最大放电（默认关闭）。'
       '⚠️ 电池杠杆只在「触发步电池有电」时有效：若价格感知电池开着（price_aware_battery_enabled），'
       '线上数据集上它可能把 SOC 提前抽干 ⇒ 表现为 +0.00% 的 no-op，需同时关掉价格感知。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_battery_discharge_enabled');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '满放 ELE 幅度', 'peak_battery_discharge_ele', 'num', NULL, 1,
       '触发步电池 ELE 动作幅度，取值 [-1, 1]，默认 -1.0 = 单步最大放电。'
       '仅当 peak_battery_discharge_enabled = true 时生效。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_battery_discharge_ele');

-- ---------------------------------------------------------------------------
-- ⑤ 分级削峰（bool + num ×2）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '分级削峰开关', 'peak_cut_graded_enabled', 'bool', NULL, 1,
       '把 0/1 硬削换成连续分级：pct = TMP_max_reduction_percent × clip((r−m_lo)/(m_hi−m_lo), 0, 1)，'
       'r = 片区当步不可调负荷 / 其运行均值。默认关闭（走硬阈值，与旧行为逐位一致）。'
       '电池仍只在 r ≥ m_hi（pct 打满）时满放。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_cut_graded_enabled');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '分级带宽下沿', 'peak_cut_graded_m_lo', 'num', NULL, 1,
       '分级削峰触发带的下沿 m_lo：r ≤ m_lo 完全不削。默认 5.0 —— 这是本数据集经官方 evaluate() '
       '重标定出的拐点（放到 4/3 会多削中尖峰，舒适代价与收益不成比例）。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_cut_graded_m_lo');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '分级带宽上沿', 'peak_cut_graded_m_hi', 'num', NULL, 1,
       '分级削峰触发带的上沿 m_hi：r ≥ m_hi 满削（pct = TMP_max_reduction_percent），'
       '且电池同此门槛满放。默认 6.0。须 > m_lo。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak_cut_graded_m_hi');

-- ---------------------------------------------------------------------------
-- ⑥ 新建配置组「片区尖峰削峰」并重算 members
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), '片区尖峰削峰',
       '片区不可调负荷尖峰触发削峰，以及电池让路、分级削峰、回弹抑制等修饰开关',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                       'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                       'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '片区尖峰削峰');

-- 题名若有微调，重跑本脚本即同步（组本身不重复建）
UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                    'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                    'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi')), '[]')
WHERE `name` = '片区尖峰削峰';

-- ---------------------------------------------------------------------------
-- ⑦ 同步 is_member：这 9 个参数全部在组里
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `is_member` = 1
WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                       'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                       'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi');

-- ---------------------------------------------------------------------------
-- ⑧ 校验
-- ---------------------------------------------------------------------------
-- 8.1 9 条都已登记（应 9 行、全部 if_system=1 / is_member=1）
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `is_member`
FROM `algorithm_param_config`
WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                       'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                       'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi')
ORDER BY `id`;

-- 8.2 「片区尖峰削峰」组应有 9 个成员
SELECT `id`, `name`,
       (LENGTH(`members`) - LENGTH(REPLACE(`members`, ',', '')) + 1) AS `member_count`
FROM `algorithm_param_config_set`
WHERE `name` = '片区尖峰削峰';

-- 8.3 全库组规模（确认没有 >13 的组冒出来）
SELECT `id`, `name`,
       (LENGTH(`members`) - LENGTH(REPLACE(`members`, ',', '')) + 1) AS `member_count`
FROM `algorithm_param_config_set`
ORDER BY `member_count` DESC, `id`;

-- 8.4 有无「登记了却没进任何组」的尖峰参数（应返回 0 行）
SELECT `id`, `name`, `param_name`, `if_system`
FROM `algorithm_param_config`
WHERE `is_member` = 0
  AND `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                       'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                       'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi');
