-- ============================================================================
-- 区域级 MARL：把「可复现最优」配置 v4 写成平台默认配置
-- ----------------------------------------------------------------------------
-- 前置：先执行 db/district_marl_pyfile.sql 与 db/district_marl_params.sql
--       （py_file 两行已登记、基础参数目录已建立）
--
-- 什么是 v4
--   在「纯 MARL（不加 CHESCA 规则）」的全谱系 8 组配置里，v4 是**唯一**
--   3-seed 平均归一峰值（all_time_peak_average）低于 0.90 的可复现变体：
--
--     配置                       3-seed mean       3-seed 散度
--     v1 调参 (320ep)            0.9476            —
--     v2-100 (方案1+2)           0.9192 ± 0.0081   ±0.0081
--     v2-200 (方案1+2)           0.8558 ± 0.0460   ±0.0460  ← 噪声主导，不可复现
--     v3a  (4维动作,无门控)      0.9304 ± 0.0007   ±0.0007
--     v3b  (4维动作,门控)        0.9241 ± 0.0059   ±0.0059
--   ★ v4  (方案1+2 + SAC旋钮)   0.8903 ± 0.0213   ±0.0213  ← 本文件固化这组
--     v4n (v4 + n-step=3)        0.8872 ± 0.0172   ±0.0172  ← 几乎打平，散度收窄
--     CHESCA soft(5,6)           0.638             ——（规则派，范式不同）
--
--   v4 = v2 的奖励配比（方案 1 按贡献分摊 + 方案 2 峰值锚定）不动，只拧两个
--   SAC 超参：replay buffer 5 万 → 20 万、target 软更新 τ 5e-3 → 2e-3。
--   唯一自变量是 SAC 超参 ⇒ 结论干净：0.9192 → 0.8903 全部来自超参。
--
-- 注意：v4 仍是「范式差距」的注脚 —— 0.8903 vs CHESCA 0.638 差 39%。
--       本文件只是把「纯 MARL 这一侧的最好成绩」变成网页可点可复现。
--
-- 落库依据
--   1) 参数目录 algorithm_param_config：登记 v4 用到的、此前目录里还没有的 5 个参数
--      （attribution / peak-anchored / replay-buffer-cap / sac-tau / sac-n-step），
--      并挂进配置组 id=10「区域级 MARL」⇒ 界面上以一张卡呈现。
--   2) py_file.algorithm_config：写入 v4 的完整参数值。
--      「算法配置 → 命令行参数」的白名单机制已取消（见 BaseDataService 的说明块）：
--      **配置里配了什么就翻成什么命令行**。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 --default-character-set=utf8mb4 citylearn < district_marl_best_v4_config.sql
--
-- 幂等 ✓ 可重复执行 ✓
--   · 5 条参数 INSERT 带 NOT EXISTS 守卫；
--   · 配置组 members 用 UPDATE 重算（把新参数并进去）；
--   · py_file.algorithm_config 用 UPDATE 整段覆盖（值确定，重跑结果相同）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0) 前置检查：py_file 两行必须已存在（没跑 district_marl_pyfile.sql 会静默 0 行更新）
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS `py_file_ready(应为2)`
FROM `py_file`
WHERE `file_name` IN ('District_MARL_train.py', 'District_MARL_eval.py');

-- ---------------------------------------------------------------------------
-- 1) 参数目录：补登 v4 用到的 5 个参数 --------------------------------------
--    param_name = 命令行选项名（与 district_train.py 的 argparse 逐字一致，含中划线）
-- ---------------------------------------------------------------------------
INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '区域分摊强度', 'attribution', 'num',
       '【方案 1】把集体尖峰惩罚按 own_net_i/dist_net 分摊给各 agent：'
       '0=均摊（旧行为，搭便车），1=严格按自己贡献的那份承担。v4 取 1.0。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'attribution');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '峰值锚定强度', 'peak-anchored', 'num',
       '【方案 2】把「接近/超过本局峰值」的步放大惩罚（最大约 2×），让造成新峰的那步拿到更大梯度。'
       '0=关（按超出量固定罚），1=开。v4 取 1.0。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'peak-anchored');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '回放池容量', 'replay-buffer-cap', 'num',
       '【方案 4】SAC 回放池容量（env-step）。项目默认 50000；v4 用 200000，'
       '让 SAC 能采样到更老的跨回合经验。0 = 用 RLlib 默认。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'replay-buffer-cap');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT 'SAC target 软更新系数', 'sac-tau', 'num',
       '【方案 4】SAC target 网络软更新系数 τ。RLlib 默认 5e-3；v4 降到 2e-3（更软、更稳），'
       '是 v4 相对 v2 的两个自变量之一。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'sac-tau');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT 'n-step 回报', 'sac-n-step', 'num',
       '【方案 4.1】n-step return。1=单步 TD（默认，= v4）；3 = v4n（散度收窄 19% 但均值几乎不变）。'
       '>1 要求 rollout 片段长度 ≥ n_step。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'sac-n-step');

-- ---------------------------------------------------------------------------
-- 2) 刷新配置组 id=10「区域级 MARL」的成员 ----------------------------------
--    原成员 9 个（seed/eval-every/eval-steps/peak-weight/team-share/
--    stagger-weight/best-metric/checkpoint-dir/checkpoint），
--    再加本轮 5 个 ⇒ 14 个。用 param_name 列表重算，重跑安全。
-- ---------------------------------------------------------------------------
UPDATE `algorithm_param_config_set`
SET `members` = CONCAT('[', (
        SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `algorithm_param_config`
        WHERE `param_name` IN ('seed', 'eval-every', 'eval-steps',
                               'peak-weight', 'team-share', 'stagger-weight',
                               'attribution', 'peak-anchored',
                               'replay-buffer-cap', 'sac-tau', 'sac-n-step',
                               'best-metric', 'checkpoint-dir', 'checkpoint')
    ), ']')
WHERE `name` = '区域级 MARL';

-- 配置组还没建过时补建（正常走 district_marl_params.sql 已存在，这里只是兜底）
INSERT INTO `algorithm_param_config_set` (`name`, `desc`, `members`)
SELECT '区域级 MARL',
       'District 观测/奖励/选点 + SAC 旋钮参数（District_MARL_train.py / District_MARL_eval.py）',
       CONCAT('[', (
           SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `algorithm_param_config`
           WHERE `param_name` IN ('seed', 'eval-every', 'eval-steps',
                                  'peak-weight', 'team-share', 'stagger-weight',
                                  'attribution', 'peak-anchored',
                                  'replay-buffer-cap', 'sac-tau', 'sac-n-step',
                                  'best-metric', 'checkpoint-dir', 'checkpoint')
       ), ']')
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL');

-- ---------------------------------------------------------------------------
-- 3) 取参数 id ---------------------------------------------------------------
--    目录参数一律用 id 反查（param_name 允许在界面上被改成别名，id 才是稳定键）
-- ---------------------------------------------------------------------------
SET @v_ee   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'eval-every');
SET @v_es   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'eval-steps');
SET @v_seed = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'seed');
SET @v_pw   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'peak-weight');
SET @v_ts   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'team-share');
SET @v_sw   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'stagger-weight');
SET @v_at   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'attribution');
SET @v_pa   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'peak-anchored');
SET @v_rb   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'replay-buffer-cap');
SET @v_tau  = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'sac-tau');
SET @v_ns   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'sac-n-step');
SET @v_bm   = (SELECT `id` FROM `algorithm_param_config` WHERE `param_name` = 'best-metric');

-- ---------------------------------------------------------------------------
-- 4) 训练脚本：写入 v4 完整配置 ---------------------------------------------
--    id=1 训练数据集（2023 phase_2 local evaluation，3 栋 720 步）
--    id=2 评估数据集
--    id=3 训练轮数（param_name='train-epochs'，v4 用 100）
--
--    ★ eval-schema 必须取**同域**（= id 1 local）：
--      v4 的 0.8903 是「local 训练 → local 评估」的成绩。若评估取 online_*（id 2）
--      就是跨域，量纲与回合长度都不同（720 vs 2208 步），数值不可与 0.8903 比较，
--      界面上会显示成一个"看不懂的更大的数"。要做跨域泛化实验再单独改这一项。
--
--    逐项对照 v4 的真实训练命令行（output/_verify_district_marl/run_3seeds_plan4.py）：
--      --train-epochs 100 --seed 3
--      --peak-weight 60.0 --team-share 0.0 --stagger-weight 0.0
--      --attribution 1.0 --peak-anchored 1.0
--      --peak-action-dim 0 --peak-action-gated 0         （动作 3 维，方案 3 关闭）
--      --replay-buffer-cap 200000 --sac-tau 2e-3
--
--    未写入配置的项（都用脚本默认值，见 district_config.py）：
--      peak-action-dim=0 / peak-action-gated=0
--      sac-n-step=1 / eval-every=20 / eval-steps=0
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `algorithm_config` = CONCAT(
        '[{"type":"alone","params":[',
        '{"id":1,"param_name":"train-schema","value":1},',
        '{"id":2,"param_name":"eval-schema","value":1},',
        '{"id":3,"param_name":"train-epochs","value":"100"},',
        '{"id":', @v_ee,   ',"param_name":"eval-every","value":"20"},',
        '{"id":', @v_es,   ',"param_name":"eval-steps","value":"0"},',
        '{"id":', @v_seed, ',"param_name":"seed","value":"3"},',
        '{"id":', @v_pw,   ',"param_name":"peak-weight","value":"60.0"},',
        '{"id":', @v_ts,   ',"param_name":"team-share","value":"0.0"},',
        '{"id":', @v_sw,   ',"param_name":"stagger-weight","value":"0.0"},',
        '{"id":', @v_at,   ',"param_name":"attribution","value":"1.0"},',
        '{"id":', @v_pa,   ',"param_name":"peak-anchored","value":"1.0"},',
        '{"id":', @v_rb,   ',"param_name":"replay-buffer-cap","value":"200000"},',
        '{"id":', @v_tau,  ',"param_name":"sac-tau","value":"0.002"},',
        '{"id":', @v_ns,   ',"param_name":"sac-n-step","value":"1"},',
        '{"id":', @v_bm,   ',"param_name":"best-metric","value":"all_time_peak_average"}',
        ']}]')
WHERE `file_name` = 'District_MARL_train.py';

-- ---------------------------------------------------------------------------
-- 5) 评估脚本：保持与训练同口径 ---------------------------------------------
--    ★ eval-schema 取 id=1（local，同域），与训练脚本一致 ⇒ 「训练+评估」编排任务
--      跑出来的 KPI 才能直接对上 v4 的 0.8903。
--      注意：独立的评估任务若用 --train-task-id 复用历史训练模型，schema 不同则
--      数值不可比 —— 这是设计上的取舍（宁可同域可比，不默认跨域）。
--    ⚠️ 评估模型由任务编排固定注入 --train-task-id 定位（按父任务目录取「本任务训练
--      子任务产出的 best 断点」），本文件不写 checkpoint。
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `algorithm_config` = CONCAT(
        '[{"type":"alone","params":[',
        '{"id":2,"param_name":"eval-schema","value":1},',
        '{"id":', @v_es, ',"param_name":"eval-steps","value":"0"}',
        ']}]')
WHERE `file_name` = 'District_MARL_eval.py';

-- ---------------------------------------------------------------------------
-- 6) 校验 -------------------------------------------------------------------
-- ---------------------------------------------------------------------------
SELECT `file_name`,
       JSON_VALID(`algorithm_config`) AS `json_ok`,
       JSON_LENGTH(`algorithm_config`) AS `sections`,
       LEFT(`algorithm_config`, 160) AS `head`
FROM `py_file`
WHERE `file_name` IN ('District_MARL_train.py', 'District_MARL_eval.py');

SELECT `id`, `name`, `param_name`, `value_type`
FROM `algorithm_param_config`
WHERE `param_name` IN ('seed', 'eval-every', 'eval-steps',
                       'peak-weight', 'team-share', 'stagger-weight',
                       'attribution', 'peak-anchored',
                       'replay-buffer-cap', 'sac-tau', 'sac-n-step',
                       'best-metric', 'checkpoint-dir', 'checkpoint')
ORDER BY `id`;

SELECT `id`, `name`, `members` FROM `algorithm_param_config_set` WHERE `name` = '区域级 MARL';

-- ============================================================================
-- 【配套代码改动】citylearnpy/district_marl/district_config.py
-- ----------------------------------------------------------------------------
-- 本文件只保证「网页点运行 → 命令行里带上 v4 的参数」。
-- 另有一处默认值同步（让**不传参数**时也是 v4）：district_config.py 的
--   DISTRICT_TRAIN_EPOCHS 320 → 100
-- 以及新增的 SAC 默认常量区。见该文件的「二·C、可复现最优（v4）」小节。
-- ============================================================================
