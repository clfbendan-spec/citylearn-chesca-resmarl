-- ============================================================================
-- 新增「任务记录」菜单权限：menu:taskList
-- ----------------------------------------------------------------------------
-- 背景
--   新增一个「任务记录」菜单，集中展示所有代码执行记录（时间倒序），
--   列为：代码名称 / 运行开始时间 / 运行状态 / 操作【详情】。
--   点「详情」跳转到代码编辑器并打开该任务所属脚本的记录页。
--
-- 权限说明
--   · SUPER_ADMIN 自动拥有全部已启用权限（见 UserService.listUserPermissionCodes），
--     所以用 admin 登录无需任何授权即可看到该菜单。
--   · 其它角色需在「用户管理」里勾选，或放开下面那段可选 SQL。
--   · sort_order = 45：排在「代码编辑器」(40) 之后、「CHESCA-ResMARL 配置」(50) 之前。
-- ============================================================================

INSERT INTO `permission` (`id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`)
VALUES ('p09', 'menu:taskList', '任务记录', NULL, 45, 1)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `parent_code` = VALUES(`parent_code`),
  `sort_order` = VALUES(`sort_order`),
  `enabled` = VALUES(`enabled`);

-- 【可选】把该菜单授予 admin2（ADMIN 角色）。
-- 默认不执行：按最小授权原则，请用「用户管理」界面按需勾选；如需直接放开，去掉注释即可。
-- INSERT INTO `user_permission` (`id`, `user_id`, `permission_id`, `create_time`)
-- SELECT REPLACE(UUID(), '-', ''), u.id, 'p09', NOW()
-- FROM `user` u
-- WHERE u.username = 'admin2'
--   AND NOT EXISTS (
--     SELECT 1 FROM `user_permission` up
--     WHERE up.user_id = u.id AND up.permission_id = 'p09'
--   );

-- 校验：确认新权限已登记
SELECT `id`, `code`, `name`, `sort_order`, `enabled`
FROM `permission`
ORDER BY `sort_order`, `id`;
