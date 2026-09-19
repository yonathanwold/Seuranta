# Seuranta Databricks bundle

This directory is a Databricks Asset Bundle for the Seuranta data platform. It
creates an append-only Bronze contract, rebuilds validated Silver tables, and
refreshes Gold metrics for the current scoped snapshot. The bundle is separate
from the React demo: the frontend continues to use the REST/WebSocket provider
and does not query Delta tables directly.

## Prerequisites

- A Databricks workspace with a SQL warehouse and permission to create a
  catalog schema and Delta tables.
- Databricks CLI 0.218 or newer, with a configured profile. The repository does
  not include credentials, profiles, warehouse IDs, or a service principal.
- An approved ingestion job or connector that appends the API contracts to the
  five `*_raw` Bronze tables. This bundle does not invent telemetry and does
  not upload personal identifiers.

From the repository root, authenticate, enter the bundle directory, and
validate the development target:

```bash
databricks auth login --profile seuranta-dev
cd databricks
databricks bundle validate -t dev --var="warehouse_id=<sql-warehouse-id>"
```

Deploy with values for the workspace that owns the data:

```bash
databricks bundle deploy -t dev \
  --var="catalog=main" \
  --var="schema=seuranta" \
  --var="warehouse_id=<sql-warehouse-id>"
```

The job is intentionally run on demand by the development target. Run it after
Bronze ingestion or attach a workspace-owned production schedule:

```bash
databricks bundle run -t dev seuranta_daily_metrics
```

The SQL tasks are ordered as schema creation, Silver cleanup/deduplication,
then Gold refresh. Each refresh is idempotent. The scope columns
`run_id`, `deployment_id`, `building_id`, `floor_id`, and `mode` remain on every
derived table so simulated and real runs cannot be mixed accidentally.

## Tables

Bronze tables are append-only inputs:

- `signal_observations_raw`
- `position_estimates_raw`
- `spatial_events_raw`
- `node_heartbeats_raw`
- `sessions_raw`

Silver tables remove malformed rows and keep the newest record for each
contract ID:

- `signal_observations_clean`
- `position_estimates_clean`
- `spatial_events_clean`
- `node_heartbeats_clean`
- `sessions_clean`

Gold tables are current, query-friendly metrics:

- `current_positions` (one latest position per scoped session)
- `zone_occupancy`
- `anchor_health`
- `zone_transitions`
- `dwell_metrics`
- `anomaly_metrics`
- `intelligence_facts`

The API still writes SQLite WAL first and reports Databricks as a separate
optional batch sink. If `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, or
`DATABRICKS_WAREHOUSE_ID` is missing, `/api/v1/health` reports a disabled sink;
it never silently changes to a simulated or fabricated Databricks response.

## Contract and privacy boundary

The normalized API models live in `services/data/models.py`. They contain
anonymous session IDs and scoped telemetry only. Names, MAC addresses, raw
packet contents, and personal profiles are outside the contract and must not be
added to Bronze tables or exports.

No remote Databricks workspace is bundled with this checkout, and no deploy or
SQL execution can be claimed until a workspace profile and warehouse are
provided. The bundle and SQL can still be reviewed locally with the static
checks documented in the repository handoff.
