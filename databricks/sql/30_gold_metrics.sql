CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.zone_occupancy') USING DELTA AS
SELECT zone_id, run_id, deployment_id, building_id, floor_id, mode,
       COUNT(*) AS position_count, MAX(calculated_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.position_estimates')
WHERE zone_id IS NOT NULL
GROUP BY zone_id, run_id, deployment_id, building_id, floor_id, mode;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.zone_transitions') USING DELTA AS
SELECT zone_id, run_id, deployment_id, building_id, floor_id, mode,
       COUNT(*) AS transition_count, MAX(occurred_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events')
WHERE event_type = 'zone_transition'
GROUP BY zone_id, run_id, deployment_id, building_id, floor_id, mode;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.dwell_metrics') USING DELTA AS
SELECT zone_id, run_id, deployment_id, building_id, floor_id, mode,
       AVG(dwell_ms) AS average_dwell_ms, percentile_approx(dwell_ms, 0.95) AS p95_dwell_ms
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events')
WHERE dwell_ms IS NOT NULL
GROUP BY zone_id, run_id, deployment_id, building_id, floor_id, mode;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.anomaly_metrics') USING DELTA AS
SELECT event_type AS anomaly_type, run_id, deployment_id, building_id, floor_id,
       COUNT(*) AS evidence_count, MAX(occurred_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.spatial_events')
WHERE event_type LIKE 'anomaly_%'
GROUP BY event_type, run_id, deployment_id, building_id, floor_id;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.intelligence_facts') USING DELTA AS
SELECT zone_id, run_id, deployment_id, building_id, floor_id,
       'position_count' AS fact_type, COUNT(*) AS fact_value, MAX(calculated_at) AS data_through
FROM IDENTIFIER(:catalog || '.' || :schema || '.position_estimates')
GROUP BY zone_id, run_id, deployment_id, building_id, floor_id;
