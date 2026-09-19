"""Frozen Seuranta V1 wire contracts.

The backend contract is deliberately implemented locally because the shared
contract package is not present in this checkout.  Every wire object includes
``schema_version`` and uses JSON snake_case names.  Validation happens at the
edge before anything is queued or transmitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

SCHEMA_VERSION = "1.0"
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


def utc_now() -> str:
    """Return a canonical RFC3339 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _uuid(value: str, name: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc
    return str(parsed)


def _timestamp(value: str, name: str) -> str:
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        raise ValueError(f"{name} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must be UTC")
    return value


def _text(value: str, name: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{name} must be a non-empty string of at most {max_length} characters")
    return value


def _enum(value: str, name: str, choices: Sequence[str]) -> str:
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}")
    return value


def _schema(data: Mapping[str, Any], expected: str = SCHEMA_VERSION) -> None:
    if data.get("schema_version") != expected:
        raise ValueError(f"schema_version must be {expected!r}")


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
    rssi_dbm: int
    channel: int
    source: str
    mode: str
    sequence_number: int
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _uuid(self.observation_id, "observation_id")
        _timestamp(self.observed_at, "observed_at")
        if not isinstance(self.timestamp_ms, int) or isinstance(self.timestamp_ms, bool) or self.timestamp_ms < 0:
            raise ValueError("timestamp_ms must be a non-negative integer")
        for name, value in (("run_id", self.run_id), ("deployment_id", self.deployment_id),
                            ("building_id", self.building_id), ("floor_id", self.floor_id),
                            ("anchor_id", self.anchor_id), ("session_id", self.session_id)):
            _text(value, name)
        if not isinstance(self.rssi_dbm, int) or isinstance(self.rssi_dbm, bool) or not -127 <= self.rssi_dbm <= 0:
            raise ValueError("rssi_dbm must be an integer from -127 through 0")
        if not isinstance(self.channel, int) or isinstance(self.channel, bool) or not 1 <= self.channel <= 196:
            raise ValueError("channel must be an integer from 1 through 196")
        _enum(self.source, "source", ("wifi", "ble", "mock", "WIFI_RSSI", "BLE_RSSI", "MOCK_RSSI", "SIMULATED_RSSI"))
        _enum(self.mode, "mode", ("LIVE", "REPLAY", "SIMULATION"))
        if not isinstance(self.sequence_number, int) or isinstance(self.sequence_number, bool) or self.sequence_number < 0:
            raise ValueError("sequence_number must be a non-negative integer")

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
    batch_id: str
    producer_id: str
    batch_sequence: int
    sent_at: str
    run_id: str
    deployment_id: str
    mode: str
    observations: tuple[SignalObservation, ...]
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _uuid(self.batch_id, "batch_id")
        _text(self.producer_id, "producer_id")
        if not isinstance(self.batch_sequence, int) or isinstance(self.batch_sequence, bool) or self.batch_sequence < 0:
            raise ValueError("batch_sequence must be a non-negative integer")
        _timestamp(self.sent_at, "sent_at")
        _text(self.run_id, "run_id")
        _text(self.deployment_id, "deployment_id")
        _enum(self.mode, "mode", ("LIVE", "REPLAY", "SIMULATION"))
        if not isinstance(self.observations, (tuple, list)) or not self.observations:
            raise ValueError("observations must be a non-empty array")
        if not all(isinstance(item, SignalObservation) for item in self.observations):
            raise ValueError("observations must contain SignalObservation values")
        if not isinstance(self.observations, tuple):
            object.__setattr__(self, "observations", tuple(self.observations))
        for observation in self.observations:
            if observation.run_id != self.run_id or observation.deployment_id != self.deployment_id:
                raise ValueError("batch observations must use the batch run and deployment")
            if observation.mode != self.mode:
                raise ValueError("batch observations must use the batch mode")

    @classmethod
    def from_observations(cls, producer_id: str, batch_sequence: int, run_id: str,
                          deployment_id: str, mode: str,
                          observations: Sequence[SignalObservation]) -> "ObservationBatch":
        from uuid import uuid4
        return cls(uuid4().hex, producer_id, batch_sequence, utc_now(), run_id,
                   deployment_id, mode, tuple(observations))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "producer_id": self.producer_id,
            "batch_sequence": self.batch_sequence,
            "sent_at": self.sent_at,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "mode": self.mode,
            "observations": [item.to_dict() for item in self.observations],
        }


@dataclass(frozen=True)
class Session:
    session_id: str
    run_id: str
    deployment_id: str
    mode: str
    status: str
    consent_scope: str
    started_at: str
    last_seen_at: str
    origin_anchor_id: str
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _text(self.session_id, "session_id")
        _text(self.run_id, "run_id")
        _text(self.deployment_id, "deployment_id")
        _enum(self.mode, "mode", ("LIVE", "REPLAY", "SIMULATION"))
        _enum(self.status, "status", ("ACTIVE", "SILENT", "ENDED"))
        _enum(self.consent_scope, "consent_scope", ("DEMO_NETWORK",))
        _timestamp(self.started_at, "started_at")
        _timestamp(self.last_seen_at, "last_seen_at")
        _text(self.origin_anchor_id, "origin_anchor_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "mode": self.mode,
            "status": self.status,
            "consent_scope": self.consent_scope,
            "started_at": self.started_at,
            "last_seen_at": self.last_seen_at,
            "origin_anchor_id": self.origin_anchor_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Session":
        _schema(data)
        return cls(
            session_id=data["session_id"], run_id=data["run_id"], deployment_id=data["deployment_id"],
            mode=data["mode"], status=data["status"], consent_scope=data["consent_scope"],
            started_at=data["started_at"], last_seen_at=data["last_seen_at"], origin_anchor_id=data["origin_anchor_id"],
        )


@dataclass(frozen=True)
class NodeHeartbeat:
    heartbeat_id: str
    emitted_at: str
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    anchor_id: str
    node_kind: str
    mode: str
    status: str
    agent_version: str
    uptime_s: int
    buffer_depth: int
    observations_sent_total: int
    last_observation_at: Optional[str]
    capture_ok: bool
    error_codes: tuple[str, ...]
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _uuid(self.heartbeat_id, "heartbeat_id")
        _timestamp(self.emitted_at, "emitted_at")
        for name, value in (("run_id", self.run_id), ("deployment_id", self.deployment_id),
                            ("building_id", self.building_id), ("floor_id", self.floor_id),
                            ("anchor_id", self.anchor_id), ("agent_version", self.agent_version)):
            _text(value, name)
        _enum(self.node_kind, "node_kind", ("REAL", "SIMULATED"))
        _enum(self.mode, "mode", ("LIVE", "REPLAY", "SIMULATION"))
        _enum(self.status, "status", ("ONLINE", "DEGRADED", "OFFLINE"))
        for name, value in (("uptime_s", self.uptime_s), ("buffer_depth", self.buffer_depth),
                            ("observations_sent_total", self.observations_sent_total)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.last_observation_at is not None:
            _timestamp(self.last_observation_at, "last_observation_at")
        if not isinstance(self.capture_ok, bool):
            raise ValueError("capture_ok must be boolean")
        if not isinstance(self.error_codes, (tuple, list)) or not all(isinstance(code, str) and code for code in self.error_codes):
            raise ValueError("error_codes must be an array of non-empty strings")
        if not isinstance(self.error_codes, tuple):
            object.__setattr__(self, "error_codes", tuple(self.error_codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "heartbeat_id": self.heartbeat_id,
            "emitted_at": self.emitted_at,
            "run_id": self.run_id,
            "deployment_id": self.deployment_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "anchor_id": self.anchor_id,
            "node_kind": self.node_kind,
            "mode": self.mode,
            "status": self.status,
            "agent_version": self.agent_version,
            "uptime_s": self.uptime_s,
            "buffer_depth": self.buffer_depth,
            "observations_sent_total": self.observations_sent_total,
            "last_observation_at": self.last_observation_at,
            "capture_ok": self.capture_ok,
            "error_codes": list(self.error_codes),
        }


def dumps(value: Any) -> str:
    """Serialize a V1 contract or mapping without changing field names."""

    payload = value.to_dict() if hasattr(value, "to_dict") else value
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
