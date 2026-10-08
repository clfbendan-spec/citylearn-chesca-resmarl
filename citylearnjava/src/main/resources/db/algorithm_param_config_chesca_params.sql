-- ============================================================================
-- 把 CHESCA-ResMARL 配置里的 4 个参数登记进算法参数目录（algorithm_param_config）
-- ----------------------------------------------------------------------------
-- 背景
--   tau / B_low / B_high / balance_type 目前只能在「CHESCA-ResMARL 配置」页里改，
--   代码编辑器「配置」弹窗的参数下拉中看不到它们。这里登记进参数目录后，
--   就能像 train-schema / train-epochs 一样把它们挂到脚本上。
--
-- 登记内容
--   name                  param_name      value_type   候选项（default_value）
--   预测优化步长           tau             ratio        1 步 / 2 步 / 3 步
--   电池树搜索适应度类型   balance_type    ratio        A / B / C 三种代价口径
--   增负荷阈值系数         B_low           num          —（数字输入框）
--   减负荷阈值系数         B_high          num          —（数字输入框）
--
--   取值口径与 CHESCA-copy/checa/agent.py 的 default_params 及 algorithm_config 表一致：
--     tau = 1、balance_type = C、B_low = 1.18、B_high = 1.0
--     balance_type：A=跟踪历史均值；B=抑制步间波动；C=跟踪均值与预测中点
--
-- ⚠️ 本脚本只登记「参数定义」，不写 algorithm_config 里的取值 ——
--    那 4 个值仍由「CHESCA-ResMARL 配置」页维护，两边互不影响。
--
-- 说明
--   · if_system = 1（系统预置）：参数配置页里打「系统」标识，只能改简介、不能删。
--   · param_name 直接用目标 JSON 的键名（tau / B_low / B_high / balance_type），
--     没写成 train-schema 那种 CLI 中划线风格 —— 它们是 chesca_agent_config.json 的字段名。
--   · ratio 的 key 一律是字符串（"1" / "A"）：算法配置弹窗按字符串匹配下拉选项，
--     写成数字会出现「有值但下拉框选不中」。
--   · 可重复执行：INSERT 带 WHERE NOT EXISTS，已存在的行不会重复插入，也不会被覆盖
--     （想改定义请走「参数配置」页，或在库里直接改）。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_chesca_params.sql
-- ============================================================================

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '预测优化步长', 'tau', 'ratio',
       '[{"key":"1","value":"1 步"},{"key":"2","value":"2 步"},{"key":"3","value":"3 步"}]',
       1,
       '电池树搜索向前看的步数：预测未来第 tau 步的净负荷再决定当前充放电动作。步数越大越有远见，搜索开销也越大。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'tau');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '电池树搜索适应度类型', 'balance_type', 'ratio',
       '[{"key":"A","value":"A — 跟踪历史均值"},{"key":"B","value":"B — 抑制步间波动"},{"key":"C","value":"C — 跟踪均值与预测中点"}]',
       1,
       '决定电池树搜索里「什么叫代价最小」：A=偏离历史净负荷均值；B=偏离上一步净负荷（更平滑）；C=偏离历史均值与下一步预测的中点（默认）。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'balance_type');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '增负荷阈值系数', 'B_low', 'num',
       NULL,
       1,
       '净负荷低于「均值 − B_low×标准差」时触发增负荷（充电）。默认 1.18，越大越不轻易增负荷。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'B_low');

INSERT INTO `algorithm_param_config`
    (`name`, `param_name`, `value_type`, `default_value`, `if_system`, `desc`, `create_time`)
SELECT '减负荷阈值系数', 'B_high', 'num',
       NULL,
       1,
       '净负荷高于「均值 + B_high×标准差」时触发减负荷（放电）。默认 1.0，越小越容易触发减负荷。',
       NOW()
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'B_high');

-- 校验：确认 4 条都已登记
SELECT `id`, `name`, `param_name`, `value_type`, `default_value`, `if_system`
FROM `algorithm_param_config`
WHERE `param_name` IN ('tau', 'balance_type', 'B_low', 'B_high')
ORDER BY `id`;
