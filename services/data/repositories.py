"""Repository interfaces used by the API and analytics adapters.

Protocols keep the API independent from SQLite and make it possible to plug in
Databricks or another durable store without changing route contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .models import NodeHeartbeat, ObservationBatch, PositionEstimate, SessionCreate, SpatialEvent


class ObservationRepository(Protocol):
    def write_observation_batch(self, batch: ObservationBatch) -> dict[str, int]: ...
    def list_observations(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                          floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...


class PositionRepository(Protocol):
    def add_position(self, position: PositionEstimate) -> bool: ...
    def list_positions(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                       floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...


class EventRepository(Protocol):
    def add_event(self, event: SpatialEvent) -> bool: ...
    def list_events(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                    floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...


class SessionRepository(Protocol):
    def add_session(self, session: SessionCreate) -> tuple[dict[str, Any], bool]: ...
    def end_session(self, session_id: str, ended_at: datetime) -> dict[str, Any] | None: ...


class NodeRepository(Protocol):
    def add_heartbeat(self, heartbeat: NodeHeartbeat) -> bool: ...
    def list_nodes(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                   floor_id: str | None = None) -> list[dict[str, Any]]: ...


class AnalyticsRepository(Protocol):
    def analytics(self, run_id: str, deployment_id: str | None, building_id: str | None,
                  floor_id: str | None, window_minutes: int = 10) -> dict[str, Any]: ...


class OutboxRepository(Protocol):
    def claim_outbox(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def complete_outbox(self, outbox_id: int) -> None: ...
    def fail_outbox(self, outbox_id: int, error: str, attempts: int) -> None: ...
