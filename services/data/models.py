"""V1 wire contracts.

The models intentionally contain only anonymous session telemetry.  In
particular, raw MAC addresses, packet payloads, names, and persistent personal
identifiers are not represented here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import math
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Mode(StrEnum):
    REAL = "real"
    SIMULATED = "simulated"

    @classmethod
    def _missing_(cls, value: object):
        # Accept the legacy edge-agent spellings while normalising all stored
        # API records to the two current modes.
        if isinstance(value, str):
            return {"live": cls.REAL, "simulation": cls.SIMULATED, "replay": cls.SIMULATED}.get(value.lower())
        return None


class NodeStatus(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            normalized = value.lower()
            return next((member for member in cls if member.value == normalized), None)
        return None


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


class AnchorDefinition(ContractModel):
    """A fixed anchor's location and RSSI calibration.

    ``tx_power_dbm_at_1m`` is the measured RSSI at one metre, not a radio's
    advertised transmit-power field.  Calibrating this value in the deployed
    room is essential for a useful range estimate.
    """

    anchor_id: str = Field(min_length=1, max_length=128)
    x_m: float
    y_m: float
    tx_power_dbm_at_1m: float = Field(default=-59.0, ge=-100, le=0)
    path_loss_exponent: float = Field(default=2.2, gt=0, le=6)

    @field_validator("x_m", "y_m", "tx_power_dbm_at_1m", "path_loss_exponent")
    @classmethod
    def ensure_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class RssiPositionRequest(ContractModel):
    """A one-shot RSSI multilateration request, useful for calibration."""

    window_start: datetime
    window_end: datetime
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    session_id: str
    source: str = Field(default="ble", min_length=1, max_length=64)
    anchors: list[AnchorDefinition] = Field(min_length=3, max_length=32)
    rssi_by_anchor: dict[str, float] = Field(min_length=3)
    mode: Mode = Mode.REAL
    sequence_number: int = Field(default=0, ge=0)

    @field_validator("window_start", "window_end")
    @classmethod
    def ensure_window_timezone(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @field_validator("rssi_by_anchor")
    @classmethod
    def validate_rssi(cls, value: dict[str, float]) -> dict[str, float]:
        for anchor_id, rssi_dbm in value.items():
            if not anchor_id:
                raise ValueError("anchor IDs must not be empty")
            if not math.isfinite(rssi_dbm) or not -127 <= rssi_dbm <= 0:
                raise ValueError("RSSI values must be finite dBm values between -127 and 0")
        return value

    @model_validator(mode="after")
    def validate_geometry_inputs(self) -> "RssiPositionRequest":
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        anchor_ids = [anchor.anchor_id for anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("anchor definitions must have unique anchor_id values")
        configured = set(anchor_ids)
        measured = set(self.rssi_by_anchor)
        unknown = measured - configured
        if unknown:
            raise ValueError(f"RSSI supplied for unknown anchors: {', '.join(sorted(unknown))}")
        if len(configured & measured) < 3:
            raise ValueError("at least three configured anchors need an RSSI measurement")
        return self


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


class QueryRequest(ContractModel):
    query: str = Field(min_length=1, max_length=500)
    run_id: str
    deployment_id: str | None = None
    building_id: str | None = None
    floor_id: str | None = None
    mode: Mode = Mode.REAL
    window_minutes: int = Field(default=10, ge=1, le=1440)
