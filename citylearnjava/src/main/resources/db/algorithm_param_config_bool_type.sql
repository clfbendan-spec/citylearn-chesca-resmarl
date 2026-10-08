-- ============================================================================
-- 值类型新增 bool（布尔）并把开关类参数改过来
-- ----------------------------------------------------------------------------
-- 背景
--   上一批「电价感知电池」的 5 个 el-switch 参数之前是按「单选」登记的
--   （候选项 开启/关闭，key 是字符串 "true"/"false"）。这属于用单选的壳子凑布尔，
--   界面上多一个下拉、下游还要把字符串再转一次布尔。现在值类型里直接支持 bool：
--     · 参数配置页：值类型下拉多一项「布尔」，该类型不需要配候选项
--     · 代码编辑器「配置」弹窗：值这一列渲染成开关，落库是 JSON 布尔值 true / false
--
-- 本脚本做两件事
--   1) 更新 value_type 列注释，把 num/text/bool/ratio/multiple/special 写全
--   2) 把 5 个开关参数的 value_type 从 ratio 改为 bool，default_value 清成 NULL
--      （bool 不使用候选项 —— default_value 只服务 单选/多选）
--
-- 可重复执行：UPDATE 有 IN 限定，改完再跑结果不变。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_bool_type.sql
-- ============================================================================

ALTER TABLE `algorithm_param_config`
    MODIFY COLUMN `value_type` VARCHAR(32) NULL DEFAULT NULL
        COMMENT '值类型：num=数字；text=文字；bool=布尔；ratio=单选；multiple=多选（后两者候选项存 default_value）；special=数据集（历史值）；NULL=普通文本';

UPDATE `algorithm_param_config`
SET `value_type` = 'bool',
    `default_value` = NULL
WHERE `param_name` IN (
    'price_aware_battery_enabled',
    'price_high_forbid_charge',
    'price_high_force_discharge',
    'price_global_reserve_enabled',
    'price_low_search_boost'
);

-- 校验：确认这 5 个开关已改成 bool 且候选项已清空
SELECT `id`, `name`, `param_name`, `value_type`, `default_value`
FROM `algorithm_param_config`
WHERE `param_name` IN (
    'price_aware_battery_enabled',
    'price_high_forbid_charge',
    'price_high_force_discharge',
    'price_global_reserve_enabled',
    'price_low_search_boost'
)
ORDER BY `id`;

-- 值类型分布：确认库里已无「本该 bool 却在用 ratio」的开关
SELECT `value_type`, COUNT(*) AS `cnt`
FROM `algorithm_param_config`
GROUP BY `value_type`
ORDER BY `value_type`;
