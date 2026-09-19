# Seuranta demo guide

This is the reliable way to present the current frontend. It uses Simulation mode, so the demo does not depend on a backend or network service.

## Start it

From the repository root:

```powershell
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173/` if Vite uses that port. A normal `npm.cmd run dev` command is also fine; use the URL Vite prints if the port is different.

## Judge flow

The whole walkthrough takes about two minutes:

1. Start in Simulation mode and point out the floor model, five anonymous device markers, and four anchors. The moving markers update every 700 ms.
2. Click `Device A7F3` in the left list. Show that the map card and right detail panel follow the same selection.
3. Type `C4E2` into Search devices, select the result, and show the zone, confidence, accuracy radius, and anchors used.
4. Click Focus, then select a different device. Focus should move once to the new session. Drag the map afterward to show that manual orbit stays under operator control while telemetry keeps updating.
5. Click Map layers and toggle Confidence or Zones. Use Top and Overview to show the other camera presets.
6. If there is time, switch to Live. Without a compatible API it should say `Live source unavailable` and show zero sessions. This is an intentional empty/error state, not a broken simulation.

## What to point out

- The floor is configuration-driven: dimensions, rooms, zones, walls, and anchor positions come from `src/domain/floorDefinition.ts`.
- The mock provider is shaped like the live provider. Both send normalized state to the same UI.
- Confidence and accuracy are part of each position estimate, so the selected uncertainty disc is tied to the data rather than being decoration.
- Session IDs are anonymous and run-scoped. The app is not a people directory.

## What not to overclaim

- Simulation is not live sensor data. It is a deterministic local demo with believable routes.
- The repository does not include the Pi service, positioning service, or data-platform API.
- Live mode is a documented REST/WebSocket boundary, not a bundled working backend.
- Replay, analytics pages, settings forms, heatmaps, and personal profiles are not implemented.
- Exact 1366 × 768 and 1920 × 1080 browser sign-off is still pending because the available QA browser did not expose those viewport overrides.
