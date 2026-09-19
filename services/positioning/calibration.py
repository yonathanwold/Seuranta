"""Versioned RSSI fingerprint data and calibration evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping

from .config import PositioningConfig
from .filtering import RssiFilter
from .models import Diagnostic, SCHEMA_VERSION, SignalObservation


class CalibrationError(ValueError):
    """Raised when a fingerprint point cannot safely be used."""


def _finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CalibrationError(f"{field_name} must be finite numeric")
    return float(value)


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class FingerprintPoint:
    point_id: str
    x_m: float
    y_m: float
    floor_id: str
    anchor_rssi_medians: Mapping[str, float]
    sample_counts: Mapping[str, int]
    rssi_spread: Mapping[str, float]
    capture_metadata: Mapping[str, Any] = field(default_factory=dict)
    quality_warnings: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _nonempty(self.point_id, "point_id")
        _nonempty(self.floor_id, "floor_id")
        _finite(self.x_m, "x_m")
        _finite(self.y_m, "y_m")
        if not self.anchor_rssi_medians:
            raise CalibrationError("fingerprint point must contain at least one anchor")
        if set(self.anchor_rssi_medians) != set(self.sample_counts):
            raise CalibrationError("sample_counts must cover exactly the fingerprint anchors")
        if not set(self.anchor_rssi_medians).issubset(set(self.rssi_spread)):
            raise CalibrationError("rssi_spread must cover every fingerprint anchor")
        for anchor_id, value in self.anchor_rssi_medians.items():
            _nonempty(anchor_id, "anchor_id")
            rssi = _finite(value, f"anchor_rssi_medians.{anchor_id}")
            if rssi < -150.0 or rssi > 10.0:
                raise CalibrationError(f"anchor_rssi_medians.{anchor_id} is outside the physical Wi-Fi range")
            count = self.sample_counts[anchor_id]
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise CalibrationError(f"sample_counts.{anchor_id} must be a positive integer")
            spread = _finite(self.rssi_spread[anchor_id], f"rssi_spread.{anchor_id}")
            if spread < 0.0:
                raise CalibrationError(f"rssi_spread.{anchor_id} cannot be negative")
        if not isinstance(self.capture_metadata, Mapping):
            raise CalibrationError("capture_metadata must be an object")
        if not isinstance(self.quality_warnings, tuple):
            raise CalibrationError("quality_warnings must be a tuple")

    @property
    def anchor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.anchor_rssi_medians))

    @property
    def mean_spread_db(self) -> float:
        return mean(self.rssi_spread.values()) if self.rssi_spread else 0.0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FingerprintPoint":
        if not isinstance(value, Mapping):
            raise CalibrationError("fingerprint point must be an object")
        schema_version = value.get("schema_version", SCHEMA_VERSION)
        if schema_version != SCHEMA_VERSION:
            raise CalibrationError(f"fingerprint point schema_version must be {SCHEMA_VERSION}")
        required = {
            "schema_version",
            "point_id",
            "x_m",
            "y_m",
            "floor_id",
            "anchor_rssi_medians",
            "sample_counts",
            "rssi_spread",
            "capture_metadata",
            "quality_warnings",
        }
        unknown = set(value) - required
        if unknown:
            raise CalibrationError(f"fingerprint point contains unsupported fields: {sorted(unknown)}")
        medians = value.get("anchor_rssi_medians")
        counts = value.get("sample_counts")
        spread = value.get("rssi_spread")
        if not isinstance(medians, Mapping) or not isinstance(counts, Mapping) or not isinstance(spread, Mapping):
            raise CalibrationError("fingerprint anchor fields must be objects")
        warnings = value.get("quality_warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise CalibrationError("quality_warnings must be an array of strings")
        metadata = value.get("capture_metadata", {})
        if not isinstance(metadata, Mapping):
            raise CalibrationError("capture_metadata must be an object")
        return cls(
            point_id=_nonempty(value.get("point_id"), "point_id"),
            x_m=_finite(value.get("x_m"), "x_m"),
            y_m=_finite(value.get("y_m"), "y_m"),
            floor_id=_nonempty(value.get("floor_id"), "floor_id"),
            anchor_rssi_medians={str(key): _finite(raw, f"anchor_rssi_medians.{key}") for key, raw in medians.items()},
            sample_counts={str(key): int(raw) for key, raw in counts.items()},
            rssi_spread={str(key): _finite(raw, f"rssi_spread.{key}") for key, raw in spread.items()},
            capture_metadata=dict(metadata),
            quality_warnings=tuple(warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "point_id": self.point_id,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "floor_id": self.floor_id,
            "anchor_rssi_medians": dict(sorted(self.anchor_rssi_medians.items())),
            "sample_counts": dict(sorted(self.sample_counts.items())),
            "rssi_spread": dict(sorted(self.rssi_spread.items())),
            "capture_metadata": dict(self.capture_metadata),
            "quality_warnings": list(self.quality_warnings),
        }


@dataclass(frozen=True)
class FingerprintSet:
    calibration_id: str
    points: tuple[FingerprintPoint, ...]
    calibration_version: str = "1.0"
    created_at: str = ""
    validation_metrics: Mapping[str, float] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _nonempty(self.calibration_id, "calibration_id")
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        if not self.points:
            raise CalibrationError("fingerprint set must contain at least one point")
        point_ids = [point.point_id for point in self.points]
        if len(point_ids) != len(set(point_ids)):
            raise CalibrationError("fingerprint point_id values must be unique")
        for key, value in self.validation_metrics.items():
            _finite(value, f"validation_metrics.{key}")

    @property
    def anchor_ids(self) -> tuple[str, ...]:
        return tuple(sorted({anchor_id for point in self.points for anchor_id in point.anchor_ids}))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FingerprintSet":
        if not isinstance(value, Mapping):
            raise CalibrationError("fingerprint set must be an object")
        schema_version = value.get("schema_version", SCHEMA_VERSION)
        if schema_version != SCHEMA_VERSION:
            raise CalibrationError(f"fingerprint set schema_version must be {SCHEMA_VERSION}")
        points = value.get("points")
        if not isinstance(points, list):
            raise CalibrationError("fingerprint set points must be an array")
        metrics = value.get("validation_metrics", {})
        if not isinstance(metrics, Mapping):
            raise CalibrationError("validation_metrics must be an object")
        return cls(
            calibration_id=_nonempty(value.get("calibration_id"), "calibration_id"),
            calibration_version=_nonempty(value.get("calibration_version", "1.0"), "calibration_version"),
            created_at=_nonempty(value.get("created_at"), "created_at"),
            points=tuple(FingerprintPoint.from_dict(item) for item in points),
            validation_metrics={str(key): _finite(raw, f"validation_metrics.{key}") for key, raw in metrics.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "calibration_version": self.calibration_version,
            "calibration_id": self.calibration_id,
            "created_at": self.created_at,
            "points": [point.to_dict() for point in self.points],
            "validation_metrics": dict(sorted(self.validation_metrics.items())),
        }

    @classmethod
    def load(cls, path: str | Path) -> "FingerprintSet":
        file_path = Path(path)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CalibrationError(f"unable to load calibration file: {file_path}") from exc
        except json.JSONDecodeError as exc:
            raise CalibrationError(f"calibration file is not valid JSON: {file_path}") from exc
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_fingerprint_point(
    *,
    point_id: str,
    x_m: float,
    y_m: float,
    floor_id: str,
    observations: Iterable[SignalObservation],
    config: PositioningConfig | None = None,
    min_anchor_count: int | None = None,
    min_samples_per_anchor: int | None = None,
    max_spread_db: float = 15.0,
    capture_metadata: Mapping[str, Any] | None = None,
    reject_bad: bool = True,
) -> FingerprintPoint:
    """Aggregate one calibration location and reject unsafe coverage."""

    effective_config = config or PositioningConfig()
    samples = list(observations)
    if not samples:
        raise CalibrationError("calibration point contains no observations")
    filtered = RssiFilter(effective_config).filter(samples)
    min_anchors = min_anchor_count or effective_config.position_min_anchors
    min_samples = min_samples_per_anchor or effective_config.min_samples_per_anchor
    warnings: list[str] = []
    medians: dict[str, float] = {}
    counts: dict[str, int] = {}
    spreads: dict[str, float] = {}
    for anchor_id, aggregate in filtered.anchors.items():
        if aggregate.sample_count < min_samples:
            warnings.append(f"{anchor_id}:sample_count<{min_samples}")
            continue
        medians[anchor_id] = aggregate.rssi_dbm
        counts[anchor_id] = aggregate.sample_count
        spreads[anchor_id] = aggregate.spread_db
        if aggregate.spread_db > max_spread_db:
            warnings.append(f"{anchor_id}:spread>{max_spread_db:g}dB")
    if len(medians) < min_anchors:
        raise CalibrationError(
            f"calibration point has insufficient anchor coverage: {len(medians)} < {min_anchors}"
        )
    if any(item.endswith(f">{max_spread_db:g}dB") for item in warnings) and reject_bad:
        raise CalibrationError("calibration point has excessive RSSI spread")
    if len(samples) < len(medians) * min_samples:
        warnings.append("total_sample_count_below_recommended_minimum")
    metadata = dict(capture_metadata or {})
    metadata.setdefault("observation_count", len(samples))
    metadata.setdefault("anchor_count", len(medians))
    return FingerprintPoint(
        point_id=point_id,
        x_m=float(x_m),
        y_m=float(y_m),
        floor_id=floor_id,
        anchor_rssi_medians=medians,
        sample_counts=counts,
        rssi_spread=spreads,
        capture_metadata=metadata,
        quality_warnings=tuple(warnings),
    )


def quality_report(fingerprint_set: FingerprintSet) -> dict[str, Any]:
    """Return a JSON-safe quality report for operators."""

    point_reports: list[dict[str, Any]] = []
    for point in fingerprint_set.points:
        point_reports.append(
            {
                "point_id": point.point_id,
                "floor_id": point.floor_id,
                "anchor_count": len(point.anchor_ids),
                "anchor_ids": list(point.anchor_ids),
                "sample_counts": dict(point.sample_counts),
                "rssi_spread_db": dict(point.rssi_spread),
                "mean_spread_db": point.mean_spread_db,
                "quality_warnings": list(point.quality_warnings),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": fingerprint_set.calibration_id,
        "calibration_version": fingerprint_set.calibration_version,
        "point_count": len(fingerprint_set.points),
        "anchor_ids": list(fingerprint_set.anchor_ids),
        "validation_metrics": dict(fingerprint_set.validation_metrics),
        "points": point_reports,
    }


def leave_one_point_out_validation(
    fingerprint_set: FingerprintSet,
    *,
    config: PositioningConfig | None = None,
) -> dict[str, Any]:
    """Evaluate each point against all other points on the same floor."""

    from .provider import WknnWifiFingerprintProvider
    from .filtering import FilteredAnchor

    effective_config = config or PositioningConfig()
    errors: list[float] = []
    point_results: list[dict[str, Any]] = []
    for target in fingerprint_set.points:
        training = tuple(
            point
            for point in fingerprint_set.points
            if point.point_id != target.point_id and point.floor_id == target.floor_id
        )
        if not training:
            point_results.append(
                {"point_id": target.point_id, "status": "insufficient_training_points"}
            )
            continue
        provider = WknnWifiFingerprintProvider(training, config=effective_config)
        observed = {
            anchor_id: FilteredAnchor(
                anchor_id=anchor_id,
                rssi_dbm=rssi,
                sample_count=target.sample_counts[anchor_id],
                raw_sample_count=target.sample_counts[anchor_id],
                rejected_sample_count=0,
                spread_db=target.rssi_spread.get(anchor_id, 0.0),
                oldest_timestamp_ms=0,
                newest_timestamp_ms=0,
                age_ms=0,
            )
            for anchor_id, rssi in target.anchor_rssi_medians.items()
        }
        estimate = provider.estimate(observed, floor_id=target.floor_id)
        if estimate is None:
            point_results.append(
                {"point_id": target.point_id, "status": "no_estimate"}
            )
            continue
        error = math.hypot(estimate.x_m - target.x_m, estimate.y_m - target.y_m)
        errors.append(error)
        point_results.append(
            {
                "point_id": target.point_id,
                "status": "validated",
                "estimated_x_m": estimate.x_m,
                "estimated_y_m": estimate.y_m,
                "error_m": error,
                "confidence": estimate.confidence,
            }
        )
    if not errors:
        metrics = {"validated_point_count": 0.0}
    else:
        ordered = sorted(errors)
        p90_index = min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)
        metrics = {
            "validated_point_count": float(len(errors)),
            "median_error_m": float(median(errors)),
            "mean_error_m": float(mean(errors)),
            "p90_error_m": float(ordered[p90_index]),
            "maximum_error_m": float(max(errors)),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": fingerprint_set.calibration_id,
        "metrics": metrics,
        "points": point_results,
    }


def update_validation_metrics(
    fingerprint_set: FingerprintSet,
    validation: Mapping[str, Any],
) -> FingerprintSet:
    metrics = validation.get("metrics", {})
    if not isinstance(metrics, Mapping):
        raise CalibrationError("validation result metrics must be an object")
    return FingerprintSet(
        calibration_id=fingerprint_set.calibration_id,
        points=fingerprint_set.points,
        calibration_version=fingerprint_set.calibration_version,
        created_at=fingerprint_set.created_at,
        validation_metrics={str(key): float(value) for key, value in metrics.items()},
    )
