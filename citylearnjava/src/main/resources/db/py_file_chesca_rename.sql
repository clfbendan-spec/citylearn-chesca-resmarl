-- CHESCA / CHESCA-ResMARL 脚本登记（py_file）
-- 将 local_evaluation_copy.py 重命名为 CHESCA.py，并新增 CHESCA_ResMARL.py

UPDATE `py_file`
SET `file_name` = 'CHESCA.py',
    `description` = '纯 CHESCA 评估（忽略配置页残差开关）',
    `name` = 'CHESCA'
WHERE `file_name` = 'local_evaluation_copy.py';

INSERT INTO `py_file` (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`, `name`, `if_show`)
SELECT '7', 'CHESCA_ResMARL.py', 'CHESCA-ResMARL 混合评估（加载 Multi-agent checkpoint）', 1, NOW(), 'admin', 'CHESCA-ResMARL', 1
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM `py_file` WHERE `file_name` = 'CHESCA_ResMARL.py'
);

UPDATE `py_file`
SET `description` = '纯 CHESCA 评估（忽略配置页残差开关）',
    `name` = 'CHESCA',
    `if_system` = 1,
    `if_show` = 1
WHERE `file_name` = 'CHESCA.py';

UPDATE `py_file`
SET `description` = 'CHESCA-ResMARL 混合评估（加载 Multi-agent checkpoint）',
    `name` = 'CHESCA-ResMARL',
    `if_system` = 1,
    `if_show` = 1
WHERE `file_name` = 'CHESCA_ResMARL.py';
