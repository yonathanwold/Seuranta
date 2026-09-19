# Four-Pi star localization

The current iPhone hotspot is the **network star**: the API host and each Pi
may use it to exchange telemetry.  It is not an 802.11s mesh, and it is not a
positioning sensor by itself.

For positioning the iPhone, place the four Pi anchors at known, non-collinear
locations on one floor (a rectangle or a wide quadrilateral is ideal).  Each
anchor produces an RSSI reading for the same short-lived iPhone session and
sends it to the API.  The API groups readings from a three-second window and
uses calibrated RSSI multilateration to write a `PositionEstimate`.

```
          Pi 1 --------------\
          Pi 2 ---------------+--> API / internal positioner --> position
          Pi 3 ---------------+
          Pi 4 --------------/

          iPhone BLE advertises a demo session to every Pi
          iPhone hotspot can carry the Pi-to-API traffic during a demo
```

The recommended no-USB-adapter sensor path is Bluetooth Low Energy: the iPhone
advertises a Seuranta BLE session and all four Pis scan it.  Wi-Fi RSSI cannot
currently supply the measurements because the built-in Pi Wi-Fi driver did not
report client RSSI or monitor-mode radiotap RSSI during hardware checks.  A
compatible monitor/AP-capable USB adapter is the alternative Wi-Fi path.

For an initial live demo, the iPhone app should advertise the fixed local name
`Seuranta-iPhone` while it is open in the foreground.  Each Pi uses that name
only as an in-memory consented token and sends a run-scoped HMAC session ID,
not a Bluetooth address.  iOS may reduce or change advertising behavior in the
background, so foreground operation is the supported first milestone.

### No-code iPhone advertiser

For the first demo, install [LightBlue](https://apps.apple.com/us/app/lightblue/id557428110)
on the iPhone.  Its App Store listing describes creating a custom peripheral
profile and advertising it from the phone.  Create one profile whose local name
is exactly `Seuranta-iPhone`, add any basic custom service, and start its
advertising toggle.  Keep LightBlue open while testing.  The Pi collector uses
the name only to select the consented advertisement; it does not send the name
or a Bluetooth address to the API.

## Anchor layout and calibration

1. Measure every anchor from a shared origin in metres.  Avoid putting all
   anchors along one wall.
2. At exactly one metre from each anchor, collect several RSSI samples from the
   iPhone, then use their median as `tx_power_dbm_at_1m`.
3. Start with a path-loss exponent of `2.2`; tune it with a few known test
   points in the room.  Typical indoor values are roughly `1.8` to `3.5`.
4. Keep anchors at a similar height, away from large metal objects and people
   standing directly in front of the antenna.

Example API configuration (replace every coordinate and calibration value with
measurements from the real room):

```sh
export SEURANTA_INTERNAL_POSITIONING=true
export SEURANTA_POSITIONING_WINDOW_SECONDS=10
export SEURANTA_POSITIONING_MIN_ANCHORS=4
export SEURANTA_POSITIONING_ANCHORS_JSON='{
  "anchors": [
    {"anchor_id":"pi-1","x_m":0,"y_m":0,"tx_power_dbm_at_1m":-59,"path_loss_exponent":2.2},
    {"anchor_id":"pi-2","x_m":6,"y_m":0,"tx_power_dbm_at_1m":-59,"path_loss_exponent":2.2},
    {"anchor_id":"pi-3","x_m":0,"y_m":4,"tx_power_dbm_at_1m":-59,"path_loss_exponent":2.2},
    {"anchor_id":"pi-4","x_m":6,"y_m":4,"tx_power_dbm_at_1m":-59,"path_loss_exponent":2.2}
  ],
  "boundary": [
    {"x_m":0,"y_m":0}, {"x_m":6,"y_m":0},
    {"x_m":6,"y_m":4}, {"x_m":0,"y_m":4}
  ]
}'
```

When live RSSI observations arrive from the configured minimum number of
anchors in the same session and time window, the API creates a position
automatically. For the four-Pi room grid, require all four anchors and use a
ten-second window so an incomplete or stale scan cannot move the phone dot.
If a raw radio estimate falls beyond the configured boundary, the stored
coordinate is projected onto the nearest boundary point and marked
`is_outside_map: true`; the raw coordinate remains available for diagnostics.
The API health endpoint exposes the internal estimator's configured-anchor,
emitted, skipped, and latest-error counts.

For calibration before the Pi BLE scanner is deployed, use
`POST /api/v1/positioning/estimate` with an RSSI snapshot, anchor coordinates,
and calibration values.  The endpoint persists the resulting position just as
the automatic path does.

Do not expect room-level precision from uncalibrated RSSI.  The estimator uses
a conservative accuracy radius, and four anchors provide better geometry and
outlier resistance than the three-anchor minimum.

## Pi BLE collector configuration

Use [`edge/pi-agent/example-ble-config.json`](../../edge/pi-agent/example-ble-config.json)
as a template for each Pi.  Give each Pi a distinct `anchor_id`, `anchor_x`,
and `anchor_y`; keep the same `deployment_id`, `building_id`, API URL,
`ble_target_name`, and run secret on all four Pis.  The agent runs
`btmgmt --timeout … find -l` for short BLE scans and emits only RSSI for the
exact configured name. This is important for iPhone advertisers: BlueZ's
ordinary `bluetoothctl` scan can see the name without producing a usable RSSI
event.

`btmgmt` uses BlueZ's management socket. Keep the agent as the dedicated
`seuranta` user and scope the required Linux capability to its systemd service
rather than running the full agent as root:

```ini
# sudo systemctl edit seuranta-edge
[Service]
CapabilityBoundingSet=CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_ADMIN
```

Restart the service after adding the drop-in. `CAP_NET_ADMIN` is a powerful
networking capability, so reserve this configuration for the dedicated demo
service and protect its installation directory from untrusted writes.

Before deployment, confirm the Pi has a working Bluetooth controller and that
the scanner output contains RSSI updates for the advertiser.

The iPhone hotspot is acceptable as a short-demo backhaul, but it moves with
the device being located.  A stationary Ethernet switch or access point is the
better long-term star backhaul once the demo works.
