-- ============================================================================
-- 登记「区域级（District-aware）MARL」两个平台入口到 py_file
-- ----------------------------------------------------------------------------
-- 目标
--   · District_MARL_train.py  只训练（区域观测 + 区域奖励 + 按区域 KPI 选 best-ckpt）
--   · District_MARL_eval.py   只评估（加载固定断点目录里的最新模型，出区域 KPI）
--
-- 为什么 file_name 是**根目录**的两个新文件，而不是 district_marl/district_train.py
--   后端执行前会把脚本复制到任务目录并拍平：
--       copyPythonScriptForTask: targetDir.resolve(source.getFileName())
--       （BaseDataService.java:4787-4798）
--   运行副本落在 output/outkpis/<taskId>/ 下，那里没有 district_marl 包，
--   且子进程 cwd = 后端 JVM 工作目录 ⇒ 子目录里的脚本必然导入失败。
--   两个根入口会把真实的 citylearnpy 根目录补进 sys.path（见文件头注释）。
--
-- 落库格式依据
--   py_file 列定义：citylearnjava/citylearn.sql（id/file_name/description/if_system/
--   create_time/create_user/name/if_show/script_type/algorithm_config）
--   同类登记脚本参考：db/py_file_script_type.sql、db/py_file_chesca_rename.sql
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < district_marl_pyfile.sql
--
-- 幂等 ✓ 可重复执行 ✓（两条 INSERT 都带 NOT EXISTS 守卫；UPDATE 只覆盖本脚本自己的行）
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) 登记两行 ---------------------------------------------------------------
--    if_system=1 ⇒ 系统预置：不可被前端删除（getPyFileList 条件为
--                  (create_user='admin' OR if_system=1)，已不按 if_show 过滤）
--    script_type：train / eval（代码编辑器页的 tain/eval/both 筛选依据）
-- ---------------------------------------------------------------------------
INSERT INTO `py_file`
    (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`,
     `name`, `if_show`, `script_type`)
SELECT 'district_marl_train', 'District_MARL_train.py',
       '区域级 MARL 训练：agent 观测含社区聚合特征，奖励含社区尖峰项，best-ckpt 按区域 KPI 选',
       1, NOW(), 'admin', 'District-MARL 训练', 1, 'train'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'District_MARL_train.py');

INSERT INTO `py_file`
    (`id`, `file_name`, `description`, `if_system`, `create_time`, `create_user`,
     `name`, `if_show`, `script_type`)
SELECT 'district_marl_eval', 'District_MARL_eval.py',
       '区域级 MARL 评估：加载最新训练断点，导出 District 级 KPI 并打印 outputkpi 段',
       1, NOW(), 'admin', 'District-MARL 评估', 1, 'eval'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `py_file` WHERE `file_name` = 'District_MARL_eval.py');

-- ---------------------------------------------------------------------------
-- 2) 收敛关键字段（重复执行安全）--------------------------------------------
--    algorithm_config 由 db/district_marl_params.sql 写入（参数目录 + 两个脚本的默认配置）。
--    不跑那个文件也能执行：脚本内置默认值（citylearnpy/district_marl/district_config.py）。
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `if_system` = 1,
    `if_show`   = 1,
    `name`      = 'District-MARL 训练',
    `script_type` = 'train'
WHERE `file_name` = 'District_MARL_train.py';

UPDATE `py_file`
SET `if_system` = 1,
    `if_show`   = 1,
    `name`      = 'District-MARL 评估',
    `script_type` = 'eval'
WHERE `file_name` = 'District_MARL_eval.py';

-- ---------------------------------------------------------------------------
-- 3) 校验 -------------------------------------------------------------------
-- ---------------------------------------------------------------------------
SELECT `id`, `file_name`, `name`, `script_type`,
       `if_system` + 0 AS `sys`, `if_show` + 0 AS `show_`
FROM `py_file`
WHERE `file_name` IN ('District_MARL_train.py', 'District_MARL_eval.py');

-- ============================================================================
-- 【配套文件】db/district_marl_params.sql
-- ----------------------------------------------------------------------------
-- 本文件只登记 py_file 两行。要让「代码编辑器 → 配置」里的参数真正下发到命令行，
-- 还要跑 db/district_marl_params.sql：它把两个脚本认得的参数登记进
-- algorithm_param_config（界面下拉可选），并写好两个脚本的 py_file.algorithm_config。
--
-- 前置说明（2026-10-10）
--   原先「算法配置 → 命令行参数」要过一层**硬编码在 Java 里**的白名单
--   （BaseDataService.ALGORITHM_CONFIG_CLI_WHITELIST），未登记的脚本一个参数都不下发。
--   该机制**已取消**：现在配置里配了什么就传什么（见 BaseDataService 里的说明块）。
--   ⇒ 本脚本不再需要任何 Java 改动即可让界面参数生效。
--
-- 提醒：后端会对**所有**脚本固定追加 `--output-dir <任务目录>`
--       （BaseDataService.java:3637-3639），两个入口都已支持该参数；
--       若配置里也配了 --output-dir，按「配置优先」覆盖（applyAlgorithmConfigArgs）。
-- ============================================================================
