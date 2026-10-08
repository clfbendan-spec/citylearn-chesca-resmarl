-- MySQL dump 10.13  Distrib 9.3.0, for Win64 (x86_64)
--
-- Host: localhost    Database: citylearn
-- ------------------------------------------------------
-- Server version	9.3.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `algorithm_config`
--

DROP TABLE IF EXISTS `algorithm_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `algorithm_config` (
  `config_key` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '配置键',
  `config_value` text COLLATE utf8mb4_general_ci NOT NULL COMMENT '配置值',
  `value_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'string' COMMENT 'number|json|string',
  `description` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '说明',
  `update_time` datetime DEFAULT NULL,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `algorithm_param_config`
--

DROP TABLE IF EXISTS `algorithm_param_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `algorithm_param_config` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '名称（界面显示，如：训练数据集）',
  `param_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '参数名（如：train-schema）',
  `if_system` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否系统自带：1=系统预置，0=用户新增',
  `value_type` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '值类型：num=数字；text=文字；bool=布尔；ratio=单选；multiple=多选（后两者候选项存 default_value）；special=数据集（历史值）；NULL=普通文本',
  `desc` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参数简介（界面名称右侧小叹号悬浮显示）',
  `default_value` text COLLATE utf8mb4_general_ci COMMENT '单选(ratio)/多选(multiple)的可选项，JSON 数组：[{"key":"..","value":".."}]',
  `is_member` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否为配置组成员：1=是（出现在某个配置组的 members 里），0=否',
  `key_alias` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '值类型为 map 时，键的别名（如「选择时段」）；其它类型为 NULL',
  `value_alias` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '值类型为 map 时，值的别名（如「电池 SOC 下限」）；其它类型为 NULL',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=61 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='算法参数定义表（可选参数目录）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `algorithm_param_config_set`
--

DROP TABLE IF EXISTS `algorithm_param_config_set`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `algorithm_param_config_set` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '组名称',
  `desc` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '简介',
  `members` text COLLATE utf8mb4_general_ci COMMENT '组成员：algorithm_param_config.id 的 JSON 数组，如 [1,2,3]',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='算法参数配置组';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `building_1`
--

DROP TABLE IF EXISTS `building_1`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `building_1` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int DEFAULT NULL,
  `hour` int DEFAULT NULL,
  `day_type` int DEFAULT NULL,
  `daylight_savings_status` int DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14,9) DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14,9) DEFAULT NULL,
  `indoor_relative_humidity` decimal(14,9) DEFAULT NULL,
  `non_shiftable_load` decimal(14,9) DEFAULT NULL,
  `dhw_demand` decimal(14,9) DEFAULT NULL,
  `cooling_demand` decimal(14,9) DEFAULT NULL,
  `heating_demand` decimal(14,9) DEFAULT NULL,
  `solar_generation` decimal(14,9) DEFAULT NULL,
  `occupant_count` int DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14,9) DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14,9) DEFAULT NULL,
  `hvac_mode` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `building_2`
--

DROP TABLE IF EXISTS `building_2`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `building_2` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int DEFAULT NULL,
  `hour` int DEFAULT NULL,
  `day_type` int DEFAULT NULL,
  `daylight_savings_status` int DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14,9) DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14,9) DEFAULT NULL,
  `indoor_relative_humidity` decimal(14,9) DEFAULT NULL,
  `non_shiftable_load` decimal(14,9) DEFAULT NULL,
  `dhw_demand` decimal(14,9) DEFAULT NULL,
  `cooling_demand` decimal(14,9) DEFAULT NULL,
  `heating_demand` decimal(14,9) DEFAULT NULL,
  `solar_generation` decimal(14,9) DEFAULT NULL,
  `occupant_count` int DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14,9) DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14,9) DEFAULT NULL,
  `hvac_mode` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `building_3`
--

DROP TABLE IF EXISTS `building_3`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `building_3` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int DEFAULT NULL,
  `hour` int DEFAULT NULL,
  `day_type` int DEFAULT NULL,
  `daylight_savings_status` int DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14,9) DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14,9) DEFAULT NULL,
  `indoor_relative_humidity` decimal(14,9) DEFAULT NULL,
  `non_shiftable_load` decimal(14,9) DEFAULT NULL,
  `dhw_demand` decimal(14,9) DEFAULT NULL,
  `cooling_demand` decimal(14,9) DEFAULT NULL,
  `heating_demand` decimal(14,9) DEFAULT NULL,
  `solar_generation` decimal(14,9) DEFAULT NULL,
  `occupant_count` int DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14,9) DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14,9) DEFAULT NULL,
  `hvac_mode` int DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `carbon_intensity`
--

DROP TABLE IF EXISTS `carbon_intensity`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `carbon_intensity` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `carbon_intensity` decimal(14,9) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `citylearn_dataset`
--

DROP TABLE IF EXISTS `citylearn_dataset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `citylearn_dataset` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schema_key` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT 'CityLearn schema 鐩?綍鍚?/ 閫夋嫨鍊',
  `display_name` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '鍓嶇?灞曠ず鍚嶇О',
  `relative_path` varchar(512) COLLATE utf8mb4_general_ci NOT NULL COMMENT '鐩稿? python-file-path 鐨勭洰褰曡矾寰',
  `building_count` int NOT NULL DEFAULT '3' COMMENT '寤虹瓚鏁伴噺',
  `time_steps` int DEFAULT NULL COMMENT '鏃堕棿姝ユ暟',
  `chesca_compatible` tinyint(1) NOT NULL DEFAULT '1' COMMENT '鏄?惁鍏煎? CHESCA',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '鏄?惁鍦ㄩ?鎷╁垪琛ㄤ腑灞曠ず',
  `sort_order` int NOT NULL DEFAULT '0' COMMENT '鎺掑簭锛堝崌搴忥級',
  `description` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_schema_key` (`schema_key`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `community`
--

DROP TABLE IF EXISTS `community`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `community` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '社区ID主键',
  `community_name` varchar(100) NOT NULL COMMENT '社区名称(如CityLearn_2023)',
  `description` text COMMENT '社区描述信息',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='社区基础信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `community_building`
--

DROP TABLE IF EXISTS `community_building`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `community_building` (
  `id` varchar(64) NOT NULL COMMENT '建筑ID主键',
  `name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '建筑名称',
  `description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '建筑信息',
  `image_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '图片地址',
  `if_delete` bit(1) DEFAULT NULL COMMENT '删除标记',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='建筑基础信息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kpis`
--

DROP TABLE IF EXISTS `kpis`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kpis` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `agent_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `all_time_peak_average` decimal(8,5) DEFAULT NULL,
  `annual_normalized_unserved_energy_total` decimal(8,5) DEFAULT NULL,
  `carbon_emissions_total` decimal(8,5) DEFAULT NULL,
  `cost_total` decimal(8,5) DEFAULT NULL,
  `daily_one_minus_load_factor_average` decimal(8,5) DEFAULT NULL,
  `daily_peak_average` decimal(8,5) DEFAULT NULL,
  `discomfort_cold_delta_average` decimal(8,5) DEFAULT NULL,
  `discomfort_cold_delta_maximum` decimal(8,5) DEFAULT NULL,
  `discomfort_cold_delta_minimum` decimal(8,5) DEFAULT NULL,
  `discomfort_cold_proportion` decimal(8,5) DEFAULT NULL,
  `discomfort_hot_delta_average` decimal(8,5) DEFAULT NULL,
  `discomfort_hot_delta_maximum` decimal(8,5) DEFAULT NULL,
  `discomfort_hot_delta_minimum` decimal(8,5) DEFAULT NULL,
  `discomfort_hot_proportion` decimal(8,5) DEFAULT NULL,
  `discomfort_proportion` decimal(8,5) DEFAULT NULL,
  `electricity_consumption_total` decimal(8,5) DEFAULT NULL,
  `monthly_one_minus_load_factor_average` decimal(8,5) DEFAULT NULL,
  `one_minus_thermal_resilience_proportion` decimal(8,5) DEFAULT NULL,
  `power_outage_normalized_unserved_energy_total` decimal(8,5) DEFAULT NULL,
  `ramping_average` decimal(8,5) DEFAULT NULL,
  `zero_net_energy` decimal(8,5) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1133 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `permission`
--

DROP TABLE IF EXISTS `permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permission` (
  `id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `code` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '权限码',
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '显示名称',
  `parent_code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '父权限码，空表示顶级',
  `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序（升序）',
  `enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_permission_code` (`code`),
  KEY `idx_parent_code` (`parent_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='系统权限';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `pricing`
--

DROP TABLE IF EXISTS `pricing`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pricing` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `electricity_pricing` decimal(12,5) DEFAULT NULL,
  `electricity_pricing_predicted_1` decimal(12,5) DEFAULT NULL,
  `electricity_pricing_predicted_2` decimal(12,5) DEFAULT NULL,
  `electricity_pricing_predicted_3` decimal(12,5) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `py_file`
--

DROP TABLE IF EXISTS `py_file`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `py_file` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `file_name` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文件名',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '文件注释',
  `if_system` bit(1) DEFAULT NULL COMMENT '是否为系统默认文件',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `create_user` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人用户名',
  `name` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '代码名',
  `if_show` bit(1) DEFAULT NULL COMMENT '是否展示此文件对应结果',
  `script_type` varchar(16) COLLATE utf8mb4_general_ci DEFAULT 'both' COMMENT '脚本类型：train 只训练 / eval 只评估 / both 训练+评估一体',
  `algorithm_config` text COLLATE utf8mb4_general_ci COMMENT '该脚本的算法配置（JSON 数组：[{"id":..,"param_name":"..","value":".."}]）',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `py_task`
--

DROP TABLE IF EXISTS `py_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `py_task` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '任务 id；编排任务的子任务为 <父任务id>-train / <父任务id>-eval',
  `py_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'python文件id',
  `status` int DEFAULT NULL COMMENT '执行状态(0执行中 1执行完成 2执行失败)',
  `task_name` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '任务名称：type=0 编排任务的名称；type=1 不用此列（名称取 py_file.file_name）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `if_delete` bit(1) DEFAULT NULL COMMENT '删除标记',
  `if_show` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'dashboard show flag',
  `show_name` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'dashboard display name',
  `if_notified` tinyint(1) DEFAULT '0' COMMENT '是否已提醒/已读：0 未读（执行完成后尚未被查看） 1 已读',
  `type` tinyint(1) NOT NULL DEFAULT '1' COMMENT '任务类型：0=训练+评估编排任务，1=代码编辑器直接执行的简易任务',
  `train_config` text COLLATE utf8mb4_general_ci COMMENT '训练卡配置（JSON 字符串，仅 type=0 有值）',
  `eval_config` text COLLATE utf8mb4_general_ci COMMENT '评估卡配置（JSON 字符串，仅 type=0 有值）',
  `is_subtask` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否子任务：1=编排任务拆出的训练/评估子任务（任务管理页主列表不显示）',
  `config` text COLLATE utf8mb4_general_ci COMMENT '本任务的脚本配置（卡片 JSON：{pyId,scriptName,datasetId,schemaKey,datasetName,trainEpochs,trainBatchSize,config}）',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '涓婚敭',
  `username` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '鐧诲綍鐢ㄦ埛鍚',
  `password` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '鐧诲綍瀵嗙爜',
  `nickname` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '鏄剧ず鍚嶇О',
  `role` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '瑙掕壊锛歋UPER_ADMIN=瓒呯?锛孉DMIN=绯荤粺绠＄悊鍛',
  `if_delete` tinyint(1) NOT NULL DEFAULT '0' COMMENT '鍒犻櫎鏍囪?',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '鍒涘缓鏃堕棿',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '鏇存柊鏃堕棿',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='绯荤粺鐢ㄦ埛';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_permission`
--

DROP TABLE IF EXISTS `user_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_permission` (
  `id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `user_id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '用户 ID',
  `permission_id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '权限 ID',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_permission` (`user_id`,`permission_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_permission_id` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户权限关联';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `weather`
--

DROP TABLE IF EXISTS `weather`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `weather` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `outdoor_dry_bulb_temperature` decimal(12,2) DEFAULT NULL,
  `outdoor_relative_humidity` decimal(12,2) DEFAULT NULL,
  `diffuse_solar_irradiance` decimal(12,2) DEFAULT NULL,
  `direct_solar_irradiance` decimal(12,2) DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_1` decimal(12,6) DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_2` decimal(12,6) DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_3` decimal(12,6) DEFAULT NULL,
  `outdoor_relative_humidity_predicted_1` decimal(12,6) DEFAULT NULL,
  `outdoor_relative_humidity_predicted_2` decimal(12,6) DEFAULT NULL,
  `outdoor_relative_humidity_predicted_3` decimal(12,6) DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_1` decimal(12,6) DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_2` decimal(12,6) DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_3` decimal(12,6) DEFAULT NULL,
  `direct_solar_irradiance_predicted_1` decimal(12,5) DEFAULT NULL,
  `direct_solar_irradiance_predicted_2` decimal(12,5) DEFAULT NULL,
  `direct_solar_irradiance_predicted_3` decimal(12,5) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'citylearn'
--

--
-- Dumping routines for database 'citylearn'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-08 22:41:48
