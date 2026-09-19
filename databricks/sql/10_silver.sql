-- Seuranta Silver contract.
-- Silver is rebuilt idempotently from Bronze. IDs are the deduplication key;
-- the newest ingested record wins when a batch is replayed.

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_clean')
USING DELTA AS
WITH ranked AS (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY observation_id
    ORDER BY observed_at DESC NULLS LAST, ingested_at DESC NULLS LAST
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_raw') r
  WHERE observation_id IS NOT NULL
    AND observed_at IS NOT NULL
    AND run_id IS NOT NULL
    AND deployment_id IS NOT NULL
    AND building_id IS NOT NULL
    AND floor_id IS NOT NULL
    AND anchor_id IS NOT NULL
    AND session_id IS NOT NULL
    AND mode IN ('real', 'simulated')
    AND rssi_dbm BETWEEN -127 AND 0
)
SELECT schema_version, observation_id, observed_at, timestamp_ms, run_id,
       deployment_id, building_id, floor_id, anchor_id, session_id, rssi_dbm,
       channel, source, mode, sequence_number, ingested_at
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.position_estimates_clean')
USING DELTA AS
WITH ranked AS (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY position_id
    ORDER BY calculated_at DESC NULLS LAST, ingested_at DESC NULLS LAST
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.position_estimates_raw') r
  WHERE position_id IS NOT NULL
    AND calculated_at IS NOT NULL
    AND window_start IS NOT NULL
    AND window_end IS NOT NULL
    AND run_id IS NOT NULL
    AND deployment_id IS NOT NULL
    AND building_id IS NOT NULL
    AND floor_id IS NOT NULL
    AND session_id IS NOT NULL
    AND x_m IS NOT NULL
    AND y_m IS NOT NULL
    AND confidence BETWEEN 0 AND 1
    AND accuracy_radius_m >= 0
    AND mode IN ('real', 'simulated')
)
SELECT schema_version, position_id, calculated_at, window_start, window_end,
       run_id, deployment_id, building_id, floor_id, session_id, raw_x_m,
       raw_y_m, x_m, y_m, zone_id, confidence, accuracy_radius_m,
       position_method, smoothing_method, anchors_used, observation_count,
       mode, sequence_number, is_outside_map, ingested_at
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_clean')
USING DELTA AS
WITH ranked AS (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY event_id
    ORDER BY emitted_at DESC NULLS LAST, ingested_at DESC NULLS LAST
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_raw') r
  WHERE event_id IS NOT NULL
    AND event_type IS NOT NULL
    AND occurred_at IS NOT NULL
    AND emitted_at IS NOT NULL
    AND run_id IS NOT NULL
    AND deployment_id IS NOT NULL
    AND building_id IS NOT NULL
    AND floor_id IS NOT NULL
    AND mode IN ('real', 'simulated')
)
SELECT schema_version, event_id, event_type, occurred_at, emitted_at, run_id,
       deployment_id, building_id, floor_id, mode, session_id, zone_id,
       position_id, dwell_ms, occupancy_after, confidence, event_sequence,
       metadata_json, ingested_at
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.node_heartbeats_clean')
USING DELTA AS
WITH ranked AS (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY heartbeat_id
    ORDER BY emitted_at DESC NULLS LAST, ingested_at DESC NULLS LAST
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.node_heartbeats_raw') r
  WHERE heartbeat_id IS NOT NULL
    AND emitted_at IS NOT NULL
    AND run_id IS NOT NULL
    AND deployment_id IS NOT NULL
    AND building_id IS NOT NULL
    AND floor_id IS NOT NULL
    AND anchor_id IS NOT NULL
    AND mode IN ('real', 'simulated')
)
SELECT schema_version, heartbeat_id, emitted_at, run_id, deployment_id,
       building_id, floor_id, anchor_id, node_kind, mode, status,
       agent_version, uptime_s, buffer_depth, observations_sent_total,
       last_observation_at, capture_ok, error_codes, ingested_at
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.sessions_clean')
USING DELTA AS
WITH ranked AS (
  SELECT r.*, ROW_NUMBER() OVER (
    PARTITION BY session_id
    ORDER BY started_at DESC NULLS LAST, ingested_at DESC NULLS LAST
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.sessions_raw') r
  WHERE session_id IS NOT NULL
    AND started_at IS NOT NULL
    AND run_id IS NOT NULL
    AND deployment_id IS NOT NULL
    AND building_id IS NOT NULL
    AND floor_id IS NOT NULL
    AND mode IN ('real', 'simulated')
)
SELECT schema_version, session_id, started_at, ended_at, run_id,
       deployment_id, building_id, floor_id, mode, ingested_at
FROM ranked
WHERE row_number = 1;
