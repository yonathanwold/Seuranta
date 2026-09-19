# Seuranta positioning and spatial engine

This package owns the V1 localization pipeline from `SignalObservation` input
through filtered RSSI fingerprint matching, temporal smoothing, zone
classification, and debounced spatial events. It uses RSSI fingerprinting and
WKNN localization terminology; it does not implement or describe the system
as true triangulation.

## Pipeline

1. `ObservationBuffer` keeps sorted event-time windows per `(run_id,
   session_id)`, rejects duplicate IDs, bounds lateness, and removes stale
   samples.
2. `RssiFilter` aggregates each anchor with a rolling median and rejects
   median/MAD outliers. It reports missing anchors and sample age.
3. `WknnWifiFingerprintProvider` compares common anchors with versioned
   calibration points, applies a missing-anchor penalty, and uses inverse
   squared distance weights. The default minimum is three usable anchors.
4. `EmaSmoother` preserves the raw WKNN coordinate and separately calculates
   the smoothed coordinate. It resets for new sessions/runs, floor changes,
   and long gaps, and emits an impossible-movement diagnostic for implausible
   jumps.
5. `SpatialEngine` applies point-in-polygon classification, priority for
   overlap, confidence gates, entry/exit hysteresis, occupancy accounting,
   dwell lifecycle events, and silent-session cleanup.

No estimate is created when calibration or evidence is insufficient. The
batch response carries diagnostics instead of a fabricated coordinate.

## Internal API

Run the standard-library service from the repository root:

```text
python3 -m services.positioning.service --port 8080 \
  --fingerprints path/to/fingerprints.json \
  --zones path/to/zones.json
```

The service exposes:

* `POST /internal/v1/observation-batches`
* `GET /internal/v1/health`
* `GET /internal/v1/ready`

All JSON uses `schema_version: "1.0"` and snake_case. Position estimates and
events never serialize names, raw MAC addresses, payloads, or persistent
device identifiers.

## JSONL and synthetic execution

Process individual observation records or observation batches:

```text
python3 -m services.positioning.cli \
  --input observations.jsonl \
  --fingerprints fingerprints.json \
  --zones zones.json
```

Generate deterministic fixtures for movement, a missing-anchor interval, or an
RSSI outlier:

```text
python3 -m services.positioning.cli --scenario movement --emit-only > movement.jsonl
python3 -m services.positioning.cli --scenario outlier
```

The second command uses the bundled deterministic fingerprint fixture. Machine
results are JSONL on stdout; compact structured execution summaries are sent
to stderr.

## Calibration

Calibration files are local versioned artifacts and are never written into
shared service configuration. Define a point, collect its JSONL observations,
inspect quality, then run leave-one-point-out validation:

```text
python3 -m tools.calibration.cli define \
  --output calibration-plan.json \
  --point-id lobby-01 --x-m 2.0 --y-m 3.0 --floor-id floor-1

python3 -m tools.calibration.cli collect \
  --input lobby-01.jsonl --plan calibration-plan.json \
  --point-id lobby-01 --output fingerprints.json

python3 -m tools.calibration.cli quality --input fingerprints.json
python3 -m tools.calibration.cli validate --input fingerprints.json --update
```

The validation report includes median, mean, p90, and maximum error. A point
with fewer than the configured anchor coverage is rejected; excessive RSSI
spread is rejected unless `--allow-bad` is explicitly supplied for inspection.
