-- ============================================================================
-- 增补：Multi-agent 系列脚本可用的「命令行参数」型算法参数
-- ----------------------------------------------------------------------------
-- 背景
--   代码编辑器执行脚本时，会把 py_file.algorithm_config 里的参数当命令行参数传给脚本
--   （见 BaseDataService#resolveAlgorithmConfigArgs，按每个脚本的白名单过滤）。
--   参数目录里原本只有 train-schema / eval-schema / train-epochs 三条 CLI 型参数，
--   而 Multi-agent.py / Multi-agent-train.py 还接受 max/min-train-epochs、seed、
--   env-runners、checkpoint-dir 等 —— 补进目录后才能在下拉里直接选（带名称/简介/值类型校验）。
--
--   注 1：界面也支持手填「自定义参数」（type=extra，如现在库里那两条 max/min-train-epochs），
--         效果与本文件加目录项完全一样；进目录的好处是有简介、num 类型只允许填数字。
--   注 2：--output-dir 不进目录：它由后端固定传「任务输出目录」，配置里填了也会被白名单过滤掉。
--   注 3：白名单在 BaseDataService#ALGORITHM_CONFIG_CLI_WHITELIST 里维护；
--         脚本新增参数时，这里（参数目录）与那里（白名单）都要补。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）
--   mysql -uroot -p000000 citylearn < algorithm_param_config_marl_cli.sql
--   下面全部用 INSERT ... WHERE NOT EXISTS，可重复执行。
-- ============================================================================

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '最大训练轮数', 'max-train-epochs', 'num',
       '训练轮数硬上限，到了无条件停（Multi-agent.py / Multi-agent-train.py）。留空则取 --train-epochs。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'max-train-epochs');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '最小训练轮数', 'min-train-epochs', 'num',
       '最小训练轮数：在此之前一律继续训练（早停判据②/③不生效）。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'min-train-epochs');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '随机种子', 'seed', 'num',
       '固定 RLlib/ray 随机种子，保证同参数可复现（论文方差可跑 0/1/2）。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'seed');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '并行采样进程数', 'env-runners', 'num',
       '并行采样进程数：0=单进程（Windows 最稳）。>0 要求奖励函数是可被 worker import 的真实模块。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'env-runners');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '断点输出目录', 'checkpoint-dir', 'text',
       '训练脚本写 checkpoint 的目录（Multi-agent.py 续训时由后端钉在固定目录，配置里的值会被忽略）。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint-dir');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评估读取断点', 'checkpoint', 'text',
       '只评估脚本（Multi-agent-eval.py）从哪个 checkpoint 加载模型，需指向训练产出的目录。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint');

-- 校验
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `desc`
FROM `algorithm_param_config` WHERE `is_member` = 0 ORDER BY `id`;
