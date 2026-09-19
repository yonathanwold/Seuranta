"""In-memory phone tracking engine used by the FastAPI transport layer.

The engine is intentionally independent from WebSocket objects and SQLite.
It accepts validated browser telemetry and produces the existing normalized
``PositionEstimate`` contract.  A later persistent positioning service can
replace this module without changing the frontend or wire format.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.data.models import (
    DevPositionRequest,
    Mode,
    PositionEstimate,
    SessionCreate,
    TrackerLocation,
    utc_now,
)

from .coordinates import CalibrationReference, geographic_to_floor, is_outside_map
from .settings import Settings
from .smoothing import ExponentialSmoother, confidence_from_accuracy
from .zones import assign_zone


SESSION_PATTERN = re.compile(r"^session-[a-z0-9][a-z0-9-]{2,63}$")


@dataclass(frozen=True)
class TrackingScope:
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str


@dataclass
class TrackerSession:
    session_id: str
    scope: TrackingScope
    started_at: datetime
    last_received_at: datetime
    last_captured_at: datetime | None = None
    latest_location: TrackerLocation | None = None
    latest_position: PositionEstimate | None = None
    smoother: ExponentialSmoother = field(default_factory=ExponentialSmoother)
    observation_count: int = 0


@dataclass(frozen=True)
class IngestResult:
    session: TrackerSession
    position: PositionEstimate | None
    session_created: bool
    calibration_required: bool = False


class TrackingEngine:
    """Thread-safe state for consenting anonymous tracker sessions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._sessions: dict[str, TrackerSession] = {}
        self._calibration: CalibrationReference | None = None
        if settings.calibration_latitude is not None and settings.calibration_longitude is not None:
            self._calibration = CalibrationReference(
                reference_latitude=settings.calibration_latitude,
                reference_longitude=settings.calibration_longitude,
                reference_floor_x=settings.calibration_x_m,
                reference_floor_y=settings.calibration_y_m,
                yaw_deg=settings.building_yaw_deg,
                calibration_id=settings.calibration_id,
                label=settings.calibration_label,
            )

    @property
    def default_scope(self) -> TrackingScope:
        return TrackingScope(
            run_id=self.settings.run_id,
            deployment_id=self.settings.deployment_id,
            building_id=self.settings.building_id,
            floor_id=self.settings.floor_id,
        )

    @property
    def calibration(self) -> CalibrationReference | None:
        with self._lock:
            return self._calibration

    def resolve_scope(
        self,
        run_id: str | None = None,
        deployment_id: str | None = None,
        building_id: str | None = None,
        floor_id: str | None = None,
    ) -> TrackingScope:
        default = self.default_scope
        scope = TrackingScope(
            run_id=run_id or default.run_id,
            deployment_id=deployment_id or default.deployment_id,
            building_id=building_id or default.building_id,
            floor_id=floor_id or default.floor_id,
        )
        if scope != default:
            raise ValueError("tracker scope does not match the configured deployment")
        return scope

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        normalized = session_id.strip().lower()
        if not SESSION_PATTERN.fullmatch(normalized):
            raise ValueError("session_id must be an anonymous value such as session-a7f3")
        return normalized

    def _get_or_create(self, session_id: str, scope: TrackingScope, now: datetime) -> tuple[TrackerSession, bool]:
        session_id = self.validate_session_id(session_id)
        with self._lock:
            current = self._sessions.get(session_id)
            if current:
                if current.scope != scope:
                    raise ValueError("session_id is already associated with another scope")
                return current, False
            current = TrackerSession(
                session_id=session_id,
                scope=scope,
                started_at=now,
                last_received_at=now,
            )
            self._sessions[session_id] = current
            return current, True

    def register(self, session_id: str, scope: TrackingScope, now: datetime | None = None) -> tuple[TrackerSession, bool]:
        return self._get_or_create(session_id, scope, now or utc_now())

    def session_create(self, session: TrackerSession) -> SessionCreate:
        return SessionCreate(
            session_id=session.session_id,
            run_id=session.scope.run_id,
            deployment_id=session.scope.deployment_id,
            building_id=session.scope.building_id,
            floor_id=session.scope.floor_id,
            mode=Mode.REAL,
            started_at=session.started_at,
        )

    def calibrate(
        self,
        session_id: str,
        scope: TrackingScope,
        latitude: float,
        longitude: float,
        calibration_id: str | None = None,
        floor_x_m: float | None = None,
        floor_y_m: float | None = None,
        label: str | None = None,
        now: datetime | None = None,
    ) -> TrackerSession:
        current, _ = self._get_or_create(session_id, scope, now or utc_now())
        if calibration_id and calibration_id != self.settings.calibration_id:
            raise ValueError("unknown calibration point")
        with self._lock:
            self._calibration = CalibrationReference(
                reference_latitude=latitude,
                reference_longitude=longitude,
                reference_floor_x=self.settings.calibration_x_m if floor_x_m is None else floor_x_m,
                reference_floor_y=self.settings.calibration_y_m if floor_y_m is None else floor_y_m,
                yaw_deg=self.settings.building_yaw_deg,
                calibration_id=calibration_id or self.settings.calibration_id,
                label=label or self.settings.calibration_label,
            )
            return current

    def ingest_location(self, location: TrackerLocation, scope: TrackingScope, now: datetime | None = None) -> IngestResult:
        received_at = now or utc_now()
        current, created = self._get_or_create(location.session_id, scope, received_at)
        with self._lock:
            current.last_received_at = received_at
            current.last_captured_at = location.captured_at
            current.latest_location = location
            calibration = self._calibration
            if calibration is None:
                return IngestResult(current, None, created, calibration_required=True)
            raw_x, raw_y = geographic_to_floor(location.latitude, location.longitude, calibration)
            x_m, y_m = current.smoother.update(raw_x, raw_y, location.accuracy_m)
            current.observation_count += 1
            position = PositionEstimate(
                calculated_at=received_at,
                window_start=location.captured_at,
                window_end=location.captured_at,
                run_id=scope.run_id,
                deployment_id=scope.deployment_id,
                building_id=scope.building_id,
                floor_id=scope.floor_id,
                session_id=current.session_id,
                raw_x_m=raw_x,
                raw_y_m=raw_y,
                x_m=x_m,
                y_m=y_m,
                zone_id=assign_zone(x_m, y_m),
                confidence=confidence_from_accuracy(location.accuracy_m),
                accuracy_radius_m=location.accuracy_m,
                position_method="phone-geolocation",
                smoothing_method="ema",
                anchors_used=[],
                observation_count=current.observation_count,
                mode=Mode.REAL,
                sequence_number=current.observation_count,
                is_outside_map=is_outside_map(
                    x_m,
                    y_m,
                    self.settings.floor_width_m,
                    self.settings.floor_depth_m,
                    self.settings.floor_origin_x_m,
                    self.settings.floor_origin_y_m,
                ),
            )
            current.latest_position = position
            return IngestResult(current, position, created)

    def ingest_dev_position(self, request: DevPositionRequest, scope: TrackingScope, now: datetime | None = None) -> IngestResult:
        received_at = now or utc_now()
        current, created = self._get_or_create(request.session_id, scope, received_at)
        with self._lock:
            current.last_received_at = received_at
            current.last_captured_at = received_at
            current.observation_count += 1
            x_m, y_m = current.smoother.update(request.x_m, request.y_m, request.accuracy_radius_m)
            position = PositionEstimate(
                calculated_at=received_at,
                window_start=received_at,
                window_end=received_at,
                run_id=scope.run_id,
                deployment_id=scope.deployment_id,
                building_id=scope.building_id,
                floor_id=scope.floor_id,
                session_id=current.session_id,
                raw_x_m=request.x_m,
                raw_y_m=request.y_m,
                x_m=x_m,
                y_m=y_m,
                zone_id=assign_zone(x_m, y_m),
                confidence=confidence_from_accuracy(request.accuracy_radius_m),
                accuracy_radius_m=request.accuracy_radius_m,
                position_method="dev-simulation",
                smoothing_method="ema",
                anchors_used=[],
                observation_count=current.observation_count,
                mode=Mode.REAL,
                sequence_number=current.observation_count,
                is_outside_map=is_outside_map(
                    x_m,
                    y_m,
                    self.settings.floor_width_m,
                    self.settings.floor_depth_m,
                    self.settings.floor_origin_x_m,
                    self.settings.floor_origin_y_m,
                ),
            )
            current.latest_position = position
            return IngestResult(current, position, created)

    def _status(self, session: TrackerSession, now: datetime) -> str:
        age = max(0.0, (now - session.last_received_at).total_seconds())
        if age < self.settings.tracker_stale_after_seconds:
            return "active"
        if age < self.settings.tracker_expire_after_seconds:
            return "degraded"
        return "expired"

    def positions_for(self, scope: TrackingScope, now: datetime | None = None) -> list[PositionEstimate]:
        current_time = now or utc_now()
        with self._lock:
            result = []
            for session in self._sessions.values():
                if session.scope == scope and session.latest_position and self._status(session, current_time) != "expired":
                    result.append(session.latest_position)
            return sorted(result, key=lambda item: item.calculated_at, reverse=True)

    def sessions_for(self, scope: TrackingScope, now: datetime | None = None) -> list[dict[str, Any]]:
        current_time = now or utc_now()
        with self._lock:
            result = []
            for session in self._sessions.values():
                if session.scope != scope:
                    continue
                result.append({
                    "session_id": session.session_id,
                    "run_id": scope.run_id,
                    "deployment_id": scope.deployment_id,
                    "building_id": scope.building_id,
                    "floor_id": scope.floor_id,
                    "mode": Mode.REAL.value,
                    "started_at": session.started_at.isoformat(),
                    "last_update": session.last_received_at.isoformat(),
                    "status": self._status(session, current_time),
                    "observation_count": session.observation_count,
                })
            return sorted(result, key=lambda item: item["last_update"], reverse=True)

    def session_ids_for(self, scope: TrackingScope) -> set[str]:
        with self._lock:
            return {session.session_id for session in self._sessions.values() if session.scope == scope}

    def config_payload(self) -> dict[str, Any]:
        with self._lock:
            calibration = self._calibration
            return {
                "run_id": self.settings.run_id,
                "deployment_id": self.settings.deployment_id,
                "building_id": self.settings.building_id,
                "floor_id": self.settings.floor_id,
                "mode": Mode.REAL.value,
                "dev_mode": self.settings.dev_mode,
                "public_tracker_url": self.settings.public_tracker_url,
                "calibration": {
                    "calibration_id": self.settings.calibration_id,
                    "label": self.settings.calibration_label,
                    "x_m": self.settings.calibration_x_m,
                    "y_m": self.settings.calibration_y_m,
                    "yaw_deg": self.settings.building_yaw_deg,
                    "configured": calibration is not None,
                },
                "floor": {
                    "width_m": self.settings.floor_width_m,
                    "depth_m": self.settings.floor_depth_m,
                    "origin_x_m": self.settings.floor_origin_x_m,
                    "origin_y_m": self.settings.floor_origin_y_m,
                },
            }
