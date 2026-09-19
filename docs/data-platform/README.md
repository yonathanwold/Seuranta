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
- Accepted observations, positions, events, heartbeats, and sessions are
  written to the outbox in the same SQLite transaction as the local record.
- Batch writes and outbox creation are one SQLite transaction; ending a
  session refreshes its pending outbox payload.
- Positioning forwarding uses a bounded queue and capped exponential retry.
- A positioning outage does not reject or delete accepted observations.
- Databricks is an optional batch sink; its disabled/unavailable state is
  reported separately from `/api/v1/health` local status.
- WebSocket clients receive a snapshot first and are resynchronized with a
  snapshot when their delta queue becomes full.

## Databricks

`databricks/` is a deployable Databricks Asset Bundle. It creates five
append-only Bronze tables, rebuilds validated Silver tables with contract-ID
deduplication, and refreshes current-position, occupancy, anchor-health,
transition, dwell, anomaly, and intelligence Gold tables. Every derived table
keeps `run_id`, `deployment_id`, `building_id`, `floor_id`, and `mode` so real
and simulated scopes stay separate.

From the repository root, with Databricks CLI 0.218 or newer:

```bash
databricks auth login --profile seuranta-dev
cd databricks
databricks bundle validate -t dev --var="warehouse_id=<sql-warehouse-id>"
databricks bundle deploy -t dev \
  --var="catalog=main" \
  --var="schema=seuranta" \
  --var="warehouse_id=<sql-warehouse-id>"
databricks bundle run -t dev seuranta_daily_metrics
```

The development job is on demand. A workspace owner can attach a schedule
after validating Bronze ingestion and permissions. The repository has no
workspace profile, token, service principal, warehouse ID, or live Databricks
connection, so remote deployment and SQL execution are not claimed here.
The local API still uses SQLite WAL as the source for live reads and reports
the optional Databricks batch sink separately at `/api/v1/health`; it never
silently substitutes simulated data for an unavailable sink.
