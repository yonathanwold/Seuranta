"""Deterministic synthetic RSSI scenarios for local execution and tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable

from .calibration import FingerprintPoint, FingerprintSet
from .models import SignalObservation, timestamp_to_iso


SYNTHETIC_ANCHORS = {
    "anchor-a": (0.0, 0.0),
    "anchor-b": (10.0, 0.0),
    "anchor-c": (0.0, 10.0),
    "anchor-d": (10.0, 10.0),
}


@dataclass(frozen=True)
class SyntheticScenario:
    name: str
    observations: tuple[SignalObservation, ...]


def synthetic_rssi(x_m: float, y_m: float, anchor_id: str) -> float:
    anchor_x, anchor_y = SYNTHETIC_ANCHORS[anchor_id]
    distance = max(1.0, math.hypot(x_m - anchor_x, y_m - anchor_y))
    return -35.0 - 18.0 * math.log10(distance)


def generate_scenario(
    name: str = "movement",
    *,
    run_id: str = "synthetic-run",
    session_id: str = "synthetic-session",
    start_timestamp_ms: int = 1_700_000_000_000,
) -> SyntheticScenario:
    paths = {
        "movement": ((2.0, 2.0), (2.0, 2.0), (4.0, 2.0), (6.0, 2.0), (8.0, 2.0), (8.0, 2.0)),
        "missing-anchor": ((2.0, 2.0), (4.0, 2.0), (6.0, 2.0)),
        "outlier": ((2.0, 2.0), (2.0, 2.0), (4.0, 2.0)),
    }
    if name not in paths:
        raise ValueError(f"unknown synthetic scenario: {name}")
    observations: list[SignalObservation] = []
    sequence = 0
    for step, (x_m, y_m) in enumerate(paths[name]):
        timestamp_ms = start_timestamp_ms + step * 1_000
        for anchor_id in SYNTHETIC_ANCHORS:
            if name == "missing-anchor" and step == 1 and anchor_id == "anchor-c":
                continue
            value = synthetic_rssi(x_m, y_m, anchor_id)
            if name == "outlier" and step == 1 and anchor_id == "anchor-b":
                value = -145.0
            for sample_index in range(3):
                sequence += 1
                observations.append(
                    SignalObservation(
                        observation_id=f"synthetic-{name}-{step}-{anchor_id}-{sample_index}",
                        observed_at=timestamp_to_iso(timestamp_ms + sample_index * 50),
                        timestamp_ms=timestamp_ms + sample_index * 50,
                        run_id=run_id,
                        deployment_id="synthetic-deployment",
                        building_id="synthetic-building",
                        floor_id="synthetic-floor",
                        anchor_id=anchor_id,
                        session_id=session_id,
                        rssi_dbm=value,
                        channel=1,
                        source="synthetic",
                        mode="synthetic",
                        sequence_number=sequence,
                    )
                )
    return SyntheticScenario(name=name, observations=tuple(observations))


def synthetic_fingerprint_set() -> FingerprintSet:
    points = ((2.0, 2.0), (4.0, 2.0), (6.0, 2.0), (8.0, 2.0))
    fingerprint_points = []
    for index, (x_m, y_m) in enumerate(points):
        medians = {anchor_id: synthetic_rssi(x_m, y_m, anchor_id) for anchor_id in SYNTHETIC_ANCHORS}
        fingerprint_points.append(
            FingerprintPoint(
                point_id=f"synthetic-point-{index + 1}",
                x_m=x_m,
                y_m=y_m,
                floor_id="synthetic-floor",
                anchor_rssi_medians=medians,
                sample_counts={anchor_id: 3 for anchor_id in medians},
                rssi_spread={anchor_id: 0.0 for anchor_id in medians},
                capture_metadata={"source": "deterministic_synthetic_fixture"},
            )
        )
    return FingerprintSet(calibration_id="synthetic-calibration-v1", points=tuple(fingerprint_points))


def write_jsonl(observations: Iterable[SignalObservation], path: str | Path) -> None:
    Path(path).write_text(
        "".join(json.dumps(observation.to_dict(), sort_keys=True) + "\n" for observation in observations),
        encoding="utf-8",
    )
