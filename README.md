# Seuranta

Seuranta is a small frontend for looking at anonymous indoor-positioning data on a floor map. We built it to make the path from Raspberry Pi observations to a useful operator view easier to understand. The app has a real Three.js floor model, a believable local simulation, and a separate boundary for the live API.

The default demo is safe to run without a backend. It shows five anonymous sessions moving around Riverside Office Floor 2, four infrastructure anchors, confidence/accuracy information, and recent zone events. It never displays names, MAC addresses, raw packet payloads, or personal profiles.

## Try the demo in a few minutes

You need Node.js and npm. From the repository root, run:

```powershell
npm.cmd install
npm.cmd run dev
```

Open the local URL printed by Vite. The app starts in Simulation mode, so there are no credentials or services to configure. For the same command used during local QA, run:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

The demo starts with an elevated view of a 32 m × 22 m floor. Use the left entity list to select a device or anchor. Selecting a device updates the right detail panel and the marker on the map. Search filters the anonymous sessions. The Overview, Top, and Focus controls change the camera; after using Focus, selecting another device moves the focus once to that device. Drag the map to orbit, pan, or zoom. The Map layers controls turn entities, anchors, labels, confidence discs, and zones on or off.

The Simulation/Live switch is in the left navigation and top bar. Simulation is the reliable presentation path. Live is useful when a Seuranta API is available and otherwise shows an honest unavailable/empty state.

## What is in the app

- A configuration-driven Riverside Office floor with rooms, wall segments, zone colors, labels, and four anchor locations.
- An orthographic Three.js scene with orbit controls, moving session markers, hover/selected labels, anchor health, and selected uncertainty discs.
- Five anonymous mock sessions that follow smooth corridor and room routes. The mock provider emits confidence, accuracy radius, timestamps, zone transitions, and anchor health.
- Searchable entity and anchor lists that stay in sync with the map and detail panel.
- A provider interface shared by Simulation and Live, so the UI does not know whether data came from the mock or API path.
- A WebGL fallback message. If Canvas cannot start, the DOM lists still provide the last known entity and anchor information.

Replay is not in the mode menu because a replay provider is not implemented yet. Building and floor are the current static demo context.

## Connecting the live API

Set the API base URL before starting Vite:

```powershell
$env:VITE_SEURANTA_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

The live provider calls `GET /api/v1/state` and opens `WS /api/v1/live`. Both requests carry `run_id`, `deployment_id`, `building_id`, `floor_id`, and a data-platform mode value (`real` for Live or `simulated` for Simulation). Reconnects include `since_revision` when possible. WebSocket messages are reduced by type instead of being treated as whole state objects:

```text
{ type, state_revision, data }
```

Position, node, and event messages must contain all four matching scope fields. Missing, cross-scope, malformed, or unknown-mode messages are ignored. `snapshot_required` triggers a fresh REST snapshot. The provider keeps the last good state while it reconnects.

The frontend is not a backend replacement. The intended data path is:

```text
Raspberry Pi heartbeat and observation batches
  -> data API
  -> positioning (WKNN, smoothing, zone events)
  -> data-platform state and analytics
  -> GET /api/v1/state + WS /api/v1/live
  -> Seuranta
```

See [the architecture notes](docs/frontend-architecture.md) for the full field contract and the differences between the existing edge, positioning, and data-platform branches.

## Project layout

```text
src/
  domain/
    types.ts            normalized UI contracts
    adapters.ts         snake_case DTO -> normalized camelCase state
    coordinates.ts      backend metre <-> Three.js transform
    floorDefinition.ts  demo rooms, walls, zones, and anchors
    mockProvider.ts     five-session local simulation
    liveProvider.ts     scoped REST/WS adapter and typed delta reducer
    camera.ts           one-shot camera behavior for selection changes
    store.ts            small Zustand UI store
  components/
    MapCanvas.tsx       R3F floor, markers, controls, and fallback
  App.tsx               shell, explorer, detail panel, and mode switching
  styles.css            visual tokens and desktop layout
docs/
  frontend-architecture.md
  demo-guide.md
```

The top-level [continuation handoff](SEURANTA_CONTINUATION_PROMPT.md) records the current branch, checks, limitations, and safe workflow.

## Commands

Windows users can use `npm.cmd`; ordinary npm commands work as well.

```text
npm.cmd install
npm.cmd run dev
npm.cmd run dev -- --host 127.0.0.1 --port 4173
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd audit --omit=dev
npm.cmd run preview
```

The matching ordinary commands are `npm install`, `npm run dev`, `npm test`, `npm run lint`, `npm run build`, `npm audit --omit=dev`, and `npm run preview`.

## Privacy boundary

The UI only uses run-scoped anonymous session IDs such as `session-a7f3`. Keep raw MAC addresses, personal names, packet contents, and other personal identifiers out of fixtures, logs, screenshots, and UI components. The floor configuration is about spaces and anchors, not people.

## Current status and limits

Automated checks currently pass with 6 test files and 16 tests. ESLint passes, the TypeScript/Vite production build passes, and `npm.cmd audit --omit=dev` reports no production vulnerabilities. The build still prints the normal advisory that the Three.js bundle is larger than 500 kB.

We manually checked the local app in Chrome at the available 1440 px-wide desktop viewport: simulation movement, search, linked selection, layers, camera presets, Focus retargeting, manual orbit persistence, Live unavailable state, and the browser console. Exact 1366 × 768 and 1920 × 1080 viewport overrides were not available in that browser tool, so those two sizes remain a follow-up check. No backend is bundled, so Live mode is expected to be empty or unavailable until a compatible API is running.

For a short, repeatable presentation path, read [docs/demo-guide.md](docs/demo-guide.md). For changes, read [CONTRIBUTING.md](CONTRIBUTING.md) first.
