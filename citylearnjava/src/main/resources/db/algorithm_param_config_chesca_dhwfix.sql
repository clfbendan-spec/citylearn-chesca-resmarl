-- ============================================================================
-- 把「DHW 储能修复」开关登记进算法参数目录，并加入「片区尖峰削峰」配置组
-- ----------------------------------------------------------------------------
-- 背景（2026-10-15）
--   上游 CityLearn 的 building.py::update_dhw_storage 有一个 bug：它把动作乘到
--   `heating_storage.capacity` 上（本项目该值为 0），而不是 `dhw_storage.capacity`
--   ⇒ DHW（生活热水）储能整段恒为 no-op，热水储能能力从未被用上。
--   修复后（把容量换成 dhw_storage.capacity）即解锁热水储能，实测：
--     soft(5,6) + DHW-fix  local 峰值 12.119@0.643，越界④ +0.00pp（新基线 B）
--     soft(5,6)             local 峰值 12.705@0.643，越界④ +0.216pp（旧基线 A）
--
--   修复本身由**环境变量** CITYLEARN_DHW_STORAGE_FIX 门控（读于第三方库，
--   每次调用实时读）；为了让平台页面上也能开，CHESCA.py / CHESCA_ResMARL.py
--   新增 CLI 参数 `--dhw_storage_fix`，在**环境构造前**把它翻成该环境变量。
--   默认 false ⇒ 不设该变量 ⇒ 逐位等于上游 CityLearn（零侵入 ✓）。
--
-- 登记内容（name / param_name / value_type / 默认）
--   DHW 储能修复   dhw_storage_fix   bool   false
--
--   ⚠️ value_type=bool：配置弹窗按「true/false」下拉，Java 侧原样翻成
--      `--dhw_storage_fix true|false`（BaseDataService#resolveAlgorithmConfigArgs）。
--
-- 先决条件
--   db/algorithm_param_config_chesca_peak.sql 已执行（「片区尖峰削峰」组已存在，
--   成员为 id 71~79）。本脚本把 id=80 追加进该组的 members。
--
-- 说明
--   · if_system = 1（系统预置）：参数配置页里打「系统」标识，只能改简介、不能删。
--   · param_name 用**下划线**写法（= CHESCA.py 的 --选项名）。
--   · 可重复执行：登记用 WHERE NOT EXISTS；组的 members 每次重算覆盖。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_dhwfix.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- ① 登记 DHW 储能修复开关（bool）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT 'DHW 储能修复', 'dhw_storage_fix', 'bool', NULL, 1,
       '是否修复上游 CityLearn 的热水储能 bug。上游 update_dhw_storage 把动作乘到 '
       'heating_storage.capacity（本项目为 0）而非 dhw_storage.capacity ⇒ 热水储能恒为 no-op。'
       '打开后解锁热水储能，是本项目「新基线 B」的组成部分（local 峰值 12.119@0.643、'
       '舒适越界 +0.00pp）。关闭时逐位等于上游 CityLearn（零侵入）。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'dhw_storage_fix');

-- ---------------------------------------------------------------------------
-- ② 把 id=80 追加进「片区尖峰削峰」组的 members（重算覆盖，幂等）
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                    'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                    'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi',
                    'dhw_storage_fix')), '[]')
WHERE `name` = '片区尖峰削峰';

-- ---------------------------------------------------------------------------
-- ③ 同步 is_member（新键 + 原有 9 键全部在组里）
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config`
SET `is_member` = 1
WHERE `param_name` IN ('peak_trigger_mode','ns_spike_mult','rebound_window','rebound_cap',
                       'peak_battery_discharge_enabled','peak_battery_discharge_ele',
                       'peak_cut_graded_enabled','peak_cut_graded_m_lo','peak_cut_graded_m_hi',
                       'dhw_storage_fix');

-- ---------------------------------------------------------------------------
-- ④ 校验
-- ---------------------------------------------------------------------------
-- 4.1 dhw_storage_fix 已登记（应 1 行、if_system=1 / is_member=1）
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `is_member`
FROM `algorithm_param_config`
WHERE `param_name` = 'dhw_storage_fix';

-- 4.2 组 members 应有 10 个 id（71~79 + 80）
SELECT `id`, `name`, `members`
FROM `algorithm_param_config_set`
WHERE `name` = '片区尖峰削峰';
