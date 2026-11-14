-- Register optional controls without rewriting saved cards or historical tasks.
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC初始化模型路径','init-checkpoint','text',
       '本机可验证的AAC初始化权重路径；warm-start-anchor必须开启。未指定时使用冻结Anchor。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='init-checkpoint');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC初始化预声明哈希','expected-init-sha256','text',
       '64位SHA256；与初始化权重不一致时训练前拒绝。实际使用权重会复制到任务目录。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='expected-init-sha256');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,default_value,`desc`,if_system)
SELECT 'AAC模型选点规则','selector','ratio',
       '[{"key":"comfort_then_cost","value":"舒适优先再Cost"},{"key":"piecewise","value":"舒适优先再分段评分"}]',
       '均只用训练侧Local结果；默认保留旧Cost规则。分段评分固定alpha=1，必须提供已登记Local Anchor。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='selector');
INSERT INTO algorithm_param_config (`name`,param_name,value_type,`desc`,if_system)
SELECT 'AAC选点Anchor结果','selection-anchor-result','text',
       '预先冻结登记的训练侧Anchor evaluation_result.json路径；分段选点必填，协议不匹配拒绝。',1
FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM algorithm_param_config WHERE param_name='selection-anchor-result');
