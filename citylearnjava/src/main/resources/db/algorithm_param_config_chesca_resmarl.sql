-- ============================================================================
-- CHESCA-ResMARL 作为「评估算法」：参数登记 + 脚本配置清单（2026-10-08）
-- ----------------------------------------------------------------------------
-- 目标（使用者要求）
--   1. 代码编辑器里 CHESCA_ResMARL.py 的「配置」清单 = CHESCA.py 的那一份，另加 3 个参数：
--        residual_alpha / residual_action_mask / resmarl_after_safety
--   2. 任务管理页能把 CHESCA_ResMARL.py 选为**评估算法**，把前置 Multi-agent-train 的模型传过去
--      （平台评估卡固定注入 train-task-id，脚本据此到 <任务id>-train/checkpoints/ 下找模型）。
--
-- 本脚本做四件事
--   A. algorithm_param_config：登记残差三项
--   B. algorithm_param_config_set：新建「CHESCA-ResMARL 残差」组（收这 3 个参数），并同步 is_member
--   C. py_file：确保 CHESCA_ResMARL.py 那一行存在、是 eval 类型且对外可见
--   D. py_file.algorithm_config：把 CHESCA.py 的参数清单整份复制过来，再追加「残差」组那张卡
--
-- 参数名 = 命令行选项名（下划线写法），Java 翻成 `--参数名 值` 传给脚本。
--
-- 配套（不在本文件里，属代码改动）
--   · BaseDataService.ALGORITHM_CONFIG_CLI_WHITELIST 增加 chesca_resmarl.py 条目
--     （= chescaCommon + marl_mode / residual_alpha / residual_action_mask /
--      resmarl_after_safety / multi_agent_checkpoint / train-task-id），
--     并且 CHESCA 系列都不再传 --min-soc-config；
--   · 脚本 CHESCA_ResMARL.py 已改造成与 CHESCA.py 同构的入口（参数表逐项对应）。
--
-- 可重复执行
--   · A/B/C 用 WHERE NOT EXISTS 或"仅在缺失时"更新；
--   · D 只在目标行还没有这张卡时重建 ⇒ 不会覆盖使用者在弹窗里改过的取值。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_resmarl.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- A. 登记残差三项
--    value_type 决定配置弹窗用哪个控件：
--      num → 数字输入框；bool → 开关；map → 键值对子弹窗
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`, `is_member`)
SELECT '残差强度 α', 'residual_alpha', 'num', '0.15', 0,
       'CHESCA-ResMARL 残差强度：a_final = (1-α)·a_CHESCA + α·a_SAC（0~1；设 0 等价于纯 CHESCA）',
       NOW(), 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'residual_alpha');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`,
     `key_alias`, `value_alias`, `is_member`)
SELECT '残差动作掩码', 'residual_action_mask', 'map',
       '[{"key":"dhw","value":"false"},{"key":"ele","value":"true"},{"key":"tmp","value":"false"}]',
       0,
       '逐维掩码（键取 dhw / ele / tmp，值为 true/false）：值为 false 的维度保持 CHESCA 原值，'
       '只让被放行的维度接受 SAC 修正。默认只放行 ele（电池充放电）。',
       NOW(), '维度', '是否放行', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'residual_action_mask');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`, `is_member`)
SELECT '安全审查后叠加残差', 'resmarl_after_safety', 'bool', 'true', 0,
       'true（默认）= 先做安全审查（动作上下限裁剪），再叠加 SAC 残差；false = 先叠加再审查。'
       '两种顺序会给出不同的 a_final，做消融时才需要改成 false。',
       NOW(), 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'resmarl_after_safety');

-- ---------------------------------------------------------------------------
-- B. 新建「CHESCA-ResMARL 残差」配置组（members 由 param_name 反查 id 算出，不依赖自增 id）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config_set` (`create_time`, `name`, `desc`, `members`)
SELECT NOW(), 'CHESCA-ResMARL 残差',
       'CHESCA 规则控制之上叠加 Multi-Agent SAC 修正所需的三个参数（模型来源由平台注入 train-task-id）',
       COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
                 WHERE `param_name` IN ('residual_alpha','residual_action_mask','resmarl_after_safety')), '[]')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = 'CHESCA-ResMARL 残差');

-- 成员变更后重算一次（幂等）
UPDATE `algorithm_param_config_set` SET `members` =
    COALESCE((SELECT CONCAT('[', GROUP_CONCAT(`id` ORDER BY `id`), ']') FROM `algorithm_param_config`
              WHERE `param_name` IN ('residual_alpha','residual_action_mask','resmarl_after_safety')), '[]')
WHERE `name` = 'CHESCA-ResMARL 残差';

UPDATE `algorithm_param_config` SET `is_member` = 1
WHERE `param_name` IN ('residual_alpha','residual_action_mask','resmarl_after_safety');

-- ---------------------------------------------------------------------------
-- C. py_file：确保 CHESCA_ResMARL.py 那一行存在、是 eval、对外可见
--    （script_type='eval' 才会出现在任务管理页「评估算法」下拉与代码编辑器的「配置」按钮上）
-- ---------------------------------------------------------------------------
INSERT INTO `py_file` (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`,
                       `name`, `if_show`, `script_type`)
SELECT '7', 'CHESCA_ResMARL.py', 'CHESCA-ResMARL 混合评估（CHESCA 规则 + Multi-Agent SAC 残差）',
       1, NOW(), 'admin', 'CHESCA-ResMARL', 1, 'eval'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'CHESCA_ResMARL.py');

UPDATE `py_file`
SET `name` = 'CHESCA-ResMARL',
    `description` = 'CHESCA-ResMARL 混合评估（CHESCA 规则 + Multi-Agent SAC 残差）',
    `script_type` = 'eval',
    `if_show` = 1
WHERE `file_name` = 'CHESCA_ResMARL.py';

-- ---------------------------------------------------------------------------
-- D. 参数清单：CHESCA.py 的那一份 + 追加「CHESCA-ResMARL 残差」组
--    值写法与 CHESCA.py 那份保持一致（num 存字符串 / bool 存 JSON 布尔 / map 存 JSON 字符串）：
--      · map 的值必须是「JSON 字符串」⇒ 用 JSON_QUOTE 生成 "[{\"key\":\"dhw\",...}]"
--      · 只在目标行还没有这张卡时重建 ⇒ 使用者后来在弹窗里改的取值不会被本脚本覆盖
-- ---------------------------------------------------------------------------
SET @resmarl_set_id := (SELECT `id` FROM `algorithm_param_config_set`
                        WHERE `name` = 'CHESCA-ResMARL 残差' LIMIT 1);
SET @id_alpha := (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'residual_alpha' LIMIT 1);
SET @id_mask  := (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'residual_action_mask' LIMIT 1);
SET @id_after := (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'resmarl_after_safety' LIMIT 1);
SET @mask_json := JSON_QUOTE('[{"key":"dhw","value":"false"},{"key":"ele","value":"true"},{"key":"tmp","value":"false"}]');

SET @base_cfg := (SELECT TRIM(`algorithm_config`) FROM `py_file` WHERE `file_name` = 'CHESCA.py' LIMIT 1);
SET @card := CONCAT(
    '{"type":"set","set_id":', @resmarl_set_id, ',"params":[',
        '{"id":', @id_alpha, ',"param_name":"residual_alpha","value":"0.15"},',
        '{"id":', @id_mask,  ',"param_name":"residual_action_mask","value":', @mask_json, '},',
        '{"id":', @id_after, ',"param_name":"resmarl_after_safety","value":true}',
    ']}');

UPDATE `py_file`
SET `algorithm_config` = CONCAT(LEFT(@base_cfg, CHAR_LENGTH(@base_cfg) - 1), ',', @card, ']')
WHERE `file_name` = 'CHESCA_ResMARL.py'
  AND @base_cfg IS NOT NULL
  AND CHAR_LENGTH(@base_cfg) > 10
  AND RIGHT(@base_cfg, 1) = ']'
  -- 只在还没有这张卡时重建（用 JSON 判存在，避免 LIKE 在不同客户端上的字串校对规则冲突）
  AND (`algorithm_config` IS NULL
       OR JSON_CONTAINS(`algorithm_config`, CONCAT('{"set_id": ', @resmarl_set_id, '}')) = 0);

-- ---------------------------------------------------------------------------
-- E. 校验
-- ---------------------------------------------------------------------------
-- E.1 三个参数是否登记齐全（应 3 行，且 is_member = 1）
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `is_member`
FROM `algorithm_param_config`
WHERE `param_name` IN ('residual_alpha','residual_action_mask','resmarl_after_safety')
ORDER BY `id`;

-- E.2 两个入口的配置清单各有多少参数、各有哪些卡（CHESCA.py 45 个 / CHESCA-ResMARL 应为 48 个）
SELECT `file_name`, `script_type`, `if_show`, CHAR_LENGTH(`algorithm_config`) AS cfg_len
FROM `py_file` WHERE `file_name` IN ('CHESCA.py','CHESCA_ResMARL.py');

-- E.3 CHESCA-ResMARL 的清单里是否包含那三张参数（应 3 行）
SELECT p.`file_name`, jt.`param_name`, jt.`value`
FROM `py_file` p,
     JSON_TABLE(p.`algorithm_config`, '$[*].params[*]'
                COLUMNS (`param_name` VARCHAR(64) PATH '$.param_name',
                         `value` VARCHAR(512) PATH '$.value')) AS jt
WHERE p.`file_name` = 'CHESCA_ResMARL.py'
  AND jt.`param_name` IN ('residual_alpha','residual_action_mask','resmarl_after_safety');
