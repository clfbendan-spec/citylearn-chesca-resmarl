-- Register AAC-MADRL's isolated train/evaluation entry points.
-- Safe to rerun: inserts are guarded and updates touch only these filenames.
INSERT INTO `py_file`
    (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`,
     `name`, `if_show`, `script_type`)
SELECT 'aacmadrl_train', 'AACMADRL_train.py',
       'AAC-MADRL 训练：本任务目录保存模型，可在评估卡复用',
       1, NOW(), 'admin', 'AAC-MADRL 训练', 1, 'train'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'AACMADRL_train.py');

INSERT INTO `py_file`
    (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`,
     `name`, `if_show`, `script_type`)
SELECT 'aacmadrl_eval', 'AACMADRL_eval.py',
       'AAC-MADRL 评估：从任务管理选择的训练任务读取模型，导出 CityLearn KPI',
       1, NOW(), 'admin', 'AAC-MADRL 评估', 1, 'eval'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'AACMADRL_eval.py');

UPDATE `py_file`
SET `if_system` = 1, `if_show` = 1, `name` = 'AAC-MADRL 训练', `script_type` = 'train'
WHERE `file_name` = 'AACMADRL_train.py';

UPDATE `py_file`
SET `if_system` = 1, `if_show` = 1, `name` = 'AAC-MADRL 评估', `script_type` = 'eval'
WHERE `file_name` = 'AACMADRL_eval.py';

SELECT `id`, `file_name`, `name`, `script_type`, `if_show` + 0 AS `show_`
FROM `py_file`
WHERE `file_name` IN ('AACMADRL_train.py', 'AACMADRL_eval.py');
