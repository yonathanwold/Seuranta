"""Configuration for the positioning and spatial pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


@dataclass(frozen=True)
class PositioningConfig:
    position_window_ms: int = 5_000
    position_min_anchors: int = 3
    max_lateness_ms: int = 1_000
    stale_sample_ms: int = 30_000
    rolling_median_size: int = 7
    mad_threshold: float = 3.5
    mad_floor_db: float = 2.0
    min_samples_per_anchor: int = 1
    wknn_k: int = 3
    missing_anchor_penalty_db: float = 8.0
    distance_epsilon: float = 1e-6
    max_rssi_distance_db: float = 40.0
    ema_alpha: float = 0.35
    smoothing_reset_gap_ms: int = 15_000
    max_jump_speed_mps: float = 8.0
    default_accuracy_radius_m: float = 8.0
    default_entry_confirm_ms: int = 750
    default_exit_confirm_ms: int = 750
    default_min_confidence: float = 0.35
    dwell_update_ms: int = 5_000
    session_timeout_ms: int = 60_000

    def __post_init__(self) -> None:
        integer_fields = (
            "position_window_ms",
            "position_min_anchors",
            "max_lateness_ms",
            "stale_sample_ms",
            "rolling_median_size",
            "min_samples_per_anchor",
            "wknn_k",
            "smoothing_reset_gap_ms",
            "dwell_update_ms",
            "session_timeout_ms",
        )
        for name in integer_fields:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.position_min_anchors < 1:
            raise ValueError("position_min_anchors must be at least one")
        if self.rolling_median_size < 1:
            raise ValueError("rolling_median_size must be at least one")
        if self.wknn_k < 1:
            raise ValueError("wknn_k must be at least one")
        if not 0.0 < self.ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be greater than zero and at most one")
        if not 0.0 <= self.default_min_confidence <= 1.0:
            raise ValueError("default_min_confidence must be between zero and one")
        if self.max_jump_speed_mps <= 0.0:
            raise ValueError("max_jump_speed_mps must be positive")

    @classmethod
    def from_env(cls) -> "PositioningConfig":
        """Read only positioning-owned environment variables."""

        return cls(
            position_window_ms=_env_int("POSITION_WINDOW_MS", cls.position_window_ms),
            position_min_anchors=_env_int("POSITION_MIN_ANCHORS", cls.position_min_anchors),
            max_lateness_ms=_env_int("POSITION_MAX_LATENESS_MS", cls.max_lateness_ms),
            stale_sample_ms=_env_int("POSITION_STALE_SAMPLE_MS", cls.stale_sample_ms),
            rolling_median_size=_env_int("RSSI_ROLLING_MEDIAN_SIZE", cls.rolling_median_size),
            mad_threshold=_env_float("RSSI_MAD_THRESHOLD", cls.mad_threshold),
            mad_floor_db=_env_float("RSSI_MAD_FLOOR_DB", cls.mad_floor_db),
            min_samples_per_anchor=_env_int("RSSI_MIN_SAMPLES_PER_ANCHOR", cls.min_samples_per_anchor),
            wknn_k=_env_int("WKNN_K", cls.wknn_k),
            missing_anchor_penalty_db=_env_float("WKNN_MISSING_ANCHOR_PENALTY_DB", cls.missing_anchor_penalty_db),
            distance_epsilon=_env_float("WKNN_DISTANCE_EPSILON", cls.distance_epsilon),
            max_rssi_distance_db=_env_float("WKNN_MAX_RSSI_DISTANCE_DB", cls.max_rssi_distance_db),
            ema_alpha=_env_float("EMA_ALPHA", cls.ema_alpha),
            smoothing_reset_gap_ms=_env_int("EMA_RESET_GAP_MS", cls.smoothing_reset_gap_ms),
            max_jump_speed_mps=_env_float("POSITION_MAX_JUMP_SPEED_MPS", cls.max_jump_speed_mps),
            default_accuracy_radius_m=_env_float("POSITION_DEFAULT_ACCURACY_RADIUS_M", cls.default_accuracy_radius_m),
            default_entry_confirm_ms=_env_int("ZONE_ENTRY_CONFIRM_MS", cls.default_entry_confirm_ms),
            default_exit_confirm_ms=_env_int("ZONE_EXIT_CONFIRM_MS", cls.default_exit_confirm_ms),
            default_min_confidence=_env_float("ZONE_MIN_CONFIDENCE", cls.default_min_confidence),
            dwell_update_ms=_env_int("DWELL_UPDATE_MS", cls.dwell_update_ms),
            session_timeout_ms=_env_int("SESSION_TIMEOUT_MS", cls.session_timeout_ms),
        )
