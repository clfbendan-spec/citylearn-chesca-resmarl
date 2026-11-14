-- 模型优选「重算 KPI」独立操作码
-- 背景：/web/basedata/updateLearn 是 GET，但会启动 Python 进程并回写 KPI，
--       原先只要求 menu:recDashboard（看板查看权），任何能看板的人都能触发重算。
-- 幂等：已存在则跳过。
INSERT INTO permission (id, code, name, parent_code, sort_order, enabled)
SELECT REPLACE(UUID(), '-', ''), 'recDashboard:updateLearn', '重算模型优选 KPI', 'menu:recDashboard', 21, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM permission WHERE code = 'recDashboard:updateLearn');
