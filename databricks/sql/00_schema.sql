-- Parameters are supplied by the Databricks SQL task.  Keep identifiers
-- controlled by deployment configuration; values are never string-concatenated
-- from API requests.
CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema);

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_raw') (
  observation_id STRING,
  observed_at TIMESTAMP,
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

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.node_heartbeats_raw') USING DELTA AS
SELECT CAST(NULL AS STRING) AS heartbeat_id, CAST(NULL AS TIMESTAMP) AS emitted_at,
       CAST(NULL AS STRING) AS run_id, CAST(NULL AS STRING) AS deployment_id,
       CAST(NULL AS STRING) AS building_id, CAST(NULL AS STRING) AS floor_id,
       CAST(NULL AS STRING) AS anchor_id, CAST(NULL AS STRING) AS node_kind,
       CAST(NULL AS STRING) AS mode, CAST(NULL AS STRING) AS status,
       CAST(NULL AS STRING) AS agent_version, CAST(NULL AS BIGINT) AS uptime_s,
       CAST(NULL AS BIGINT) AS buffer_depth, CAST(NULL AS BIGINT) AS observations_sent_total,
       CAST(NULL AS TIMESTAMP) AS last_observation_at, CAST(NULL AS BOOLEAN) AS capture_ok,
       CAST(NULL AS ARRAY<STRING>) AS error_codes, CAST(NULL AS TIMESTAMP) AS ingested_at
WHERE FALSE;
