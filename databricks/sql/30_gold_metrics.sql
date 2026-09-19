-- Seuranta Gold metrics.
-- Every output is replaced from the current Silver snapshot so rerunning the
-- job after a replay does not preserve stale aggregates.

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.current_positions')
USING DELTA AS
WITH ranked AS (
  SELECT p.*, ROW_NUMBER() OVER (
    PARTITION BY run_id, deployment_id, building_id, floor_id, mode, session_id
    ORDER BY calculated_at DESC, sequence_number DESC, position_id DESC
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.position_estimates_clean') p
)
SELECT schema_version, position_id, calculated_at, window_start, window_end,
       run_id, deployment_id, building_id, floor_id, session_id, raw_x_m,
       raw_y_m, x_m, y_m, zone_id, confidence, accuracy_radius_m,
       position_method, smoothing_method, anchors_used, observation_count,
       mode, sequence_number, is_outside_map
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.zone_occupancy')
USING DELTA AS
SELECT run_id, deployment_id, building_id, floor_id, mode, zone_id,
       COUNT(DISTINCT session_id) AS occupancy,
       COUNT(*) AS position_count,
       MAX(calculated_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.current_positions')
WHERE zone_id IS NOT NULL
GROUP BY run_id, deployment_id, building_id, floor_id, mode, zone_id;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.anchor_health')
USING DELTA AS
WITH ranked AS (
  SELECT h.*, ROW_NUMBER() OVER (
    PARTITION BY run_id, deployment_id, building_id, floor_id, mode, anchor_id
    ORDER BY emitted_at DESC, heartbeat_id DESC
  ) AS row_number
  FROM IDENTIFIER(:catalog || '.' || :schema || '.node_heartbeats_clean') h
)
SELECT run_id, deployment_id, building_id, floor_id, mode, anchor_id,
       node_kind, status, emitted_at, agent_version, uptime_s, buffer_depth,
       observations_sent_total, last_observation_at, capture_ok, error_codes
FROM ranked
WHERE row_number = 1;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.zone_transitions')
USING DELTA AS
SELECT run_id, deployment_id, building_id, floor_id, mode, zone_id,
       COUNT(*) AS transition_count,
       COUNT(DISTINCT session_id) AS sessions,
       MAX(occurred_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_clean')
WHERE LOWER(event_type) IN ('zone_transition', 'entry', 'exit')
GROUP BY run_id, deployment_id, building_id, floor_id, mode, zone_id;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.dwell_metrics')
USING DELTA AS
SELECT run_id, deployment_id, building_id, floor_id, mode, zone_id,
       COUNT(*) AS dwell_events,
       AVG(dwell_ms) AS average_dwell_ms,
       percentile_approx(dwell_ms, 0.95) AS p95_dwell_ms,
       MAX(occurred_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_clean')
WHERE dwell_ms IS NOT NULL
  AND dwell_ms >= 0
GROUP BY run_id, deployment_id, building_id, floor_id, mode, zone_id;

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.anomaly_metrics')
USING DELTA AS
SELECT run_id, deployment_id, building_id, floor_id, mode,
       LOWER(event_type) AS anomaly_type,
       COUNT(*) AS evidence_count,
       MAX(occurred_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events_clean')
WHERE LOWER(event_type) LIKE 'anomaly_%'
GROUP BY run_id, deployment_id, building_id, floor_id, mode, LOWER(event_type);

CREATE OR REPLACE TABLE IDENTIFIER(:catalog || '.' || :schema || '.intelligence_facts')
USING DELTA AS
SELECT run_id, deployment_id, building_id, floor_id, mode,
       'zone_occupancy' AS fact_type, zone_id AS subject_id,
       CAST(occupancy AS DOUBLE) AS fact_value, data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.zone_occupancy')
UNION ALL
SELECT run_id, deployment_id, building_id, floor_id, mode,
       'zone_transitions' AS fact_type, zone_id AS subject_id,
       CAST(transition_count AS DOUBLE) AS fact_value, data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.zone_transitions')
UNION ALL
SELECT run_id, deployment_id, building_id, floor_id, mode,
       'average_dwell_ms' AS fact_type, zone_id AS subject_id,
       CAST(average_dwell_ms AS DOUBLE) AS fact_value, data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.dwell_metrics');
