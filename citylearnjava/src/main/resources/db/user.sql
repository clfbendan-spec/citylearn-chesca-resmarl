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

-- 默认超管：admin / 000000（库里存的是 bcrypt 哈希，明文口令见此行注释）
-- 哈希 = bcrypt(cost 10) + 随机盐，格式 '{bcrypt}$2a$10$...'，长 68 字符。
-- ⚠️ ON DUPLICATE 里**故意不再带 password**：否则重跑本脚本会把用户自己改过的口令
--    重置回 000000（历史上就是这么写的，属于隐性坑）。
INSERT INTO `user` (`id`, `username`, `password`, `nickname`, `role`, `if_delete`, `create_time`, `update_time`)
VALUES ('1', 'admin', '{bcrypt}$2a$10$hPyWJFln/aq3.vlCq2/LfOgMeJqZrPQ/jjwtmRFfOpixwXogdh8b.', 'Admin', 'SUPER_ADMIN', 0, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  `nickname` = VALUES(`nickname`),
  `role` = VALUES(`role`),
  `if_delete` = 0;
