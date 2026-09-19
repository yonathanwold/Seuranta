# Frontend architecture

This document is the short version of how the Seuranta frontend fits together. The main idea is simple: backend DTOs stop at one adapter boundary, and everything after that uses the same normalized UI types. That lets the map work with the mock provider today and with the live API later.

## Folders and responsibilities

```text
src/
  domain/
    types.ts            organization/site/building/floor, positions, events, nodes, state, providers
    adapters.ts         snake_case DTO -> normalized camelCase state
    coordinates.ts      backend metre <-> Three.js world conversion
    floorDefinition.ts  Riverside Office rooms, walls, zones, and anchors
    mockProvider.ts     deterministic five-session simulation
    liveProvider.ts     scoped REST/WS adapter and typed delta reducer
    camera.ts           one-shot camera behavior for selection changes
    store.ts            Zustand selection, search, mode, and layer state
  components/
    MapCanvas.tsx       R3F floor, markers, labels, controls, and fallback
  App.tsx               shell, explorer, detail panel, and provider switching
  styles.css            design tokens and desktop layout
docs/
  frontend-architecture.md
  demo-guide.md
```

`App` picks a provider from the selected mode and subscribes to a `ProviderSnapshot`. The map and lists do not care which provider produced it. The mock emits a new snapshot every 700 ms. Marker movement happens in R3F `useFrame`, so the render loop does not need a whole-app state update for every interpolation step.

The adapter is the normalized UI boundary. Wire names stay snake_case; components and the store use names such as `sessionId`, `accuracyRadiusM`, and `recentEvents`. If a backend response changes shape, fix the adapter or provider rather than teaching each component another DTO format.

## PositionEstimate V1

The positioning/data-platform payload uses this exact field set:

```text
schema_version, position_id, calculated_at, window_start, window_end,
run_id, deployment_id, building_id, floor_id, session_id,
raw_x_m, raw_y_m, x_m, y_m, zone_id, confidence (0..1),
accuracy_radius_m, position_method, smoothing_method, anchors_used,
observation_count, mode, sequence_number, is_outside_map
```

The normalized `PositionEstimate` uses:

```text
schemaVersion, positionId, calculatedAt, windowStart, windowEnd,
runId, deploymentId, buildingId, floorId, sessionId,
rawXM, rawYM, xM, yM, zoneId, confidence, accuracyRadiusM,
positionMethod, smoothingMethod, anchorsUsed, observationCount,
mode, sequenceNumber, isOutsideMap
```

The adapter clamps confidence to 0..1 and keeps accuracy non-negative. Session IDs remain anonymous and run-scoped.

## Other data types

The node heartbeat carries the scope and health information needed by the explorer:

```text
building_id, floor_id, anchor_id, node_kind,
mode, status (online | degraded | offline), emitted_at,
uptime_s, buffer_depth, observations_sent_total,
last_observation_at, capture_ok, error_codes
```

The normalized node also keeps the schema version, heartbeat ID, deployment/run IDs, and optional agent version. `FloorDefinition` supplies the anchor coordinates because current heartbeat and observation payloads do not.

Spatial events include an event ID/type, timestamps, scope, mode, optional session/position/zone fields, event sequence, and metadata. The adapter accepts both `metadata` and positioning's `attributes`, and understands `from_zone_id` and `to_zone_id`. Current event types include zone/room enter and exit, dwell lifecycle events, occupancy changes, session start/end, position updates, and anomalies.

The data-platform state snapshot can include `state_revision`, `generated_at`, `counts`, `sessions`, `positions`, `nodes`, `zones`, `zone_metrics`, `recent_events`, `anomalies`, and `is_partial`. The frontend currently renders positions, nodes, zone metrics, recent events, and counts.

## REST and WebSocket boundary

The live provider uses these routes:

```text
GET /api/v1/state
WS  /api/v1/live
```

Both requests are scoped with `run_id`, `deployment_id`, `building_id`, `floor_id`, and a data-platform mode query value. Normalized `LIVE` maps to `real`; normalized `SIMULATION` maps to `simulated`. A reconnect includes `since_revision` when the provider has a revision. A `snapshot_required` message forces a full scoped REST refresh.

The REST adapter accepts either a bare snapshot or a `{ data: ... }` envelope. The WebSocket protocol is treated as typed messages rather than as partial copies of `BuildingState`:

```text
{ type, state_revision, data }
```

`snapshot` and `state` replace the usable snapshot. `position` updates one session by `session_id`, `node` updates one anchor by `anchor_id`, and `event` adds or replaces one recent event by `event_id`. Observation and heartbeat messages can advance the revision but do not replace normalized state. Unknown, malformed, missing-scope, cross-scope, and unknown-mode deltas are ignored, so one bad message cannot wipe the last good view. Reconnects use bounded backoff and retain that last view.

The existing branches do not use exactly one vocabulary yet:

- Edge commonly uses uppercase `LIVE`, `REPLAY`, and `SIMULATION`, plus uppercase health statuses.
- Data-platform payloads use lowercase `real` and `simulated` in places.
- Some edge sessions routes return a bare array while data responses use `{ data: ... }`.
- Data-platform observation forwarding can include a full `ObservationBatch`, while positioning's accepted shape is narrower (`schema_version` plus `observations`).
- Positioning events may put zone changes in event fields while data-platform events may put them in `metadata`.

`adapters.ts` maps `REAL`/`PRODUCTION` to `LIVE`, `REPLAY`/`HISTORICAL` to `REPLAY`, and simulated variants to `SIMULATION`. The UI only exposes Simulation and Live because no replay provider exists. These compatibility rules stay in the frontend adapter; this branch does not modify any backend.

## Floor definition and coordinates

The demo floor is configured in `src/domain/floorDefinition.ts`:

- 32 m wide × 22 m deep
- 0.25 m slab
- 0.65 m wall height
- seven labeled rooms, zone polygons, wall segments, and four anchors

The floor origin in backend coordinates is its center, `(16 m, 11 m)`. One world unit equals one metre. Backend `x_m` maps to Three.js world `x`; backend `y_m` maps to world `-z`, which makes north read upward in the elevated view. Three.js world `y` is vertical height. The inverse conversion is in the same module for UI-to-map work. Components should call `coordinates.ts` and should not repeat these formulas.

## Providers and mode switching

`PositionProvider` exposes `start`, `stop`, and `refresh`, and always emits the same `ProviderSnapshot` shape.

- `MockPositionProvider` is the default. It uses five anonymous session IDs, smooth waypoint routes, timestamps, confidence, accuracy radius, zone transitions, and four anchors with mixed health.
- `LivePositionProvider` uses the scoped REST/WebSocket boundary above. It reports connecting, live, reconnecting, and error states without hiding an empty or unavailable source.

The app selects the provider from the mode in the Zustand store. The same map, search, detail panel, and layer controls are used for both. `VITE_SEURANTA_API_URL` can point to a separately hosted API; leaving it unset uses same-origin routes.

## Camera and fallback behavior

Overview, Top, and Focus are explicit camera requests. Manual OrbitControls input cancels an active transition. Selecting a different session while Focus is active creates one new request for that session; normal 700 ms telemetry ticks never move the camera. If WebGL cannot initialize, the Canvas fallback explains what happened while the entity and anchor lists remain available in the DOM.

## Pi to UI path

The intended connection is:

```text
Pi observations and node heartbeats
  -> data API (/api/v1/observations, /api/v1/nodes/heartbeat)
  -> positioning (WKNN, smoothing, and zone events)
  -> data-platform state reconstruction and analytics
  -> GET /api/v1/state + WS /api/v1/live
  -> normalized Seuranta UI state
```

The frontend assumes the public V1 fields above. It does not assume raw identifiers, names, personal profiles, or unsupported analytics surfaces. Until the backend contracts converge, the adapter owns wrapper, casing, status, event-attribute, scope, partial-snapshot, and revision tolerance.

## Current limits

There is no backend service in this repository, so Live mode cannot show real data by itself. Building and floor are static demo context, and Replay is not implemented. The current browser QA environment provided a 1440 px-wide viewport but no exact 1366 × 768 or 1920 × 1080 override. The production bundle also has the normal Three.js chunk-size advisory. These are follow-up items, not hidden claims in the UI.
