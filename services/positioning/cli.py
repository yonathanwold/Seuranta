"""JSONL and deterministic synthetic execution CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from .calibration import CalibrationError, FingerprintSet
from .engine import PositioningEngine
from .models import ObservationBatch, SignalObservation
from .service import load_zones
from .synthetic import generate_scenario, synthetic_fingerprint_set


def _read_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    stream = sys.stdin if str(path) == "-" else Path(path).open("r", encoding="utf-8")
    try:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            yield value
    finally:
        if stream is not sys.stdin:
            stream.close()


def _batch_from_line(value: dict[str, Any]) -> ObservationBatch:
    if "observations" in value:
        return ObservationBatch.from_dict(value)
    return ObservationBatch(observations=(SignalObservation.from_dict(value),))


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Seuranta positioning JSONL")
    parser.add_argument("--input", default="-", help="JSONL observations or - for stdin")
    parser.add_argument("--fingerprints", help="versioned fingerprint JSON file")
    parser.add_argument("--zones", help="zone JSON file")
    parser.add_argument("--scenario", choices=("movement", "missing-anchor", "outlier"))
    parser.add_argument("--emit-only", action="store_true", help="emit synthetic observations instead of processing them")
    args = parser.parse_args()
    try:
        if args.scenario:
            scenario = generate_scenario(args.scenario)
            if args.emit_only:
                for observation in scenario.observations:
                    print(json.dumps(observation.to_dict(), sort_keys=True))
                return 0
            batches: Iterable[ObservationBatch] = (
                ObservationBatch(observations=tuple(scenario.observations)),
            )
            fingerprints = FingerprintSet.load(args.fingerprints) if args.fingerprints else synthetic_fingerprint_set()
        else:
            batches = (_batch_from_line(value) for value in _read_jsonl(args.input))
            fingerprints = FingerprintSet.load(args.fingerprints) if args.fingerprints else None
        zones = load_zones(args.zones) if args.zones else ()
        engine = PositioningEngine(fingerprints=fingerprints, zones=zones)
        for batch in batches:
            result = engine.process_batch(batch)
            print(json.dumps(result.to_dict(), sort_keys=True))
            print(
                json.dumps(
                    {
                        "level": "info",
                        "component": "positioning",
                        "position_count": len(result.position_estimates),
                        "event_count": len(result.spatial_events),
                        "diagnostic_count": len(result.diagnostics),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
    except (ValueError, OSError, CalibrationError) as exc:
        print(json.dumps({"level": "error", "component": "positioning", "message": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
