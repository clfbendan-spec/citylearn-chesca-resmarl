-- 权限定义表（可分配权限；用户管理不入库，仅超管）
CREATE TABLE IF NOT EXISTS `permission` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键',
  `code` VARCHAR(64) NOT NULL COMMENT '权限码',
  `name` VARCHAR(128) NOT NULL COMMENT '显示名称',
  `parent_code` VARCHAR(64) NULL DEFAULT NULL COMMENT '父权限码，空表示顶级',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序（升序）',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `create_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_permission_code` (`code`),
  KEY `idx_parent_code` (`parent_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='系统权限';

-- 用户-权限关联表
CREATE TABLE IF NOT EXISTS `user_permission` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键',
  `user_id` VARCHAR(32) NOT NULL COMMENT '用户 ID',
  `permission_id` VARCHAR(32) NOT NULL COMMENT '权限 ID',
  `create_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_permission` (`user_id`, `permission_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_permission_id` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户权限关联';

INSERT INTO `permission` (`id`, `code`, `name`, `parent_code`, `sort_order`, `enabled`) VALUES
('p01', 'menu:home', '首页（有菜单即全部权限）', NULL, 10, 1),
('p02', 'menu:recDashboard', '模型优选（有菜单即全部权限）', NULL, 20, 1),
('p03', 'menu:dataList', '原始数据', NULL, 30, 1),
('p04', 'menu:codeEditor', '代码编辑器', NULL, 40, 1),
('p05', 'codeEditor:operate', '操作（执行 / 保存 / 新建 / 改名等）', 'menu:codeEditor', 41, 1),
('p06', 'codeEditor:delete', '删除（删除代码文件 / 执行记录）', 'menu:codeEditor', 42, 1),
('p07', 'menu:resMarlConfig', 'CHESCA-ResMARL 配置', NULL, 50, 1),
('p08', 'resMarlConfig:operate', '操作（修改配置 / 保存 / 恢复默认）', 'menu:resMarlConfig', 51, 1)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `parent_code` = VALUES(`parent_code`),
  `sort_order` = VALUES(`sort_order`),
  `enabled` = VALUES(`enabled`);
