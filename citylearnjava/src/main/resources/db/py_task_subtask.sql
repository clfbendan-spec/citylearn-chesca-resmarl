-- ============================================================================
-- 编排任务（训练+评估）拆分为子任务：py_task 增 is_subtask / config
-- ----------------------------------------------------------------------------
-- 背景
--   任务管理页「新建任务」建立的 type=0（训练+评估）任务，从「一张行记录两张卡的
--   配置」改为「一行父任务 + 两行子任务」：
--     · 父任务 id     = <uuid>            role：只保存任务名称与整体状态
--     · 训练子任务 id = <uuid>-train      config = 训练卡 JSON
--     · 评估子任务 id = <uuid>-eval       config = 评估卡 JSON（含固定参数「训练模型」=父任务 id）
--   子任务同样是 py_task 的一行（type=1，即“由脚本执行的任务”），is_subtask=1 用于区分；
--   任务管理页只展示父任务，子任务在其详情里展开的子表格中显示（代码编辑器记录列表也会
--   带「子任务」标识展示它们）。
--
-- 字段变化
--   + is_subtask  tinyint(1)  是否子任务（0 父/普通任务，1 子任务）
--   + config      TEXT        本任务的脚本配置（卡片 JSON，替代原来的 train_config / eval_config）
--   - train_config / eval_config（数据已迁到对应子任务的 config，最后一步删除）
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）
--   mysql -uroot -p000000 citylearn < py_task_subtask.sql
--   ① ② 可重复执行（重复执行 ALTER 会报 Duplicate column / 无变化，跳过即可）；
--   ③ 用 NOT EXISTS 保证幂等；④ 是删列，确认前三步无误后再单独执行。
-- ============================================================================

-- ① 主键扩容：子任务 id = 父任务 id + '-train' / '-eval'（32 位 uuid → 38 位）
ALTER TABLE `py_task`
    MODIFY COLUMN `id` VARCHAR(64) NOT NULL
        COMMENT '任务 id；编排任务的子任务为 <父任务id>-train / <父任务id>-eval';

-- ② 新增两列
ALTER TABLE `py_task`
    ADD COLUMN `is_subtask` tinyint(1) NOT NULL DEFAULT 0
        COMMENT '是否子任务：1=编排任务拆出的训练/评估子任务（任务管理页主列表不显示）',
    ADD COLUMN `config` TEXT NULL
        COMMENT '本任务的脚本配置（卡片 JSON：{pyId,scriptName,datasetId,schemaKey,datasetName,trainEpochs,trainBatchSize,config}）';

UPDATE `py_task` SET `is_subtask` = 0 WHERE `is_subtask` IS NULL;

-- ③ 历史数据：把已有编排任务（type=0）的两张卡配置各拆成一个子任务
--    · 子任务 type 记为 1（它是“由某个脚本执行的任务”，与代码编辑器直接执行的任务同构）
--    · 状态沿用父任务当前状态（多数应为 5-待执行；已跑过的历史任务保持原状态以免误导）
--    · 父任务不再持有配置（config 留空），配置归属改由两个子任务承担
--    · 「训练模型」这条固定参数由后端在读取/执行时补齐（见 BaseDataService），此处不写 SQL
INSERT INTO `py_task`
    (`id`, `py_id`, `type`, `status`, `task_name`, `if_delete`, `if_show`, `if_notified`,
     `is_subtask`, `config`, `create_time`, `update_time`)
SELECT CONCAT(t.id, '-train'),
       JSON_UNQUOTE(JSON_EXTRACT(t.train_config, '$.pyId')),
       1, t.status, CONCAT(IFNULL(t.task_name, '任务'), '·训练'),
       0, 0, 0, 1, t.train_config, t.create_time, t.create_time
FROM `py_task` t
WHERE t.type = 0
  AND t*.train_config IS NOT NULL AND t.train_config <> ''
  AND NOT EXISTS (SELECT 1 FROM (SELECT `id` FROM `py_task`) x WHERE x.id = CONCAT(t.id, '-train'));

INSERT INTO `py_task`
    (`id`, `py_id`, `type`, `status`, `task_name`, `if_delete`, `if_show`, `if_notified`,
     `is_subtask`, `config`, `create_time`, `update_time`)
SELECT CONCAT(t.id, '-eval'),
       JSON_UNQUOTE(JSON_EXTRACT(t.eval_config, '$.pyId')),
       1, t.status, CONCAT(IFNULL(t.task_name, '任务'), '·评估'),
       0, 0, 0, 1, t.eval_config, t.create_time, t.create_time
FROM `py_task` t
WHERE t.type = 0
  AND t.eval_config IS NOT NULL AND t.eval_config <> ''
  AND NOT EXISTS (SELECT 1 FROM (SELECT `id` FROM `py_task`) x WHERE x.id = CONCAT(t.id, '-eval'));

-- 校验
SELECT `id`, `type`, `status`, `is_subtask`, LEFT(IFNULL(`config`, ''), 60) AS config_head
FROM `py_task` WHERE `is_subtask` = 1 OR `type` = 0 ORDER BY `create_time` DESC LIMIT 20;

-- ④【确认 ①~③ 无误后再单独执行】删除被 config 取代的两列
-- ALTER TABLE `py_task` DROP COLUMN `train_config`, DROP COLUMN `eval_config`;
