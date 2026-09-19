CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_clean') USING DELTA AS
SELECT * FROM IDENTIFIER(:catalog || '.' || :schema || '.signal_observations_raw') WHERE FALSE;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.position_estimates') USING DELTA AS
SELECT CAST(NULL AS STRING) AS position_id, CAST(NULL AS TIMESTAMP) AS calculated_at,
       CAST(NULL AS STRING) AS run_id, CAST(NULL AS STRING) AS deployment_id,
       CAST(NULL AS STRING) AS building_id, CAST(NULL AS STRING) AS floor_id,
       CAST(NULL AS STRING) AS session_id, CAST(NULL AS DOUBLE) AS x_m,
       CAST(NULL AS DOUBLE) AS y_m, CAST(NULL AS STRING) AS zone_id,
       CAST(NULL AS DOUBLE) AS confidence, CAST(NULL AS STRING) AS mode
WHERE FALSE;
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.sessions') USING DELTA AS
SELECT CAST(NULL AS STRING) AS session_id, CAST(NULL AS TIMESTAMP) AS started_at,
       CAST(NULL AS TIMESTAMP) AS ended_at, CAST(NULL AS STRING) AS run_id,
       CAST(NULL AS STRING) AS deployment_id, CAST(NULL AS STRING) AS building_id,
       CAST(NULL AS STRING) AS floor_id, CAST(NULL AS STRING) AS mode
WHERE FALSE;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.spatial_events') USING DELTA AS
SELECT CAST(NULL AS STRING) AS event_id, CAST(NULL AS STRING) AS event_type,
       CAST(NULL AS TIMESTAMP) AS occurred_at, CAST(NULL AS STRING) AS run_id,
       CAST(NULL AS STRING) AS deployment_id, CAST(NULL AS STRING) AS building_id,
       CAST(NULL AS STRING) AS floor_id, CAST(NULL AS STRING) AS zone_id,
       CAST(NULL AS BIGINT) AS dwell_ms, CAST(NULL AS STRING) AS mode
WHERE FALSE;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.anchor_health') USING DELTA AS
SELECT CAST(NULL AS STRING) AS anchor_id, CAST(NULL AS TIMESTAMP) AS emitted_at,
       CAST(NULL AS STRING) AS status, CAST(NULL AS STRING) AS run_id,
       CAST(NULL AS STRING) AS deployment_id, CAST(NULL AS STRING) AS building_id,
       CAST(NULL AS STRING) AS floor_id, CAST(NULL AS STRING) AS mode
WHERE FALSE;
