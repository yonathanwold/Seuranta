from __future__ import annotations

from math import hypot, log10

import pytest

from services.positioning.engine import PositioningError, RangeMeasurement, estimate_rssi_position


def measurement(anchor_id: str, x_m: float, y_m: float, target_x: float, target_y: float) -> RangeMeasurement:
    distance = hypot(target_x - x_m, target_y - y_m)
    return RangeMeasurement(anchor_id=anchor_id, x_m=x_m, y_m=y_m,
                            rssi_dbm=-59 - 22 * log10(distance),
                            tx_power_dbm_at_1m=-59, path_loss_exponent=2.2)


def test_multilateration_recovers_a_calibrated_position():
    readings = [
        measurement("pi-1", 0, 0, 2.0, 1.5),
        measurement("pi-2", 6, 0, 2.0, 1.5),
        measurement("pi-3", 0, 4, 2.0, 1.5),
        measurement("pi-4", 6, 4, 2.0, 1.5),
    ]

    result = estimate_rssi_position(readings)

    assert result.x_m == pytest.approx(2.0, abs=0.01)
    assert result.y_m == pytest.approx(1.5, abs=0.01)
    assert result.accuracy_radius_m == pytest.approx(1.5)
    assert result.anchors_used == ("pi-1", "pi-2", "pi-3", "pi-4")


def test_collinear_anchors_are_rejected():
    readings = [
        measurement("pi-1", 0, 0, 2.0, 1.5),
        measurement("pi-2", 3, 0, 2.0, 1.5),
        measurement("pi-3", 6, 0, 2.0, 1.5),
    ]

    with pytest.raises(PositioningError, match="geometry"):
        estimate_rssi_position(readings)
