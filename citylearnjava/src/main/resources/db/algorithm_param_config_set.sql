-- ============================================================================
-- 参数配置「配置组」：algorithm_param_config_set 表 + algorithm_param_config.is_member
-- ----------------------------------------------------------------------------
-- 背景
--   「参数配置」页原来只有一列参数清单。现在引入「配置组」概念 —— 一组相关参数的集合，
--   页面上用页签切换「单独配置 / 配置组」：
--     · 单独配置：未加入任何配置组的参数（is_member = 0）
--     · 配置组  ：组清单 → 点「详情」进入组内参数页，可在其中添加/编辑参数配置
--
-- 1) algorithm_param_config_set（配置组）
--     id          主键
--     create_time 创建时间
--     name        组名称
--     desc        简介
--     members     组成员：algorithm_param_config.id 的 JSON 数组，如 [1,2,3]
--
-- 2) algorithm_param_config 增加 is_member
--      =1 属于某个配置组，=0 不属于
--      这是 members 的冗余索引列 —— 目的只是让「单独配置」页能一句 SQL 过滤出来，
--      不必把几十个组的 members 反查一遍。写入组时由后端同步维护。
--
-- 执行方式（本项目手工执行 db/*.sql，无自动迁移）：
--   mysql -uroot -p000000 citylearn < algorithm_param_config_set.sql
--
-- ⚠️ ALTER 那句只需执行一次，重复执行会报 Duplicate column name，跳过继续即可；
--    其余语句幂等，可重复执行。
-- ============================================================================

CREATE TABLE IF NOT EXISTS `algorithm_param_config_set` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    `create_time` DATETIME     NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `name`        VARCHAR(128) NOT NULL COMMENT '组名称',
    `desc`        VARCHAR(512) NULL DEFAULT NULL COMMENT '简介',
    `members`     TEXT         NULL COMMENT '组成员：algorithm_param_config.id 的 JSON 数组，如 [1,2,3]',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='算法参数配置组';

ALTER TABLE `algorithm_param_config`
    ADD COLUMN `is_member` TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否为配置组成员：1=是（出现在某个配置组的 members 里），0=否';

-- 原有数据一律置 0（默认值已保证，这里再显式收敛一次，防手工插入时漏填）
UPDATE `algorithm_param_config` SET `is_member` = 0 WHERE `is_member` <> 0;

-- 校验
SELECT `id`, `name`, `param_name`, `value_type`, `is_member` FROM `algorithm_param_config` ORDER BY `id`;
SHOW COLUMNS FROM `algorithm_param_config_set`;
