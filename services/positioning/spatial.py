"""Zone classification, hysteresis, dwell tracking, and spatial events."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping
import uuid

from .config import PositioningConfig
from .models import Diagnostic, PositionEstimate, SpatialEvent, Zone, timestamp_to_iso


SessionKey = tuple[str, str]


def point_in_polygon(
    x_m: float,
    y_m: float,
    polygon: Iterable[tuple[float, float]],
    *,
    boundary_inside: bool = True,
    tolerance: float = 1e-9,
) -> bool:
    """Return whether a point is inside a polygon, including boundaries by default."""

    points = tuple(polygon)
    if len(points) < 3:
        return False
    inside = False
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        cross = (x_m - x1) * (y2 - y1) - (y_m - y1) * (x2 - x1)
        if abs(cross) <= tolerance:
            dot = (x_m - x1) * (x2 - x1) + (y_m - y1) * (y2 - y1)
            length_squared = (x2 - x1) ** 2 + (y2 - y1) ** 2
            if -tolerance <= dot <= length_squared + tolerance:
                return boundary_inside
        if (y1 > y_m) != (y2 > y_m):
            x_intersection = (x2 - x1) * (y_m - y1) / (y2 - y1) + x1
            if x_m < x_intersection:
                inside = not inside
    return inside


@dataclass(frozen=True)
class SpatialResult:
    zone_id: str | None
    is_outside_map: bool
    events: tuple[SpatialEvent, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass
class _SpatialSessionState:
    run_id: str
    deployment_id: str
    building_id: str
    floor_id: str
    mode: str
    session_id: str
    current_zone: Zone | None = None
    candidate_zone: Zone | None = None
    candidate_since_ms: int | None = None
    exit_since_ms: int | None = None
    dwell_started_ms: int | None = None
    last_dwell_update_ms: int | None = None
    last_seen_ms: int | None = None
    pending_from_zone_id: str | None = None
    event_sequence: int = 0
    started: bool = False


class SpatialEngine:
    """Stateful spatial classifier with per-session hysteresis."""

    def __init__(
        self,
        zones: Iterable[Zone] = (),
        *,
        config: PositioningConfig | None = None,
        boundary_inside: bool = True,
    ) -> None:
        self.config = config or PositioningConfig()
        self.boundary_inside = boundary_inside
        self.zones = tuple(zones)
        self._sessions: dict[SessionKey, _SpatialSessionState] = {}
        self._occupancy: dict[tuple[str, str, str, str, str], int] = {}

    def set_zones(self, zones: Iterable[Zone]) -> None:
        self.zones = tuple(zones)

    def candidate_zone(
        self,
        *,
        building_id: str,
        floor_id: str,
        x_m: float,
        y_m: float,
    ) -> Zone | None:
        candidates = [
            zone
            for zone in self.zones
            if zone.enabled
            and zone.building_id == building_id
            and zone.floor_id == floor_id
            and point_in_polygon(x_m, y_m, zone.polygon, boundary_inside=self.boundary_inside)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda zone: (zone.priority, zone.zone_id))

    def process(self, position: PositionEstimate, *, now_ms: int | None = None) -> SpatialResult:
        event_time_ms = max(0, int(now_ms if now_ms is not None else _timestamp_ms(position.calculated_at)))
        key = (position.run_id, position.session_id)
        state = self._sessions.get(key)
        if state is None:
            state = _SpatialSessionState(
                run_id=position.run_id,
                deployment_id=position.deployment_id,
                building_id=position.building_id,
                floor_id=position.floor_id,
                mode=position.mode,
                session_id=position.session_id,
            )
            self._sessions[key] = state
        diagnostics: list[Diagnostic] = []
        events: list[SpatialEvent] = []
        if not state.started:
            state.started = True
            events.append(self._event(position, state, "SESSION_STARTED", event_time_ms))
        candidate = self.candidate_zone(
            building_id=position.building_id,
            floor_id=position.floor_id,
            x_m=position.x_m,
            y_m=position.y_m,
        )
        outside_map = bool(self.zones) and candidate is None
        current = state.current_zone
        if current is None:
            if candidate is not None and position.confidence >= max(candidate.min_confidence, self.config.default_min_confidence):
                self._track_entry(state, candidate, event_time_ms)
                if self._entry_confirmed(state, event_time_ms):
                    events.extend(self._enter(position, state, candidate, event_time_ms))
            else:
                if candidate is not None and position.confidence < candidate.min_confidence:
                    diagnostics.append(self._low_confidence(position, candidate, "entry"))
                self._clear_candidate(state)
        elif candidate is not None and candidate.zone_id == current.zone_id:
            state.exit_since_ms = None
            self._clear_candidate(state)
            events.extend(self._dwell_updates(position, state, event_time_ms))
        else:
            if position.confidence < max(current.min_confidence, self.config.default_min_confidence):
                diagnostics.append(self._low_confidence(position, current, "exit"))
            else:
                if state.exit_since_ms is None:
                    state.exit_since_ms = event_time_ms
                if event_time_ms - state.exit_since_ms >= current.exit_confirm_ms:
                    old_zone = current
                    events.extend(
                        self._exit(
                            position,
                            state,
                            old_zone,
                            event_time_ms,
                            to_zone_id=candidate.zone_id if candidate is not None else None,
                        )
                    )
                    state.current_zone = None
                    state.exit_since_ms = None
                    state.pending_from_zone_id = old_zone.zone_id
                    if candidate is not None and position.confidence >= candidate.min_confidence:
                        self._track_entry(state, candidate, event_time_ms)
                        if candidate.entry_confirm_ms == 0:
                            events.extend(
                                self._enter(
                                    position,
                                    state,
                                    candidate,
                                    event_time_ms,
                                    from_zone_id=state.pending_from_zone_id,
                                )
                            )
        if state.current_zone is not None:
            position_zone_id = state.current_zone.zone_id
        else:
            position_zone_id = None
        events.append(
            self._event(
                position,
                state,
                "POSITION_UPDATED",
                event_time_ms,
                zone_id=position_zone_id,
            )
        )
        state.last_seen_ms = event_time_ms
        state.floor_id = position.floor_id
        return SpatialResult(position_zone_id, outside_map, tuple(events), tuple(diagnostics))

    def expire(self, *, now_ms: int) -> tuple[SpatialEvent, ...]:
        """End sessions silent beyond the configured timeout."""

        events: list[SpatialEvent] = []
        for key, state in list(self._sessions.items()):
            if state.last_seen_ms is None or now_ms - state.last_seen_ms < self.config.session_timeout_ms:
                continue
            placeholder = _placeholder_position(state, state.last_seen_ms)
            if state.current_zone is not None:
                events.extend(self._exit(placeholder, state, state.current_zone, now_ms))
                state.current_zone = None
            events.append(self._event(placeholder, state, "SESSION_ENDED", now_ms))
            del self._sessions[key]
        return tuple(events)

    def occupancy(self) -> Mapping[tuple[str, str, str, str, str], int]:
        return dict(self._occupancy)

    def _track_entry(self, state: _SpatialSessionState, candidate: Zone, timestamp_ms: int) -> None:
        if state.candidate_zone is None or state.candidate_zone.zone_id != candidate.zone_id:
            state.candidate_zone = candidate
            state.candidate_since_ms = timestamp_ms

    def _clear_candidate(self, state: _SpatialSessionState) -> None:
        state.candidate_zone = None
        state.candidate_since_ms = None

    def _entry_confirmed(self, state: _SpatialSessionState, timestamp_ms: int) -> bool:
        if state.candidate_zone is None or state.candidate_since_ms is None:
            return False
        return timestamp_ms - state.candidate_since_ms >= state.candidate_zone.entry_confirm_ms

    def _enter(
        self,
        position: PositionEstimate,
        state: _SpatialSessionState,
        zone: Zone,
        timestamp_ms: int,
        *,
        from_zone_id: str | None = None,
    ) -> list[SpatialEvent]:
        state.current_zone = zone
        state.dwell_started_ms = timestamp_ms
        state.last_dwell_update_ms = timestamp_ms
        self._clear_candidate(state)
        occupancy_after = self._change_occupancy(position, zone, 1)
        transition_from = from_zone_id if from_zone_id is not None else state.pending_from_zone_id
        state.pending_from_zone_id = None
        events = [
            self._event(
                position,
                state,
                "ZONE_ENTERED",
                timestamp_ms,
                zone_id=zone.zone_id,
                from_zone_id=transition_from,
                to_zone_id=zone.zone_id if transition_from is not None else None,
            ),
        ]
        if zone.kind.casefold() == "room":
            events.append(
                self._event(
                    position,
                    state,
                    "ROOM_ENTERED",
                    timestamp_ms,
                    zone_id=zone.zone_id,
                    from_zone_id=transition_from,
                    to_zone_id=zone.zone_id if transition_from is not None else None,
                )
            )
        events.append(
            self._event(
                position,
                state,
                "OCCUPANCY_CHANGE",
                timestamp_ms,
                zone_id=zone.zone_id,
                occupancy_after=occupancy_after,
            )
        )
        events.append(
            self._event(
                position,
                state,
                "DWELL_STARTED",
                timestamp_ms,
                zone_id=zone.zone_id,
                dwell_ms=0,
            )
        )
        return events

    def _exit(
        self,
        position: PositionEstimate,
        state: _SpatialSessionState,
        zone: Zone,
        timestamp_ms: int,
        *,
        to_zone_id: str | None = None,
    ) -> list[SpatialEvent]:
        dwell_ms = 0
        if state.dwell_started_ms is not None:
            dwell_ms = max(0, timestamp_ms - state.dwell_started_ms)
        occupancy_after = self._change_occupancy(position, zone, -1)
        events = [
            self._event(
                position,
                state,
                "ZONE_EXITED",
                timestamp_ms,
                zone_id=zone.zone_id,
                from_zone_id=zone.zone_id if to_zone_id is not None else None,
                to_zone_id=to_zone_id,
            ),
        ]
        if zone.kind.casefold() == "room":
            events.append(
                self._event(
                    position,
                    state,
                    "ROOM_EXITED",
                    timestamp_ms,
                    zone_id=zone.zone_id,
                    from_zone_id=zone.zone_id if to_zone_id is not None else None,
                    to_zone_id=to_zone_id,
                )
            )
        events.append(
            self._event(
                position,
                state,
                "OCCUPANCY_CHANGE",
                timestamp_ms,
                zone_id=zone.zone_id,
                occupancy_after=occupancy_after,
            )
        )
        events.append(
            self._event(
                position,
                state,
                "DWELL_ENDED",
                timestamp_ms,
                zone_id=zone.zone_id,
                dwell_ms=dwell_ms,
            )
        )
        state.dwell_started_ms = None
        state.last_dwell_update_ms = None
        return events

    def _dwell_updates(
        self,
        position: PositionEstimate,
        state: _SpatialSessionState,
        timestamp_ms: int,
    ) -> list[SpatialEvent]:
        if state.current_zone is None or state.dwell_started_ms is None:
            return []
        dwell_ms = max(0, timestamp_ms - state.dwell_started_ms)
        if (
            state.last_dwell_update_ms is None
            or timestamp_ms - state.last_dwell_update_ms >= self.config.dwell_update_ms
        ):
            state.last_dwell_update_ms = timestamp_ms
            return [
                self._event(
                    position,
                    state,
                    "DWELL_UPDATED",
                    timestamp_ms,
                    zone_id=state.current_zone.zone_id,
                    dwell_ms=dwell_ms,
                )
            ]
        return []

    def _change_occupancy(self, position: PositionEstimate, zone: Zone, delta: int) -> int:
        key = (position.run_id, position.deployment_id, zone.building_id, zone.floor_id, zone.zone_id)
        after = max(0, self._occupancy.get(key, 0) + delta)
        self._occupancy[key] = after
        return after

    def _low_confidence(self, position: PositionEstimate, zone: Zone, transition: str) -> Diagnostic:
        return Diagnostic(
            code="low_confidence_zone_transition_suppressed",
            message="Zone transition was suppressed because confidence is below the zone threshold.",
            run_id=position.run_id,
            session_id=position.session_id,
            details={
                "zone_id": zone.zone_id,
                "transition": transition,
                "confidence": position.confidence,
                "min_confidence": zone.min_confidence,
            },
        )

    def _event(
        self,
        position: PositionEstimate,
        state: _SpatialSessionState,
        event_type: str,
        timestamp_ms: int,
        *,
        zone_id: str | None = None,
        from_zone_id: str | None = None,
        to_zone_id: str | None = None,
        dwell_ms: int | None = None,
        occupancy_after: int | None = None,
    ) -> SpatialEvent:
        state.event_sequence += 1
        return SpatialEvent(
            event_id=uuid.uuid4().hex,
            event_type=event_type,
            occurred_at=timestamp_to_iso(timestamp_ms),
            emitted_at=timestamp_to_iso(timestamp_ms),
            run_id=position.run_id,
            deployment_id=position.deployment_id,
            building_id=position.building_id,
            floor_id=position.floor_id,
            mode=position.mode,
            session_id=position.session_id,
            zone_id=zone_id,
            from_zone_id=from_zone_id,
            to_zone_id=to_zone_id,
            position_id=position.position_id,
            dwell_ms=dwell_ms,
            occupancy_after=occupancy_after,
            confidence=position.confidence,
            event_sequence=state.event_sequence,
        )


def _timestamp_ms(value: str) -> int:
    from .models import parse_timestamp_ms

    return parse_timestamp_ms(value)


def _placeholder_position(state: _SpatialSessionState, timestamp_ms: int) -> PositionEstimate:
    return PositionEstimate(
        position_id=uuid.uuid4().hex,
        calculated_at=timestamp_to_iso(timestamp_ms),
        window_start=timestamp_to_iso(timestamp_ms),
        window_end=timestamp_to_iso(timestamp_ms),
        run_id=state.run_id,
        deployment_id=state.deployment_id,
        building_id=state.building_id,
        floor_id=state.floor_id,
        session_id=state.session_id,
        raw_x_m=0.0,
        raw_y_m=0.0,
        x_m=0.0,
        y_m=0.0,
        zone_id=state.current_zone.zone_id if state.current_zone else None,
        confidence=0.0,
        accuracy_radius_m=0.0,
        position_method="session_timeout",
        smoothing_method="none",
        anchors_used=(),
        observation_count=0,
        mode=state.mode,
        sequence_number=state.event_sequence,
        is_outside_map=False,
    )
