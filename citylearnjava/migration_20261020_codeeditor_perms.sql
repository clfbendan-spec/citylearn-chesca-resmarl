-- =============================================================================
-- 代码编辑器权限细化（2026-10-20）
--
-- 旧结构（2 条粗粒度）：
--   codeEditor:operate  执行 / 保存 / 新建 / 改名
--   codeEditor:delete   删除代码 / 删除执行记录
--
-- 新结构（6 条，全部挂在 menu:codeEditor 下）：
--   codeEditor:save          保存代码   （含新建脚本 / 脚本改名 / 文件简介 / 算法配置）
--   codeEditor:run           执行脚本   （含终止运行中的任务 / 续训开关）
--   codeEditor:deleteRecord  删除记录
--   codeEditor:renameRecord  记录改名   （模型优选的展示名称）
--   codeEditor:showRecord    记录展示   （展示 / 未展示）
--   codeEditor:deleteFile    删除脚本
--
-- 旧的两条**不删除、只置 enabled=0**：保留历史行便于追溯，且 enabled=0 后
-- 既不会出现在授权树里（UserService.listEnabledPermissions 过滤），也不能再被分配。
--
-- 幂等：重复执行结果一致（ON DUPLICATE KEY UPDATE + 回填前查重）。
-- 执行：mysql -uroot -p000000 --default-character-set=utf8mb4 citylearn < migration_20261020_codeeditor_perms.sql
-- =============================================================================

-- 1) 旧权限下线 --------------------------------------------------------------
UPDATE `permission` SET `enabled` = 0
WHERE `code` IN ('codeEditor:operate', 'codeEditor:delete');

-- 2) 新增 6 条 ---------------------------------------------------------------
-- sort_order 41~46：紧跟在菜单节点（40）后面，顺序与界面上的按钮一致
INSERT INTO `permission` (`id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`) VALUES
    ('p25', 'codeEditor:save',         '保存代码', 'menu:codeEditor', 41, 1),
    ('p26', 'codeEditor:run',          '执行脚本', 'menu:codeEditor', 42, 1),
    ('p27', 'codeEditor:deleteRecord', '删除记录', 'menu:codeEditor', 43, 1),
    ('p28', 'codeEditor:renameRecord', '记录改名', 'menu:codeEditor', 44, 1),
    ('p29', 'codeEditor:showRecord',   '记录展示', 'menu:codeEditor', 45, 1),
    ('p30', 'codeEditor:deleteFile',   '删除脚本', 'menu:codeEditor', 46, 1)
ON DUPLICATE KEY UPDATE
    `name`        = VALUES(`name`),
    `parent_code` = VALUES(`parent_code`),
    `sort_order`  = VALUES(`sort_order`),
    `enabled`     = 1;

-- 3) 存量授权回填 ------------------------------------------------------------
-- 原来有「执行/保存」的总开关 ⇒ 补 保存 + 执行；
-- 原来有「删除」的总开关   ⇒ 补 删除脚本 + 删除记录。
-- 用临时表承接待补清单，避免 INSERT ... SELECT 直接读目标表。
DROP TEMPORARY TABLE IF EXISTS `tmp_code_perm_backfill`;
CREATE TEMPORARY TABLE `tmp_code_perm_backfill` (
    `user_id`  varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
    `new_code` varchar(64) COLLATE utf8mb4_general_ci NOT NULL
);

INSERT INTO `tmp_code_perm_backfill` (`user_id`, `new_code`)
SELECT up.user_id, np.code
FROM `user_permission` up
JOIN `permission` op ON op.id = up.permission_id
JOIN `permission` np
  ON (op.code = 'codeEditor:operate' AND np.code IN ('codeEditor:save', 'codeEditor:run'))
  OR (op.code = 'codeEditor:delete'  AND np.code IN ('codeEditor:deleteFile', 'codeEditor:deleteRecord'));

INSERT INTO `user_permission` (`id`, `user_id`, `permission_id`, `create_time`)
SELECT REPLACE(UUID(), '-', ''), t.user_id, np.id, NOW()
FROM `tmp_code_perm_backfill` t
JOIN `permission` np ON np.code = t.new_code
LEFT JOIN `user_permission` ex
       ON ex.user_id = t.user_id AND ex.permission_id = np.id
WHERE ex.user_id IS NULL;

DROP TEMPORARY TABLE IF EXISTS `tmp_code_perm_backfill`;

-- 4) 校验 --------------------------------------------------------------------
-- 期望：codeEditor 下 6 条 enabled=1；旧 2 条 enabled=0
SELECT `id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`
FROM `permission`
WHERE `code` LIKE 'codeEditor:%'
ORDER BY `sort_order`, `id`;

SELECT COUNT(*) AS `codeEditor_enabled` FROM `permission`
WHERE `parent_code` = 'menu:codeEditor' AND `enabled` = 1;
