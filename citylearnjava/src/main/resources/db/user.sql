-- 系统用户表（超管 / 系统管理员）
CREATE TABLE IF NOT EXISTS `user` (
  `id` VARCHAR(32) NOT NULL COMMENT '主键',
  `username` VARCHAR(64) NOT NULL COMMENT '登录用户名',
  `password` VARCHAR(128) NOT NULL COMMENT '登录密码',
  `nickname` VARCHAR(64) NULL DEFAULT NULL COMMENT '显示名称',
  `role` VARCHAR(32) NOT NULL COMMENT '角色：SUPER_ADMIN=超管，ADMIN=系统管理员',
  `if_delete` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '删除标记',
  `create_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='系统用户';

-- 默认超管：admin / 000000
INSERT INTO `user` (`id`, `username`, `password`, `nickname`, `role`, `if_delete`, `create_time`, `update_time`)
VALUES ('1', 'admin', '000000', 'Admin', 'SUPER_ADMIN', 0, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  `password` = VALUES(`password`),
  `nickname` = VALUES(`nickname`),
  `role` = VALUES(`role`),
  `if_delete` = 0;
