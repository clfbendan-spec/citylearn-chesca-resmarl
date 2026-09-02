-- 执行记录「展示/未展示」：供仿真仪表盘按任务筛选分组
-- 若列已存在会报错，可忽略
ALTER TABLE py_task
  ADD COLUMN if_show TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否在仪表盘展示(0未展示 1展示)' AFTER if_delete;
