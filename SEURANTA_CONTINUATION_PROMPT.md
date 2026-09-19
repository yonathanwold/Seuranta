# SEURANTA CONTINUATION PROMPT

Continue the Seuranta frontend in `https://github.com/yonathanwold/Seuranta.git`.

## Start here

1. Run `git fetch origin`.
2. Switch to `team/app` and inspect `git status --short --branch` plus `git log --oneline --decorate -8`.
3. Read this file, `README.md`, and `docs/frontend-architecture.md`.
4. Install and run the app with `npm.cmd install` and `npm.cmd run dev -- --host 127.0.0.1 --port 4173`.
5. Run `npm.cmd test`, `npm.cmd run lint`, and `npm.cmd run build` before changing behavior.
6. Continue from the current implementation. Do not restart or redesign working systems without a concrete reason.

## Repository and Git state

- Repository: `https://github.com/yonathanwold/Seuranta.git`
- Current branch: `team/app`
- Latest implementation commit when this handoff was written: `fe55a3d` (`feat(ui): adopt Seuranta white and black brand system`)
- Run `git rev-parse HEAD` after checkout for the exact newest handoff commit.

`team/app` is an orphan frontend history. It has no merge base with the three backend team branches. Do not merge those histories into this branch, force-push, or rewrite another team's branch.

Branches inspected:

- `origin/team/edge` at `7e9ce2a`
- `origin/team/data-platform` at `9dff3ca`
- `origin/team/positioning` at `5667d03`

The newer data-platform commit only imported edge documentation/files; it did not change the frontend API contract.

## Current application

The app is a React 18, TypeScript, Vite, Three.js, React Three Fiber, Drei, and Zustand frontend. It shows the first floor of Virginia Tech's Academic Classroom Building as the main operational map.

Important files:

```text
public/models/
  vt-academic-classroom.glb
  vt-academic-classroom.meshopt.glb
  vt-academic-classroom.metadata.json
src/
  App.tsx
  styles.css
  components/MapCanvas.tsx
  brand-system.css
  domain/
    adapters.ts
    camera.ts
    coordinates.ts
    floorDefinition.ts
    liveProvider.ts
    mockProvider.ts
    roomModel.ts
    simulation.ts
    store.ts
    types.ts
  tests/
docs/
  demo-guide.md
  frontend-architecture.md
README.md
CONTRIBUTING.md
```

The app uses the uncompressed GLB because it is about 0.5 MB and opens without a Meshopt decoder. The compressed copy is kept for later optimization. `MapCanvas` clones the scene and removes `Floor_02`, `Floor_03`, and `Roof`, so the operational view is a first-floor cutaway without changing the source file.

## Completed features

- Virginia Tech first-floor 3D model with orbit, pan, zoom, Overview, Top, Focus, and Reset.
- Six anonymous simulated devices on repeatable learning-space and circulation routes.
- Four planned anchors with simulated online/degraded state.
- Smooth marker interpolation, confidence, uncertainty radius, zones, timestamps, and activity events.
- Search and linked list/map/detail selection.
- Layer switches for devices, anchors, labels, uncertainty, and floor overlay.
- Pause, play, restart, speed, and weak-signal simulation controls.
- Floor setup for width, depth, origin, yaw, anchor IDs, and anchor coordinates.
- Live setup for API URL and exact run/deployment/building/floor scope.
- Shared normalized provider boundary for Simulation and Live.
- Strict live snapshot/delta scope validation, monotonic revisions, abort/generation guards, data-less heartbeat handling, and honest unavailable states.
- Responsive desktop layout checked at 1366×768 and 1920×1080.
- Supplied Seuranta logo cropped into full and compact assets, applied to the navigation, favicon, README, and responsive rail.
- White/black product theme with green/amber reserved for health and simulation state.
- Static floor-plan fallback with selectable devices and anchors when a browser cannot create WebGL.
- Natural project documentation, demo guide, architecture notes, and privacy guidance.

## Model and coordinate assumptions

The supplied metadata says the model is reference-derived, not a survey or BIM:

```text
units: metres
up axis: +Y
ground plane: XZ
estimated footprint: 76.9195 m × 44.6473 m
scale uncertainty: about ±15%
measured: false
```

One Three.js unit equals one metre. Backend `x_m` maps to world X. Backend `y_m` maps to world -Z. World Y is vertical. The floor-local backend range defaults to `(0, 0)` through approximately `(76.92, 44.65)`. The model scale is applied to the GLB only; telemetry must not be scaled twice. Origin and yaw are centralized in `src/domain/coordinates.ts`.

Default live scope:

```text
run_id:        vt-acb-floor1
deployment_id: vt-acb-pilot
building_id:   vt-academic-classroom-building
floor_id:      floor-1
mode:          real
```

These values are placeholders for the pilot and can be changed in Floor setup.

## Position and live contracts

Position wire fields:

```text
schema_version, position_id, calculated_at, window_start, window_end,
run_id, deployment_id, building_id, floor_id, session_id,
raw_x_m, raw_y_m, x_m, y_m, zone_id, confidence,
accuracy_radius_m, position_method, smoothing_method, anchors_used,
observation_count, mode, sequence_number, is_outside_map
```

Live boundary:

```text
GET /api/v1/state
WS  /api/v1/live
{ type, state_revision, data }
```

Full snapshots and typed position/node/event updates must match run, deployment, building, and floor. Lower revisions are ignored. `snapshot_required` forces a full REST reload. A data-less heartbeat may advance the revision. Changing scope clears old data immediately. Do not remove these protections to make an incomplete backend fixture pass.

The future integration path remains:

```text
Raspberry Pi observations and heartbeats
  -> data-platform ingestion
  -> positioning and smoothing
  -> state reconstruction
  -> REST snapshot + WebSocket stream
  -> Seuranta normalized state
```

Do not add direct Pi networking to the frontend.

## Checks completed

```text
npm.cmd run lint             passed
npm.cmd test -- --run        7 files, 21 tests passed
npm.cmd run build            passed
npm.cmd audit --omit=dev     0 vulnerabilities
```

The build prints Vite's chunk-size advisory because Three.js is in the main bundle. That is the only build warning. The full GLB was also verified in a software-WebGL Chromium capture; restricted browsers use the static floor-plan fallback instead.

Manual browser QA covered:

- WebGL model rendering at 1920×1080 with software WebGL, plus the static preview at 1366×768 and 1920×1080 in the restricted browser surface
- Overview, Top, and Focus
- search and linked selection
- pause/play and simulation movement
- Floor setup values and live scope fields
- Live unavailable state with zero fake devices
- no horizontal overflow at the target desktop sizes

## Incomplete work and known limits

- The model scale, geometry, upper floors, and planned anchors are estimates. The team still needs an on-site measurement and anchor survey.
- There is no backend bundled on `team/app`, so Live mode needs separately running team services.
- Upper-floor switching, replay, heatmaps, and historical analytics are not implemented.
- Simulation routes are metadata-informed demo loops, not validation of positioning accuracy.
- The optimized Meshopt asset is stored but not loaded yet.
- Three.js code splitting is not implemented.

No active application bug was known when this handoff was written.

## Immediate next priorities

1. Run a small first-floor pilot: measure known points, choose the coordinate origin, and enter installed anchor coordinates.
2. Start the data-platform API and validate a real scoped REST snapshot and WebSocket stream.
3. Compare known physical device positions with the UI and record error before tuning confidence or smoothing.
4. Add floor switching only when there is real positioning data for another floor.
5. Optimize the bundle or enable Meshopt only if measured load time makes it necessary.

Recommended assignments:

- Lead: protect architecture and coordinate contracts, review integration decisions.
- Frontend implementation: pilot setup, map interactions, and measured performance work.
- Data integration: run the API and validate scope/revision behavior end to end.
- Reviewer: independently check coordinate calibration and stale/cross-scope handling before a live demo.

## Active files and Git workflow

No files were intentionally left mid-edit at handoff. Still run `git status` because all agents share one checkout.

Work on `team/app`. Use small conventional commits, run tests/lint/build before each push, and push with:

```powershell
git push origin team/app
```

Never force-push. Do not reset or delete `team/edge`, `team/data-platform`, or `team/positioning`. Fetch before bringing in teammate work, inspect the diff, resolve conflicts deliberately, and rerun all checks.
