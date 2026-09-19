# Seuranta data platform

The API writes validated anonymous telemetry to local SQLite in WAL mode before
attempting any downstream call. This makes live ingestion and state recovery
independent of positioning and Databricks availability.

## Local run

Install the API dependencies from `services/api/requirements.txt`, then run:

```bash
uvicorn services.api.main:app --reload
```

Useful configuration includes `SEURANTA_DATABASE_PATH`, `SEURANTA_MAX_BATCH_SIZE`,
`POSITIONING_URL`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`,
`DATABRICKS_CATALOG`, `DATABRICKS_SCHEMA`, and `DATABRICKS_WAREHOUSE_ID`.

## Reliability boundaries

- Duplicate observations and events are ignored by their contract IDs.
- Batch writes and outbox creation are one SQLite transaction.
- Positioning forwarding uses a bounded queue and capped exponential retry.
- A positioning outage does not reject or delete accepted observations.
- Databricks is an optional batch sink; its disabled/unavailable state is
  reported separately from `/api/v1/health` local status.
- WebSocket clients receive a snapshot first and are resynchronized with a
  snapshot when their delta queue becomes full.

## Databricks

`databricks/` is a minimal bundle with Bronze, Silver, and Gold Delta table
definitions. Deployments must provide the workspace host and warehouse ID.
The local API does not fabricate warehouse results when credentials are absent.
