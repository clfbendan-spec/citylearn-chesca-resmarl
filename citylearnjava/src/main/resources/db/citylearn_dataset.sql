-- CityLearn 本地数据集目录（与 ResMARL / 原始数据页共用）
CREATE TABLE IF NOT EXISTS `citylearn_dataset` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `schema_key` VARCHAR(128) NOT NULL COMMENT 'CityLearn schema 目录名 / 选择值',
  `display_name` VARCHAR(255) NOT NULL COMMENT '前端展示名称',
  `relative_path` VARCHAR(512) NOT NULL COMMENT '相对 python-file-path 的目录路径',
  `building_count` INT NOT NULL DEFAULT 3 COMMENT '建筑数量',
  `time_steps` INT NULL DEFAULT NULL COMMENT '时间步数',
  `chesca_compatible` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否兼容 CHESCA',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否在选择列表中展示',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序（升序）',
  `description` VARCHAR(512) NULL DEFAULT NULL,
  `create_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_schema_key` (`schema_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `citylearn_dataset`
(`schema_key`, `display_name`, `relative_path`, `building_count`, `time_steps`, `chesca_compatible`, `enabled`, `sort_order`, `description`)
VALUES
('citylearn_challenge_2023_phase_2_local_evaluation', '2023 local（3栋·720步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_2_local_evaluation', 3, 720, 1, 1, 10, '默认本地评估集'),
('citylearn_challenge_2023_phase_2_online_evaluation_1', '2023 online_1（3栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_2_online_evaluation_1', 3, 2208, 1, 1, 20, NULL),
('citylearn_challenge_2023_phase_2_online_evaluation_2', '2023 online_2（3栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_2_online_evaluation_2', 3, 2208, 1, 1, 30, NULL),
('citylearn_challenge_2023_phase_2_online_evaluation_3', '2023 online_3（3栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_2_online_evaluation_3', 3, 2208, 1, 1, 40, NULL),
('citylearn_challenge_2023_phase_3_1', '2023 phase_3_1（6栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_3_1', 6, 2208, 1, 1, 50, NULL),
('citylearn_challenge_2023_phase_3_2', '2023 phase_3_2（6栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_3_2', 6, 2208, 1, 1, 60, NULL),
('citylearn_challenge_2023_phase_3_3', '2023 phase_3_3（6栋·2208步）✓ CHESCA', 'CHESCA-copy/data/schemas/citylearn_challenge_2023_phase_3_3', 6, 2208, 1, 1, 70, NULL),
('citylearn_challenge_2026_jul_sep', '2026 暑期 7–9月（3栋·2208步）✓ CHESCA · 基于 online_1', 'CHESCA-copy/data/schemas/citylearn_challenge_2026_jul_sep', 3, 2208, 1, 1, 80, NULL),
('citylearn_challenge_2026_from_2022', '2026 全年（3栋·8760步）✓ CHESCA · 2022底座+2023补全', 'CHESCA-copy/data/schemas/citylearn_challenge_2026_from_2022', 3, 8760, 1, 1, 90, NULL),
('citylearn_challenge_2022_phase_all', '2022 phase_all（17栋·8760步）✗ 仅 Multi-agent/NOCONTROL', 'CHESCA-main/data/schemas/citylearn_challenge_2022_phase_all', 17, 8760, 0, 1, 100, '仅电池动作，与 CHESCA 不兼容'),
('citylearn_challenge_2022_phase_1', '2022 phase_1（5栋·8760步）✗ 仅 Multi-agent/NOCONTROL', 'CHESCA-main/data/schemas/citylearn_challenge_2022_phase_1', 5, 8760, 0, 1, 110, NULL),
('citylearn_challenge_2022_phase_all_plus_evs', '2022 phase_all+EVs ✗ 仅 Multi-agent/NOCONTROL', 'CHESCA-main/data/schemas/citylearn_challenge_2022_phase_all_plus_evs', 17, 8760, 0, 1, 120, NULL),
('baeda_3dem', 'baeda_3dem（4栋·2928步）· 兼容性需实测', 'CHESCA-main/data/schemas/baeda_3dem', 4, 2928, 0, 1, 130, NULL)
ON DUPLICATE KEY UPDATE
  `display_name` = VALUES(`display_name`),
  `relative_path` = VALUES(`relative_path`),
  `building_count` = VALUES(`building_count`),
  `time_steps` = VALUES(`time_steps`),
  `chesca_compatible` = VALUES(`chesca_compatible`),
  `enabled` = VALUES(`enabled`),
  `sort_order` = VALUES(`sort_order`),
  `description` = VALUES(`description`);
