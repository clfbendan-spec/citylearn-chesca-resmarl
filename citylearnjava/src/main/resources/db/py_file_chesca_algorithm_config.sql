-- ============================================================================
-- 把「配置页」里的 CHESCA 参数（含当前取值）灌进**代码编辑器** CHESCA.py 的脚本配置
-- ----------------------------------------------------------------------------
-- 目标：py_file.algorithm_config（file_name = 'CHESCA.py'）
--   ⇒ 编辑器里选中 CHESCA.py 点「配置」，7 个配置组已挂好、值也填好了。
--
-- 落库格式（与 AlgorithmConfigDialog.vue 的 buildSectionsFromFile 逐字一致）
--   [ {"type":"alone","params":[]},
--     {"type":"set","set_id":<配置组 id>,"params":[{"id":..,"param_name":"..","value":".."}, ...]},
--     ... ]
--   · type=set 的字段名是 set_id（下划线 ✓）；params[].id = algorithm_param_config.id ✓
--   · 第一个 section 固定是「单独配置」空卡（弹窗约定 ✓）
--
-- 取值来源 = **配置页**（表 algorithm_config，由 BatteryMinSocConfigService 维护）
--   · 一般参数：取同名 key 的当前值
--   · B_low / B_high / TMP_max_reduction_percent：配置页里存的是**小写键** ⇒ 这里做名字映射
--   · eval_schema（value_type=special）：配置页存的是 schema 名 ⇒ 换成 citylearn_dataset.id
--     （弹窗只认 id ✓，与 eval-schema 那条同一处理 ✓）
--   · min_soc_per_hour（value_type=map）：取目录的 default_value（本就是弹窗要的
--     [{"key":"0","value":"0.6"}, ...] 形状 ✓）；map 类参数不会被翻成命令行参数 ✓
--   · 配置页没存过的键 ⇒ 空串（界面显示未填，运行时走脚本默认 ✓）
--
-- ⚠️ 先决条件：先跑 algorithm_param_config_chesca_groups2.sql（7 组齐全 ✓）；
--    缺组也不会写出非法 JSON（缺的组自动跳过 ✓）。
-- ⚠️ 会**覆盖** CHESCA.py 现有脚本配置 ⇒ 先看第 0 步的预览 ✓。
-- 可重复执行 ✓（每次都按当时的配置页取值重新生成 ✓）。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < py_file_chesca_algorithm_config.sql
-- ============================================================================

-- group_concat 默认上限只有 1024 字节 ⇒ 45 个参数约 2.7KB 会被**截断** ✗ ⇒ 先放开 ✓
SET SESSION group_concat_max_len = 1000000;

-- ---------------------------------------------------------------------------
-- 0) 执行前预览：现在配了什么（确认下面要覆盖掉什么）
-- ---------------------------------------------------------------------------
SELECT `file_name`, CHAR_LENGTH(`algorithm_config`) AS `len`,
       LEFT(`algorithm_config`, 300) AS `head`
FROM `py_file`
WHERE `file_name` = 'CHESCA.py';

-- ---------------------------------------------------------------------------
-- 1) 生成 7 个配置组的 JSON 片段（缺组自然没有那一段 ✓；组序固定为人类可读顺序 ✓）
-- ---------------------------------------------------------------------------
SET @sets = (
    SELECT CONCAT('[', GROUP_CONCAT(`sec` ORDER BY `ord` SEPARATOR ','), ']')
    FROM (
        SELECT CONCAT(
                   '{"type":"set","set_id":', `s`.`id`, ',"params":[',
                   GROUP_CONCAT(
                       CONCAT('{"id":', `p`.`id`,
                              ',"param_name":"', `p`.`param_name`,
                              '","value":"', `val`.`v`, '"}')
                       ORDER BY `p`.`id` SEPARATOR ','
                   ),
                   ']}'
               ) AS `sec`,
               FIELD(`s`.`name`,
                     '冷机', '电力恢复时 TMP 功率帽', '电力恢复后缓充', 'SOC 参数配置',
                     '电价感知电池', '树搜索与负荷阈值', '纯CHESCA 评估数据集') AS `ord`
        FROM `algorithm_param_config_set` AS `s`
        JOIN `algorithm_param_config` AS `p`
          ON FIND_IN_SET(`p`.`id`, REPLACE(REPLACE(`s`.`members`, '[', ''), ']', '')) > 0
        JOIN (
            SELECT `p2`.`id` AS `pid`,
                   CASE
                     -- special（数据集）⇒ citylearn_dataset.id
                     WHEN `p2`.`value_type` = 'special' THEN COALESCE(CAST((
                          SELECT `d`.`id` FROM `citylearn_dataset` AS `d`
                          WHERE `d`.`schema_key` = (
                                SELECT `a`.`config_value` FROM `algorithm_config` AS `a`
                                WHERE `a`.`config_key` = 'eval_schema')
                          ORDER BY `d`.`enabled` DESC, `d`.`id` LIMIT 1) AS CHAR), '')
                     -- map（键值对）⇒ 目录里的 default_value（已是弹窗形状 ✓，含双引号 ⇒ 转义 ✓）
                     WHEN `p2`.`value_type` = 'map'
                          THEN REPLACE(COALESCE(`p2`.`default_value`, ''), '"', '\\"')
                     -- 其余 ⇒ 配置页当前值（三个大小写不同的键做映射 ✓）
                     ELSE COALESCE((
                          SELECT `a2`.`config_value` FROM `algorithm_config` AS `a2`
                          WHERE `a2`.`config_key` = CASE `p2`.`param_name`
                                    WHEN 'B_low' THEN 'b_low'
                                    WHEN 'B_high' THEN 'b_high'
                                    WHEN 'TMP_max_reduction_percent' THEN 'tmp_max_reduction_percent'
                                    ELSE `p2`.`param_name` END), '')
                   END AS `v`
            FROM `algorithm_param_config` AS `p2`
        ) AS `val` ON `val`.`pid` = `p`.`id`
        WHERE `s`.`name` IN (
            '冷机', '电力恢复时 TMP 功率帽', '电力恢复后缓充', 'SOC 参数配置',
            '电价感知电池', '树搜索与负荷阈值', '纯CHESCA 评估数据集')
        GROUP BY `s`.`id`, `s`.`name`
    ) AS `t`
);

-- ---------------------------------------------------------------------------
-- 2) 写进 py_file（第一个 section = 「单独配置」空卡 ✓）
-- ---------------------------------------------------------------------------
UPDATE `py_file`
SET `algorithm_config` = CONCAT(
        '[{"type":"alone","params":[]}',
        IF(@sets IS NULL OR @sets = '' OR @sets = '[]', '', CONCAT(',', @sets)),
        ']')
WHERE `file_name` = 'CHESCA.py';

-- ---------------------------------------------------------------------------
-- 3) 校验
-- ---------------------------------------------------------------------------
-- 3.1 顶层是合法 JSON，section 数应为 8（1 个 alone + 7 个 set）
SELECT `file_name`,
       JSON_VALID(`algorithm_config`) AS `json_ok`,
       JSON_LENGTH(`algorithm_config`) AS `section_count`,
       CHAR_LENGTH(`algorithm_config`) AS `len`
FROM `py_file`
WHERE `file_name` = 'CHESCA.py';

-- 3.2 前 600 字符预览（人眼确认结构 ✓）
SELECT LEFT(`algorithm_config`, 600) AS `head`
FROM `py_file`
WHERE `file_name` = 'CHESCA.py';

-- 3.3 各 section 的类型与参数个数（应见 alone=0；7 个 set = 12/5/6/4/13/4/1）
SELECT `t`.`idx` AS `section_no`,
       JSON_UNQUOTE(JSON_EXTRACT(`algorithm_config`, CONCAT('$[', `t`.`idx`, '].type'))) AS `type`,
       JSON_UNQUOTE(JSON_EXTRACT(`algorithm_config`, CONCAT('$[', `t`.`idx`, '].set_id'))) AS `set_id`,
       JSON_LENGTH(JSON_EXTRACT(`algorithm_config`, CONCAT('$[', `t`.`idx`, '].params`))) AS `param_count`
FROM `py_file`,
     (SELECT 0 AS `idx` UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
      UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7) AS `t`
WHERE `file_name` = 'CHESCA.py';
