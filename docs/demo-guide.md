# Demo guide

Simulation mode is the reliable presentation path. It does not need Wi-Fi, hardware, or a backend.

## Start the app

```powershell
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173/`.

## Two-minute walkthrough

1. Start on Building. Explain that the first render shows the complete modeled Virginia Tech Academic Classroom Building. Then choose Floor 1 to open the operational cutaway. The geometry is an estimate, not a survey.
2. Point out the twenty anonymous devices and four planned anchors. The devices use routes traced from the supplied floor metadata.
3. Select `Device A7F3`. Show its coordinates, confidence, uncertainty radius, zone, and update time.
4. Search for `E5F6`, select it, and press Focus. The camera moves once and then leaves manual control alone.
5. Switch between Top and Overview. Drag to orbit or pan and scroll to zoom.
6. Click Walkthrough, use W A S D to move, drag the mouse to look, or use arrow keys to turn. Explain that the demo keeps movement inside modeled walkable regions and leaves the final floor graph to the live integration. Escape exits; clicking outside the canvas stops movement.
7. Toggle Devices, Anchors, Labels, Uncertainty, or Floor overlay in Map layers.
8. Pause and resume the simulation. Restart resets the routes. Weak signal lowers one device's confidence and degrades one anchor.
9. Open Floor setup. Show the floor dimensions, origin, yaw, anchor IDs, anchor coordinates, and exact live scope fields.
10. Open Devices, search `E5F6`, then Locate in map. Pause first if you want to compare exact coordinates.
11. Open Events, select an event, and Resolve · demo. Reports shows the same local acknowledgment count. Download snapshot JSON produces a local file with the current values.
12. Use 2D preview to show the selectable fallback. Switch back with 3D map.
13. Switch to Live. With no API running, the app shows zero devices, planned anchors as offline, and `Live source unavailable`. Switch back to Demo to finish.

## Small pilot checklist

Before testing with Raspberry Pis in the building:

1. Measure two known distances on the first floor and update the width and depth if the model scale is off.
2. Pick a local `(0, 0)` point and confirm which direction backend `x_m` and `y_m` increase.
3. Enter the installed anchor IDs and measure each anchor from the same origin.
4. Use the same run, deployment, building, and floor IDs in the backend and Floor setup.
5. Put a consenting test device at a few known spots and compare the live marker with tape-measured coordinates.
6. Record the observed error before adjusting confidence or uncertainty settings.

## Claims we can make

- Simulation and Live use the same renderer and domain types.
- Coordinates are in metres and conversion math is centralized.
- Scope and revision checks protect the view from stale or cross-floor data.
- The model is usable offline for the presentation.

## Claims we should not make yet

- The model is not a survey, BIM, or confirmed georeferenced floor plan.
- Planned anchors are not installed or measured anchors.
- Simulated confidence is demo data, not a benchmark of the final positioning system.
- Live mode is ready for the documented API. This branch also includes the scoped data API and a Databricks Asset Bundle, but the Pi agent, positioning worker, credentials, warehouse, and workspace deployment are still deployment work.

Health labels describe position age and confidence, not physical device connectivity. We do not have battery readings or historical uptime. The Building view draws Floor 1 markers over geometry for readability; use the cutaway to interpret their location.
