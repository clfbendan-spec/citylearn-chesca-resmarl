-- ============================================================================
-- py_file 增加「脚本类型」字段 script_type：区分 训练 / 评估 / 训练+评估一体
-- ----------------------------------------------------------------------------
-- 背景
--   Multi-agent.py 原本是「训练 + 评估」一体化脚本：一次运行必须把 Multi-Agent
--   SAC 从头训完（TRAIN_EPOCHS=360 轮，约 2.8h），训练结束立刻跑评估仿真出 KPI。
--   想「训一次、反复评估」只能重训，代价极高。
--
--   现拆成两个独立入口（公共工具层仍与 Multi-agent.py 保持一致）：
--     Multi-agent-train.py  只训练，训练结束保存 RLlib checkpoint
--     Multi-agent-eval.py   只评估，从 checkpoint 恢复模型后直接出 KPI
--
--   代码编辑器页需要按这 3 种类型筛选文件列表，故给 py_file 加 script_type。
--
-- 取值
--   train  只训练        （Multi-agent-train.py）
--   eval   只评估        （Multi-agent-eval.py；纯评估类脚本也可归入）
--   both   训练+评估一体  （历史脚本默认值，行为不变）
--
-- 本脚本可重复执行：加列那句若已执行过会报 "Duplicate column name"，
-- 跳过它、继续执行后面的 UPDATE / INSERT / SELECT 即可（后面的都是幂等的）。
--
-- 执行方式（Q 项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < py_file_script_type.sql
-- ============================================================================

-- 1) 加列 --------------------------------------------------------------------
ALTER TABLE `py_file`
    ADD COLUMN `script_type` varchar(16) NULL DEFAULT 'both'
    COMMENT '脚本类型：train 只训练 / eval 只评估 / both 训练+评估一体';

-- 2) 历史脚本一律「训练+评估一体」，保持原有行为 ----------------------------
UPDATE `py_file`
SET `script_type` = 'both'
WHERE `script_type` IS NULL OR `script_type` = '';

-- 3) 两个新入口：若尚未登记则登记（本机已手工登记为 id=8/9，这两句会跳过） ---
INSERT INTO `py_file` (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`, `name`, `if_show`, `script_type`)
SELECT 'marl_train', 'Multi-agent-train.py', '多智能体训练（只训练，结束保存 checkpoint）', 1, NOW(), 'admin', 'Multi-agent 训练', 1, 'train'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'Multi-agent-train.py');

INSERT INTO `py_file` (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`, `name`, `if_show`, `script_type`)
SELECT 'marl_eval', 'Multi-agent-eval.py', '多智能体评估（加载 checkpoint，只评估出 KPI）', 1, NOW(), 'admin', 'Multi-agent 评估', 1, 'eval'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'Multi-agent-eval.py');

-- 4) 类型归类：以「文件名」为准，最后执行，重复执行安全 ----------------------
UPDATE `py_file` SET `script_type` = 'train' WHERE `file_name` = 'Multi-agent-train.py';
UPDATE `py_file` SET `script_type` = 'eval'  WHERE `file_name` = 'Multi-agent-eval.py';

-- 保证这两个入口在代码编辑器页可见（if_show=1；if_system=1 时不可被删除）
UPDATE `py_file`
SET `if_show` = 1, `if_system` = 1
WHERE `file_name` IN ('Multi-agent-train.py', 'Multi-agent-eval.py');

-- 【可选】下面几个其实是「纯评估」类脚本，按需求"旧的代码全部为训练+评估一体"
-- 暂归 both。若想让它们出现在「评估」筛选下，放开这行即可：
-- UPDATE `py_file` SET `script_type` = 'eval'
--   WHERE `file_name` IN ('CHESCA.py', 'CHESCA_ResMARL.py', 'NOCONTROL.py');

-- 5) 校验 --------------------------------------------------------------------
SELECT `id`, `file_name`, `name`, `script_type`, `if_system` + 0 AS sys, `if_show` + 0 AS show_
FROM `py_file`
ORDER BY FIELD(`script_type`, 'train', 'eval', 'both'), `id`;
