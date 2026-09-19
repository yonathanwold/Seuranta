"""Robust RSSI aggregation and diagnostics."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import math
from statistics import median
from typing import Iterable, Mapping

from .config import PositioningConfig
from .models import Diagnostic, SignalObservation


@dataclass(frozen=True)
class FilteredAnchor:
    anchor_id: str
    rssi_dbm: float
    sample_count: int
    raw_sample_count: int
    rejected_sample_count: int
    spread_db: float
    oldest_timestamp_ms: int
    newest_timestamp_ms: int
    age_ms: int


@dataclass(frozen=True)
class FilterResult:
    anchors: Mapping[str, FilteredAnchor]
    missing_anchor_ids: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
    observation_count: int


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


class RssiFilter:
    """Aggregate a window with median/MAD rejection.

    A small rolling history is retained per run/session/anchor so calls that
    contain only a few samples still have stable medians, while the current
    window remains the source of sample-age and observation-count metrics.
    """

    def __init__(self, config: PositioningConfig | None = None) -> None:
        self.config = config or PositioningConfig()
        self._rolling: dict[tuple[str, str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=self.config.rolling_median_size)
        )

    def filter(
        self,
        observations: Iterable[SignalObservation],
        *,
        expected_anchor_ids: Iterable[str] | None = None,
        now_ms: int | None = None,
    ) -> FilterResult:
        grouped: dict[str, list[SignalObservation]] = defaultdict(list)
        observation_list = list(observations)
        for observation in observation_list:
            if not math.isfinite(observation.rssi_dbm):
                continue
            grouped[observation.anchor_id].append(observation)
        diagnostics: list[Diagnostic] = []
        result: dict[str, FilteredAnchor] = {}
        reference_ms = now_ms
        if reference_ms is None and observation_list:
            reference_ms = max(item.timestamp_ms for item in observation_list)
        reference_ms = reference_ms or 0
        for anchor_id, samples in sorted(grouped.items()):
            values = [item.rssi_dbm for item in samples]
            local_median = median(values)
            deviations = [abs(value - local_median) for value in values]
            mad = median(deviations) if deviations else 0.0
            threshold = max(self.config.mad_floor_db, self.config.mad_threshold * 1.4826 * mad)
            retained = [item for item in samples if abs(item.rssi_dbm - local_median) <= threshold]
            rejected_count = len(samples) - len(retained)
            if rejected_count:
                diagnostics.append(
                    Diagnostic(
                        code="rssi_outliers_rejected",
                        message="Extreme RSSI samples were rejected by the median/MAD filter.",
                        run_id=samples[0].run_id,
                        session_id=samples[0].session_id,
                        details={
                            "anchor_id": anchor_id,
                            "raw_sample_count": len(samples),
                            "rejected_sample_count": rejected_count,
                            "mad_db": mad,
                        },
                    )
                )
            if len(retained) < self.config.min_samples_per_anchor:
                diagnostics.append(
                    Diagnostic(
                        code="anchor_insufficient_samples",
                        message="Anchor did not provide enough usable RSSI samples.",
                        run_id=samples[0].run_id,
                        session_id=samples[0].session_id,
                        details={"anchor_id": anchor_id, "sample_count": len(retained)},
                    )
                )
                continue
            retained_values = [item.rssi_dbm for item in retained]
            smoothed_key = (samples[0].run_id, samples[0].session_id, anchor_id)
            rolling = self._rolling[smoothed_key]
            rolling.extend(retained_values)
            aggregate_values = list(rolling)
            aggregate = float(median(aggregate_values))
            timestamps = [item.timestamp_ms for item in retained]
            spread = _percentile(retained_values, 0.75) - _percentile(retained_values, 0.25)
            newest = max(timestamps)
            oldest = min(timestamps)
            age = max(0, reference_ms - newest)
            result[anchor_id] = FilteredAnchor(
                anchor_id=anchor_id,
                rssi_dbm=aggregate,
                sample_count=len(retained),
                raw_sample_count=len(samples),
                rejected_sample_count=rejected_count,
                spread_db=float(spread),
                oldest_timestamp_ms=oldest,
                newest_timestamp_ms=newest,
                age_ms=age,
            )
        if expected_anchor_ids is not None:
            expected = set(expected_anchor_ids)
            missing = tuple(sorted(expected - set(result)))
        else:
            missing = ()
        if missing:
            diagnostics.append(
                Diagnostic(
                    code="missing_anchors",
                    message="Expected anchors were not present in the usable RSSI window.",
                    run_id=observation_list[0].run_id if observation_list else None,
                    session_id=observation_list[0].session_id if observation_list else None,
                    details={"missing_anchor_ids": list(missing)},
                )
            )
        if not result:
            diagnostics.append(
                Diagnostic(
                    code="no_usable_rssi",
                    message="No usable RSSI samples remain after filtering.",
                    run_id=observation_list[0].run_id if observation_list else None,
                    session_id=observation_list[0].session_id if observation_list else None,
                )
            )
        return FilterResult(result, missing, tuple(diagnostics), len(observation_list))
