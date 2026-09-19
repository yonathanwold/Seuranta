"""Local compatibility models for the frozen Seuranta V1 contract.

The models are deliberately strict at the HTTP boundary.  The positioning
engine never receives arbitrary dictionaries and output serializers only emit
the fields allowed by the V1 contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"

_FORBIDDEN_KEY_PARTS = (
    "mac",
    "payload",
    "persistent",
    "device_name",
    "person_name",
    "user_name",
)

EVENT_TYPES = frozenset(
    {
        "ZONE_ENTERED",
        "ZONE_EXITED",
        "ROOM_ENTERED",
        "ROOM_EXITED",
        "DWELL_STARTED",
        "DWELL_UPDATED",
        "DWELL_ENDED",
        "OCCUPANCY_CHANGE",
        "SESSION_STARTED",
        "SESSION_ENDED",
        "POSITION_UPDATED",
        "ANOMALY",
    }
)


def timestamp_to_iso(timestamp_ms: int | float) -> str:
    """Return a stable UTC ISO-8601 timestamp for a millisecond epoch value."""

    value = float(timestamp_ms)
    if not math.isfinite(value):
        raise ValueError("timestamp_ms must be finite")
    instant = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp_ms(value: Any, *, field_name: str = "timestamp") -> int:
    """Parse either an epoch-millisecond value or an ISO-8601 timestamp."""

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a timestamp")
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field_name} must be finite")
        return int(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an epoch millisecond or ISO timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _require_string(data: Mapping[str, Any], name: str, *, allow_empty: bool = False) -> str:
    value = data.get(name)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_number(data: Mapping[str, Any], name: str) -> float:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _require_int(data: Mapping[str, Any], name: str) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_string(data: Mapping[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    return value


def _check_schema(data: Mapping[str, Any], context: str) -> None:
    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"{context}.schema_version must be {SCHEMA_VERSION}")


def _check_allowed(data: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unsupported fields: {', '.join(unknown)}")


def _assert_safe_key(key: str, context: str) -> None:
    normalized = key.casefold()
    if normalized == "name":
        # Zone.name is explicitly part of the V1 Zone contract.  Attributes
        # and events are checked separately and never permit this key.
        return
    if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
        raise ValueError(f"{context} contains a forbidden identifier or payload field")


def assert_safe_attributes(value: Any, *, context: str = "attributes") -> None:
    """Reject raw device identity, names, payloads, and persistent IDs."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{context} keys must be strings")
            _assert_safe_key(key, context)
            assert_safe_attributes(child, context=f"{context}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_safe_attributes(child, context=f"{context}[{index}]")


@dataclass(frozen=True)
class SignalObservation:
    observation_id: str
    observed_at: str
    timestamp_ms: int
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    anchor_id: str
    session_id: str
    rssi_dbm: float
    channel: int | str
    source: str
    mode: str
    sequence_number: int
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SignalObservation":
        data = _require_mapping(value, "observation")
        allowed = {
            "schema_version",
            "observation_id",
            "observed_at",
            "timestamp_ms",
            "run_id",
            "deployment_id",
            "building_id",
            "floor_id",
            "anchor_id",
            "session_id",
            "rssi_dbm",
            "channel",
            "source",
            "mode",
            "sequence_number",
        }
        _check_allowed(data, allowed, "observation")
        _check_schema(data, "observation")
        channel = data.get("channel")
        if isinstance(channel, bool) or not isinstance(channel, (int, str)):
            raise ValueError("channel must be an integer or string")
        timestamp_ms = _require_int(data, "timestamp_ms")
        observed_at = _require_string(data, "observed_at")
        # Validate the human-readable timestamp as well as retaining the exact
        # wire value supplied by the collector.
        parse_timestamp_ms(observed_at, field_name="observed_at")
        rssi = _require_number(data, "rssi_dbm")
        if rssi < -150.0 or rssi > 10.0:
            raise ValueError("rssi_dbm is outside the physical Wi-Fi range")
        return cls(
            observation_id=_require_string(data, "observation_id"),
            observed_at=observed_at,
            timestamp_ms=timestamp_ms,
            run_id=_require_string(data, "run_id"),
            deployment_id=_require_string(data, "deployment_id"),
            building_id=_require_string(data, "building_id"),
            floor_id=_require_string(data, "floor_id"),
            anchor_id=_require_string(data, "anchor_id"),
            session_id=_require_string(data, "session_id"),
            rssi_dbm=rssi,
            channel=channel,
            source=_require_string(data, "source"),
            mode=_require_string(data, "mode"),
            sequence_number=_require_int(data, "sequence_number"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "observed_at": self.observed_at,
            "timestamp_ms": self.timestamp_ms,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "anchor_id": self.anchor_id,
            "session_id": self.session_id,
            "rssi_dbm": self.rssi_dbm,
            "channel": self.channel,
            "source": self.source,
            "mode": self.mode,
            "sequence_number": self.sequence_number,
        }


@dataclass(frozen=True)
class ObservationBatch:
    observations: tuple[SignalObservation, ...]
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObservationBatch":
        data = _require_mapping(value, "observation_batch")
        _check_allowed(data, {"schema_version", "observations"}, "observation_batch")
        _check_schema(data, "observation_batch")
        raw_observations = data.get("observations")
        if not isinstance(raw_observations, Sequence) or isinstance(raw_observations, (str, bytes)):
            raise ValueError("observations must be an array")
        observations = tuple(SignalObservation.from_dict(item) for item in raw_observations)
        return cls(observations=observations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observations": [observation.to_dict() for observation in self.observations],
        }


@dataclass(frozen=True)
class PositionEstimate:
    position_id: str
    calculated_at: str
    window_start: str
    window_end: str
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    session_id: str
    raw_x_m: float
    raw_y_m: float
    x_m: float
    y_m: float
    zone_id: str | None
    confidence: float
    accuracy_radius_m: float
    position_method: str
    smoothing_method: str
    anchors_used: tuple[str, ...]
    observation_count: int
    mode: str
    sequence_number: int
    is_outside_map: bool
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PositionEstimate":
        data = _require_mapping(value, "position_estimate")
        allowed = {
            "schema_version",
            "position_id",
            "calculated_at",
            "window_start",
            "window_end",
            "run_id",
            "deployment_id",
            "building_id",
            "floor_id",
            "session_id",
            "raw_x_m",
            "raw_y_m",
            "x_m",
            "y_m",
            "zone_id",
            "confidence",
            "accuracy_radius_m",
            "position_method",
            "smoothing_method",
            "anchors_used",
            "observation_count",
            "mode",
            "sequence_number",
            "is_outside_map",
        }
        _check_allowed(data, allowed, "position_estimate")
        _check_schema(data, "position_estimate")
        anchors = data.get("anchors_used")
        if not isinstance(anchors, Sequence) or isinstance(anchors, (str, bytes)):
            raise ValueError("anchors_used must be an array")
        parsed_anchors = tuple(item for item in anchors if isinstance(item, str) and item)
        if len(parsed_anchors) != len(anchors):
            raise ValueError("anchors_used must contain non-empty strings")
        confidence = _require_number(data, "confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        radius = _require_number(data, "accuracy_radius_m")
        if radius < 0.0:
            raise ValueError("accuracy_radius_m cannot be negative")
        for timestamp_field in ("calculated_at", "window_start", "window_end"):
            parse_timestamp_ms(data.get(timestamp_field), field_name=timestamp_field)
        return cls(
            position_id=_require_string(data, "position_id"),
            calculated_at=_require_string(data, "calculated_at"),
            window_start=_require_string(data, "window_start"),
            window_end=_require_string(data, "window_end"),
            run_id=_require_string(data, "run_id"),
            deployment_id=_require_string(data, "deployment_id"),
            building_id=_require_string(data, "building_id"),
            floor_id=_require_string(data, "floor_id"),
            session_id=_require_string(data, "session_id"),
            raw_x_m=_require_number(data, "raw_x_m"),
            raw_y_m=_require_number(data, "raw_y_m"),
            x_m=_require_number(data, "x_m"),
            y_m=_require_number(data, "y_m"),
            zone_id=_optional_string(data, "zone_id"),
            confidence=confidence,
            accuracy_radius_m=radius,
            position_method=_require_string(data, "position_method"),
            smoothing_method=_require_string(data, "smoothing_method"),
            anchors_used=parsed_anchors,
            observation_count=_require_int(data, "observation_count"),
            mode=_require_string(data, "mode"),
            sequence_number=_require_int(data, "sequence_number"),
            is_outside_map=data.get("is_outside_map") if isinstance(data.get("is_outside_map"), bool) else False,
        )

    def to_dict(self) -> dict[str, Any]:
        output = {
            "schema_version": self.schema_version,
            "position_id": self.position_id,
            "calculated_at": self.calculated_at,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "session_id": self.session_id,
            "raw_x_m": self.raw_x_m,
            "raw_y_m": self.raw_y_m,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "zone_id": self.zone_id,
            "confidence": self.confidence,
            "accuracy_radius_m": self.accuracy_radius_m,
            "position_method": self.position_method,
            "smoothing_method": self.smoothing_method,
            "anchors_used": list(self.anchors_used),
            "observation_count": self.observation_count,
            "mode": self.mode,
            "sequence_number": self.sequence_number,
            "is_outside_map": self.is_outside_map,
        }
        assert_safe_attributes(output, context="position_estimate")
        return output


def _parse_polygon(value: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("polygon must be an array")
    points: list[tuple[float, float]] = []
    for point in value:
        if isinstance(point, Mapping):
            x = point.get("x_m")
            y = point.get("y_m")
        elif isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) == 2:
            x, y = point
        else:
            raise ValueError("polygon points must be [x_m, y_m] pairs")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError("polygon coordinates must be numeric")
        x_value, y_value = float(x), float(y)
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ValueError("polygon coordinates must be finite")
        points.append((x_value, y_value))
    if len(points) < 3:
        raise ValueError("polygon must contain at least three points")
    return tuple(points)


@dataclass(frozen=True)
class Zone:
    zone_id: str
    building_id: str
    floor_id: str
    name: str
    kind: str
    polygon: tuple[tuple[float, float], ...]
    priority: int
    entry_confirm_ms: int
    exit_confirm_ms: int
    min_confidence: float
    enabled: bool
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Zone":
        data = _require_mapping(value, "zone")
        allowed = {
            "schema_version",
            "zone_id",
            "building_id",
            "floor_id",
            "name",
            "kind",
            "polygon",
            "priority",
            "entry_confirm_ms",
            "exit_confirm_ms",
            "min_confidence",
            "enabled",
        }
        _check_allowed(data, allowed, "zone")
        _check_schema(data, "zone")
        min_confidence = _require_number(data, "min_confidence")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        entry_confirm_ms = _require_int(data, "entry_confirm_ms")
        exit_confirm_ms = _require_int(data, "exit_confirm_ms")
        if entry_confirm_ms < 0 or exit_confirm_ms < 0:
            raise ValueError("zone confirmation durations cannot be negative")
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        return cls(
            zone_id=_require_string(data, "zone_id"),
            building_id=_require_string(data, "building_id"),
            floor_id=_require_string(data, "floor_id"),
            name=_require_string(data, "name"),
            kind=_require_string(data, "kind"),
            polygon=_parse_polygon(data.get("polygon")),
            priority=_require_int(data, "priority"),
            entry_confirm_ms=entry_confirm_ms,
            exit_confirm_ms=exit_confirm_ms,
            min_confidence=min_confidence,
            enabled=enabled,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "zone_id": self.zone_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "name": self.name,
            "kind": self.kind,
            "polygon": [[x, y] for x, y in self.polygon],
            "priority": self.priority,
            "entry_confirm_ms": self.entry_confirm_ms,
            "exit_confirm_ms": self.exit_confirm_ms,
            "min_confidence": self.min_confidence,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class SpatialEvent:
    event_id: str
    event_type: str
    occurred_at: str
    emitted_at: str
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    mode: str
    event_sequence: int
    session_id: str | None = None
    zone_id: str | None = None
    from_zone_id: str | None = None
    to_zone_id: str | None = None
    position_id: str | None = None
    dwell_ms: int | None = None
    occupancy_after: int | None = None
    confidence: float | None = None
    attributes: Mapping[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event_type: {self.event_type}")
        for field_name in ("occurred_at", "emitted_at"):
            parse_timestamp_ms(getattr(self, field_name), field_name=field_name)
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("event confidence must be between 0 and 1")
        if self.dwell_ms is not None and self.dwell_ms < 0:
            raise ValueError("dwell_ms cannot be negative")
        if self.occupancy_after is not None and self.occupancy_after < 0:
            raise ValueError("occupancy_after cannot be negative")
        assert_safe_attributes(self.attributes or {}, context="event.attributes")

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "emitted_at": self.emitted_at,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "mode": self.mode,
            "event_sequence": self.event_sequence,
        }
        optional = {
            "session_id": self.session_id,
            "zone_id": self.zone_id,
            "from_zone_id": self.from_zone_id,
            "to_zone_id": self.to_zone_id,
            "position_id": self.position_id,
            "dwell_ms": self.dwell_ms,
            "occupancy_after": self.occupancy_after,
            "confidence": self.confidence,
            "attributes": dict(self.attributes) if self.attributes is not None else None,
        }
        output.update({key: value for key, value in optional.items() if value is not None})
        assert_safe_attributes(output, context="spatial_event")
        return output


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "warning"
    run_id: str | None = None
    session_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("diagnostic severity must be info, warning, or error")
        assert_safe_attributes(self.details, context="diagnostic.details")

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "schema_version": self.schema_version,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "details": dict(self.details),
        }
        if self.run_id is not None:
            output["run_id"] = self.run_id
        if self.session_id is not None:
            output["session_id"] = self.session_id
        assert_safe_attributes(output, context="diagnostic")
        return output
