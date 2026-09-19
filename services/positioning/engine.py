"""Dependency-free RSSI multilateration for a single two-dimensional floor.

RSSI is inherently noisy, so this module deliberately reports a conservative
accuracy radius rather than presenting an RSSI result as a precise coordinate.
It uses a log-distance path-loss model followed by robust Gauss-Newton
refinement.  The caller owns calibration: each anchor needs a measured RSSI at
one metre and a path-loss exponent suited to the room.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, sqrt
from typing import Iterable


class PositioningError(ValueError):
    """The supplied measurements cannot form a reliable 2D estimate."""


@dataclass(frozen=True)
class RangeMeasurement:
    anchor_id: str
    x_m: float
    y_m: float
    rssi_dbm: float
    tx_power_dbm_at_1m: float
    path_loss_exponent: float

    @property
    def distance_m(self) -> float:
        # The bounds prevent a single bad RSSI sample from destabilising the
        # solver while preserving a very broad indoor operating range.
        distance = 10 ** ((self.tx_power_dbm_at_1m - self.rssi_dbm) / (10 * self.path_loss_exponent))
        return min(100.0, max(0.25, distance))


@dataclass(frozen=True)
class RssiPosition:
    x_m: float
    y_m: float
    accuracy_radius_m: float
    confidence: float
    residual_rms_m: float
    anchors_used: tuple[str, ...]


def _solve_2x2(a11: float, a12: float, a22: float, b1: float, b2: float) -> tuple[float, float, float]:
    determinant = a11 * a22 - a12 * a12
    scale = max(abs(a11 * a22), abs(a12 * a12), 1.0)
    if abs(determinant) < scale * 1e-9:
        raise PositioningError("anchor geometry is collinear or too weak for a 2D estimate")
    return ((a22 * b1 - a12 * b2) / determinant,
            (a11 * b2 - a12 * b1) / determinant,
            determinant)


def _base_weight(measurement: RangeMeasurement) -> float:
    # Farther RSSI-derived ranges are less useful; no measurement is discarded
    # solely because it is far away.
    return 1.0 / max(1.0, measurement.distance_m) ** 2


def _linear_seed(measurements: list[RangeMeasurement]) -> tuple[float, float]:
    reference = measurements[0]
    reference_distance = reference.distance_m
    a11 = a12 = a22 = b1 = b2 = 0.0
    for measurement in measurements[1:]:
        row_x = 2.0 * (measurement.x_m - reference.x_m)
        row_y = 2.0 * (measurement.y_m - reference.y_m)
        right = (measurement.x_m ** 2 + measurement.y_m ** 2 - reference.x_m ** 2 - reference.y_m ** 2
                 - measurement.distance_m ** 2 + reference_distance ** 2)
        weight = _base_weight(measurement)
        a11 += weight * row_x * row_x
        a12 += weight * row_x * row_y
        a22 += weight * row_y * row_y
        b1 += weight * row_x * right
        b2 += weight * row_y * right
    x_m, y_m, _ = _solve_2x2(a11, a12, a22, b1, b2)
    return x_m, y_m


def _refine(x_m: float, y_m: float, measurements: list[RangeMeasurement]) -> tuple[float, float, float]:
    """Robustly minimise range residuals and return x, y, and RMS."""
    for _ in range(10):
        a11 = a12 = a22 = b1 = b2 = squared_error = 0.0
        for measurement in measurements:
            dx = x_m - measurement.x_m
            dy = y_m - measurement.y_m
            range_at_point = max(hypot(dx, dy), 0.05)
            residual = range_at_point - measurement.distance_m
            # Huber-like down-weighting means a reflected/multipath reading
            # cannot completely drag the result to a distant anchor.
            robust_weight = 1.0 / max(1.0, abs(residual) / 3.0)
            weight = _base_weight(measurement) * robust_weight
            jacobian_x = dx / range_at_point
            jacobian_y = dy / range_at_point
            a11 += weight * jacobian_x * jacobian_x
            a12 += weight * jacobian_x * jacobian_y
            a22 += weight * jacobian_y * jacobian_y
            b1 += weight * jacobian_x * residual
            b2 += weight * jacobian_y * residual
            squared_error += residual ** 2
        delta_x, delta_y, _ = _solve_2x2(a11, a12, a22, b1, b2)
        x_m -= delta_x
        y_m -= delta_y
        if hypot(delta_x, delta_y) < 0.001:
            break

    residuals = [hypot(x_m - item.x_m, y_m - item.y_m) - item.distance_m for item in measurements]
    rms = sqrt(sum(residual * residual for residual in residuals) / len(residuals))
    return x_m, y_m, rms


def _minimum_anchor_spread(measurements: list[RangeMeasurement]) -> float:
    """Return the smallest standard deviation of the anchor layout in metres."""
    mean_x = sum(item.x_m for item in measurements) / len(measurements)
    mean_y = sum(item.y_m for item in measurements) / len(measurements)
    variance_x = sum((item.x_m - mean_x) ** 2 for item in measurements) / len(measurements)
    variance_y = sum((item.y_m - mean_y) ** 2 for item in measurements) / len(measurements)
    covariance = sum((item.x_m - mean_x) * (item.y_m - mean_y) for item in measurements) / len(measurements)
    trace = variance_x + variance_y
    smallest_eigenvalue = max(0.0, (trace - sqrt(max(0.0, (variance_x - variance_y) ** 2 + 4 * covariance ** 2))) / 2)
    return sqrt(smallest_eigenvalue)


def estimate_rssi_position(measurements: Iterable[RangeMeasurement]) -> RssiPosition:
    """Estimate a 2D position from at least three calibrated RSSI readings."""
    usable = list(measurements)
    anchor_ids = [item.anchor_id for item in usable]
    if len(usable) < 3:
        raise PositioningError("at least three anchor measurements are required")
    if len(anchor_ids) != len(set(anchor_ids)):
        raise PositioningError("anchor measurements must use unique anchor IDs")

    x_m, y_m = _linear_seed(usable)
    x_m, y_m, rms = _refine(x_m, y_m, usable)

    # Treat RSSI as a low-precision ranging method even for a perfect synthetic
    # fit.  The geometry term grows when anchors occupy a narrow strip; 1.5 m
    # is a deliberately conservative best-case radius for a well-spread room.
    minimum_spread_m = _minimum_anchor_spread(usable)
    geometry_penalty_m = 1.5 * max(1.0, 2.0 / max(minimum_spread_m, 0.1))
    accuracy_radius_m = max(1.5, rms * 1.5, geometry_penalty_m)
    confidence = max(0.05, min(0.95, (len(usable) / 4.0) * (1.0 / (1.0 + accuracy_radius_m / 3.0))))

    return RssiPosition(x_m=x_m, y_m=y_m, accuracy_radius_m=accuracy_radius_m,
                        confidence=confidence, residual_rms_m=rms,
                        anchors_used=tuple(sorted(anchor_ids)))
