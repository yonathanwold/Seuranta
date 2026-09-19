# Seuranta Atlas edge agent

This is the Raspberry Pi/anchor-side reference implementation for the frozen
Seuranta V1 contracts. It uses Python's standard library only and is safe to
run in `MOCK` mode without a Pi, Wi-Fi adapter, backend, or third-party
packages.

## Quick mock smoke test

From this directory:

```text
python -m seuranta_edge --defaults validate-config
python -m seuranta_edge --defaults mock-stream --count 3
python -m seuranta_edge --defaults buffer-status
```

The default queue is a local SQLite file. It is a demo artifact and should be
placed under `/var/lib/seuranta-edge` on a real Pi; do not commit it.

## Environment configuration

Production configuration is loaded from a JSON file plus uppercase environment
overrides. The secret is intentionally not included in the example file:

```text
export DEMO_RUN_SECRET='a-new-random-secret-at-least-16-bytes'
python -m seuranta_edge --config-file example-config.json validate-config
```

Required names are `ANCHOR_ID`, `ANCHOR_X`, `ANCHOR_Y`, `ANCHOR_FLOOR`,
`DEPLOYMENT_ID`, `BUILDING_ID`, `SEURANTA_API_URL`, `SEURANTA_WIFI_SSID`,
`SEURANTA_WIFI_CHANNEL`, `WIFI_INTERFACE`, `CAPTURE_STRATEGY`,
`OBSERVATION_INTERVAL_MS`, `HEARTBEAT_INTERVAL_MS`, `BATCH_MAX_SIZE`,
`BUFFER_PATH`, and `DEMO_RUN_SECRET`. `validate-config` redacts the secret.

### BLE iPhone positioning mode

Set `CAPTURE_STRATEGY` to `BLE` when a consented iPhone advertises the fixed
local Bluetooth name in `BLE_TARGET_NAME` (for example `Seuranta-iPhone`).
`BLE_SCAN_SECONDS` defaults to `3`.  The agent scans only for that exact name,
keeps Bluetooth addresses in memory only long enough to pair a name and RSSI,
then HMACs the configured name into the shared run-scoped session ID before
sending metadata.  It uses the Pi's Bluetooth radio, leaving `wlan0` connected
to the hotspot for API traffic.

See `example-ble-config.json` and
[`docs/hardware/star-localization.md`](../../docs/hardware/star-localization.md)
for the four-anchor layout, API configuration, calibration, and iPhone
advertising requirements.

## Privacy boundary

The collectors read signal metadata only. Raw station identifiers are held in
memory just long enough to map an opted-in device to a run-scoped HMAC ID.
They are never put into a contract, SQLite queue, log, diagnostic, or packet
capture. Non-active sessions are dropped before `SignalObservation` creation.

## API client routes

`HttpTransport` uses the following exact V1 routes:

* `POST /api/v1/sessions`
* `POST /api/v1/sessions/{session_id}/end`
* `POST /api/v1/observations/batch`
* `POST /api/v1/nodes/heartbeat`
* `GET /api/v1/sessions`

The SQLite queue writes a batch before delivery. A backend outage therefore
retains batch IDs and payloads across process restarts, and retries in FIFO
order with bounded exponential backoff.

## Hardware boundary

No Raspberry Pi, Wi-Fi adapter, monitor-mode capture, or physical channel
validation was available in this implementation environment. Follow the
hardware runbooks in `docs/hardware/` and record the actual adapter and
channel validation results before calling a node production-ready.
