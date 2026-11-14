CREATE TABLE IF NOT EXISTS managed_building (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  metadata LONGTEXT NOT NULL,
  token_hash VARCHAR(64) NULL,
  archived TINYINT NOT NULL DEFAULT 0,
  create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS building_measurement (
  building_id BIGINT NOT NULL,
  timestamp_ms BIGINT NOT NULL,
  payload LONGTEXT NOT NULL,
  source VARCHAR(32) NOT NULL,
  received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (building_id, timestamp_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS building_ingestion_batch (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  building_id BIGINT NOT NULL,
  source VARCHAR(32) NOT NULL,
  raw_payload LONGTEXT NOT NULL,
  payload_hash VARCHAR(64) NOT NULL,
  accepted INT NOT NULL,
  duplicates INT NOT NULL,
  create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_building_batch (building_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS building_dataset_version (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  building_id BIGINT NOT NULL,
  schema_key VARCHAR(128) NOT NULL UNIQUE,
  name VARCHAR(160) NOT NULL,
  purpose VARCHAR(16) NOT NULL,
  start_time VARCHAR(40) NOT NULL,
  end_time VARCHAR(40) NOT NULL,
  time_steps INT NOT NULL,
  relative_path VARCHAR(512) NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_building_version (building_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO permission (id, code, name, parent_code, sort_order, enabled) VALUES
('building-menu', 'menu:buildingManagement', '建筑管理', NULL, 31, 1),
('building-write', 'building:write', '维护建筑与接入数据', 'menu:buildingManagement', 32, 1);

CREATE TABLE IF NOT EXISTS building_experiment_run (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  building_id BIGINT NOT NULL,
  version_id VARCHAR(36) NOT NULL,
  mode VARCHAR(16) NOT NULL,
  status VARCHAR(16) NOT NULL,
  config_json LONGTEXT NOT NULL,
  result_json LONGTEXT NULL,
  error_message TEXT NULL,
  create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_building_run (building_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS building_experiment_lock (
  id INT NOT NULL PRIMARY KEY
) ENGINE=InnoDB;
INSERT IGNORE INTO building_experiment_lock(id) VALUES (1);

CREATE TABLE IF NOT EXISTS community_dataset_release (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  schema_key VARCHAR(128) NOT NULL UNIQUE,
  name VARCHAR(160) NOT NULL,
  start_time VARCHAR(40) NOT NULL,
  end_time VARCHAR(40) NOT NULL,
  time_steps INT NOT NULL,
  building_count INT NOT NULL,
  sources_json LONGTEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
