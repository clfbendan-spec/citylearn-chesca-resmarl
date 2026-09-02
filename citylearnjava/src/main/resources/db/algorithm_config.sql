-- CHESCA 算法通用配置表（键值存储，便于扩展更多参数）
-- min_soc_per_hour / max_soc_normal / max_soc_outage 均存储在本表，不再使用 battery_min_soc_hour 表
CREATE TABLE IF NOT EXISTS `algorithm_config` (
  `config_key` VARCHAR(64) NOT NULL COMMENT '配置键',
  `config_value` TEXT NOT NULL COMMENT '配置值',
  `value_type` VARCHAR(16) NOT NULL DEFAULT 'string' COMMENT 'number|json|string',
  `description` VARCHAR(255) NULL DEFAULT NULL COMMENT '说明',
  `update_time` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 默认与 CHESCA-copy/checa/agent.py 内置值一致
INSERT INTO `algorithm_config` (`config_key`, `config_value`, `value_type`, `description`, `update_time`) VALUES
('min_soc_per_hour', '{"0":0.6,"1":0.65,"2":0.72,"3":0.78,"4":0.8,"5":0.85,"6":0.8,"7":0.75,"8":0.7,"9":0.6,"10":0.5,"11":0.6,"12":0.65,"13":0.65,"14":0.7,"15":0.7,"16":0.7,"17":0.65,"18":0.7,"19":0.6,"20":0.6,"21":0.6,"22":0.6,"23":0.55}', 'json', '24小时电池SOC下限', NOW()),
('max_soc_normal', '0.99', 'number', '正常时段电池SOC上限', NOW()),
('max_soc_outage', '0.87', 'number', '停电时段电池SOC上限', NOW()),
('max_soc_reduction_in_outage', '0.70', 'number', '停电时最大SOC降幅', NOW()),
('b_low', '1.18', 'number', '负荷平衡增负荷阈值系数B_low', NOW()),
('b_high', '1.0', 'number', '负荷平衡减负荷阈值系数B_high', NOW()),
('tmp_max_reduction_percent', '0.0', 'number', '冷机最大削减比例TMP_max_reduction_percent', NOW()),
('tau', '1', 'number', '预测优化步长tau', NOW()),
('balance_type', 'C', 'string', '电池树搜索适应度类型balance_type', NOW()),
('resmarl_enabled', 'false', 'string', '是否启用 CHESCA-ResMARL', NOW()),
('marl_mode', 'none', 'string', 'MARL 模式：none / multi_agent', NOW()),
('multi_agent_train_epochs', '20', 'number', 'Multi-Agent SAC 训练轮数', NOW()),
('multi_agent_explore', 'false', 'string', 'Multi-Agent 评估时是否开启 explore', NOW()),
('residual_alpha', '0.0', 'number', 'CHESCA-ResMARL 残差强度 α∈[0,1]', NOW()),
('residual_action_mask', '{"dhw":false,"ele":true,"tmp":false}', 'json', 'CHESCA-ResMARL 可修正动作维 mask', NOW()),
('resmarl_after_safety', 'true', 'string', '残差是否在安全审查之后施加', NOW()),
('schema_split_enabled', 'true', 'string', '是否启用训测 schema 分离（方案 A）', NOW()),
('train_schema', 'citylearn_challenge_2023_phase_2_local_evaluation', 'string', 'Multi-Agent SAC 训练 schema', NOW()),
('eval_schema', 'citylearn_challenge_2023_phase_2_online_evaluation_1', 'string', 'CHESCA 仿真/KPI 评估 schema', NOW())
ON DUPLICATE KEY UPDATE
  `config_value` = VALUES(`config_value`),
  `value_type` = VALUES(`value_type`),
  `description` = VALUES(`description`);
