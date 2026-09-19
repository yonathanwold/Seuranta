from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.positioning.calibration import FingerprintPoint, FingerprintSet
from services.positioning.config import PositioningConfig
from services.positioning.engine import PositioningEngine
from services.positioning.models import SignalObservation, Zone, timestamp_to_iso
from services.positioning.service import PositioningHTTPServer


def observation(observation_id: str, anchor_id: str, timestamp_ms: int, rssi_dbm: float) -> SignalObservation:
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
        source="synthetic",
        mode="synthetic",
        sequence_number=timestamp_ms,
    )


def calibration() -> FingerprintSet:
    return FingerprintSet(
        calibration_id="calibration-1",
        points=(
            FingerprintPoint(
                point_id="point-1",
                x_m=2.0,
                y_m=2.0,
                floor_id="floor-1",
                anchor_rssi_medians={"a": -40.0, "b": -50.0, "c": -60.0},
                sample_counts={"a": 3, "b": 3, "c": 3},
                rssi_spread={"a": 0.0, "b": 0.0, "c": 0.0},
            ),
        ),
    )


class EngineTests(unittest.TestCase):
    def test_synthetic_observations_produce_estimate_and_events(self) -> None:
        zone = Zone(
            zone_id="room-a",
            building_id="building-1",
            floor_id="floor-1",
            name="Room A",
            kind="room",
            polygon=((0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)),
            priority=1,
            entry_confirm_ms=0,
            exit_confirm_ms=0,
            min_confidence=0.0,
            enabled=True,
        )
        engine = PositioningEngine(fingerprints=calibration(), zones=(zone,))
        result = engine.process_observations(
            [
                observation("o-a", "a", 1_000, -40.0),
                observation("o-b", "b", 1_000, -50.0),
                observation("o-c", "c", 1_000, -60.0),
            ]
        )
        self.assertEqual(len(result.position_estimates), 1)
        estimate = result.position_estimates[0]
        self.assertAlmostEqual(estimate.raw_x_m, 2.0)
        self.assertAlmostEqual(estimate.x_m, 2.0)
        self.assertEqual(estimate.zone_id, "room-a")
        self.assertFalse(estimate.is_outside_map)
        self.assertIn("ZONE_ENTERED", {event.event_type for event in result.spatial_events})

    def test_missing_calibration_returns_diagnostic_without_coordinate(self) -> None:
        engine = PositioningEngine()
        result = engine.process_observations(
            [
                observation("o-a", "a", 1_000, -40.0),
                observation("o-b", "b", 1_000, -50.0),
                observation("o-c", "c", 1_000, -60.0),
            ]
        )
        self.assertEqual(result.position_estimates, ())
        self.assertIn("insufficient_position_evidence", {item.code for item in result.diagnostics})


class InternalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = PositioningHTTPServer(("127.0.0.1", 0), PositioningEngine(fingerprints=calibration()))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)

    def test_health_ready_and_batch_validation(self) -> None:
        with urlopen(self.base_url + "/internal/v1/health", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["status"], "ok")
        with urlopen(self.base_url + "/internal/v1/ready", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["ready"])
        request = Request(
            self.base_url + "/internal/v1/observation-batches",
            data=json.dumps({"schema_version": "1.0", "observations": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("diagnostics", payload)
        invalid_request = Request(
            self.base_url + "/internal/v1/observation-batches",
            data=b"{not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(invalid_request, timeout=2)
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
