"""End-to-end observation batch processing for the positioning service."""

from __future__ import annotations

from dataclasses import dataclass, replace
import uuid
from typing import Any, Iterable, Mapping

from .buffer import ObservationBuffer
from .calibration import FingerprintSet
from .config import PositioningConfig
from .filtering import RssiFilter
from .models import (
    Diagnostic,
    ObservationBatch,
    PositionEstimate,
    SignalObservation,
    SpatialEvent,
    Zone,
    timestamp_to_iso,
)
from .provider import PositionProvider, WknnWifiFingerprintProvider
from .smoothing import EmaSmoother
from .spatial import SpatialEngine


@dataclass(frozen=True)
class EngineResult:
    position_estimates: tuple[PositionEstimate, ...]
    spatial_events: tuple[SpatialEvent, ...]
    diagnostics: tuple[Diagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "position_estimates": [estimate.to_dict() for estimate in self.position_estimates],
            "spatial_events": [event.to_dict() for event in self.spatial_events],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


class PositioningEngine:
    """Compose buffering, filtering, WKNN, EMA, and spatial classification."""

    service_name = "seuranta-positioning"

    def __init__(
        self,
        *,
        config: PositioningConfig | None = None,
        provider: PositionProvider | None = None,
        fingerprints: FingerprintSet | Iterable[Any] | None = None,
        zones: Iterable[Zone] = (),
    ) -> None:
        self.config = config or PositioningConfig()
        if provider is not None:
            self.provider = provider
        elif fingerprints is None:
            self.provider = WknnWifiFingerprintProvider((), config=self.config)
        else:
            self.provider = WknnWifiFingerprintProvider(fingerprints, config=self.config)
        self.buffer = ObservationBuffer(self.config)
        self.filterer = RssiFilter(self.config)
        self.smoother = EmaSmoother(self.config)
        self.spatial = SpatialEngine(zones, config=self.config)

    @property
    def ready(self) -> bool:
        # A missing calibration is a valid degraded operating state: the
        # service can accept observations and return diagnostics without ever
        # fabricating a coordinate.
        return self.provider is not None and self.buffer is not None

    def process_batch(self, value: ObservationBatch | Mapping[str, Any]) -> EngineResult:
        if isinstance(value, ObservationBatch):
            batch = value
        else:
            batch = ObservationBatch.from_dict(value)
        return self.process_observations(batch.observations)

    def process_observations(self, observations: Iterable[SignalObservation]) -> EngineResult:
        observation_list = tuple(observations)
        if not observation_list:
            return EngineResult(
                position_estimates=(),
                spatial_events=(),
                diagnostics=(Diagnostic(code="empty_observation_batch", message="Observation batch was empty."),),
            )
        latest_timestamp_ms = max(item.timestamp_ms for item in observation_list)
        buffered = self.buffer.ingest(observation_list, now_ms=latest_timestamp_ms)
        diagnostics: list[Diagnostic] = list(buffered.diagnostics)
        estimates: list[PositionEstimate] = []
        events: list[SpatialEvent] = list(self.spatial.expire(now_ms=latest_timestamp_ms))
        expected_anchor_ids = getattr(self.provider, "expected_anchor_ids", ())
        for key in sorted(buffered.touched_sessions):
            window = self.buffer.window_for(key)
            if window is None:
                diagnostics.append(
                    Diagnostic(
                        code="empty_position_window",
                        message="No observations remain in the configured position window.",
                        run_id=key[0],
                        session_id=key[1],
                    )
                )
                continue
            filtered = self.filterer.filter(
                window.observations,
                expected_anchor_ids=expected_anchor_ids,
                now_ms=window.window_end_ms,
            )
            diagnostics.extend(filtered.diagnostics)
            if len(filtered.anchors) < self.config.position_min_anchors:
                diagnostics.append(
                    Diagnostic(
                        code="insufficient_anchor_coverage",
                        message="Position estimate withheld because too few anchors are usable.",
                        run_id=window.run_id,
                        session_id=window.session_id,
                        details={
                            "usable_anchor_count": len(filtered.anchors),
                            "required_anchor_count": self.config.position_min_anchors,
                        },
                    )
                )
                continue
            first = window.observations[0]
            provider_estimate = self.provider.estimate(
                filtered.anchors,
                floor_id=first.floor_id,
                observation_count=filtered.observation_count,
            )
            if provider_estimate is None:
                diagnostics.append(
                    Diagnostic(
                        code="insufficient_position_evidence",
                        message="Position estimate withheld because calibration or RSSI coverage is insufficient.",
                        run_id=window.run_id,
                        session_id=window.session_id,
                        details={
                            "usable_anchor_count": len(filtered.anchors),
                            "required_anchor_count": self.config.position_min_anchors,
                            "calibration_anchor_count": len(expected_anchor_ids),
                        },
                    )
                )
                continue
            diagnostics.extend(provider_estimate.diagnostics)
            smoothing = self.smoother.smooth(
                run_id=first.run_id,
                session_id=first.session_id,
                floor_id=first.floor_id,
                timestamp_ms=window.window_end_ms,
                raw_x_m=provider_estimate.x_m,
                raw_y_m=provider_estimate.y_m,
                confidence=provider_estimate.confidence,
            )
            diagnostics.extend(smoothing.diagnostics)
            estimate = PositionEstimate(
                position_id=uuid.uuid4().hex,
                calculated_at=timestamp_to_iso(window.window_end_ms),
                window_start=window.start_iso,
                window_end=window.end_iso,
                run_id=first.run_id,
                deployment_id=first.deployment_id,
                building_id=first.building_id,
                floor_id=first.floor_id,
                session_id=first.session_id,
                raw_x_m=provider_estimate.x_m,
                raw_y_m=provider_estimate.y_m,
                x_m=smoothing.x_m,
                y_m=smoothing.y_m,
                zone_id=None,
                confidence=smoothing.confidence,
                accuracy_radius_m=provider_estimate.accuracy_radius_m * (1.0 + max(0.0, 0.5 - smoothing.confidence)),
                position_method=getattr(self.provider, "method_name", "position_provider"),
                smoothing_method=smoothing.smoothing_method,
                anchors_used=provider_estimate.anchors_used,
                observation_count=provider_estimate.observation_count,
                mode=first.mode,
                sequence_number=max(item.sequence_number for item in window.observations),
                is_outside_map=False,
            )
            spatial_result = self.spatial.process(estimate, now_ms=window.window_end_ms)
            diagnostics.extend(spatial_result.diagnostics)
            events.extend(spatial_result.events)
            estimate = replace(
                estimate,
                zone_id=spatial_result.zone_id,
                is_outside_map=spatial_result.is_outside_map,
            )
            estimates.append(estimate)
        return EngineResult(tuple(estimates), tuple(events), tuple(diagnostics))
