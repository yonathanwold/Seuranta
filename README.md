# Seuranta

![Seuranta logo](public/brand/seuranta-logo.png)

Seuranta is our indoor positioning dashboard. It turns location estimates from anonymous test devices into a live view of a building floor. Our current pilot is the first floor of Virginia Tech's Academic Classroom Building.

The app starts in Simulation mode, so it is safe to demo without Raspberry Pis, Wi-Fi capture, or a backend. Twenty anonymous devices move through classrooms and common areas while four planned anchors report simulated health. Live mode uses the same map and pages, but it stays honest and shows an error if a compatible API is not running. That split lets us test the product in a smaller space first, then connect the positioning pipeline when the hardware is ready.

## Run it locally

You need Node.js and npm. From the repository root:

```powershell
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Then open `http://127.0.0.1:4173/`.

Other useful commands:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run preview
```

On macOS or Linux, use the same commands without `.cmd`.

## What works right now

- A real React Three Fiber scene using the supplied Virginia Tech building model, with a readable static floor-plan fallback if WebGL is unavailable.
- A white-and-black Seuranta interface using the team logo, with green and amber reserved for system state.
- A full-building first render with every modeled floor, plus a Floor 1 cutaway with orbit, pan, zoom, Overview, Top, Focus, Reset, and Walkthrough controls.
- Twenty anonymous simulated devices following repeatable routes through learning and circulation spaces.
- Smooth marker movement, confidence values, uncertainty radius, timestamps, and zone names.
- Four planned anchor locations with online, degraded, and offline states.
- Search and linked selection between the device list, 3D map, and details panel.
- Devices, Events, and Reports pages that read from the same provider snapshot as the map. Room and occupancy records stay in that shared model so the numbers do not drift between pages.
- Simulation controls on the map for pause, restart, speed, and a weak-signal scenario. Simulation is a data mode, not a separate page.
- Floor calibration and live API settings stored locally in the browser.
- A strict live provider for scoped REST snapshots and WebSocket updates.
- A selectable 2D preview for restricted browsers, keyboard focus in Floor setup, and reduced-motion camera transitions.
- Current-snapshot reports with a real local JSON download. No invented battery levels, signal readings, uptime history, or report schedules.

The operations pages are deliberately small and useful for the demo: search an anonymous device, filter by health, locate it on the map, review an event, acknowledge it locally, and compare the report cards with the map. They are all derived from the current snapshot instead of separate fixture arrays.

Device health comes from position confidence and age relative to the snapshot. It is not a hardware heartbeat. Room names are shared across pages, and occupancy counts anonymous devices, not people. Resolving an event is a clearly labeled local demo action; it survives page navigation and clears when you reload, switch sources, change setup, restart, or change scenarios.

The default building footprint is about 76.9 m × 44.6 m. That number comes from the supplied reference model and has roughly ±15% scale uncertainty. It is not a survey or BIM. The setup screen lets us replace the floor dimensions, origin, rotation, anchor IDs, and anchor coordinates after measuring the real site.

## Model files

The model bundle is in `public/models/`:

```text
vt-academic-classroom.glb           reliable default used by the app
vt-academic-classroom.meshopt.glb   smaller optimized copy for later use
vt-academic-classroom.metadata.json source notes, estimated bounds, rooms, and openings
```

We use the uncompressed GLB right now because it opens without extra decoder setup. The Meshopt copy is kept for a later performance pass. The first render keeps the upper floors and roof visible so the building reads as a building; choosing Floor 1 removes the upper floors and roof from the operational view without changing the source model.

## Simulation and live data

Both modes feed the same normalized frontend objects. React components do not import mock fixtures directly.

```text
MockPositionProvider ─┐
                      ├─> normalized state ─> map, lists, details, metrics
LivePositionProvider ─┘
```

The live provider calls:

```text
GET /api/v1/state
WS  /api/v1/live
```

Both requests include `run_id`, `deployment_id`, `building_id`, `floor_id`, and mode. The default Virginia Tech scope is:

```text
run_id:        vt-acb-floor1
deployment_id: vt-acb-pilot
building_id:   vt-academic-classroom-building
floor_id:      floor-1
```

You can set the API URL in Floor setup or before starting Vite:

```powershell
$env:VITE_SEURANTA_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

Live snapshots and updates must match all four scope IDs. Old revisions, malformed messages, and cross-floor data are ignored. Switching scopes clears the old view immediately. Live mode never quietly falls back to simulation.

The bundled integration path is:

```text
Raspberry Pi observations and heartbeats
  -> data API
  -> positioning and smoothing
  -> floor state and events
  -> REST snapshot + WebSocket updates
  -> Seuranta
  -> optional Databricks Bronze/Silver/Gold batch metrics
```

## Project layout

```text
src/
  components/MapCanvas.tsx   3D floor, camera, anchors, and device markers
  domain/
    adapters.ts              backend DTOs to frontend types
    coordinates.ts           metres, origin, axes, and rotation
    floorDefinition.ts       Virginia Tech floor identity and planned anchors
    roomModel.ts             model asset, calibration, and saved setup
    simulation.ts            first-floor routes and zone names for 20 demo sessions
    mockProvider.ts          local demo state and controls
    liveProvider.ts          scoped REST/WebSocket connection
    workspace.ts             shared devices, spaces, events, and report model
    types.ts                 normalized domain contracts
  App.tsx                    dashboard shell and interactions
  styles.css                layout and visual system
docs/
  frontend-architecture.md
  demo-guide.md
  data-platform/README.md

databricks/
  databricks.yml             Databricks Asset Bundle entry point
  resources/                 on-demand Silver/Gold refresh job
  sql/                       Bronze schema, Silver cleanup, and Gold metrics

services/
  api/                       scoped REST/WebSocket ingestion API
  data/                      anonymous contracts, SQLite WAL, and sink boundary
```

## Privacy

The demo uses IDs such as `session-a7f3`. Do not add names, MAC addresses, raw packet contents, or personal profiles to fixtures, logs, screenshots, or UI components. We are demonstrating spatial analytics, not building a people directory.

## Current checks and limits

ESLint, all 29 frontend tests, the production build, and the static Databricks bundle checks pass. V2 adds regression coverage for shared workspace values and walkthrough bounds. We manually checked the main flow at 1366×768 and 1920×1080, including navigation between every page and locating a device from the inventory back on the map. The production build still prints a chunk-size warning because Three.js is large; it does not stop the build.

The model scale and upper floors are estimated, the planned anchor positions have not been surveyed, and no Raspberry Pi hardware or Databricks workspace was available for remote validation. The data-platform API and deployable Databricks bundle are included, but credentials, warehouse IDs, ingestion scheduling, and workspace permissions remain deployment configuration. The V2 review started from remote `main` at `7d452a5`. See [docs/v2-review.md](docs/v2-review.md) for the checks and remaining limits. Read [docs/demo-guide.md](docs/demo-guide.md) before presenting, [docs/frontend-architecture.md](docs/frontend-architecture.md) before connecting a backend, and [docs/data-platform/README.md](docs/data-platform/README.md) before deploying the data platform.
