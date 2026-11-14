-- Register the parameters consumed by aacmadrl.task; safe to rerun.
-- The platform injects --train-task-id into pipeline evaluation cards automatically.
INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT '训练批次大小', 'train-batch-size', 'ratio',
       '[{"key":"128","value":"128"},{"key":"256","value":"256"}]',
       '每轮经验回放的批次大小。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'train-batch-size');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '随机种子', 'seed', 'num', '训练和评估使用的随机种子。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'seed');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT 'Actor 学习率', 'actor-lr', 'num', 'Actor 的学习率。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'actor-lr');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT '历史状态输入', 'history', 'ratio',
       '[{"key":"on","value":"开启"},{"key":"off","value":"关闭"}]',
       '是否使用历史状态特征。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'history');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT 'Actor 结构', 'actor-architecture', 'ratio',
       '[{"key":"building_heads","value":"共享编码器 + 分楼动作头"},{"key":"shared","value":"共享网络"}]',
       '选择共享策略或每栋楼独立动作头。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'actor-architecture');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT 'Critic 目标', 'critic-objective', 'ratio',
       '[{"key":"separate","value":"成本/舒适度分头"},{"key":"scalarized","value":"标量化"}]',
       '选择双目标分头或标量化价值目标。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'critic-objective');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '不适权重', 'discomfort-weight', 'num', '训练奖励中的不适权重。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'discomfort-weight');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '不适目标', 'discomfort-target', 'num', '模型筛选和舒适优先机制使用的目标比例，最大为 0.1。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'discomfort-target');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT '历史模型初始化', 'warm-start-anchor', 'ratio',
       '[{"key":"on","value":"开启"},{"key":"off","value":"关闭"}]',
       '是否从随算法包保存的已验证 anchor checkpoint 初始化。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'warm-start-anchor');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '行为 KL 惩罚', 'behavior-kl-penalty', 'num', '约束更新策略偏离 anchor 行为的强度。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'behavior-kl-penalty');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT '预热策略', 'warmup-policy', 'ratio',
       '[{"key":"uniform","value":"均匀随机"},{"key":"anchor_epsilon_greedy","value":"Anchor ε-greedy"}]',
       '经验回放预热阶段的动作采样策略。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'warmup-policy');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `default_value`, `desc`, `if_system`)
SELECT '每步优化次数', 'optimizer-updates-per-step', 'ratio',
       '[{"key":"1","value":"1"},{"key":"2","value":"2"}]',
       '每个环境步对应的优化器更新次数。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'optimizer-updates-per-step');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '训练步数', 'train-steps', 'num', '每轮训练转换步数；0 使用数据集完整范围。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'train-steps');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评估步数', 'eval-steps', 'num', '评估转换步数；0 使用数据集完整范围。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'eval-steps');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '训练起始步', 'simulation-start-time-step', 'num', '训练窗口起点；留空则从 schema 起始步开始。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'simulation-start-time-step');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评估起始步', 'evaluation-start-time-step', 'num', '评估窗口起点；留空则从 schema 起始步开始。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'evaluation-start-time-step');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评分 Alpha', 'score-alpha', 'num', 'Anchor 对比的分段不适惩罚权重；只在提供同数据集、同窗口的 anchor 结果时计算。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'score-alpha');

-- Build defaults from catalog/dataset IDs instead of assuming database auto-increment values.
SET @train_schema_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'train-schema' LIMIT 1);
SET @eval_schema_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'eval-schema' LIMIT 1);
SET @epochs_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'train-epochs' LIMIT 1);
SET @batch_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'train-batch-size' LIMIT 1);
SET @seed_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'seed' LIMIT 1);
SET @lr_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'actor-lr' LIMIT 1);
SET @history_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'history' LIMIT 1);
SET @actor_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'actor-architecture' LIMIT 1);
SET @critic_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'critic-objective' LIMIT 1);
SET @weight_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'discomfort-weight' LIMIT 1);
SET @target_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'discomfort-target' LIMIT 1);
SET @warm_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'warm-start-anchor' LIMIT 1);
SET @kl_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'behavior-kl-penalty' LIMIT 1);
SET @warmup_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'warmup-policy' LIMIT 1);
SET @updates_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'optimizer-updates-per-step' LIMIT 1);
SET @train_steps_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'train-steps' LIMIT 1);
SET @eval_steps_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'eval-steps' LIMIT 1);
SET @train_start_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'simulation-start-time-step' LIMIT 1);
SET @eval_start_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'evaluation-start-time-step' LIMIT 1);
SET @alpha_id = (SELECT id FROM `algorithm_param_config` WHERE `param_name` = 'score-alpha' LIMIT 1);
SET @local_id = (SELECT id FROM `citylearn_dataset` WHERE `schema_key` = 'citylearn_challenge_2023_phase_2_local_evaluation' LIMIT 1);
SET @online_id = (SELECT id FROM `citylearn_dataset` WHERE `schema_key` = 'citylearn_challenge_2023_phase_2_online_evaluation_1' LIMIT 1);

UPDATE `py_file`
SET `algorithm_config` = CONCAT('[{"type":"alone","params":[',
    '{"id":', @train_schema_id, ',"param_name":"train-schema","value":"', @local_id, '"},',
    '{"id":', @eval_schema_id, ',"param_name":"eval-schema","value":"', @online_id, '"},',
    '{"id":', @epochs_id, ',"param_name":"train-epochs","value":"5"},',
    '{"id":', @batch_id, ',"param_name":"train-batch-size","value":"256"},',
    '{"id":', @seed_id, ',"param_name":"seed","value":"49"},',
    '{"id":', @lr_id, ',"param_name":"actor-lr","value":"0.0001"},',
    '{"id":', @history_id, ',"param_name":"history","value":"on"},',
    '{"id":', @actor_id, ',"param_name":"actor-architecture","value":"shared"},',
    '{"id":', @critic_id, ',"param_name":"critic-objective","value":"separate"},',
    '{"id":', @weight_id, ',"param_name":"discomfort-weight","value":"1.0"},',
    '{"id":', @target_id, ',"param_name":"discomfort-target","value":"0.1"},',
    '{"id":', @warm_id, ',"param_name":"warm-start-anchor","value":"on"},',
    '{"id":', @kl_id, ',"param_name":"behavior-kl-penalty","value":"0.0"},',
    '{"id":', @warmup_id, ',"param_name":"warmup-policy","value":"uniform"},',
    '{"id":', @updates_id, ',"param_name":"optimizer-updates-per-step","value":"2"},',
    '{"id":', @train_steps_id, ',"param_name":"train-steps","value":"0"},',
    '{"id":', @eval_steps_id, ',"param_name":"eval-steps","value":"0"},',
    '{"id":', @alpha_id, ',"param_name":"score-alpha","value":"1.0"}',
    ']}]')
WHERE `file_name` = 'AACMADRL_train.py'
  AND (`algorithm_config` IS NULL OR TRIM(`algorithm_config`) = '');

UPDATE `py_file`
SET `algorithm_config` = CONCAT('[{"type":"alone","params":[',
    '{"id":', @train_schema_id, ',"param_name":"train-schema","value":"', @local_id, '"},',
    '{"id":', @eval_schema_id, ',"param_name":"eval-schema","value":"', @online_id, '"},',
    '{"id":', @eval_steps_id, ',"param_name":"eval-steps","value":"0"},',
    '{"id":', @alpha_id, ',"param_name":"score-alpha","value":"1.0"}',
    ']}]')
WHERE `file_name` = 'AACMADRL_eval.py'
  AND (`algorithm_config` IS NULL OR TRIM(`algorithm_config`) = '');

SELECT `file_name`, JSON_VALID(`algorithm_config`) AS `json_ok`,
       JSON_LENGTH(`algorithm_config`) AS `sections`
FROM `py_file`
WHERE `file_name` IN ('AACMADRL_train.py', 'AACMADRL_eval.py');
