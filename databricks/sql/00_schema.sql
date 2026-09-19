-- Seuranta Bronze contract.
-- SQL task parameters :catalog and :schema are supplied by the bundle. The
-- API writes append-only records to these tables through the workspace's
-- ingestion job or an approved batch connector; this bundle never accepts
-- identifiers from request payloads.

CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema);

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_raw') (
  schema_version STRING,
  observation_id STRING,
  observed_at TIMESTAMP,
  timestamp_ms BIGINT,
  run_id STRING,
  deployment_id STRING,
  building_id STRING,
  floor_id STRING,
  anchor_id STRING,
  session_id STRING,
  rssi_dbm INT,
  channel INT,
  source STRING,
  mode STRING,
  sequence_number BIGINT,
  ingested_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.position_estimates_raw') (
  schema_version STRING,
  position_id STRING,
  calculated_at TIMESTAMP,
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  run_id STRING,
  deployment_id STRING,
  building_id STRING,
  floor_id STRING,
  session_id STRING,
  raw_x_m DOUBLE,
  raw_y_m DOUBLE,
  x_m DOUBLE,
  y_m DOUBLE,
  zone_id STRING,
  confidence DOUBLE,
  accuracy_radius_m DOUBLE,
  position_method STRING,
  smoothing_method STRING,
  anchors_used ARRAY<STRING>,
  observation_count BIGINT,
  mode STRING,
  sequence_number BIGINT,
  is_outside_map BOOLEAN,
  ingested_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_raw') (
  schema_version STRING,
  event_id STRING,
  event_type STRING,
  occurred_at TIMESTAMP,
  emitted_at TIMESTAMP,
  run_id STRING,
  deployment_id STRING,
  building_id STRING,
  floor_id STRING,
  mode STRING,
  session_id STRING,
  zone_id STRING,
  position_id STRING,
  dwell_ms BIGINT,
  occupancy_after BIGINT,
  confidence DOUBLE,
  event_sequence BIGINT,
  metadata_json STRING,
  ingested_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.node_heartbeats_raw') (
  schema_version STRING,
  heartbeat_id STRING,
  emitted_at TIMESTAMP,
  run_id STRING,
  deployment_id STRING,
  building_id STRING,
  floor_id STRING,
  anchor_id STRING,
  node_kind STRING,
  mode STRING,
  status STRING,
  agent_version STRING,
  uptime_s BIGINT,
  buffer_depth BIGINT,
  observations_sent_total BIGINT,
  last_observation_at TIMESTAMP,
  capture_ok BOOLEAN,
  error_codes ARRAY<STRING>,
  ingested_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.sessions_raw') (
  schema_version STRING,
  session_id STRING,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  run_id STRING,
  deployment_id STRING,
  building_id STRING,
  floor_id STRING,
  mode STRING,
  ingested_at TIMESTAMP
) USING DELTA;
