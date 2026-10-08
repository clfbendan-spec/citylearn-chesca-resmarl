-- ============================================================================
-- 参数配置页（algorithm_param_config）增补
-- ----------------------------------------------------------------------------
-- 1) 新增 default_value：值类型为「单选(ratio) / 多选(multiple)」时，存可选项。
--    JSON 数组，元素形如 {"key":"high","value":"高峰"}：
--      key   —— 存进 py_file.algorithm_config 里 value 的真实取值
--      value —— 界面上显示的文字
--    例：[{"key":"1","value":"方案一"},{"key":"2","value":"方案二"}]
--    值类型为 num / text（以及历史上的 special）时该列为 NULL。
--
-- 2) 新增「参数配置」菜单权限：menu:algorithmParam
--    · SUPER_ADMIN 自动拥有全部已启用权限，用 admin 登录无需授权即可看到菜单。
--    · 其它角色需在「用户管理」里勾选，或放开文件末尾那段可选 SQL。
--    · sort_order = 55：排在「CHESCA-ResMARL 配置」(50) 之后。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_value.sql
--
-- ⚠️ ALTER 那句只需执行一次，重复执行会报 Duplicate column name，跳过即可；
--    后面的 INSERT 是幂等的，可重复执行。
-- ============================================================================

ALTER TABLE `algorithm_param_config`
    ADD COLUMN `default_value` TEXT NULL
        COMMENT '单选(ratio)/多选(multiple)的可选项，JSON 数组：[{"key":"..","value":".."}]';

INSERT INTO `permission` (`id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`)
VALUES ('p10', 'menu:algorithmParam', '参数配置', NULL, 55, 1)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `parent_code` = VALUES(`parent_code`),
  `sort_order` = VALUES(`sort_order`),
  `enabled` = VALUES(`enabled`);

-- 【可选】把该菜单授予 admin2（ADMIN 角色）。
-- 默认不执行：按最小授权原则，请用「用户管理」界面按需勾选；如需直接放开，去掉注释即可。
-- INSERT INTO `user_permission` (`id`, `user_id`, `permission_id`, `create_time`)
-- SELECT REPLACE(UUID(), '-', ''), u.id, 'p10', NOW()
-- FROM `user` u
-- WHERE u.username = 'admin2'
--   AND NOT EXISTS (
--     SELECT 1 FROM `user_permission` up
--     WHERE up.user_id = u.id AND up.permission_id = 'p10'
--   );

-- 校验
SELECT `id`, `name`, `param_name`, `value_type`, `default_value`, `if_system`, `create_time`
FROM `algorithm_param_config` ORDER BY `id`;

SELECT `id`, `code`, `name`, `sort_order`, `enabled`
FROM `permission`
ORDER BY `sort_order`, `id`;
