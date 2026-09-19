from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from services.positioning.engine import PositioningEngine
from services.positioning.models import SignalObservation, timestamp_to_iso
from services.positioning.synthetic import generate_scenario, synthetic_fingerprint_set, write_jsonl
from tools.calibration.cli import main as calibration_main


def calibration_observation(index: int, anchor_id: str, rssi_dbm: float) -> SignalObservation:
    timestamp_ms = 1_000 + index * 100
    return SignalObservation(
        observation_id=f"cal-{index}-{anchor_id}",
        observed_at=timestamp_to_iso(timestamp_ms),
        timestamp_ms=timestamp_ms,
        run_id="calibration-run",
        deployment_id="deployment-1",
        building_id="building-1",
        floor_id="floor-1",
        anchor_id=anchor_id,
        session_id="calibration-session",
        rssi_dbm=rssi_dbm,
        channel=1,
        source="calibration",
        mode="synthetic",
        sequence_number=index,
    )


class SyntheticTests(unittest.TestCase):
    def test_scenarios_are_deterministic_and_outlier_is_processable(self) -> None:
        first = generate_scenario("outlier")
        second = generate_scenario("outlier")
        self.assertEqual([item.to_dict() for item in first.observations], [item.to_dict() for item in second.observations])
        self.assertTrue(any(item.rssi_dbm < -140 for item in first.observations))
        engine = PositioningEngine(fingerprints=synthetic_fingerprint_set())
        result = engine.process_observations(first.observations)
        self.assertEqual(len(result.position_estimates), 1)
        self.assertIn("rssi_outliers_rejected", {item.code for item in result.diagnostics})


class CalibrationCliTests(unittest.TestCase):
    def test_define_collect_quality_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="seuranta-calibration-") as directory:
            root = Path(directory)
            plan = root / "plan.json"
            observations = root / "observations.jsonl"
            fingerprints = root / "fingerprints.json"
            write_jsonl(
                (
                    calibration_observation(0, "a", -40.0),
                    calibration_observation(1, "b", -50.0),
                    calibration_observation(2, "c", -60.0),
                ),
                observations,
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    calibration_main(
                        [
                            "define",
                            "--output",
                            str(plan),
                            "--point-id",
                            "p1",
                            "--x-m",
                            "1",
                            "--y-m",
                            "2",
                            "--floor-id",
                            "floor-1",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    calibration_main(
                        [
                            "collect",
                            "--input",
                            str(observations),
                            "--output",
                            str(fingerprints),
                            "--plan",
                            str(plan),
                            "--point-id",
                            "p1",
                        ]
                    ),
                    0,
                )
                self.assertEqual(calibration_main(["quality", "--input", str(fingerprints)]), 0)
                self.assertEqual(calibration_main(["validate", "--input", str(fingerprints)]), 0)
            payload = json.loads(fingerprints.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(payload["points"][0]["point_id"], "p1")


if __name__ == "__main__":
    unittest.main()
