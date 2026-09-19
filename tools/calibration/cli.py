"""CLI for defining calibration points and producing evaluated fingerprints.

Calibration files are intentionally local artifacts under a caller-selected
path.  This tool never edits shared service configuration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from services.positioning.calibration import (
    CalibrationError,
    FingerprintPoint,
    FingerprintSet,
    build_fingerprint_point,
    leave_one_point_out_validation,
    quality_report,
    update_validation_metrics,
)
from services.positioning.models import ObservationBatch, SignalObservation, SCHEMA_VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_jsonl(path: str | Path) -> list[SignalObservation]:
    stream = sys.stdin if str(path) == "-" else Path(path).open("r", encoding="utf-8")
    observations: list[SignalObservation] = []
    try:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CalibrationError(f"invalid JSONL at line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise CalibrationError(f"JSONL line {line_number} must be an object")
            if "observations" in value:
                observations.extend(ObservationBatch.from_dict(value).observations)
            else:
                observations.append(SignalObservation.from_dict(value))
    finally:
        if stream is not sys.stdin:
            stream.close()
    return observations


def _read_plan(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"unable to read calibration plan: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise CalibrationError("calibration plan must be a V1 object")
    points = value.get("points")
    if not isinstance(points, list):
        raise CalibrationError("calibration plan points must be an array")
    return value


def _write_plan(path: str | Path, value: MappingLike) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


MappingLike = dict[str, Any]


def _point_definition(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "point_id": args.point_id,
        "x_m": float(args.x_m),
        "y_m": float(args.y_m),
        "floor_id": args.floor_id,
        "capture_metadata": json.loads(args.metadata) if args.metadata else {},
    }


def command_define(args: argparse.Namespace) -> int:
    if args.metadata:
        metadata = json.loads(args.metadata)
        if not isinstance(metadata, dict):
            raise CalibrationError("--metadata must be a JSON object")
    else:
        metadata = {}
    point = _point_definition(args)
    point["capture_metadata"] = metadata
    if Path(args.output).exists():
        plan = _read_plan(args.output)
    else:
        plan = {
            "schema_version": SCHEMA_VERSION,
            "calibration_version": "1.0",
            "calibration_id": args.calibration_id,
            "created_at": _now_iso(),
            "points": [],
        }
    plan["calibration_id"] = args.calibration_id or plan.get("calibration_id") or "calibration-v1"
    points = [item for item in plan["points"] if item.get("point_id") != args.point_id]
    points.append(point)
    plan["points"] = sorted(points, key=lambda item: item["point_id"])
    _write_plan(args.output, plan)
    print(json.dumps({"status": "defined", "point_id": args.point_id, "plan": str(args.output)}))
    return 0


def _definition_from_plan(plan: dict[str, Any], point_id: str) -> dict[str, Any]:
    for point in plan["points"]:
        if isinstance(point, dict) and point.get("point_id") == point_id:
            return point
    raise CalibrationError(f"point_id not found in calibration plan: {point_id}")


def _load_or_create_fingerprint_set(path: str | Path, calibration_id: str) -> FingerprintSet | None:
    if not Path(path).exists():
        return None
    return FingerprintSet.load(path)


def command_collect(args: argparse.Namespace) -> int:
    plan = _read_plan(args.plan) if args.plan else None
    if plan is not None:
        definition = _definition_from_plan(plan, args.point_id)
        x_m, y_m, floor_id = definition["x_m"], definition["y_m"], definition["floor_id"]
        metadata = definition.get("capture_metadata", {})
        calibration_id = plan.get("calibration_id", args.calibration_id)
    else:
        if args.x_m is None or args.y_m is None or args.floor_id is None:
            raise CalibrationError("collect requires --plan or --x-m, --y-m, and --floor-id")
        x_m, y_m, floor_id = args.x_m, args.y_m, args.floor_id
        metadata = {}
        calibration_id = args.calibration_id
    observations = _read_jsonl(args.input)
    point = build_fingerprint_point(
        point_id=args.point_id,
        x_m=x_m,
        y_m=y_m,
        floor_id=floor_id,
        observations=observations,
        min_anchor_count=args.min_anchors,
        min_samples_per_anchor=args.min_samples,
        max_spread_db=args.max_spread_db,
        capture_metadata={**metadata, "input": str(args.input)},
        reject_bad=not args.allow_bad,
    )
    existing = _load_or_create_fingerprint_set(args.output, calibration_id)
    if existing is None:
        result = FingerprintSet(calibration_id=calibration_id, points=(point,))
    else:
        points = [item for item in existing.points if item.point_id != point.point_id]
        points.append(point)
        result = FingerprintSet(
            calibration_id=existing.calibration_id,
            points=tuple(sorted(points, key=lambda item: item.point_id)),
            calibration_version=existing.calibration_version,
            created_at=existing.created_at,
            validation_metrics=existing.validation_metrics,
        )
    result.save(args.output)
    print(json.dumps(quality_report(result), indent=2, sort_keys=True))
    return 0


def command_quality(args: argparse.Namespace) -> int:
    result = FingerprintSet.load(args.input)
    print(json.dumps(quality_report(result), indent=2, sort_keys=True))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    result = FingerprintSet.load(args.input)
    validation = leave_one_point_out_validation(result)
    if args.update:
        result = update_validation_metrics(result, validation)
        result.save(args.input)
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0


def command_load(args: argparse.Namespace) -> int:
    result = FingerprintSet.load(args.input)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seuranta RSSI calibration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    define = subparsers.add_parser("define", help="define or update a calibration point in a local plan")
    define.add_argument("--output", required=True)
    define.add_argument("--point-id", required=True)
    define.add_argument("--x-m", type=float, required=True)
    define.add_argument("--y-m", type=float, required=True)
    define.add_argument("--floor-id", required=True)
    define.add_argument("--calibration-id", default="calibration-v1")
    define.add_argument("--metadata", help="safe capture metadata as a JSON object")
    define.set_defaults(handler=command_define)

    collect = subparsers.add_parser("collect", help="aggregate observations into a versioned fingerprint point")
    collect.add_argument("--input", required=True, help="observation JSONL file or -")
    collect.add_argument("--output", required=True, help="versioned fingerprint JSON file")
    collect.add_argument("--point-id", required=True)
    collect.add_argument("--plan")
    collect.add_argument("--x-m", type=float)
    collect.add_argument("--y-m", type=float)
    collect.add_argument("--floor-id")
    collect.add_argument("--calibration-id", default="calibration-v1")
    collect.add_argument("--min-anchors", type=int, default=3)
    collect.add_argument("--min-samples", type=int, default=1)
    collect.add_argument("--max-spread-db", type=float, default=15.0)
    collect.add_argument("--allow-bad", action="store_true", help="keep quality warnings instead of rejecting high spread")
    collect.set_defaults(handler=command_collect)

    quality = subparsers.add_parser("quality", help="print calibration coverage and RSSI quality")
    quality.add_argument("--input", required=True)
    quality.set_defaults(handler=command_quality)

    validate = subparsers.add_parser("validate", help="run leave-one-point-out validation")
    validate.add_argument("--input", required=True)
    validate.add_argument("--update", action="store_true", help="save validation metrics into the fingerprint file")
    validate.set_defaults(handler=command_validate)

    load = subparsers.add_parser("load", help="load and print a versioned fingerprint file")
    load.add_argument("--input", required=True)
    load.set_defaults(handler=command_load)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (CalibrationError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
