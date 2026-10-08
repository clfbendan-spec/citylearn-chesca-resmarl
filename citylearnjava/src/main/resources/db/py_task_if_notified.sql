-- ============================================================================
-- py_task 增加「是否提醒过 / 已读」字段 if_notified
-- ----------------------------------------------------------------------------
-- 背景
--   需要一个「执行完成后还没被查看过」的概念，用于：
--     · 顶栏显示"执行完但未被查看的任务数量"
--     · 代码编辑器文件列表在对应脚本旁显示未读数（红底白字圆角矩形）
--     · 执行记录列表给未读记录打「未读」标记，点击后置为已读
--
-- 取值
--   0（默认）未读：执行完成后尚未被查看
--   1        已读：已被查看过
--
-- 规则
--   · 旧数据全部置 0（下方 UPDATE 兜底，防止历史上出现过 NULL）
--   · 新任务插入时由后端显式写 0（见 BaseDataService.insertPyTask）
--   · 「未读」只在 status != 0（即已结束）时才计数，执行中的任务不计入
--
-- 列类型用 tinyint(1) 与同表的 if_show 保持一致，MyBatis 会映射为 Boolean。
-- 本脚本只需执行一次；重复执行第一条 ALTER 会报 "Duplicate column name"，跳过即可。
-- ============================================================================

ALTER TABLE `py_task`
    ADD COLUMN `if_notified` tinyint(1) NULL DEFAULT 0
    COMMENT '是否已提醒/已读：0 未读（执行完成后尚未被查看） 1 已读';

-- 旧数据一律置 0（正常情况 ALTER 已给出默认值，这里是兜底）
UPDATE `py_task` SET `if_notified` = 0 WHERE `if_notified` IS NULL;

-- 校验：确认列已存在，并看看当前未读分布
SELECT COLUMN_NAME, COLUMN_TYPE, IFNULL(COLUMN_DEFAULT, 'NULL') AS def, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'citylearn' AND TABLE_NAME = 'py_task' AND COLUMN_NAME = 'if_notified';

SELECT SUM(status = 0) AS running,
       SUM(status <> 0 AND IFNULL(if_notified, 0) = 0) AS unread_finished,
       COUNT(*) AS total
FROM `py_task`
WHERE if_delete = 0;

-- ============================================================================
-- 【可选】历史记录一次性置为已读
-- ----------------------------------------------------------------------------
-- 按上面的规则，加列后**所有历史记录都会算作未读**（本项目当时是 112 条），
-- 顶栏会显示「待查看 112」，看着像刷屏。若不需要保留历史未读，执行下面这条把
-- 「某个时间点之前」的记录直接置为已读即可（保留最近的几条便于观察新功能）。
--
-- 本项目已执行过一次（2026-09-22，把当天 00:00 之前的 106 条置为已读，剩 6 条）。
-- 换环境部署时按需调整时间点或去掉时间条件。
-- ============================================================================
-- UPDATE `py_task` SET `if_notified` = 1
-- WHERE `if_delete` = 0
--   AND `status` <> 0
--   AND IFNULL(`if_notified`, 0) = 0
--   AND `create_time` < '2026-09-22 00:00';
