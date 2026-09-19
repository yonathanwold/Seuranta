from __future__ import annotations

import unittest

from services.positioning.buffer import ObservationBuffer
from services.positioning.config import PositioningConfig
from services.positioning.filtering import RssiFilter
from services.positioning.models import SignalObservation, timestamp_to_iso


def observation(
    observation_id: str,
    anchor_id: str,
    timestamp_ms: int,
    rssi_dbm: float = -50.0,
    sequence_number: int = 1,
) -> SignalObservation:
    return SignalObservation(
        observation_id=observation_id,
        observed_at=timestamp_to_iso(timestamp_ms),
        timestamp_ms=timestamp_ms,
        run_id="run-1",
        deployment_id="deployment-1",
        building_id="building-1",
        floor_id="floor-1",
        anchor_id=anchor_id,
        session_id="session-1",
        rssi_dbm=rssi_dbm,
        channel=1,
        source="test",
        mode="synthetic",
        sequence_number=sequence_number,
    )


class BufferTests(unittest.TestCase):
    def test_duplicate_and_bounded_lateness(self) -> None:
        config = PositioningConfig(max_lateness_ms=100, stale_sample_ms=10_000)
        buffer = ObservationBuffer(config)
        first = observation("a-1", "a", 1_000)
        result = buffer.ingest([first, first])
        self.assertEqual(len(result.accepted), 1)
        self.assertIn("duplicate_observation", {item.code for item in result.diagnostics})

        late = buffer.ingest([observation("a-0", "a", 800)])
        self.assertIn("late_observation_dropped", {item.code for item in late.diagnostics})

    def test_event_time_ordering_and_window(self) -> None:
        config = PositioningConfig(position_window_ms=200, max_lateness_ms=100, stale_sample_ms=10_000)
        buffer = ObservationBuffer(config)
        buffer.ingest(
            [
                observation("a-2", "a", 1_200),
                observation("a-1", "a", 1_000),
                observation("a-3", "a", 1_300),
            ]
        )
        window = buffer.window_for(("run-1", "session-1"))
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual([item.timestamp_ms for item in window.observations], [1_200, 1_300])
        self.assertEqual(window.window_start_ms, 1_200)
        self.assertEqual(window.window_end_ms, 1_300)

    def test_existing_samples_are_removed_when_they_become_stale(self) -> None:
        config = PositioningConfig(position_window_ms=1_000, stale_sample_ms=100, max_lateness_ms=100)
        buffer = ObservationBuffer(config)
        buffer.ingest([observation("a-1", "a", 1_000)])
        buffer.ingest([observation("a-2", "a", 1_500)])
        window = buffer.window_for(("run-1", "session-1"))
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual([item.timestamp_ms for item in window.observations], [1_500])


class FilteringTests(unittest.TestCase):
    def test_median_mad_rejects_extreme_rssi(self) -> None:
        filterer = RssiFilter(PositioningConfig(mad_floor_db=2.0, min_samples_per_anchor=1))
        samples = [
            observation(f"a-{index}", "anchor-a", 1_000 + index, value)
            for index, value in enumerate((-50.0, -51.0, -49.0, -50.0, -100.0))
        ]
        result = filterer.filter(samples)
        filtered = result.anchors["anchor-a"]
        self.assertEqual(filtered.rejected_sample_count, 1)
        self.assertAlmostEqual(filtered.rssi_dbm, -50.0)
        self.assertIn("rssi_outliers_rejected", {item.code for item in result.diagnostics})

    def test_missing_anchor_diagnostic_and_age(self) -> None:
        filterer = RssiFilter()
        result = filterer.filter(
            [observation("a-1", "anchor-a", 1_000, -60.0)],
            expected_anchor_ids=("anchor-a", "anchor-b"),
            now_ms=1_500,
        )
        self.assertEqual(result.missing_anchor_ids, ("anchor-b",))
        self.assertEqual(result.anchors["anchor-a"].age_ms, 500)
        self.assertIn("missing_anchors", {item.code for item in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
