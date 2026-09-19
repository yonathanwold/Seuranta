"""V1 wire contracts.

The models intentionally contain only anonymous session telemetry.  In
particular, raw MAC addresses, packet payloads, names, and persistent personal
identifiers are not represented here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Mode(StrEnum):
    REAL = "real"
    SIMULATED = "simulated"


class NodeStatus(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class SignalObservation(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    observed_at: datetime
    timestamp_ms: int | None = None
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    anchor_id: str
    session_id: str
    rssi_dbm: int = Field(ge=-127, le=0)
    channel: int = Field(ge=1, le=233)
    source: str = "wifi"
    mode: Mode = Mode.REAL
    sequence_number: int = Field(ge=0)

    @field_validator("observed_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ObservationBatch(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    batch_id: str = Field(default_factory=lambda: str(uuid4()))
    producer_id: str
    batch_sequence: int = Field(ge=0)
    sent_at: datetime = Field(default_factory=utc_now)
    run_id: str
    deployment_id: str
    mode: Mode = Mode.REAL
    observations: list[SignalObservation] = Field(min_length=1)


class PositionEstimate(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    position_id: str = Field(default_factory=lambda: str(uuid4()))
    calculated_at: datetime = Field(default_factory=utc_now)
    window_start: datetime
    window_end: datetime
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    session_id: str
    raw_x_m: float
    raw_y_m: float
    x_m: float
    y_m: float
    zone_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    accuracy_radius_m: float = Field(ge=0)
    position_method: str
    smoothing_method: str
    anchors_used: list[str] = Field(default_factory=list)
    observation_count: int = Field(ge=0)
    mode: Mode = Mode.REAL
    sequence_number: int = Field(ge=0)
    is_outside_map: bool = False


class SpatialEvent(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    occurred_at: datetime
    emitted_at: datetime = Field(default_factory=utc_now)
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    mode: Mode = Mode.REAL
    session_id: str | None = None
    zone_id: str | None = None
    position_id: str | None = None
    dwell_ms: int | None = Field(default=None, ge=0)
    occupancy_after: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    event_sequence: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeHeartbeat(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    heartbeat_id: str = Field(default_factory=lambda: str(uuid4()))
    emitted_at: datetime = Field(default_factory=utc_now)
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    anchor_id: str
    node_kind: str
    mode: Mode = Mode.REAL
    status: NodeStatus
    agent_version: str
    uptime_s: int = Field(ge=0)
    buffer_depth: int = Field(ge=0)
    observations_sent_total: int = Field(ge=0)
    last_observation_at: datetime | None = None
    capture_ok: bool
    error_codes: list[str] = Field(default_factory=list)


class Anomaly(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    anomaly_id: str = Field(default_factory=lambda: str(uuid4()))
    anomaly_type: str
    status: Literal["open", "resolved"] = "open"
    severity: Literal["info", "warning", "critical"]
    detected_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    run_id: str
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None
    mode: Mode
    session_id: str | None = None
    anchor_id: str | None = None
    zone_id: str | None = None
    title: str
    description: str
    observed_value: float | None = None
    threshold: float | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_event_ids: list[str] = Field(default_factory=list)
    detector: str


class BuildingState(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    state_revision: int
    generated_at: datetime = Field(default_factory=utc_now)
    deployment_id: str
    building_id: str
    floor_id: str
    run_id: str
    mode: Mode
    counts: dict[str, int] = Field(default_factory=dict)
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    zones: list[dict[str, Any]] = Field(default_factory=list)
    zone_metrics: list[dict[str, Any]] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    is_partial: bool = False


class IntelligenceSummary(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    summary_id: str = Field(default_factory=lambda: str(uuid4()))
    generated_at: datetime = Field(default_factory=utc_now)
    window_start: datetime
    window_end: datetime
    data_through: datetime | None = None
    run_id: str
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None
    mode: Mode
    query: str
    answer: str
    facts: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    anomaly_ids: list[str] = Field(default_factory=list)
    generated_by: str = "deterministic-local"
    grounded: bool = True
    model_endpoint: str | None = None


class SessionCreate(ContractModel):
    session_id: str
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    mode: Mode = Mode.REAL
    started_at: datetime = Field(default_factory=utc_now)


class SessionEnd(ContractModel):
    ended_at: datetime = Field(default_factory=utc_now)


class TrackerLocation(ContractModel):
    """Anonymous browser geolocation packet sent by the mobile tracker."""

    type: Literal["location"] = "location"
    session_id: str = Field(min_length=1, max_length=80)
    captured_at: datetime = Field(default_factory=utc_now)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: float | None = None
    accuracy_m: float = Field(gt=0, le=10_000)
    altitude_accuracy_m: float | None = Field(default=None, ge=0)
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    speed_mps: float | None = Field(default=None, ge=0, le=1_000)
    run_id: str | None = None
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None

    @field_validator("captured_at")
    @classmethod
    def ensure_captured_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class TrackerHello(ContractModel):
    type: Literal["hello"] = "hello"
    session_id: str = Field(min_length=1, max_length=80)
    run_id: str | None = None
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None


class TrackerCalibration(ContractModel):
    type: Literal["calibrate"] = "calibrate"
    session_id: str = Field(min_length=1, max_length=80)
    calibration_id: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    run_id: str | None = None
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None


class DevPositionRequest(ContractModel):
    session_id: str = Field(min_length=1, max_length=80)
    x_m: float
    y_m: float
    accuracy_radius_m: float = Field(default=2.0, gt=0, le=10_000)
    run_id: str | None = None
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None


class QueryRequest(ContractModel):
    query: str = Field(min_length=1, max_length=500)
    run_id: str
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None
    mode: Mode = Mode.REAL
    window_minutes: int = Field(default=10, ge=1, le=1440)
