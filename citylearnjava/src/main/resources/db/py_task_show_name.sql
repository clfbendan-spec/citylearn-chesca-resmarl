-- 执行记录展示名称（仪表盘分组优先使用）
ALTER TABLE py_task
  ADD COLUMN show_name VARCHAR(128) NULL DEFAULT NULL COMMENT '仪表盘展示名称' AFTER if_show;
