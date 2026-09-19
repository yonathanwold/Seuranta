"""Position provider abstractions and weighted k-nearest-neighbour WKNN."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .calibration import FingerprintPoint, FingerprintSet
from .config import PositioningConfig
from .filtering import FilteredAnchor
from .models import Diagnostic


@dataclass(frozen=True)
class ProviderEstimate:
    x_m: float
    y_m: float
    confidence: float
    accuracy_radius_m: float
    anchors_used: tuple[str, ...]
    observation_count: int
    neighbor_distances_db: tuple[float, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


class PositionProvider(ABC):
    """Algorithm boundary used by the rest of the positioning pipeline."""

    method_name = "position_provider"

    @abstractmethod
    def estimate(
        self,
        filtered_anchors: Mapping[str, FilteredAnchor | float],
        *,
        floor_id: str | None = None,
        observation_count: int | None = None,
    ) -> ProviderEstimate | None:
        raise NotImplementedError


def _anchor_value(value: FilteredAnchor | float) -> tuple[float, int, float, int]:
    if isinstance(value, FilteredAnchor):
        return value.rssi_dbm, value.sample_count, value.age_ms, value.spread_db
    return float(value), 1, 0, 0


class WknnWifiFingerprintProvider(PositionProvider):
    """Weighted k-nearest-neighbour RSSI fingerprint localization."""

    method_name = "wknn_wifi_fingerprint"

    def __init__(
        self,
        fingerprints: Iterable[FingerprintPoint] | FingerprintSet,
        *,
        config: PositioningConfig | None = None,
    ) -> None:
        self.config = config or PositioningConfig()
        if isinstance(fingerprints, FingerprintSet):
            self.fingerprint_set = fingerprints
            points = fingerprints.points
            self.validation_metrics = fingerprints.validation_metrics
        else:
            points = tuple(fingerprints)
            self.fingerprint_set = None
            self.validation_metrics = {}
        self.points = tuple(points)
        self.expected_anchor_ids = tuple(sorted({anchor_id for point in self.points for anchor_id in point.anchor_ids}))

    def estimate(
        self,
        filtered_anchors: Mapping[str, FilteredAnchor | float],
        *,
        floor_id: str | None = None,
        observation_count: int | None = None,
    ) -> ProviderEstimate | None:
        if not self.points:
            return None
        if not filtered_anchors:
            return None
        current = {str(anchor_id): _anchor_value(value) for anchor_id, value in filtered_anchors.items()}
        candidate_points = [point for point in self.points if floor_id is None or point.floor_id == floor_id]
        if not candidate_points:
            return None
        neighbors: list[tuple[float, FingerprintPoint, tuple[str, ...]]] = []
        for point in candidate_points:
            common = tuple(sorted(set(current) & set(point.anchor_rssi_medians)))
            if len(common) < self.config.position_min_anchors:
                continue
            missing_count = len(set(current) | set(point.anchor_rssi_medians)) - len(common)
            squared_error = sum(
                (current[anchor_id][0] - point.anchor_rssi_medians[anchor_id]) ** 2
                for anchor_id in common
            )
            if missing_count:
                squared_error += (self.config.missing_anchor_penalty_db ** 2) * missing_count
            distance = math.sqrt(squared_error / max(1, len(common)))
            neighbors.append((distance, point, common))
        if not neighbors:
            return None
        neighbors.sort(key=lambda item: (item[0], item[1].point_id))
        if neighbors[0][0] > self.config.max_rssi_distance_db:
            return None
        selected = neighbors[: min(self.config.wknn_k, len(neighbors))]
        exact = [item for item in selected if item[0] <= self.config.distance_epsilon]
        if exact:
            weights = [1.0 / len(exact)] * len(exact)
            selected_for_position = exact
        else:
            weights = [1.0 / (item[0] * item[0] + self.config.distance_epsilon) for item in selected]
            selected_for_position = selected
        weight_total = sum(weights)
        if weight_total <= 0.0 or not math.isfinite(weight_total):
            return None
        x_m = sum(weight * item[1].x_m for weight, item in zip(weights, selected_for_position)) / weight_total
        y_m = sum(weight * item[1].y_m for weight, item in zip(weights, selected_for_position)) / weight_total

        best_distance = neighbors[0][0]
        second_distance = neighbors[1][0] if len(neighbors) > 1 else best_distance + 1.0
        common_anchors = selected[0][2]
        coverage = min(1.0, len(common_anchors) / max(1, len(self.expected_anchor_ids)))
        distance_quality = math.exp(-best_distance / max(1.0, self.config.max_rssi_distance_db / 2.0))
        separation = min(1.0, max(0.0, (second_distance - best_distance) / max(second_distance, 1.0)))
        values = list(current.values())
        max_age = max(item[2] for item in values)
        freshness = math.exp(-max_age / max(1.0, float(self.config.stale_sample_ms)))
        total_samples = observation_count if observation_count is not None else sum(item[1] for item in values)
        sample_quality = min(1.0, total_samples / max(1.0, self.config.position_min_anchors * 3.0))
        calibration_spread = sum(selected_item[1].mean_spread_db for selected_item in selected) / len(selected)
        calibration_quality = max(0.0, min(1.0, 1.0 - calibration_spread / 20.0))
        confidence = max(
            0.0,
            min(
                1.0,
                0.30 * coverage
                + 0.25 * distance_quality
                + 0.15 * separation
                + 0.10 * freshness
                + 0.10 * sample_quality
                + 0.10 * calibration_quality,
            ),
        )
        validation_p90 = self.validation_metrics.get("p90_error_m")
        if validation_p90 is None:
            validation_p90 = self.config.default_accuracy_radius_m
        match_penalty = best_distance / max(1.0, self.config.max_rssi_distance_db)
        accuracy_radius = max(
            0.25,
            float(validation_p90) * (1.0 + 0.75 * match_penalty)
            + calibration_spread * 0.10
            + best_distance * 0.05,
        )
        diagnostics: list[Diagnostic] = []
        if len(common_anchors) < len(self.expected_anchor_ids):
            diagnostics.append(
                Diagnostic(
                    code="provider_missing_anchor_penalty",
                    message="WKNN applied a penalty for anchors missing from the comparison vector.",
                    details={
                        "anchors_used": list(common_anchors),
                        "expected_anchor_count": len(self.expected_anchor_ids),
                    },
                )
            )
        if confidence < self.config.default_min_confidence:
            diagnostics.append(
                Diagnostic(
                    code="low_position_confidence",
                    message="Position confidence is degraded by match quality or evidence freshness.",
                    details={"confidence": confidence, "best_rssi_distance_db": best_distance},
                )
            )
        return ProviderEstimate(
            x_m=x_m,
            y_m=y_m,
            confidence=confidence,
            accuracy_radius_m=accuracy_radius,
            anchors_used=common_anchors,
            observation_count=total_samples,
            neighbor_distances_db=tuple(item[0] for item in neighbors[: self.config.wknn_k]),
            diagnostics=tuple(diagnostics),
        )
