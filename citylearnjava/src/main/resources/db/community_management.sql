CREATE TABLE IF NOT EXISTS managed_community (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL,
 metadata LONGTEXT NOT NULL, token_hash VARCHAR(64) NULL, archived TINYINT NOT NULL DEFAULT 0,
 create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_building (
 community_id BIGINT NOT NULL, building_id BIGINT NOT NULL,
 PRIMARY KEY(community_id,building_id), UNIQUE KEY unique_building_owner(building_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_measurement (
 community_id BIGINT NOT NULL, timestamp_ms BIGINT NOT NULL, payload LONGTEXT NOT NULL,
 source VARCHAR(32) NOT NULL, received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(community_id,timestamp_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_ingestion_batch (
 id VARCHAR(36) NOT NULL PRIMARY KEY, community_id BIGINT NOT NULL, source VARCHAR(32) NOT NULL,
 raw_payload LONGTEXT NOT NULL, payload_hash VARCHAR(64) NOT NULL, accepted INT NOT NULL,
 duplicates INT NOT NULL, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_community_batch(community_id,create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_asset (
 community_id BIGINT NOT NULL, name VARCHAR(255) NOT NULL, sha256 VARCHAR(64) NOT NULL,
 size_bytes BIGINT NOT NULL, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(community_id,name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_dataset_owner (
 release_id VARCHAR(36) NOT NULL PRIMARY KEY, community_id BIGINT NOT NULL,
 KEY idx_community_release(community_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_publication_task (
 id VARCHAR(36) NOT NULL PRIMARY KEY, community_id BIGINT NOT NULL,
 status VARCHAR(20) NOT NULL, stage VARCHAR(80) NOT NULL,
 completed INT NOT NULL DEFAULT 0, total INT NOT NULL DEFAULT 0,
 request_json LONGTEXT NOT NULL, result_json LONGTEXT NULL, error_message TEXT NULL,
 create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, start_time TIMESTAMP NULL, end_time TIMESTAMP NULL,
 KEY idx_publication_community(community_id,create_time), KEY idx_publication_status(status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_migration (
 id VARCHAR(80) NOT NULL PRIMARY KEY, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_assessment_run (
 id VARCHAR(36) NOT NULL PRIMARY KEY, community_id BIGINT NOT NULL, release_id VARCHAR(36) NOT NULL,
 status VARCHAR(20) NOT NULL, stage VARCHAR(80) NOT NULL,
 config_json LONGTEXT NOT NULL, result_json LONGTEXT NULL, error_message TEXT NULL,
 create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, start_time TIMESTAMP NULL, end_time TIMESTAMP NULL,
 KEY idx_assessment_release(community_id,release_id,create_time), KEY idx_assessment_status(status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_assessment_kpi (
 run_id VARCHAR(36) NOT NULL, case_id VARCHAR(64) NOT NULL, level_name VARCHAR(32) NOT NULL,
 building_name VARCHAR(120) NOT NULL, cost_total DECIMAL(20,10) NULL,
 discomfort_proportion DECIMAL(20,10) NULL, score DECIMAL(20,10) NULL,
 metrics_json LONGTEXT NOT NULL, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(run_id,case_id,level_name,building_name), KEY idx_assessment_kpi_time(create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_assessment_artifact (
 run_id VARCHAR(36) NOT NULL, artifact_type VARCHAR(40) NOT NULL,
 content LONGTEXT NOT NULL, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(run_id,artifact_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS community_scenario_generation_task (
 id VARCHAR(36) NOT NULL PRIMARY KEY, community_id BIGINT NOT NULL,
 status VARCHAR(20) NOT NULL, stage VARCHAR(80) NOT NULL, completed INT NOT NULL DEFAULT 0,
 total INT NOT NULL DEFAULT 0, config_json LONGTEXT NOT NULL, result_json LONGTEXT NULL,
 error_message TEXT NULL, create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 start_time TIMESTAMP NULL, end_time TIMESTAMP NULL,
 KEY idx_scenario_task_community(community_id,create_time), KEY idx_scenario_task_status(status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
