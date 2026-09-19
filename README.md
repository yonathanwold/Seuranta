# Seuranta

![Seuranta logo](public/brand/seuranta-logo.png)

Seuranta is our indoor positioning dashboard. It turns location estimates from anonymous test devices into a live 3D view of a building floor. Our current pilot is the first floor of Virginia Tech's Academic Classroom Building.

The app starts in Simulation mode, so it is safe to demo without Raspberry Pis, Wi-Fi capture, or a backend. Six anonymous devices move through classrooms and common areas while four planned anchors report simulated health. Live mode uses the same map and UI, but it stays empty and shows an error if a compatible API is not running. That split is intentional: we can test the product in a smaller space first, then connect the positioning pipeline when the hardware is ready.

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
- A first-floor cutaway with orbit, pan, zoom, Overview, Top, Focus, and Reset controls.
- Six anonymous simulated devices following repeatable routes through learning and circulation spaces.
- Smooth marker movement, confidence values, uncertainty radius, timestamps, and zone names.
- Four planned anchor locations with online, degraded, and offline states.
- Search and linked selection between the device list, 3D map, and details panel.
- Simulation controls for pause, restart, speed, and a weak-signal scenario.
- Floor calibration and live API settings stored locally in the browser.
- A strict live provider for scoped REST snapshots and WebSocket updates.

The default building footprint is about 76.9 m × 44.6 m. That number comes from the supplied reference model and has roughly ±15% scale uncertainty. It is not a survey or BIM. The setup screen lets us replace the floor dimensions, origin, rotation, anchor IDs, and anchor coordinates after measuring the real site.

## Model files

The model bundle is in `public/models/`:

```text
vt-academic-classroom.glb           reliable default used by the app
vt-academic-classroom.meshopt.glb   smaller optimized copy for later use
vt-academic-classroom.metadata.json source notes, estimated bounds, rooms, and openings
```

We use the uncompressed GLB right now because it opens without extra decoder setup. The Meshopt copy is kept for a later performance pass. The app only shows `Floor_01`; the upper floors and roof are still present in the source model.

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

The future pipeline is:

```text
Raspberry Pi observations and heartbeats
  -> data API
  -> positioning and smoothing
  -> floor state and events
  -> REST snapshot + WebSocket updates
  -> Seuranta
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
    simulation.ts            first-floor routes and zone names
    mockProvider.ts          local demo state
    liveProvider.ts          scoped REST/WebSocket connection
    types.ts                 normalized domain contracts
  App.tsx                    dashboard shell and interactions
  styles.css                layout and visual system
docs/
  frontend-architecture.md
  demo-guide.md
```

## Privacy

The demo uses IDs such as `session-a7f3`. Do not add names, MAC addresses, raw packet contents, or personal profiles to fixtures, logs, screenshots, or UI components. We are demonstrating spatial analytics, not building a people directory.

## Current checks and limits

ESLint, all 21 tests, and the production build pass. We manually checked the main flow at 1366×768 and 1920×1080. The production build still prints a chunk-size warning because Three.js is large; it does not stop the build.

The model scale and upper floors are estimated, the planned anchor positions have not been surveyed, and no Raspberry Pi service is bundled with this branch. Read [docs/demo-guide.md](docs/demo-guide.md) before presenting and [docs/frontend-architecture.md](docs/frontend-architecture.md) before connecting a backend.
