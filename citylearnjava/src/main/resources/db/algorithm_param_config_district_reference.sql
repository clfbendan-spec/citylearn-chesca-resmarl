-- Append with an empty value to existing District train/eval cards.
-- Empty training uses legacy mode; empty evaluation inherits the checkpoint.
INSERT INTO algorithm_param_config
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `is_member`, `desc`, `create_time`)
SELECT
    '制冷理想负荷参考', 'cooling-reference-mode', 'ratio',
    '[{"key":"dataset_ideal","value":"旧版理想负荷参考"},{"key":"disabled","value":"关闭理想负荷参考"}]',
    0, 0,
    '仅District：清空时训练默认旧版、评估跟随模型。关闭后参考观测置零并使用固定动作映射，须匹配训练；不等于已实现共同信息访问白名单。',
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name = 'cooling-reference-mode'
);
