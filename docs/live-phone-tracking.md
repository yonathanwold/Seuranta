# Live phone tracking

This branch adds a consenting, anonymous browser tracker to the existing Seuranta V2 live pipeline:

```text
iPhone / Android browser
  -> /tracker/ browser geolocation
  -> WS /api/v1/tracker (REST fallback: /api/v1/telemetry/location)
  -> calibration + local metres + yaw + EMA + confidence
  -> existing PositionEstimate contract
  -> WS /api/v1/live
  -> LivePositionProvider
  -> existing 3D map, Devices, Events, Reports
```

The backend is the existing `services.api.main:app`; the phone page is the small static bundle in `tracker/`. No native app, MAC address, phone number, name, or device fingerprint is used.

## Start the backend on Windows

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r services\api\requirements.txt

$env:SEURANTA_DEV_MODE = "true"
$env:SEURANTA_ALLOWED_ORIGINS = "http://localhost:4173,http://127.0.0.1:4173"
python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```

On macOS/Linux, activate with `source .venv/bin/activate` and use forward slashes. The API and tracker are then available at:

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/tracker/
```

Use a different `SEURANTA_DATABASE_PATH` for a clean local run if an old SQLite file exists.

## Start the dashboard

In another terminal:

```powershell
npm install
$env:VITE_SEURANTA_API_URL = "http://127.0.0.1:8000"
npm run dev -- --host 0.0.0.0 --port 4173
```

Open `http://127.0.0.1:4173/`, switch to Live, and use Floor setup if the API URL or scope differs from the defaults. Live mode uses:

```text
run_id:        vt-acb-floor1
deployment_id: vt-acb-pilot
building_id:   vt-academic-classroom-building
floor_id:      floor-1
mode:          real
```

If the dashboard is opened from a laptop hotspot/LAN address instead of localhost, add that exact dashboard origin (for example `http://192.168.137.1:4173`) to `SEURANTA_ALLOWED_ORIGINS` before starting the backend.

## Phone workflow

1. Put the laptop and consenting phones on the same test network or hotspot.
2. For phone geolocation, expose the backend through a legitimate HTTPS URL. A local `localhost` URL is suitable for laptop-only browser testing, but a phone should use an HTTPS tunnel or HTTPS reverse proxy. Cloudflare Tunnel is one possible temporary hackathon tunnel; the application does not depend on it.
3. Set `SEURANTA_PUBLIC_TRACKER_URL` to the HTTPS tracker URL when the URL is known, or open the backend URL plus `/tracker/` directly. Example: `https://tracker-example.example.com/tracker/`.
4. In the dashboard Live map, scan the Connect device QR code or copy its URL. The QR is rendered locally by the backend; the URL is not sent to a third-party QR service.
5. On the phone, review the anonymous session ID and press **Enable Precise Location**. The browser permission prompt is intentionally not requested before this interaction.
6. Grant precise location permission. The tracker displays the actual browser-reported accuracy, latitude/longitude, update count, and connection state.
7. Stand at the configured known point and press **Calibrate Position**. Keep the page open and walk several metres. The next updates should move the same anonymous marker in the existing 3D map.
8. Repeat on another consenting phone. Each phone has a different anonymous ID stored only in that browser's local storage.
9. Press **Stop Sharing** on a phone to call `clearWatch`, close the tracker socket, and revoke that anonymous session immediately. The tracker keeps ended IDs from being reused; press **Start New Anonymous Session** before sharing again. If a browser reloads with an older ended ID, the tracker rotates it once and reconnects automatically.

The default thresholds are active under 10 seconds, degraded/stale from 10 seconds up to 30 seconds, and removed from active state at 30 seconds. They can be changed with `SEURANTA_TRACKER_STALE_SECONDS` and `SEURANTA_TRACKER_EXPIRE_SECONDS`.

## Calibration and coordinates

The first version uses one known point. Configure its floor-local coordinates with:

```powershell
$env:SEURANTA_CALIBRATION_X_M = "12"
$env:SEURANTA_CALIBRATION_Y_M = "18"
$env:SEURANTA_BUILDING_YAW_DEG = "0"
```

When a tracker presses Calibrate, the current latitude/longitude becomes the reference for that point. For a fixed preconfigured reference, also set `SEURANTA_CALIBRATION_LAT` and `SEURANTA_CALIBRATION_LON`. At yaw 0, east is floor X and north is floor Y. The result is not clamped; `is_outside_map` is set when it falls outside the configured `SEURANTA_FLOOR_WIDTH_M` × `SEURANTA_FLOOR_DEPTH_M` rectangle.

Reported horizontal accuracy is preserved as `accuracy_radius_m`. Confidence is a bounded display signal derived from that accuracy; it is not a claim of exact indoor positioning. Browser GPS can be poor or unavailable indoors.

## Development injection

The dev endpoint is disabled unless `SEURANTA_DEV_MODE=true`:

```powershell
$body = @{ session_id = "session-test"; x_m = 20; y_m = 15; accuracy_radius_m = 2 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/dev/position" -Method Post -ContentType "application/json" -Body $body
```

With dev mode enabled, the tracker page also shows a clearly labeled **DEV SIMULATION** button. It posts floor-local positions and never labels them as phone geolocation. Repeated calls to the endpoint or the button drive the same `/api/v1/live` dashboard stream.

## Tests and checks

```powershell
python -m pytest services/api/tests -q
npm install
npm test
npm run lint
npm run build
```

The backend tests cover coordinate conversion, yaw, calibration offsets, smoothing, confidence, outside-map detection, session creation/expiry, malformed packets, scope validation, state revision, REST ingestion, dev injection, and tracker/dashboard WebSocket behavior. The existing frontend tests continue to cover the normalized provider and simulation paths.

## Known limitations

- Browser geolocation is not centimeter-level or reliably room-level indoors; the UI exposes the reported accuracy and confidence instead of hiding that uncertainty.
- One-point calibration supplies translation only. Two-point calibration and heading calibration are future extensions.
- The hackathon state store is in memory for active tracker sessions and SQLite for the existing local records; it is not a horizontally scaled production service.
- The supplied Virginia Tech model and floor dimensions remain reference estimates until surveyed.
- HTTPS tunneling, hotspot setup, and QR scanning are deployment conveniences. Captive portal behavior is not required for correctness.
