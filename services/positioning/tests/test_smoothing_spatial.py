from __future__ import annotations

import unittest

from services.positioning.config import PositioningConfig
from services.positioning.models import PositionEstimate, Zone, timestamp_to_iso
from services.positioning.smoothing import EmaSmoother
from services.positioning.spatial import SpatialEngine, point_in_polygon


def position(
    timestamp_ms: int,
    x_m: float,
    y_m: float = 1.0,
    confidence: float = 0.9,
    floor_id: str = "floor-1",
    sequence_number: int = 1,
) -> PositionEstimate:
    iso = timestamp_to_iso(timestamp_ms)
    return PositionEstimate(
        position_id=f"position-{timestamp_ms}-{sequence_number}",
        calculated_at=iso,
        window_start=iso,
        window_end=iso,
        run_id="run-1",
        deployment_id="deployment-1",
        building_id="building-1",
        floor_id=floor_id,
        session_id="session-1",
        raw_x_m=x_m,
        raw_y_m=y_m,
        x_m=x_m,
        y_m=y_m,
        zone_id=None,
        confidence=confidence,
        accuracy_radius_m=1.0,
        position_method="wknn_wifi_fingerprint",
        smoothing_method="ema",
        anchors_used=("a", "b", "c"),
        observation_count=3,
        mode="synthetic",
        sequence_number=sequence_number,
        is_outside_map=False,
    )


def room(
    zone_id: str = "room-a",
    *,
    x_start: float = 0.0,
    x_end: float = 10.0,
    priority: int = 1,
    entry_confirm_ms: int = 1_000,
    exit_confirm_ms: int = 1_000,
    min_confidence: float = 0.5,
) -> Zone:
    return Zone(
        zone_id=zone_id,
        building_id="building-1",
        floor_id="floor-1",
        name=zone_id,
        kind="room",
        polygon=((x_start, 0.0), (x_end, 0.0), (x_end, 10.0), (x_start, 10.0)),
        priority=priority,
        entry_confirm_ms=entry_confirm_ms,
        exit_confirm_ms=exit_confirm_ms,
        min_confidence=min_confidence,
        enabled=True,
    )


class SmoothingTests(unittest.TestCase):
    def test_ema_keeps_raw_and_smoothed_values_distinct(self) -> None:
        smoother = EmaSmoother(PositioningConfig(ema_alpha=0.25, smoothing_reset_gap_ms=10_000))
        first = smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-1", timestamp_ms=0,
            raw_x_m=0.0, raw_y_m=0.0, confidence=1.0,
        )
        second = smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-1", timestamp_ms=1_000,
            raw_x_m=10.0, raw_y_m=0.0, confidence=1.0,
        )
        self.assertEqual(first.x_m, 0.0)
        self.assertAlmostEqual(second.x_m, 2.5)
        self.assertIsNone(second.reset_reason)

    def test_smoothing_resets_after_gap_floor_change_and_reports_jump(self) -> None:
        config = PositioningConfig(
            ema_alpha=0.5,
            smoothing_reset_gap_ms=1_000,
            max_jump_speed_mps=1.0,
        )
        smoother = EmaSmoother(config)
        smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-1", timestamp_ms=0,
            raw_x_m=0.0, raw_y_m=0.0, confidence=1.0,
        )
        jump = smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-1", timestamp_ms=100,
            raw_x_m=10.0, raw_y_m=0.0, confidence=1.0,
        )
        self.assertIn("impossible_movement", {item.code for item in jump.diagnostics})
        self.assertLess(jump.confidence, 1.0)
        gap = smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-1", timestamp_ms=2_000,
            raw_x_m=20.0, raw_y_m=0.0, confidence=1.0,
        )
        self.assertEqual(gap.reset_reason, "long_data_gap")
        floor = smoother.smooth(
            run_id="run-1", session_id="session-1", floor_id="floor-2", timestamp_ms=2_100,
            raw_x_m=1.0, raw_y_m=1.0, confidence=1.0,
        )
        self.assertEqual(floor.reset_reason, "floor_change")


class SpatialTests(unittest.TestCase):
    def test_point_polygon_boundary_and_priority(self) -> None:
        polygon = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
        self.assertTrue(point_in_polygon(5.0, 5.0, polygon))
        self.assertFalse(point_in_polygon(15.0, 5.0, polygon))
        self.assertTrue(point_in_polygon(0.0, 5.0, polygon))
        self.assertFalse(point_in_polygon(0.0, 5.0, polygon, boundary_inside=False))

        engine = SpatialEngine([room("low", priority=1), room("high", priority=2)])
        self.assertEqual(engine.candidate_zone(building_id="building-1", floor_id="floor-1", x_m=5.0, y_m=5.0).zone_id, "high")

    def test_entry_exit_hysteresis_and_noisy_point(self) -> None:
        zone = room(entry_confirm_ms=1_000, exit_confirm_ms=1_000)
        engine = SpatialEngine([zone], config=PositioningConfig(dwell_update_ms=5_000))
        first = engine.process(position(0, 5.0))
        self.assertNotIn("ROOM_ENTERED", {event.event_type for event in first.events})
        noisy_outside = engine.process(position(500, 15.0))
        self.assertNotIn("ROOM_ENTERED", {event.event_type for event in noisy_outside.events})
        sustained = engine.process(position(1_000, 5.0))
        self.assertNotIn("ROOM_ENTERED", {event.event_type for event in sustained.events})
        entered = engine.process(position(2_000, 5.0))
        self.assertIn("ZONE_ENTERED", {event.event_type for event in entered.events})
        self.assertIn("ROOM_ENTERED", {event.event_type for event in entered.events})
        not_yet_exited = engine.process(position(2_500, 15.0))
        self.assertNotIn("ZONE_EXITED", {event.event_type for event in not_yet_exited.events})
        exited = engine.process(position(3_500, 15.0))
        self.assertIn("ZONE_EXITED", {event.event_type for event in exited.events})
        self.assertIn("ROOM_EXITED", {event.event_type for event in exited.events})

    def test_dwell_events_low_confidence_and_timeout(self) -> None:
        zone = room(entry_confirm_ms=0, exit_confirm_ms=0)
        config = PositioningConfig(dwell_update_ms=1_000, session_timeout_ms=2_000)
        engine = SpatialEngine([zone], config=config)
        entered = engine.process(position(0, 5.0))
        self.assertIn("DWELL_STARTED", {event.event_type for event in entered.events})
        updated = engine.process(position(1_000, 5.0))
        self.assertIn("DWELL_UPDATED", {event.event_type for event in updated.events})
        low = engine.process(position(2_000, 15.0, confidence=0.1))
        self.assertIn("low_confidence_zone_transition_suppressed", {item.code for item in low.diagnostics})
        timed_out = engine.expire(now_ms=4_500)
        self.assertIn("DWELL_ENDED", {event.event_type for event in timed_out})
        self.assertIn("SESSION_ENDED", {event.event_type for event in timed_out})


if __name__ == "__main__":
    unittest.main()
