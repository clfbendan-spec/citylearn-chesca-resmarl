-- ============================================================================
-- py_task 增加任务名称字段
--
-- 背景
--   任务管理页需要把「代码名称」列改为「任务名称」：
--     type=0（训练+评估编排任务）→ 读取本表的 task_name
--     type=1（代码编辑器直接执行的简易任务）→ 仍读取关联脚本名 py_file.file_name
--   因此 type=0 的任务需要有一个自己的名称字段。
--
-- 说明
--   1. 只需执行一次；重复执行会报「Duplicate column name 'task_name'」。
--   2. 不复用已有的 show_name：那一列是「仿真仪表盘展示名称」，
--      与任务本身的名字是两个概念（只在 if_show=1 的执行成功任务上使用）。
--   3. 不对历史数据回填：type=1 的任务名称一律取脚本名，本列为空即可。
-- ============================================================================

ALTER TABLE py_task
    ADD COLUMN task_name varchar(128) NULL
        COMMENT '任务名称：type=0 编排任务的名称；type=1 不用此列（名称取 py_file.file_name）'
        AFTER `status`;

-- 校验：新列已就位（历史数据该列应为 NULL）
SELECT COUNT(*) AS total,
       SUM(CASE WHEN task_name IS NULL THEN 1 ELSE 0 END) AS task_name_null_cnt
FROM py_task;
