"""Accuracy-aware exponential smoothing for phone positions."""

from __future__ import annotations

import math
from dataclasses import dataclass


def alpha_for_accuracy(accuracy_m: float) -> float:
    """Choose a responsive EMA weight while respecting poor GPS accuracy."""

    if accuracy_m <= 4.0:
        return 0.40
    if accuracy_m <= 8.0:
        return 0.20
    return 0.08


def confidence_from_accuracy(accuracy_m: float) -> float:
    """Map reported horizontal accuracy to a bounded, honest confidence.

    This is a UI/normalization signal, not a probability that the point is
    correct.  It deliberately remains below 1 for every non-zero accuracy.
    """

    if not math.isfinite(accuracy_m) or accuracy_m < 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 / (1.0 + accuracy_m / 25.0)))


@dataclass
class ExponentialSmoother:
    x_m: float | None = None
    y_m: float | None = None

    def reset(self) -> None:
        self.x_m = None
        self.y_m = None

    def update(self, x_m: float, y_m: float, accuracy_m: float) -> tuple[float, float]:
        if self.x_m is None or self.y_m is None:
            self.x_m = x_m
            self.y_m = y_m
            return x_m, y_m
        alpha = alpha_for_accuracy(accuracy_m)
        self.x_m = alpha * x_m + (1.0 - alpha) * self.x_m
        self.y_m = alpha * y_m + (1.0 - alpha) * self.y_m
        return self.x_m, self.y_m
