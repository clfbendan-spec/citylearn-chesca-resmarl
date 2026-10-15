-- ============================================================================
-- 区域级 MARL：参数目录登记 + 两个脚本的配置（py_file.algorithm_config）
-- ----------------------------------------------------------------------------
-- 前置：先执行 db/district_marl_pyfile.sql（py_file 里两行已登记）。
--
-- 背景（2026-10-10）
--   「算法配置 → 命令行参数」的白名单机制已取消（见 BaseDataService 里的说明块）：
--   现在**配置里配了什么就传什么**，不再按脚本裁剪。
--   因此本文件只做两件事：
--     ① 把两个脚本认得的参数登记进 algorithm_param_config（→ 界面下拉可选、带简介与值类型校验）；
--     ② 给两个脚本写一份 py_file.algorithm_config（→ 界面打开就已是可跑的默认配置）。
--
-- 参数名 = 命令行选项名（下划线/中划线写法与脚本 argparse 逐字一致），
-- Java 翻成 `--参数名 值` 传给脚本。
--
-- 可重复执行 ✓（INSERT 带 NOT EXISTS；SET/UPDATE 幂等）
-- 执行方式：
--   mysql -uroot -p000000 citylearn < district_marl_params.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) 参数目录 ---------------------------------------------------------------
--    train-schema / eval-schema / train-epochs 三个已存在（id 1/2/3，special 的数据集
--    参数存 citylearn_dataset.id），这里只补区域级与通用项。
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '随机种子', 'seed', 'num',
       '固定 RLlib/ray 随机种子，保证同参数可复现。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'seed');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '区域评估间隔', 'eval-every', 'num',
       '每多少轮做一次区域评估（贪心跑整段并算 District 级 KPI）。越小越准、越慢。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'eval-every');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评估段长', 'eval-steps', 'num',
       '评估跑多少步；0 = 用数据集默认整段。填小值只适合冒烟。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'eval-steps');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '社区尖峰惩罚权重', 'peak-weight', 'num',
       '区域奖励项：r -= w × max(0, 社区净用电 − 目标线)。0 = 关闭。越大越偏向削峰。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak-weight');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '团队奖励混合系数', 'team-share', 'num',
       '区域奖励项：r_i ← (1−s)·r_i + s·mean(r)，s∈[0,1]。0 = 关闭；越大越偏公共目标（治搭便车）。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'team-share');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '谷期错峰引导权重', 'stagger-weight', 'num',
       '区域奖励项：社区谷底时 SOC 越低的楼充电奖励越大（让最空的先充）。0 = 关闭。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'stagger-weight');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT 'best 选点指标', 'best-metric', 'text',
       '按哪个 District 级归一 KPI 选 best-checkpoint（越小越好）。'
       '常用 all_time_peak_average / daily_peak_average / cost_total。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'best-metric');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '断点输出目录', 'checkpoint-dir', 'text',
       '训练写 checkpoint 的目录（评估脚本默认也读这里）。留空 = district_config.DISTRICT_CHECKPOINT_DIR。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint-dir');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '评估读取断点', 'checkpoint', 'text',
       '评估脚本从哪个 checkpoint 目录加载模型（显式指定，独立运行时用）。'
       '任务编排的评估子任务会固定注入「训练模型」(train-task-id) ⇒ 此处配的值不参与；'
       '留空 = 旧版全局兜底目录 district_config.DISTRICT_CHECKPOINT_DIR。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint');

-- 已装库刷新描述（上面的 INSERT 有 NOT EXISTS 守卫，不会更新老行）
UPDATE `algorithm_param_config`
SET `desc` = '评估脚本从哪个 checkpoint 目录加载模型（显式指定，独立运行时用）。'
             '任务编排的评估子任务会固定注入「训练模型」(train-task-id) ⇒ 此处配的值不参与；'
             '留空 = 旧版全局兜底目录 district_config.DISTRICT_CHECKPOINT_DIR。'
WHERE `param_name` = 'checkpoint';

-- ---------------------------------------------------------------------------
-- 2) 配置组：把上面这批归成一张卡 -------------------------------------------
-- ---------------------------------------------------------------------------
SET @set_id = (SELECT id FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL' LIMIT 1);
INSERT INTO `algorithm_param_config_set` (`name`, `desc`, `members`)
SELECT '区域级 MARL', 'District 观测/奖励/选点相关参数（District_MARL_train.py / District_MARL_eval.py）',
       CONCAT('[', (SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `algorithm_param_config`
                    WHERE `param_name` IN ('seed','eval-every','eval-steps','peak-weight',
                                           'team-share','stagger-weight','best-metric',
                                           'checkpoint-dir','checkpoint')), ']')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL');

-- 重复执行时刷新成员（参数可能后加的）
UPDATE `algorithm_param_config_set`
SET `members` = CONCAT('[', (SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `algorithm_param_config`
                             WHERE `param_name` IN ('seed','eval-every','eval-steps','peak-weight',
                                                    'team-share','stagger-weight','best-metric',
                                                    'checkpoint-dir','checkpoint')), ']')
WHERE `name` = '区域级 MARL';

SET @set_id = (SELECT id FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL' LIMIT 1);
SET @ee   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'eval-every');
SET @es   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'eval-steps');
SET @seed = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'seed');
SET @pw   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'peak-weight');
SET @ts   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'team-share');
SET @sw   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'stagger-weight');
SET @bm   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'best-metric');
SET @cd   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint-dir');
SET @ck   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'checkpoint');

-- ---------------------------------------------------------------------------
-- 3) 训练脚本的配置（与 district_config.py 的默认值一致，界面打开即可跑）----
--    说明：id=1 训练数据集（citylearn_dataset.id=1 → 2023 local 3栋720步）
--          id=2 评估数据集（id=2 → 2023 online_1）
--          checkpoint-dir 与后端注入的同名参数冲突时**以配置为准**（applyAlgorithmConfigArgs）。
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `algorithm_config` = CONCAT(
        '[{"type":"alone","params":[',
        '{"id":1,"param_name":"train-schema","value":1},',
        '{"id":2,"param_name":"eval-schema","value":2},',
        '{"id":3,"param_name":"train-epochs","value":"320"},',
        '{"id":', @ee,   ',"param_name":"eval-every","value":"20"},',
        '{"id":', @es,   ',"param_name":"eval-steps","value":"0"},',
        '{"id":', @seed, ',"param_name":"seed","value":"3"},',
        '{"id":', @pw,   ',"param_name":"peak-weight","value":"3.0"},',
        '{"id":', @ts,   ',"param_name":"team-share","value":"0.25"},',
        '{"id":', @sw,   ',"param_name":"stagger-weight","value":"0.0"},',
        '{"id":', @bm,   ',"param_name":"best-metric","value":"all_time_peak_average"}',
        ']}]')
WHERE `file_name` = 'District_MARL_train.py';

-- ---------------------------------------------------------------------------
-- 4) 评估脚本的配置 ---------------------------------------------------------
--    eval-schema 用 online_1（与 Multi-agent-eval.py 同一口径：换数据集看泛化）
--    断点定位（2026-10-10 改）：脚本按优先级 --train-task-id → --checkpoint → 全局兜底。
--    任务编排的评估子任务会被固定注入 --train-task-id（值 = 父任务 id 或所复用的历史
--    训练任务 id）⇒ 按任务目录定位本任务训练子任务产出的模型；下面这条 checkpoint
--    只在**独立运行**（代码编辑器直接跑评估、没有 train-task-id）时才会被用到。
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `algorithm_config` = CONCAT(
        '[{"type":"alone","params":[',
        '{"id":2,"param_name":"eval-schema","value":2},',
        '{"id":', @es, ',"param_name":"eval-steps","value":"0"},',
        '{"id":', @ck, ',"param_name":"checkpoint","value":"D:/citylearn-demo/output/district_marl_checkpoints"}',
        ']}]')
WHERE `file_name` = 'District_MARL_eval.py';

-- ---------------------------------------------------------------------------
-- 5) 校验 -------------------------------------------------------------------
-- ---------------------------------------------------------------------------
SELECT `file_name`, JSON_VALID(`algorithm_config`) AS `json_ok`,
       JSON_LENGTH(`algorithm_config`) AS `sections`,
       LEFT(`algorithm_config`, 220) AS `head`
FROM `py_file`
WHERE `file_name` IN ('District_MARL_train.py', 'District_MARL_eval.py');

SELECT `id`, `name`, `param_name`, `value_type`
FROM `algorithm_param_config`
WHERE `param_name` IN ('seed','eval-every','eval-steps','peak-weight',
                       'team-share','stagger-weight','best-metric',
                       'checkpoint-dir','checkpoint')
ORDER BY `id`;

SELECT `id`, `name`, `members` FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL';
