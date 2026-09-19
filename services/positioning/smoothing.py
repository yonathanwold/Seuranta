"""Temporal smoothing and impossible-movement detection."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .config import PositioningConfig
from .models import Diagnostic


SessionKey = tuple[str, str]


@dataclass(frozen=True)
class SmoothingResult:
    x_m: float
    y_m: float
    confidence: float
    smoothing_method: str
    reset_reason: str | None
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass
class _SmoothingState:
    x_m: float
    y_m: float
    timestamp_ms: int
    floor_id: str


class EmaSmoother:
    """Apply an EMA independently per run/session and reset at context breaks."""

    method_name = "ema"

    def __init__(self, config: PositioningConfig | None = None) -> None:
        self.config = config or PositioningConfig()
        self._states: dict[SessionKey, _SmoothingState] = {}

    def smooth(
        self,
        *,
        run_id: str,
        session_id: str,
        floor_id: str,
        timestamp_ms: int,
        raw_x_m: float,
        raw_y_m: float,
        confidence: float,
    ) -> SmoothingResult:
        key = (run_id, session_id)
        previous = self._states.get(key)
        reset_reason: str | None = None
        diagnostics: list[Diagnostic] = []
        effective_confidence = max(0.0, min(1.0, confidence))
        if previous is None:
            reset_reason = "new_session_or_run"
            smoothed_x, smoothed_y = raw_x_m, raw_y_m
        elif previous.floor_id != floor_id:
            reset_reason = "floor_change"
            smoothed_x, smoothed_y = raw_x_m, raw_y_m
        elif timestamp_ms - previous.timestamp_ms > self.config.smoothing_reset_gap_ms:
            reset_reason = "long_data_gap"
            smoothed_x, smoothed_y = raw_x_m, raw_y_m
        else:
            delta_ms = timestamp_ms - previous.timestamp_ms
            distance = math.hypot(raw_x_m - previous.x_m, raw_y_m - previous.y_m)
            if delta_ms <= 0:
                speed_mps = float("inf") if distance > 0.0 else 0.0
            else:
                speed_mps = distance / (delta_ms / 1000.0)
            if speed_mps > self.config.max_jump_speed_mps:
                ratio = min(1.0, self.config.max_jump_speed_mps / max(speed_mps, 1e-9))
                effective_confidence *= ratio
                diagnostics.append(
                    Diagnostic(
                        code="impossible_movement",
                        message="Raw position implies an implausibly fast movement; confidence was reduced.",
                        run_id=run_id,
                        session_id=session_id,
                        details={
                            "speed_mps": speed_mps,
                            "max_jump_speed_mps": self.config.max_jump_speed_mps,
                            "distance_m": distance,
                        },
                    )
                )
            alpha = self.config.ema_alpha
            smoothed_x = alpha * raw_x_m + (1.0 - alpha) * previous.x_m
            smoothed_y = alpha * raw_y_m + (1.0 - alpha) * previous.y_m
        self._states[key] = _SmoothingState(smoothed_x, smoothed_y, timestamp_ms, floor_id)
        return SmoothingResult(
            x_m=smoothed_x,
            y_m=smoothed_y,
            confidence=effective_confidence,
            smoothing_method=self.method_name,
            reset_reason=reset_reason,
            diagnostics=tuple(diagnostics),
        )

    def reset(self, *, run_id: str, session_id: str) -> None:
        self._states.pop((run_id, session_id), None)

    def clear(self) -> None:
        self._states.clear()
