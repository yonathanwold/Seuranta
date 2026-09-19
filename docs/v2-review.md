# V2 review — September 19, 2026

The checkout was clean on `team/positioning`. After fetching, we checked out the existing remote `team/app-v2`. `git rev-parse --short HEAD` returned **7d452a5**; remote `main` pointed to the same commit (`7d452a5de18a9ded219b79b2d7e04e776fc5cd32`). No backend branches were merged or rewritten.

## What changed

- Camera presets fit the available map viewport. The first screen keeps the whole building, and Floor 1 opens the cutaway. Device markers remain visible over geometry; they all represent Floor 1 data. Removed the fixed scale and north indicators, which did not follow zoom or rotation.
- Walkthrough has focused WASD input, drag-to-look, keyboard turning, Escape to exit, and a camera-only coordinate readout. Presets exit walking, blur clears movement, and marker clicks do not interrupt a walk. Movement uses bounded substeps and edge sliding through the same approximate envelopes as simulation. Nonzero origins now work consistently with routes and anchor validation.
- Marker positions interpolate in the frame loop without a React position reset on each telemetry update. Simulation controls no longer receive redundant React state updates on every provider tick.
- Devices uses actual position age and confidence for health. Removed invented battery levels, radio strength, index-based offline status, fake pagination, and controls that claimed to queue backend work. Room filtering works, and table headers scroll with rows.
- Room names match the map. Unmapped zones stay unassigned. Event locations come from event fields, and event severity does not change when a device’s current health changes.
- Event close and filtering work. Resolve is explicitly a local demo acknowledgment shared with Reports, scoped to the source and event occurrence. It survives navigation without mutating provider state.
- Reports shows current occupancy counts, position health, planned anchor health, and event counts. Removed synthetic history, uptime claims, saved-report runs, and schedules. Download snapshot JSON produces a local export of the current values.
- Added pressed states, modal focus containment/restoration, visible keyboard focus, reduced-motion preset handling, and a selectable 2D preview. Floor setup anchor IDs keep focus while editing. Planned anchors remain inspectable with no heartbeat.

## Checks actually run

On macOS, using a temporary npm installation with the bundled Node runtime:

- `npm install` completed. It reported five development-tool advisories (three moderate, one high, one critical); dependencies were not upgraded during this UI pass. `npm audit --omit=dev` reported **0 production vulnerabilities**.
- Baseline: 22 tests passed; lint and production build passed before editing.
- Final application: `npm test` — 9 files, 29 tests passed.
- `npm run lint` — passed.
- `npm run build` — passed, with the existing Three.js chunk-size advisory (about 1.16 MB JavaScript / 322 kB gzip).
- `git diff --check` — passed.

The in-app Chromium browser loaded the real uncompressed GLB. Reviewed Map, Devices, Events, and Reports at 1366×768 and 1920×1080. Checked the complete building, cutaway, camera presets, manual orbit, walkthrough mouse look and discrete WASD presses, Escape, pause/resume, search, health filtering, Locate in map, event filters, local resolve across navigation, snapshot download action, and modal keyboard focus. Browser console inspection returned no application errors, including after switching to unavailable Live mode.

Concrete consistency checks used a paused snapshot: E5F6 had identical coordinates and 89% confidence in Devices and the map; Reports showed 20 devices, 8 returned events, 20 provider-reported events in the last hour, and the same one locally resolved event as Events. The camera readout changed independently while paused device telemetry stayed fixed. Bounds tests drive thousands of movements into outer edges and cutouts, including a shifted and resized calibration.

The selectable 2D preview was inspected and device selection worked. An actual GPU-disabled browser was not separately provisioned; the automatic no-WebGL path shares this preview. Reduced-motion handling was reviewed in code, not tested by changing the operating system preference. The long-duration boundary checks are automated domain tests, not a claim of surveyed wall collision.

## Remaining limits

Geometry and anchor locations are estimates, not surveyed measurements. The movement envelope can cross an interior visual wall within a shared region; it prevents escape from the navigation envelope, not every GLB wall intersection. Device health is relative to snapshot time, while the source connection status indicates an unavailable or stale feed.

No Raspberry Pi hardware, monitor mode, packet capture, Databricks, positioning service, or working live backend was tested. Live-unavailable behavior and existing provider contract tests were checked. The uncompressed model remains the runtime asset and Meshopt remains unused. Historical analytics, scheduled reports, replay, and upper-floor telemetry are absent. No new runtime library was added.
