# Frontend architecture

The frontend has one main rule: backend and simulation data must cross a provider boundary before reaching React. Everything after that boundary uses the normalized types in `src/domain/types.ts`.

## Main modules

```text
src/
  domain/
    types.ts            normalized positions, nodes, events, state, and providers
    adapters.ts         snake_case backend payloads to camelCase frontend objects
    coordinates.ts      floor metres to Three.js world coordinates and back
    floorDefinition.ts  building/floor identity, footprint, zones, and anchors
    roomModel.ts        GLB information, calibration, validation, and local storage
    simulation.ts       Virginia Tech first-floor routes and zone names
    mockProvider.ts     deterministic simulation snapshots and controls
    liveProvider.ts     scoped REST snapshot and WebSocket update client
    camera.ts           one-shot Focus behavior
    store.ts            selected entity, search, layers, and mode
  components/
    MapCanvas.tsx       R3F model, markers, labels, lighting, and camera controls
  brand-system.css      white/black product tokens, logo layout, responsive states, and fallback preview
  App.tsx               dashboard panels, setup, details, and provider switching
```

`App` creates either `MockPositionProvider` or `LivePositionProvider`. Both emit `ProviderSnapshot`, so the map, lists, metrics, and detail panel do not know where the data came from. Marker interpolation runs inside the Three.js frame loop instead of causing a React render for every visual step.

## Virginia Tech floor model

The runtime model is `public/models/vt-academic-classroom.glb`. The source also includes a Meshopt-compressed copy and a metadata JSON file. The app uses the uncompressed file because it is only about 0.5 MB and does not need a decoder.

The source contains three floors and a roof. `MapCanvas` clones the loaded scene and removes `Floor_02`, `Floor_03`, and `Roof` from the operational view. The original files stay unchanged.

If a browser cannot create a WebGL context, the same component renders a lightweight static floor-plan preview with the same anchors and entity selection behavior. That keeps the demo usable on restricted machines without changing the provider or UI contract.

Metadata says:

```text
units: metres
up axis: +Y
ground plane: XZ
estimated first-floor bounds: 76.9195 m × 44.6473 m
scale uncertainty: about ±15%
measured survey: false
```

Floor setup can replace width, depth, yaw, origin, and planned anchor coordinates. These settings are validated and stored in local storage under a Virginia Tech-specific key.

## Coordinate system

The live API sends floor-local coordinates:

```text
x_m: horizontal floor axis
y_m: floor depth axis
```

One Three.js unit equals one metre. `coordinates.ts` centers the configured floor, maps backend X to world X, maps backend Y to world -Z, and uses world Y for height. Model scale is applied only to the GLB. Position and anchor coordinates are not scaled a second time.

Default floor coordinates run from `(0, 0)` to approximately `(76.92, 44.65)`. `originXM` and `originYM` let a real deployment use a different backend origin, while `yawDeg` aligns the model with the deployment axes. All markers, anchors, and overlays use the same transform.

## Position contract

The frontend expects positioning records with these wire fields:

```text
schema_version, position_id, calculated_at, window_start, window_end,
run_id, deployment_id, building_id, floor_id, session_id,
raw_x_m, raw_y_m, x_m, y_m, zone_id, confidence,
accuracy_radius_m, position_method, smoothing_method, anchors_used,
observation_count, mode, sequence_number, is_outside_map
```

`confidence` is normalized to 0..1. `accuracy_radius_m` is a radius in metres, not a plus/minus guarantee. The adapter clamps invalid ranges before UI components receive them.

Node heartbeats need the same scope plus:

```text
anchor_id, node_kind, mode, status, emitted_at, uptime_s,
buffer_depth, observations_sent_total, last_observation_at,
capture_ok, error_codes
```

Heartbeat payloads report health. Anchor coordinates come from Floor setup because the current heartbeat contract does not include installed coordinates.

## Live provider

The provider uses:

```text
GET /api/v1/state
WS  /api/v1/live
```

Both are scoped by `run_id`, `deployment_id`, `building_id`, `floor_id`, and mode. UI mode `LIVE` maps to API mode `real`; `SIMULATION` maps to `simulated`.

WebSocket messages use:

```text
{ type, state_revision, data }
```

- `snapshot` and `state` replace the current scoped snapshot.
- `position`, `node`, and `event` update one record.
- data-less `heartbeat` and observation messages can advance the revision.
- `snapshot_required` closes the socket and fetches a full REST snapshot.

Full snapshots and typed updates must match all four scope IDs. Lower revisions are ignored. Starting a new scope emits an empty connecting state immediately, aborts the older fetch, and guards socket callbacks with a generation number. A failed source remains visibly failed; it never switches to mock data.

## Simulation provider

The simulation uses six anonymous sessions. Routes are loops traced inside first-floor learning and circulation regions from the supplied metadata. Each snapshot includes positions, confidence, uncertainty radius, timestamps, zone occupancy, events, and node health. Pause stops timestamps and movement, Restart resets route progress, and Weak signal changes confidence and anchor health.

The simulation is intentionally believable but not presented as measured positioning performance.

## Raspberry Pi integration

The frontend integration point is the data API, not direct Pi networking:

```text
Pi observations and heartbeats
  -> data-platform ingestion
  -> positioning, smoothing, and zone events
  -> state reconstruction
  -> REST + WebSocket live provider
  -> normalized frontend state
```

The frontend does not implement packet capture, device identity, calibration math for the positioning engine, or Raspberry Pi deployment.

## Current limits

- The Virginia Tech geometry and scale are reference-derived estimates.
- Upper-floor operational views are not implemented yet, although the model contains them.
- Planned anchors need a site survey before live testing.
- Replay and heatmaps are not implemented.
- The Three.js bundle triggers Vite's chunk-size advisory, but the build completes.
