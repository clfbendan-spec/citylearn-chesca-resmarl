-- Expose existing AAC learner controls without changing saved task/card defaults.
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC约束更新率','dual-lr','num',
       '训练侧成本和不适约束权重更新率，有限且非负；0关闭更新，默认0。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='dual-lr');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC约束权重上限','dual-max','num',
       '动态约束权重上限，有限正数，默认4。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='dual-max');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC约束更新起始轮','dual-start-episode','num',
       '从第几训练轮结束后更新约束权重，整数至少1，默认2。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='dual-start-episode');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC动态成本目标','dual-cost-target','num',
       '训练侧动态约束的原生Cost目标，范围(0,0.9]，默认0.9；不是排名硬门槛。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='dual-cost-target');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC动态不适目标','dual-discomfort-target','num',
       '训练侧动态约束的不适比例目标，范围(0,0.1]，默认0.1；不替代逐楼评估资格。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='dual-discomfort-target');
