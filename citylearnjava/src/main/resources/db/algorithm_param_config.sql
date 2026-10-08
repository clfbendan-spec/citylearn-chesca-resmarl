-- ============================================================================
-- 算法参数定义表 + py_file 算法配置字段
--
-- 用途
--   代码编辑器里选中 train / eval 类型的脚本时，可点「配置」按钮为该脚本挂上
--   任意数量的算法参数（例：训练数据集 = ...、评估数据集 = ...）。
--   本表是「可选参数目录」，py_file.algorithm_config 存该脚本实际选了哪些参数。
--
-- ⚠️ 表名说明（重要）
--   这里刻意叫 algorithm_param_config，不叫 algorithm_config ——
--   后者已存在且被大量使用：CHESCA / ResMARL 的算法参数键值库
--   （建表脚本 db/algorithm_config.sql，实体 com.citylearn.entity.AlgorithmConfig，
--     由 BatteryMinSocConfigService 读写 min_soc_per_hour / b_low /
--     resmarl_eval_schema 等几十个 key）。
--   两者结构不兼容（那张是 config_key 主键的键值表），同名会导致现有配置页失效。
--
-- 说明
--   1. 只需执行一次；ALTER 部分重复执行会报「Duplicate column name 'algorithm_config'」。
--   2. 两条系统数据用 INSERT ... WHERE NOT EXISTS 保证可重复执行不产生重复行。
-- ============================================================================

CREATE TABLE IF NOT EXISTS `algorithm_param_config` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `create_time` DATETIME     NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `name`        VARCHAR(128) NOT NULL COMMENT '名称（界面显示，如：训练数据集）',
    `param_name`  VARCHAR(128) NOT NULL COMMENT '参数名（如：train-schema）',
    `if_system`   TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否系统自带：1=系统预置，0=用户新增',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='算法参数定义表（可选参数目录）';

-- 默认两条系统数据（存在则跳过，可重复执行）
INSERT INTO `algorithm_param_config` (`name`, `param_name`, `if_system`)
SELECT '训练数据集', 'train-schema', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'train-schema');

INSERT INTO `algorithm_param_config` (`name`, `param_name`, `if_system`)
SELECT '评估数据集', 'eval-schema', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'eval-schema');

-- py_file 增加算法配置字段：存该脚本选中的参数，JSON 数组
--   [{"id":1,"param_name":"train-schema","value":"1"}, ...]
--   id        = algorithm_param_config.id（选的是哪个参数）
--   param_name= 参数别名（界面第二列右侧输入框填的值；留空表示沿用原名）
--   value     = 参数值；数据集类参数存 citylearn_dataset.id
ALTER TABLE `py_file`
    ADD COLUMN `algorithm_config` TEXT NULL
        COMMENT '该脚本的算法配置（JSON 数组：[{"id":..,"param_name":"..","value":".."}]）';

-- 校验
SELECT * FROM `algorithm_param_config` ORDER BY `id`;
SHOW COLUMNS FROM `py_file` LIKE 'algorithm_config';


-- ============================================================================
-- 增补 1：value_type（值类型）+ desc（参数简介）+ 系统参数「训练轮数」
--
-- value_type 决定界面「值」这一列渲染成什么控件：
--   num     → 只允许输入数字的输入框       （当前：训练轮数 train-epochs）
--   special → 特殊值，不是自由文本          （当前：两个数据集参数，渲染成数据集下拉，
--                                           值存 citylearn_dataset.id）
--   NULL    → 普通文本输入框
--
-- desc 是参数简介：界面在「名称」右侧显示一个小叹号，鼠标悬浮时显示这段文字。
--
-- ⚠️ desc 是 MySQL 保留字，SQL 里必须写成 `desc`（带反引号）。
--    实体类里同样要写 @TableField("`desc`")，否则 MyBatis-Plus 生成的 SQL 会语法错误。
--
-- ⚠️ ALTER 部分同前面一样「只需执行一次」，重复执行会报 Duplicate column name。
--    下面的 UPDATE / INSERT 可重复执行（WHERE 限定 + WHERE NOT EXISTS）。
-- ============================================================================

ALTER TABLE `algorithm_param_config`
    ADD COLUMN `value_type` VARCHAR(32)  NULL DEFAULT NULL
        COMMENT '值类型：num=只允许数字；special=特殊控件（如数据集下拉）；NULL=普通文本',
    ADD COLUMN `desc`       VARCHAR(512) NULL DEFAULT NULL
        COMMENT '参数简介（界面名称右侧小叹号悬浮显示）';

-- 两个数据集参数：值类型 = special，并补上简介
UPDATE `algorithm_param_config`
SET `value_type` = 'special',
    `desc` = '训练用的数据集：从已启用的数据集中选一个，保存的是数据集 id。'
WHERE `param_name` = 'train-schema';

UPDATE `algorithm_param_config`
SET `value_type` = 'special',
    `desc` = '评估用的数据集：同样保存数据集 id，一般与训练数据集配套选择。'
WHERE `param_name` = 'eval-schema';

-- 新增系统自带参数：训练轮数（train-epochs），值类型 = num（界面只允许输入数字）
INSERT INTO `algorithm_param_config` (`name`, `param_name`, `value_type`, `desc`, `if_system`)
SELECT '训练轮数', 'train-epochs', 'num', '训练的总轮数（epochs），只能填正整数。', 1 FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM `algorithm_param_config` WHERE `param_name` = 'train-epochs');

-- 校验
SELECT `id`, `name`, `param_name`, `value_type`, `if_system`, `desc`
FROM `algorithm_param_config` ORDER BY `id`;
