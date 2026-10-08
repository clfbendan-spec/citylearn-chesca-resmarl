-- ============================================================================
-- py_task 增加「编排任务」支持
--
-- 背景
--   任务管理页新增「新建任务」按钮，点开后是一个双卡编排界面（训练卡 → 评估卡）。
--   这种任务与「在代码编辑器里直接运行某个脚本」产生的任务语义不同，需要在同一张
--   表里区分开，并把两张卡片的配置分别保存下来。
--
-- 新增字段
--   type         任务类型：
--                  0 = 训练+评估编排任务（任务管理页「新建任务」创建）
--                  1 = 代码编辑器直接执行的简易任务（含全部历史数据）
--   train_config 训练卡配置（JSON 字符串）
--   eval_config  评估卡配置（JSON 字符串）
--
-- 说明
--   1. 只需执行一次；重复执行会报「Duplicate column name 'type'」。
--   2. type 的 DEFAULT 1 已让历史数据自动成为「简易任务」，
--      下面的 UPDATE 只是显式兜底（防止有人建列时改了默认值）。
--   3. train_config / eval_config 用 text 而非 json 类型：
--      便于兼容 MySQL 5.7，且这两列只做整体读写、不需要 JSON 函数检索。
-- ============================================================================

ALTER TABLE py_task
    ADD COLUMN `type` tinyint(1) NOT NULL DEFAULT 1
        COMMENT '任务类型：0=训练+评估编排任务，1=代码编辑器直接执行的简易任务',
    ADD COLUMN train_config text NULL COMMENT '训练卡配置（JSON 字符串，仅 type=0 有值）',
    ADD COLUMN eval_config  text NULL COMMENT '评估卡配置（JSON 字符串，仅 type=0 有值）';

-- 回填：历史数据一律视为「代码编辑器直接执行的简易任务」
UPDATE py_task SET `type` = 1 WHERE `type` IS NULL;

-- 校验：执行后应只看到 type=1 的历史数据（除非已经建过编排任务）
SELECT `type`, COUNT(*) AS cnt FROM py_task GROUP BY `type`;
