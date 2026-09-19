# Seuranta Atlas frontend architecture

## Boundary and module ownership

The UI has one normalized boundary. Backend payloads remain snake_case at the boundary; components and stores use camelCase domain types only. Camera presets use a short interpolated transition and yield to manual OrbitControls input.

```text
src/
  domain/
    types.ts          organization/site/building/floor, positions, events, nodes, state, provider
    adapters.ts       DTO -> normalized state; mode/status/wrapper tolerance
    coordinates.ts    backend map metres <-> Three world coordinates
    floorDefinition.ts dimensional Riverside Office demo geometry
    mockProvider.ts   deterministic route simulation
    liveProvider.ts   REST snapshot + WebSocket reconnect boundary
    store.ts          small Zustand UI state (selection, filters, layers)
  components/
    MapCanvas.tsx     R3F scene, camera presets, markers, and labels
  App.tsx             shell composition, explorer, detail panel, mode controls
  styles.css          tokens and responsive command-center layout
```

The `App` component chooses a provider by data mode and subscribes the same `ProviderSnapshot` shape for both providers. High-frequency marker interpolation happens in R3F `useFrame`; the Zustand snapshot changes on provider ticks, not on every render frame.

## Exact PositionEstimate V1 contract

The adapter accepts the positioning/data-platform wire shape with these fields:

```text
schema_version, position_id, calculated_at, window_start, window_end,
run_id, deployment_id, building_id, floor_id, session_id,
raw_x_m, raw_y_m, x_m, y_m, zone_id, confidence (0..1),
accuracy_radius_m, position_method, smoothing_method, anchors_used,
observation_count, mode, sequence_number, is_outside_map
```

The normalized UI names are `schemaVersion`, `positionId`, `calculatedAt`, `windowStart`, `windowEnd`, `runId`, `deploymentId`, `buildingId`, `floorId`, `sessionId`, `rawXM`, `rawYM`, `xM`, `yM`, `zoneId`, `confidence`, `accuracyRadiusM`, `positionMethod`, `smoothingMethod`, `anchorsUsed`, `observationCount`, `mode`, `sequenceNumber`, and `isOutsideMap`.

The UI also normalizes `SpatialEvent` and `NodeHeartbeat`. Event adapters accept `metadata` or positioning's `attributes`, and recognize `from_zone_id` / `to_zone_id`; node statuses are normalized to `online`, `degraded`, or `offline`.

## Data API and live behavior

The live provider targets:

- `GET /api/v1/state` with `run_id`, `deployment_id`, `building_id`, `floor_id`, and `mode` query parameters.
- `WS /api/v1/live` for an initial snapshot and subsequent `{ type, state_revision, data }` deltas.

The REST adapter accepts either a bare object or `{ data: object }`. The WebSocket adapter accepts snapshot/state messages, ignores heartbeat messages, and keeps the last valid state while reconnecting with bounded backoff. An empty initial state is marked partial and shown as an honest empty/unavailable workspace.

The current data-platform state shape includes `state_revision`, `generated_at`, `counts`, `sessions`, `positions`, `nodes`, `zones`, `zone_metrics`, `recent_events`, `anomalies`, and `is_partial`. The current backend branches differ in mode vocabulary: edge uses uppercase `LIVE`, `REPLAY`, and `SIMULATION`, while data models include lowercase `real` and `simulated`; the adapter maps `REAL`/`PRODUCTION` to `LIVE`, `REPLAY`/`HISTORICAL` to `REPLAY`, and other simulated variants to `SIMULATION`.

The current edge heartbeat does not carry anchor coordinates. `FloorDefinition` remains authoritative for marker placement until a versioned floor-definition endpoint is added. The frontend does not modify any backend contract.

## Floor and coordinates

The demo floor is 32 m × 22 m, with a 0.25 m slab and 0.65 m wall height. Rooms, colored zones, wall segments, labels, and all four anchor coordinates are defined in `src/domain/floorDefinition.ts`.

The floor-plan origin is its centre `(16 m, 11 m)`. One Three world unit is one metre. Backend `x_m` maps to world `x`; backend `y_m` maps to world `-z` so north reads upward in the elevated view. World `y` is vertical height. All conversion is in `src/domain/coordinates.ts`; components never perform ad hoc coordinate math.

## Switching providers

Simulation is default and requires no credentials. The mode controls select `MockPositionProvider` or `LivePositionProvider`; both feed the same normalized state, map, explorer, and detail components. Use `VITE_SEURANTA_API_URL` for a separately hosted API. A same-origin deployment may leave it unset. A future authenticated production adapter should be added outside the domain components and must preserve the anonymous session boundary.

## Future Pi → positioning → data-platform connection

The intended path is:

```text
Pi / edge heartbeat + observation batches
  -> data API /api/v1/observations and /api/v1/nodes/heartbeat
  -> positioning service (WKNN + smoothing + zone events)
  -> data-platform state reconstruction and analytics
  -> GET /api/v1/state + WS /api/v1/live
  -> Seuranta Atlas normalized adapter
```

The frontend assumes only the public V1 fields above. It does not assume raw identifiers, personal profiles, triangulation terminology, or unsupported heatmaps/AI. Reconnect handling, partial snapshots, state revisions, and mode normalization are intentionally client-side concerns until the backend contracts converge.
