from __future__ import annotations

import unittest

from services.positioning.calibration import (
    CalibrationError,
    FingerprintPoint,
    FingerprintSet,
    build_fingerprint_point,
    leave_one_point_out_validation,
)
from services.positioning.config import PositioningConfig
from services.positioning.filtering import FilteredAnchor
from services.positioning.models import SignalObservation, timestamp_to_iso
from services.positioning.provider import WknnWifiFingerprintProvider


def sample(anchor_id: str, rssi: float, timestamp_ms: int = 1_000) -> SignalObservation:
    return SignalObservation(
        observation_id=f"{anchor_id}-{timestamp_ms}-{rssi}",
        observed_at=timestamp_to_iso(timestamp_ms),
        timestamp_ms=timestamp_ms,
        run_id="run-1",
        deployment_id="deployment-1",
        building_id="building-1",
        floor_id="floor-1",
        anchor_id=anchor_id,
        session_id="session-1",
        rssi_dbm=rssi,
        channel=1,
        source="calibration",
        mode="synthetic",
        sequence_number=timestamp_ms,
    )


def point(point_id: str, x_m: float, values: dict[str, float]) -> FingerprintPoint:
    return FingerprintPoint(
        point_id=point_id,
        x_m=x_m,
        y_m=0.0,
        floor_id="floor-1",
        anchor_rssi_medians=values,
        sample_counts={anchor_id: 3 for anchor_id in values},
        rssi_spread={anchor_id: 0.0 for anchor_id in values},
    )


def filtered(values: dict[str, float], sample_count: int = 3) -> dict[str, FilteredAnchor]:
    return {
        anchor_id: FilteredAnchor(
            anchor_id=anchor_id,
            rssi_dbm=value,
            sample_count=sample_count,
            raw_sample_count=sample_count,
            rejected_sample_count=0,
            spread_db=0.0,
            oldest_timestamp_ms=1_000,
            newest_timestamp_ms=1_000,
            age_ms=0,
        )
        for anchor_id, value in values.items()
    }


class CalibrationTests(unittest.TestCase):
    def test_build_fingerprint_and_reject_bad_coverage(self) -> None:
        observations = [
            sample("a", -40.0),
            sample("b", -50.0),
            sample("c", -60.0),
        ]
        fingerprint = build_fingerprint_point(
            point_id="p1",
            x_m=1.0,
            y_m=2.0,
            floor_id="floor-1",
            observations=observations,
        )
        self.assertEqual(fingerprint.anchor_ids, ("a", "b", "c"))
        self.assertEqual(fingerprint.sample_counts["a"], 1)

        with self.assertRaises(CalibrationError):
            build_fingerprint_point(
                point_id="bad",
                x_m=0.0,
                y_m=0.0,
                floor_id="floor-1",
                observations=observations[:2],
            )

    def test_leave_one_point_out_reports_error_metrics(self) -> None:
        calibration = FingerprintSet(
            calibration_id="cal-1",
            points=(
                point("p1", 0.0, {"a": -40.0, "b": -50.0, "c": -60.0}),
                point("p2", 10.0, {"a": -60.0, "b": -50.0, "c": -40.0}),
                point("p3", 20.0, {"a": -80.0, "b": -50.0, "c": -20.0}),
            ),
        )
        result = leave_one_point_out_validation(calibration)
        self.assertEqual(result["metrics"]["validated_point_count"], 3.0)
        self.assertIn("median_error_m", result["metrics"])
        self.assertIn("maximum_error_m", result["metrics"])


class ProviderTests(unittest.TestCase):
    def test_exact_fingerprint_match_is_safe(self) -> None:
        provider = WknnWifiFingerprintProvider(
            [point("p1", 4.0, {"a": -40.0, "b": -50.0, "c": -60.0})]
        )
        estimate = provider.estimate(filtered({"a": -40.0, "b": -50.0, "c": -60.0}), floor_id="floor-1")
        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertAlmostEqual(estimate.x_m, 4.0)
        self.assertAlmostEqual(estimate.y_m, 0.0)
        self.assertEqual(estimate.anchors_used, ("a", "b", "c"))

    def test_weighted_interpolation(self) -> None:
        config = PositioningConfig(position_min_anchors=2, wknn_k=2)
        provider = WknnWifiFingerprintProvider(
            [
                point("left", 0.0, {"a": -40.0, "b": -50.0}),
                point("right", 10.0, {"a": -60.0, "b": -70.0}),
            ],
            config=config,
        )
        estimate = provider.estimate(filtered({"a": -50.0, "b": -60.0}), floor_id="floor-1")
        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertAlmostEqual(estimate.x_m, 5.0)

    def test_default_requires_three_anchors_and_missing_penalty_is_diagnostic(self) -> None:
        provider = WknnWifiFingerprintProvider(
            [point("p1", 0.0, {"a": -40.0, "b": -50.0, "c": -60.0})]
        )
        self.assertIsNone(provider.estimate(filtered({"a": -40.0, "b": -50.0}), floor_id="floor-1"))

        permissive = WknnWifiFingerprintProvider(
            [point("p1", 0.0, {"a": -40.0, "b": -50.0, "c": -60.0})],
            config=PositioningConfig(position_min_anchors=2),
        )
        estimate = permissive.estimate(filtered({"a": -40.0, "b": -50.0}), floor_id="floor-1")
        self.assertIsNotNone(estimate)
        assert estimate is not None
        self.assertIn("provider_missing_anchor_penalty", {item.code for item in estimate.diagnostics})


if __name__ == "__main__":
    unittest.main()
