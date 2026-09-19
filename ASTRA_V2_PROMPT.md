# SEURANTA V2 / ASTRA CONTINUATION PROMPT

You are taking over the Seuranta repository for a final UI, UX, and integration-quality pass before our hackathon demo.

## Repository and starting point

- Repository: `https://github.com/yonathanwold/Seuranta.git`
- Baseline branch: `main`
- Current app branch: `team/app`
- V2 branch to continue and push: `team/app-v2` (it is already seeded from `main`; if it is missing, create it from the latest `main` commit)
- Treat the latest remote `main` commit as the baseline. Run `git rev-parse --short HEAD` after checkout and use that value in your review notes; do not rely on a copied SHA in this prompt.
- Branches already inspected: `team/edge`, `team/data-platform`, `team/positioning`, and `team/app`.

Start by running:

```powershell
git fetch origin
git status --short --branch
git log --oneline --decorate -12
Get-Content README.md
Get-Content SEURANTA_CONTINUATION_PROMPT.md
npm.cmd install
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Open the app and use it before editing. The current demo is deliberately working; keep the existing provider boundary and improve the product around it instead of starting over.

## What is already in the baseline

Seuranta is a React 18, TypeScript, Vite, React Three Fiber, Drei, Three.js, and Zustand application. It uses the supplied Virginia Tech Academic Classroom Building GLB in `public/models/` and starts in Simulation mode with twenty anonymous devices and four planned anchors.

The current flow is:

```text
Building overview -> Floor 1 cutaway -> devices/anchors -> entity detail -> operations pages
```

The first render shows the complete modeled building. The Floor 1 button makes a cutaway that hides `Floor_02`, `Floor_03`, and `Roof`. Walkthrough mode switches to an eye-height perspective camera with WASD movement and mouse look. The demo route validator and navigation envelope keep simulated movement inside the modeled floor; doorway bands are intentionally shared. Devices, Events, and Reports all derive from the same `ProviderSnapshot` through `src/domain/workspace.ts`. There is no Spaces navigation item and no separate Simulations page.

Important contracts and files:

- `src/domain/types.ts`: normalized provider state.
- `src/domain/adapters.ts`: backend DTO to normalized state conversion.
- `src/domain/mockProvider.ts`: deterministic twenty-device demo provider.
- `src/domain/liveProvider.ts`: scoped REST/WebSocket provider boundary.
- `src/domain/coordinates.ts`: metre scale, origin, yaw, and GLB/world axes.
- `src/domain/simulation.ts`: route definitions, zone names, and walkability validation.
- `src/domain/workspace.ts`: shared devices, room records, events, and report model.
- `src/components/MapCanvas.tsx`: model, markers, layers, camera, fallback preview, and walkthrough.
- `src/App.tsx`: shell, navigation, setup, map controls, and cross-page selection.
- `src/components/OperationsPages.tsx`: Devices, Events, and Reports views.
- `README.md`, `docs/frontend-architecture.md`, and `docs/demo-guide.md`: project documentation.

The logo and visual direction are intentionally restrained: white and black as the base, green for healthy/live state, and amber for simulation or degraded state. Keep the voice practical and human. We are college sophomores building a serious prototype, not a fake enterprise marketing site.

## V2 assignment

Continue on `team/app-v2`, which is seeded from the latest `main` commit. If the branch is missing in a fresh checkout, create it from `main`. Do not force-push and do not rewrite or merge the other team branches. All agents share the checkout, so inspect `git status` first and preserve work you did not create.

Review the complete product as if you were the final design and engineering reviewer. Make improvements only when they make the demo clearer, more reliable, or more believable:

1. Inspect every page at a normal laptop size and a 1920×1080 display. Remove stale copy, broken controls, awkward overflow, console errors, and anything that still refers to a removed Spaces or Simulations page.
2. Make the Building/Floor 1 choice obvious. Confirm the complete model loads first, Floor 1 keeps the tracked entities readable, and the camera controls do not fight manual orbit or walkthrough input.
3. Test first-person mode with W A S D and mouse look. Improve the interaction if needed, but keep collision logic centralized and explain any approximation in the docs. Do not replace it with a fake screenshot.
4. Check that the same device, anchor, room, event, and occupancy values stay consistent across the map, Devices, Events, and Reports pages. Do not add page-specific fixture arrays.
5. Make the operations pages feel useful without inventing backend functionality. Demo buttons can acknowledge an action, but the UI should say when something is a demo interaction.
6. Review accessibility: button names, keyboard focus, contrast, reduced-motion behavior where practical, and readable fallback content when WebGL is unavailable.
7. Review performance: avoid per-tick React tree churn, preserve marker interpolation, and do not add large libraries just for decoration. If you change model loading or Meshopt, verify it in a real browser and keep the uncompressed fallback.
8. Keep the privacy boundary. Use anonymous IDs only; do not add names, MAC addresses, raw packet contents, or personal profiles.
9. Update the README and handoff docs in a normal student-team voice. Be honest about estimated geometry, planned anchors, simulation data, and the fact that the Pi/data-platform services are not bundled here.

## Acceptance checklist

Before pushing V2, verify all of the following:

- `npm.cmd test` passes.
- `npm.cmd run lint` passes.
- `npm.cmd run build` passes.
- A fresh browser run has no application console errors.
- The default screen shows the full building and twenty moving devices.
- Floor 1, Top, Overview, Focus, Reset, and Walkthrough all do something visible.
- Walkthrough cannot leave the modeled floor bounds and does not alter the provider data.
- Devices search/filter and Locate in map work.
- Events filtering and resolve state work without changing unrelated pages incorrectly.
- Reports use the same current snapshot as the map and operations pages.
- Live mode stays honest when its API is unavailable; it must not silently fall back to Simulation.
- `git diff --check` is clean.

Use small conventional commits such as `fix(v2): ...`, `feat(v2): ...`, or `docs(v2): ...`. Push the finished branch with:

```powershell
git push -u origin team/app-v2
```

At the end, report the exact commit SHA, the checks you actually ran, and any remaining limits. Do not claim that Raspberry Pi hardware, monitor mode, Databricks, or a live backend was tested unless it really was.
