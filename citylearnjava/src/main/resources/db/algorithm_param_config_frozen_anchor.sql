-- Optional AAC evaluation source; leave off for ordinary training-task evaluation.
-- Append to AACMADRL_eval.py's existing card rather than replacing its parameters.
INSERT INTO algorithm_param_config
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `is_member`, `desc`, `create_time`)
SELECT
    '固定Anchor评估', 'frozen-anchor', 'ratio',
    '[{"key":"off","value":"关闭"},{"key":"on","value":"开启"}]', 0, 0,
    '仅AAC评估：开启后直接评估固定指纹的Anchor权重；清空训练模型及checkpoint。不会训练，也不会自动注册场景评分基准。',
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name = 'frozen-anchor'
);
