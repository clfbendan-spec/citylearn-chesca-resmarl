-- Add missing runtime controls without replacing any saved algorithm/task configuration.
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT '经验回放预热条数','learning-starts','num',
       '开始梯度更新前的经验条数。AAC 默认 719，District 默认 512；短程验链和正式实验应分别登记。',1
FROM DUAL WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name='learning-starts');

INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT '每轮最小采样步数','sample-steps-per-iteration','num',
       'District 每次 train() 至少采集的环境步数；不是完整回合数，默认 100。',1
FROM DUAL WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name='sample-steps-per-iteration');

INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT '训练强度','training-intensity','num',
       'District SAC 重放训练与新采样的强度。默认保留历史配置 512，必须为有限正数。',1
FROM DUAL WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name='training-intensity');

INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'Ray CPU 数量','ray-num-cpus','num',
       'District Ray 可见 CPU 数。留空使用自动检测；Windows 短程验链可设 1。',1
FROM DUAL WHERE NOT EXISTS (
    SELECT 1 FROM algorithm_param_config WHERE param_name='ray-num-cpus');
