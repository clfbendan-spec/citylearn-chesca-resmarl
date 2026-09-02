/*
 Navicat Premium Dump SQL

 Source Server         : local
 Source Server Type    : MySQL
 Source Server Version : 90300 (9.3.0)
 Source Host           : localhost:3306
 Source Schema         : citylearn

 Target Server Type    : MySQL
 Target Server Version : 90300 (9.3.0)
 File Encoding         : 65001

 Date: 01/09/2025 21:35:10
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for building_1
-- ----------------------------
DROP TABLE IF EXISTS `building_1`;
CREATE TABLE `building_1`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int NULL DEFAULT NULL,
  `hour` int NULL DEFAULT NULL,
  `day_type` int NULL DEFAULT NULL,
  `daylight_savings_status` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14, 9) NULL DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_relative_humidity` decimal(14, 9) NULL DEFAULT NULL,
  `non_shiftable_load` decimal(14, 9) NULL DEFAULT NULL,
  `dhw_demand` decimal(14, 9) NULL DEFAULT NULL,
  `cooling_demand` decimal(14, 9) NULL DEFAULT NULL,
  `heating_demand` decimal(14, 9) NULL DEFAULT NULL,
  `solar_generation` decimal(14, 9) NULL DEFAULT NULL,
  `occupant_count` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `hvac_mode` int NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for building_2
-- ----------------------------
DROP TABLE IF EXISTS `building_2`;
CREATE TABLE `building_2`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int NULL DEFAULT NULL,
  `hour` int NULL DEFAULT NULL,
  `day_type` int NULL DEFAULT NULL,
  `daylight_savings_status` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14, 9) NULL DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_relative_humidity` decimal(14, 9) NULL DEFAULT NULL,
  `non_shiftable_load` decimal(14, 9) NULL DEFAULT NULL,
  `dhw_demand` decimal(14, 9) NULL DEFAULT NULL,
  `cooling_demand` decimal(14, 9) NULL DEFAULT NULL,
  `heating_demand` decimal(14, 9) NULL DEFAULT NULL,
  `solar_generation` decimal(14, 9) NULL DEFAULT NULL,
  `occupant_count` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `hvac_mode` int NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for building_3
-- ----------------------------
DROP TABLE IF EXISTS `building_3`;
CREATE TABLE `building_3`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `month` int NULL DEFAULT NULL,
  `hour` int NULL DEFAULT NULL,
  `day_type` int NULL DEFAULT NULL,
  `daylight_savings_status` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature` decimal(14, 9) NULL DEFAULT NULL,
  `average_unmet_cooling_setpoint_difference` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_relative_humidity` decimal(14, 9) NULL DEFAULT NULL,
  `non_shiftable_load` decimal(14, 9) NULL DEFAULT NULL,
  `dhw_demand` decimal(14, 9) NULL DEFAULT NULL,
  `cooling_demand` decimal(14, 9) NULL DEFAULT NULL,
  `heating_demand` decimal(14, 9) NULL DEFAULT NULL,
  `solar_generation` decimal(14, 9) NULL DEFAULT NULL,
  `occupant_count` int NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_cooling_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `indoor_dry_bulb_temperature_heating_set_point` decimal(14, 9) NULL DEFAULT NULL,
  `hvac_mode` int NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for carbon_intensity
-- ----------------------------
DROP TABLE IF EXISTS `carbon_intensity`;
CREATE TABLE `carbon_intensity`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `carbon_intensity` decimal(14, 9) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for kpis
-- ----------------------------
DROP TABLE IF EXISTS `kpis`;
CREATE TABLE `kpis`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `agent_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `all_time_peak_average` decimal(8, 5) NULL DEFAULT NULL,
  `annual_normalized_unserved_energy_total` decimal(8, 5) NULL DEFAULT NULL,
  `carbon_emissions_total` decimal(8, 5) NULL DEFAULT NULL,
  `cost_total` decimal(8, 5) NULL DEFAULT NULL,
  `daily_one_minus_load_factor_average` decimal(8, 5) NULL DEFAULT NULL,
  `daily_peak_average` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_cold_delta_average` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_cold_delta_maximum` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_cold_delta_minimum` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_cold_proportion` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_hot_delta_average` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_hot_delta_maximum` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_hot_delta_minimum` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_hot_proportion` decimal(8, 5) NULL DEFAULT NULL,
  `discomfort_proportion` decimal(8, 5) NULL DEFAULT NULL,
  `electricity_consumption_total` decimal(8, 5) NULL DEFAULT NULL,
  `monthly_one_minus_load_factor_average` decimal(8, 5) NULL DEFAULT NULL,
  `one_minus_thermal_resilience_proportion` decimal(8, 5) NULL DEFAULT NULL,
  `power_outage_normalized_unserved_energy_total` decimal(8, 5) NULL DEFAULT NULL,
  `ramping_average` decimal(8, 5) NULL DEFAULT NULL,
  `zero_net_energy` decimal(8, 5) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 57 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for pricing
-- ----------------------------
DROP TABLE IF EXISTS `pricing`;
CREATE TABLE `pricing`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `electricity_pricing` decimal(12, 5) NULL DEFAULT NULL,
  `electricity_pricing_predicted_1` decimal(12, 5) NULL DEFAULT NULL,
  `electricity_pricing_predicted_2` decimal(12, 5) NULL DEFAULT NULL,
  `electricity_pricing_predicted_3` decimal(12, 5) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for weather
-- ----------------------------
DROP TABLE IF EXISTS `weather`;
CREATE TABLE `weather`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `outdoor_dry_bulb_temperature` decimal(12, 2) NULL DEFAULT NULL,
  `outdoor_relative_humidity` decimal(12, 2) NULL DEFAULT NULL,
  `diffuse_solar_irradiance` decimal(12, 2) NULL DEFAULT NULL,
  `direct_solar_irradiance` decimal(12, 2) NULL DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_1` decimal(12, 6) NULL DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_2` decimal(12, 6) NULL DEFAULT NULL,
  `outdoor_dry_bulb_temperature_predicted_3` decimal(12, 6) NULL DEFAULT NULL,
  `outdoor_relative_humidity_predicted_1` decimal(12, 6) NULL DEFAULT NULL,
  `outdoor_relative_humidity_predicted_2` decimal(12, 6) NULL DEFAULT NULL,
  `outdoor_relative_humidity_predicted_3` decimal(12, 6) NULL DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_1` decimal(12, 6) NULL DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_2` decimal(12, 6) NULL DEFAULT NULL,
  `diffuse_solar_irradiance_predicted_3` decimal(12, 6) NULL DEFAULT NULL,
  `direct_solar_irradiance_predicted_1` decimal(12, 5) NULL DEFAULT NULL,
  `direct_solar_irradiance_predicted_2` decimal(12, 5) NULL DEFAULT NULL,
  `direct_solar_irradiance_predicted_3` decimal(12, 5) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 721 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;

-- ----------------------------
-- Table structure for py_file
-- ----------------------------
DROP TABLE IF EXISTS `py_file`;
CREATE TABLE `py_file`  (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `file_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `desc` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `if_system` tinyint(1) NULL DEFAULT NULL,
  `create_time` datetime NULL DEFAULT NULL,
  `create_user` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;
