-- ============================================================================
-- 值类型新增 map（键值对）所需的两列：key_alias / value_alias
-- ----------------------------------------------------------------------------
-- 背景
--   前面已支持 num / text / bool / ratio / multiple / special 六种值类型，
--   它们都只描述「一个值」。但有些参数天然是「一组键值对」，最典型的是
--   min_soc_per_hour —— 24 个小时各自一个 SOC 下限。
--
-- 新值类型 map
--   · 键值对本身仍存在 default_value 列（与 单选/多选 同构的 JSON 数组）：
--       [{"key":"0","value":"0.6"},{"key":"1","value":"0.65"}, ...]
--   · 额外用两列描述「键叫什么、值叫什么」，让界面不再出现生硬的 key/value：
--       key_alias   —— 键的别名，如「选择时段」
--       value_alias —— 值的别名，如「电池 SOC 下限」
--   · 参数自身的 desc 就是这组键值对的简介。
--   其它值类型这两列为 NULL。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_map_type.sql
--
-- ⚠️ ALTER 只需执行一次，重复执行会报 Duplicate column name，跳过继续即可。
-- ============================================================================

ALTER TABLE `algorithm_param_config`
    ADD COLUMN `key_alias` VARCHAR(64) NULL DEFAULT NULL
        COMMENT '值类型为 map 时，键的别名（如「选择时段」）；其它类型为 NULL',
    ADD COLUMN `value_alias` VARCHAR(64) NULL DEFAULT NULL
        COMMENT '值类型为 map 时，值的别名（如「电池 SOC 下限」）；其它类型为 NULL';

SHOW COLUMNS FROM `algorithm_param_config`;
