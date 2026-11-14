-- Optional District outage seed. Empty invocation preserves schema settings.
-- Add this catalog entry to the existing train/eval cards with an empty value.
INSERT INTO algorithm_param_config
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `is_member`, `desc`, `create_time`)
SELECT
    '停电模型种子覆盖', 'power-outage-seed', 'num', NULL, 0, 0,
    '仅District：留空保留数据集停电种子；显式90000复现旧包装器。范围0至4294967295，修改后须重新评估。',
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name = 'power-outage-seed'
);
