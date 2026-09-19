# Seuranta Atlas

Seuranta Atlas is a desktop-first operations workspace for anonymous indoor-positioning telemetry. It pairs a configuration-driven Riverside Office floor definition with a real `@react-three/fiber` map, smooth mock movement, anchor health, uncertainty, and a provider boundary ready for the Seuranta REST/WebSocket API.

The demo is intentionally privacy-preserving: it renders only run-scoped anonymous session identifiers. No names, raw MAC addresses, packet payloads, or personal profiles are represented in the UI.

## Run on Windows

From the repository root:

```powershell
npm.cmd install
npm.cmd run dev
```

Open the URL printed by Vite (normally `http://127.0.0.1:4173/`). The demo starts in Simulation mode, so no backend or credentials are needed. To use the live adapter, set `VITE_SEURANTA_API_URL` before starting Vite, or leave it empty when the API is proxied from the same origin.

```powershell
$env:VITE_SEURANTA_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

## Ordinary npm commands

```text
npm install
npm run dev
npm run build
npm test
npm run lint
npm run preview
```

`npm run build` runs the strict TypeScript build and Vite production build. `npm test` runs the Vitest unit suite for coordinate transforms, wire adapters, and the mock provider. `npm run lint` runs ESLint across the source tree.

## What is implemented

- A quiet operations-atlas shell with navigation, building/floor context, simulation/live mode, entity explorer, map layers, search, detail panel, recent transitions, and keyboard-visible controls.
- An elevated orthographic Three.js/R3F floor with dimensional slab, wall segments, room surfaces, labels, four anchor markers, anonymous moving entities, selected confidence/accuracy disc, hover/selected HTML cards, OrbitControls, and Overview/Top/Focus presets.
- `MockPositionProvider` with five anonymous sessions, route interpolation, confidence, accuracy radius, zones, transition events, and mixed anchor health.
- `LivePositionProvider` with REST snapshot loading from `GET /api/v1/state` and a reconnecting WebSocket boundary at `/api/v1/live`. The UI receives only normalized domain state.

## Repository guide

- `src/domain/types.ts` — normalized UI contracts.
- `src/domain/adapters.ts` — snake_case DTO and mode/status normalization boundary.
- `src/domain/coordinates.ts` — tested backend metre to Three world transform.
- `src/domain/floorDefinition.ts` — demo floor dimensions, walls, rooms, zones, and anchor coordinates.
- `src/domain/mockProvider.ts` / `src/domain/liveProvider.ts` — provider implementations.
- `src/components/MapCanvas.tsx` — R3F floor scene, camera, marker interactions, and fallback plan.
- `src/App.tsx` / `src/styles.css` — application composition and design system.
- `docs/frontend-architecture.md` — contracts, provider switching, integration assumptions, and future connection path.
- `SEURANTA_CONTINUATION_PROMPT.md` — handoff and continuation runbook.

## Data modes and integration note

Simulation is the safe default and is visually explicit in the navigation and top bar. Live mode preserves the last normalized snapshot while it reconnects and exposes a clear unavailable state when the API cannot be reached. Read the architecture document before wiring a backend: the existing edge, positioning, and data-platform branches use different mode vocabulary and response wrappers, and the adapter intentionally absorbs those differences.
