# SEURANTA CONTINUATION PROMPT

You are continuing the Seuranta Atlas frontend implementation in `https://github.com/yonathanwold/Seuranta.git`.

## Start here

The current branch is `team/app`. This branch is an orphan frontend branch and intentionally has no merge base with `team/edge`, `team/data-platform`, or `team/positioning`. Never merge those histories into this branch and never reset or force-push any team branch. Fetch first, inspect recent commits and status, read this handoff and `docs/frontend-architecture.md`, then run the app, tests, and build before changing design or structure.

```powershell
git fetch origin
git switch team/app
git status --short --branch
git log --oneline --decorate -8
Get-Content .\SEURANTA_CONTINUATION_PROMPT.md
npm.cmd install
npm.cmd run dev
npm.cmd test
npm.cmd run build
```

The final SHA is deliberately self-referential: after the final commit, run `git rev-parse HEAD` and record that value here if this handoff is updated. The latest pre-handoff SHA before this docs/handoff commit is `e95cfa8` (`feat(3d): smooth camera preset transitions`).

## Inspect before editing

Inspected upstream branches and heads at implementation time:

- `origin/team/edge` — `7e9ce2a` (Pi edge agent, mode/status and heartbeat conventions).
- `origin/team/data-platform` — `4014883` (FastAPI/data API, state reconstruction and WebSocket deltas).
- `origin/team/positioning` — `5667d03` (positioning, zones, smoothing, event variants).

These histories are unrelated. Backend changes are out of scope for this frontend branch.

## Architecture and files

- `src/domain/types.ts`: normalized organization/site/building/floor, `PositionEstimate`, `SpatialEvent`, `NodeHeartbeat`, provider snapshot, and state types.
- `src/domain/adapters.ts`: the one snake_case-to-camelCase boundary. It normalizes `REAL`/`real` to `LIVE`, simulated variants to `SIMULATION`, and accepts REST `{ data: ... }` wrappers.
- `src/domain/coordinates.ts`: one world unit per metre, backend x → world x, backend y → world -z, centred `(16, 11)` origin.
- `src/domain/floorDefinition.ts`: 32 m × 22 m Riverside Office Floor 2, 0.25 m slab, 0.65 m walls, room/zone polygons, and four anchor coordinates.
- `src/domain/mockProvider.ts`: five anonymous sessions on believable routes, confidence/accuracy, events, zone occupancy, and mixed anchor status.
- `src/domain/liveProvider.ts`: `GET /api/v1/state` plus `/api/v1/live` WebSocket with bounded reconnect and last-state preservation.
- `src/components/MapCanvas.tsx`: R3F floor geometry, OrbitControls, Overview/Top/Focus cameras, entity interpolation, anchors, confidence disc, and labels.
- `src/App.tsx` and `src/styles.css`: operation shell, explorer, synchronized selection/search, detail panel, layer controls, responsive design system.
- `src/tests/`: coordinate, adapter, and provider unit coverage.

## Completed

- Polished dark-nav/light-stage operations atlas shell.
- Real Three.js/R3F floor scene with dimensional geometry, entities, anchors, confidence, labels, and camera controls.
- Smooth 350 ms-class camera preset transitions that stop when the operator manually orbits/pans/zooms.
- Simulation and live provider abstraction with normalized contracts and honest empty/reconnect state.
- Synchronized entity search/list/map/detail selection and operational event feed.
- Documentation, privacy boundary, tests, lint, and production build.

## Incomplete / known limitations

- The live API is scaffolded to the documented V1 REST/WebSocket boundary; no backend is bundled on this branch, so Live mode is expected to show unavailable/empty state without a running service.
- Browser verification used the local Vite app and confirmed shell, simulation updates, selection/search, layer/camera controls, empty live state, and clean console. The in-app browser had a constrained 1280×720 viewport; use a normal desktop browser for final visual sign-off at 1920×1080 and 1366×768.
- The current backend does not send anchor coordinates in heartbeat payloads; floor configuration remains authoritative.
- The production bundle emits the normal Vite warning that the Three.js chunk is larger than 500 kB; code splitting can be considered after product scope stabilizes.
- Unsupported product surfaces such as heatmaps, AI summaries, personal profiles, and settings forms are intentionally omitted.

## Checks run

The following were run successfully during this handoff:

```text
npm.cmd install
npm.cmd test       # 3 files, 7 tests passed
npm.cmd run lint   # passed
npm.cmd run build  # TypeScript + Vite production build passed; chunk-size advisory only
```

The dev server was run with `npm.cmd run dev -- --host 127.0.0.1 --port 4173`. Browser checks confirmed the simulation revision advances, five anonymous devices appear, entity search filters, list selection updates the detail panel and scene label, camera presets change state, layer toggles work, and Live mode presents an empty/unavailable state without console errors.

## Integration assumptions and contracts

Keep the exact PositionEstimate V1 field set in `docs/frontend-architecture.md`. State is expected from `GET /api/v1/state` and live updates from `WS /api/v1/live` as initial snapshots plus `{ type, state_revision, data }` deltas. Keep DTO tolerance for wrappers, mode casing, edge/data status differences, and positioning event `attributes` versus data-platform `metadata`. Do not put raw MACs, payloads, names, or personal identifiers into the UI.

## Priorities for the next agent

1. Run a normal browser at 1920×1080 and 1366×768; inspect floor framing and marker readability, then fix only concrete visual/runtime issues.
2. Connect a real API through the existing adapter and test snapshot/delta/reconnect behavior against the data-platform branch without copying backend code here.
3. Add targeted tests for any contract changes; keep `npm.cmd test`, lint, and build green.
4. Consider code splitting the Three.js bundle only if performance evidence warrants it.

## Agent assignments and active-file warning

The root lead owns architecture decisions and final synthesis. The app implementation agent owns this branch's frontend, docs, tests, commits, and pushes. Other agents may inspect branches read-only. Files under `src/`, `docs/`, and this handoff are active implementation files; inspect the working tree before editing because all collaborators share the checkout.

## Safe git workflow

Use small, buildable conventional commits. Confirm branch and status before edits. Push only `team/app` with a normal push; never force-push. Do not reset, merge, delete, or rewrite `origin/team/edge`, `origin/team/data-platform`, or `origin/team/positioning`. Before handoff, run `git status`, `git log`, tests, lint, build, and `git rev-parse HEAD`, then update this file with the final SHA if desired.
