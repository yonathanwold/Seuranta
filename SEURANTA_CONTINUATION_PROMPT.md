# SEURANTA CONTINUATION PROMPT

You are continuing the Seuranta frontend in `https://github.com/yonathanwold/Seuranta.git`.

## First six steps

1. Fetch the remote without changing unrelated branches: `git fetch origin`.
2. Inspect the current checkout and recent commits: `git switch team/app`, `git status --short --branch`, and `git log --oneline --decorate -8`.
3. Read this file and `docs/frontend-architecture.md` before changing code.
4. Run the app with `npm.cmd install` and `npm.cmd run dev` (or the exact QA command `npm.cmd run dev -- --host 127.0.0.1 --port 4173`).
5. Run `npm.cmd test`, `npm.cmd run lint`, and `npm.cmd run build`; also run `npm.cmd audit --omit=dev` when security status matters.
6. Continue from the current implementation and its open items. Do not redesign the app or copy backend histories just because you are new to the repository.

## Branch and commit context

The current branch is `team/app`. It is an orphan frontend branch with no merge base with `team/edge`, `team/data-platform`, or `team/positioning`. Do not merge those histories into this branch. Do not reset, delete, force-push, or rewrite any of those three team branches.

The final SHA in this file is intentionally self-referential. After the last commit, run `git rev-parse HEAD` to get the exact final SHA; putting that value into this file would create another commit. The latest pre-handoff SHA is `70ab041687ee1ca1e00975775d11bac8fc68dc10` (`docs(app): record final live scope revision`).

## Branches inspected

These upstream heads were inspected while building the frontend:

- `origin/team/edge` — `7e9ce2a`, Pi edge agent, heartbeat and mode/status conventions.
- `origin/team/data-platform` — `4014883`, state reconstruction, REST, and WebSocket deltas.
- `origin/team/positioning` — `5667d03`, position estimates, zones, smoothing, and event variants.

They have unrelated root histories. Backend changes are outside the scope of `team/app`.

## What is here

- `src/domain/types.ts` — normalized organization/site/building/floor, position, event, node, state, and provider types.
- `src/domain/adapters.ts` — the single snake_case-to-camelCase boundary, including mode/status and response-wrapper handling.
- `src/domain/coordinates.ts` — tested metre-to-Three.js transform and inverse conversion.
- `src/domain/floorDefinition.ts` — 32 m × 22 m Riverside Office Floor 2, rooms, zones, walls, and four configured anchor locations.
- `src/domain/mockProvider.ts` — five anonymous sessions on smooth waypoint routes, confidence, accuracy, events, and mixed anchor health.
- `src/domain/liveProvider.ts` — scoped REST/WS adapter, typed position/node/event deltas, strict four-field scope checks, revision handling, reconnects, and snapshot-required rehydration.
- `src/domain/camera.ts` — one-shot Focus retargeting when the selected session identity changes.
- `src/domain/store.ts` — Zustand mode, selection, search, snapshot, and layer state.
- `src/components/MapCanvas.tsx` — R3F floor, orbit controls, markers, confidence discs, labels, camera presets, and Canvas fallback.
- `src/App.tsx` and `src/styles.css` — the shell, explorer, details, controls, and visual system.
- `src/tests/` — transform, floor, adapter, mock provider, live provider, and camera tests.
- `docs/frontend-architecture.md` — contracts, module responsibilities, coordinates, provider behavior, and integration path.
- `docs/demo-guide.md` — repeatable Simulation presentation flow.
- `CONTRIBUTING.md` — branch, check, privacy, and pull request guidance.
- `.github/PULL_REQUEST_TEMPLATE.md` — short review checklist.

## Completed

- Real Three.js/R3F floor geometry with a readable elevated view.
- Smooth anonymous simulation with five sessions, four anchors, confidence, uncertainty, zone events, and anchor health.
- Shared Mock/Live provider boundary with scoped live URLs and typed WebSocket deltas.
- REST/WS mode normalization (`LIVE`/`SIMULATION` to `real`/`simulated`) and defensive scope/mode validation.
- Entity search, linked list/map/detail selection, anchor diagnostics, recent activity, layer switches, and working Overview/Top/Focus controls.
- Focus retargeting on selection identity changes without camera movement on routine telemetry ticks.
- Honest live unavailable/empty state and a real Canvas WebGL fallback message with usable DOM lists.
- Documentation, contribution notes, demo guide, privacy boundary, tests, lint, production build, and production-only audit check.

## Incomplete and known limitations

- No backend service is bundled. Live mode is expected to show unavailable or empty state until a compatible scoped API is running.
- Building and floor are static demo context. Replay is not exposed because no replay provider exists.
- The current backend heartbeat does not carry anchor coordinates; the floor definition remains authoritative for placement.
- The browser QA tool provided a 1440 px-wide desktop viewport but no exact 1366 × 768 or 1920 × 1080 override. Those exact sizes still need a normal resizable browser check.
- The production build prints the usual Three.js chunk-size advisory. No code-splitting work has been started.
- If WebGL cannot initialize, the fallback is a concise message plus the entity/anchor DOM lists; there is no alternate DOM-rendered floor.
- No functional app bug is known from the current checks. Unsupported surfaces such as analytics, settings forms, heatmaps, personal profiles, and summaries are intentionally omitted.

## Checks and exact commands

The current code has been checked with:

```text
npm.cmd install
npm.cmd test                 # 6 files, 16 tests passed
npm.cmd run lint             # passed
npm.cmd run build            # passed; Three.js chunk-size advisory only
npm.cmd audit --omit=dev     # 0 production vulnerabilities
```

The ordinary npm equivalents are `npm install`, `npm test`, `npm run lint`, `npm run build`, and `npm audit --omit=dev`.

The local dev server used for browser QA was:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Manual QA covered Simulation movement, five anonymous devices, search, linked selection, layers, camera presets, Focus retargeting, manual orbit persistence across telemetry, Live unavailable state, and the browser console. The available browser showed no current app console errors; unrelated extension warnings and one stale pre-reload Vite HMR message were not app failures.

## Contracts and assumptions

Keep the exact PositionEstimate V1 fields in `docs/frontend-architecture.md`:

```text
schema_version, position_id, calculated_at, window_start, window_end,
run_id, deployment_id, building_id, floor_id, session_id,
raw_x_m, raw_y_m, x_m, y_m, zone_id, confidence,
accuracy_radius_m, position_method, smoothing_method, anchors_used,
observation_count, mode, sequence_number, is_outside_map
```

The live boundary is scoped `GET /api/v1/state` plus `WS /api/v1/live`. Both use `run_id`, `deployment_id`, `building_id`, `floor_id`, and `real`/`simulated` mode query values. Reconnects use `since_revision` where possible. WebSocket messages are `{ type, state_revision, data }`; snapshots replace state, position/node/event messages update one entity, heartbeat/observation messages can advance revisions, and `snapshot_required` triggers a full refresh. Missing or cross-scope typed deltas must not be accepted.

Keep adapter tolerance for bare versus `{ data: ... }` responses, edge uppercase modes/statuses, data-platform lowercase modes, positioning `attributes` versus data-platform `metadata`, and the known sessions/observation-batch shape differences. Do not put names, raw MACs, packet payloads, or personal identifiers into the UI.

The coordinate contract is one world unit per metre. The floor origin is `(16, 11)` m; backend `x_m` maps to world `x`, backend `y_m` maps to world `-z`, and world `y` is vertical. Use `src/domain/coordinates.ts` instead of repeating math in components.

## Next priorities

1. Run the demo in a normal browser at exactly 1366 × 768 and 1920 × 1080, then fix only concrete framing or readability problems.
2. Connect a compatible data-platform API and test scoped snapshots, typed deltas, reconnects, and `snapshot_required` behavior without copying backend code into this branch.
3. Add focused tests for any contract change and keep all existing checks green.
4. Consider Three.js code splitting only if measured load/performance evidence makes it worth the added complexity.

## Ownership and active-file warning

The root lead owns architecture decisions, task scope, and final synthesis. The app implementation agent owns the `team/app` frontend, docs, tests, commits, and pushes. Read-only reviewers may inspect the branch but should not edit it.

Files under `src/`, `docs/`, `README.md`, `CONTRIBUTING.md`, `.github/`, and this handoff are active. Everyone shares this checkout, so inspect `git status` before editing and preserve changes you did not make.

## Safe Git workflow

Use small conventional commits that build and test. Work only on `team/app`, push with a normal `git push origin team/app`, and never force-push. Do not use `git reset --hard`, merge unrelated team branches, or rewrite `origin/team/edge`, `origin/team/data-platform`, or `origin/team/positioning`. Before handing work back, run `git status --short --branch`, `git log --oneline -8`, the checks above, and `git rev-parse HEAD`.
