-- ============================================================================
-- 2026-10-20 新增「操作级」权限
--   1) 任务管理：新建 / 编辑 / 删除 / 执行
--   2) 参数配置：单独配置（新建/编辑/删除）、配置组（新建/编辑/删除/移入/移出）
--
-- 说明：
--   · 权限树由 permission 表驱动（UserService.permissionTree），加行即生效，无需改代码列表。
--   · uk_permission_code 唯一键 ⇒ 用 ON DUPLICATE KEY UPDATE 保证可重复执行。
--   · cluster 节点（algorithmParam:item / algorithmParam:set）本身不控制任何按钮，
--     只是让「单独配置」和「配置组」在授权树里各成一组，避免 8 个动作挤成一排。
--   · 勾选子权限时后端会自动补齐上级（normalizePermissions），所以只勾子项也能用。
--
-- 执行：mysql -uroot -p000000 --default-character-set=utf8mb4 citylearn < migration_20261020_permission_actions.sql
-- ============================================================================

INSERT INTO `permission`
  (`id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`, `create_time`, `update_time`)
VALUES
  -- 任务管理
  ('p11', 'taskList:create', '新建任务', 'menu:taskList', 51, 1, NOW(), NOW()),
  ('p12', 'taskList:edit',   '编辑任务', 'menu:taskList', 52, 1, NOW(), NOW()),
  ('p13', 'taskList:delete', '删除任务', 'menu:taskList', 53, 1, NOW(), NOW()),
  ('p14', 'taskList:run',    '执行任务', 'menu:taskList', 54, 1, NOW(), NOW()),
  -- 参数配置 → 单独配置
  ('p15', 'algorithmParam:item',       '单独配置',   'menu:algorithmParam', 61, 1, NOW(), NOW()),
  ('p16', 'algorithmParam:itemCreate', '新建配置',   'algorithmParam:item', 62, 1, NOW(), NOW()),
  ('p17', 'algorithmParam:itemEdit',   '编辑配置',   'algorithmParam:item', 63, 1, NOW(), NOW()),
  ('p18', 'algorithmParam:itemDelete', '删除配置',   'algorithmParam:item', 64, 1, NOW(), NOW()),
  -- 参数配置 → 配置组
  ('p19', 'algorithmParam:set',          '配置组',     'menu:algorithmParam', 65, 1, NOW(), NOW()),
  ('p20', 'algorithmParam:setCreate',    '新建配置组', 'algorithmParam:set', 66, 1, NOW(), NOW()),
  ('p21', 'algorithmParam:setEdit',      '编辑配置组', 'algorithmParam:set', 67, 1, NOW(), NOW()),
  ('p22', 'algorithmParam:setDelete',    '删除配置组', 'algorithmParam:set', 68, 1, NOW(), NOW()),
  ('p23', 'algorithmParam:setMoveIn',    '移入配置组', 'algorithmParam:set', 69, 1, NOW(), NOW()),
  ('p24', 'algorithmParam:setMoveOut',   '移出配置组', 'algorithmParam:set', 70, 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `parent_code` = VALUES(`parent_code`),
  `sort_order` = VALUES(`sort_order`),
  `enabled` = VALUES(`enabled`),
  `update_time` = NOW();

-- 回归：把「已拥有菜单权限」的用户补上该菜单下的全部动作权限，避免升级后按钮凭空消失。
-- （超级管理员本来就有全部权限，这里排掉；只补两层：菜单 → 分组 → 动作。）
INSERT IGNORE INTO `user_permission` (`id`, `user_id`, `permission_id`, `create_time`)
SELECT REPLACE(UUID(), '-', ''), u.id, p.id, NOW()
FROM `user` u
JOIN `user_permission` up ON up.user_id = u.id
JOIN `permission` mp ON mp.id = up.permission_id
JOIN `permission` p ON p.parent_code = mp.code
                    OR p.parent_code IN (SELECT g.code FROM `permission` g WHERE g.parent_code = mp.code)
WHERE u.role <> 'SUPER_ADMIN'
  AND u.if_delete = 0
  AND mp.code IN ('menu:taskList', 'menu:algorithmParam');
