# Positioning contract coordination

The positioning engine currently uses local compatibility models in
`services/positioning/models.py` because the repository was empty when this
branch was initialized. Those models mirror the frozen V1 shapes and emit
`schema_version: "1.0"` with snake_case fields.

When the shared contracts are introduced, the integration should replace the
local import boundary without changing the positioning algorithms. The
following invariants must remain unchanged:

* `SignalObservation` contains no names, raw MACs, payload data, or persistent
  device identifiers.
* A missing or insufficient RSSI vector produces diagnostics and no fabricated
  `PositionEstimate`.
* `PositionEstimate` retains both `raw_x_m`/`raw_y_m` and smoothed `x_m`/`y_m`.
* WKNN emits `position_method: "wknn_wifi_fingerprint"` and records
  `anchors_used` and `observation_count`.
* Spatial events use only the required V1 event types and nullable contextual
  fields (`zone_id`, `from_zone_id`, `to_zone_id`, `dwell_ms`, and
  `occupancy_after`) when applicable.

No shared contract or configuration file is modified by this branch.
