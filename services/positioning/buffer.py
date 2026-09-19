"""Event-time observation buffering with bounded lateness."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Iterable

from .config import PositioningConfig
from .models import Diagnostic, SignalObservation, timestamp_to_iso


SessionKey = tuple[str, str]


@dataclass(frozen=True)
class ObservationWindow:
    run_id: str
    session_id: str
    observations: tuple[SignalObservation, ...]
    window_start_ms: int
    window_end_ms: int
    watermark_ms: int

    @property
    def start_iso(self) -> str:
        return timestamp_to_iso(self.window_start_ms)

    @property
    def end_iso(self) -> str:
        return timestamp_to_iso(self.window_end_ms)


@dataclass
class _SessionBuffer:
    observations: list[SignalObservation] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    seen_observation_ids: set[str] = field(default_factory=set)
    max_seen_timestamp_ms: int | None = None
    last_ingest_timestamp_ms: int | None = None


@dataclass(frozen=True)
class BufferResult:
    accepted: tuple[SignalObservation, ...]
    touched_sessions: tuple[SessionKey, ...]
    diagnostics: tuple[Diagnostic, ...]


class ObservationBuffer:
    """Keep bounded, sorted event-time windows independently per run/session."""

    def __init__(self, config: PositioningConfig | None = None) -> None:
        self.config = config or PositioningConfig()
        self._sessions: dict[SessionKey, _SessionBuffer] = {}

    def ingest(
        self,
        observations: Iterable[SignalObservation],
        *,
        now_ms: int | None = None,
    ) -> BufferResult:
        accepted: list[SignalObservation] = []
        touched: set[SessionKey] = set()
        diagnostics: list[Diagnostic] = []
        for observation in observations:
            key = (observation.run_id, observation.session_id)
            state = self._sessions.setdefault(key, _SessionBuffer())
            touched.add(key)
            if observation.observation_id in state.seen_observation_ids:
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_observation",
                        message="Duplicate observation ignored.",
                        run_id=observation.run_id,
                        session_id=observation.session_id,
                        details={"observation_id": observation.observation_id},
                    )
                )
                continue
            if state.max_seen_timestamp_ms is not None:
                watermark = state.max_seen_timestamp_ms - self.config.max_lateness_ms
                if observation.timestamp_ms < watermark:
                    diagnostics.append(
                        Diagnostic(
                            code="late_observation_dropped",
                            message="Observation arrived beyond the bounded lateness horizon.",
                            run_id=observation.run_id,
                            session_id=observation.session_id,
                            details={
                                "timestamp_ms": observation.timestamp_ms,
                                "watermark_ms": watermark,
                            },
                        )
                    )
                    continue
            reference_ms = max(
                state.max_seen_timestamp_ms if state.max_seen_timestamp_ms is not None else observation.timestamp_ms,
                now_ms if now_ms is not None else observation.timestamp_ms,
            )
            if reference_ms - observation.timestamp_ms > self.config.stale_sample_ms:
                diagnostics.append(
                    Diagnostic(
                        code="stale_observation_dropped",
                        message="Observation was older than the configured sample-age limit.",
                        run_id=observation.run_id,
                        session_id=observation.session_id,
                        details={
                            "timestamp_ms": observation.timestamp_ms,
                            "reference_ms": reference_ms,
                            "stale_sample_ms": self.config.stale_sample_ms,
                        },
                    )
                )
                continue
            insertion_index = bisect_right(state.timestamps, observation.timestamp_ms)
            state.timestamps.insert(insertion_index, observation.timestamp_ms)
            state.observations.insert(insertion_index, observation)
            state.seen_observation_ids.add(observation.observation_id)
            if state.max_seen_timestamp_ms is None or observation.timestamp_ms > state.max_seen_timestamp_ms:
                state.max_seen_timestamp_ms = observation.timestamp_ms
            state.last_ingest_timestamp_ms = now_ms or observation.timestamp_ms
            accepted.append(observation)
        for key in touched:
            self._trim(key)
        return BufferResult(tuple(accepted), tuple(sorted(touched)), tuple(diagnostics))

    def _trim(self, key: SessionKey) -> None:
        state = self._sessions.get(key)
        if state is None or state.max_seen_timestamp_ms is None:
            return
        lower_bound = state.max_seen_timestamp_ms - self.config.position_window_ms - self.config.max_lateness_ms
        first_keep = bisect_right(state.timestamps, lower_bound - 1)
        if first_keep <= 0:
            return
        removed = state.observations[:first_keep]
        del state.observations[:first_keep]
        del state.timestamps[:first_keep]
        # Keep duplicate IDs for the lifetime of a session.  A retransmitted
        # sample should remain a duplicate even after its sample leaves the window.
        del removed

    def window_for(self, key: SessionKey) -> ObservationWindow | None:
        state = self._sessions.get(key)
        if state is None or not state.observations or state.max_seen_timestamp_ms is None:
            return None
        lower_bound = state.max_seen_timestamp_ms - self.config.position_window_ms
        start = bisect_right(state.timestamps, lower_bound - 1)
        current = tuple(state.observations[start:])
        if not current:
            return None
        return ObservationWindow(
            run_id=key[0],
            session_id=key[1],
            observations=current,
            window_start_ms=current[0].timestamp_ms,
            window_end_ms=current[-1].timestamp_ms,
            watermark_ms=state.max_seen_timestamp_ms - self.config.max_lateness_ms,
        )

    def windows_for(self, keys: Iterable[SessionKey]) -> dict[SessionKey, ObservationWindow]:
        windows: dict[SessionKey, ObservationWindow] = {}
        for key in keys:
            window = self.window_for(key)
            if window is not None:
                windows[key] = window
        return windows

    def clear_session(self, key: SessionKey) -> None:
        self._sessions.pop(key, None)

    def session_count(self) -> int:
        return len(self._sessions)
