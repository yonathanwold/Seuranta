"""In-process star-topology positioner.

Each anchor sends observations to the API.  This component groups fresh,
same-session readings by anchor and writes one deterministic position when at
least the configured number of calibrated anchors are available.  It is intentionally in-process
for a small four-Pi demo; it can later be replaced by the existing external
positioning forwarder without changing the edge contract.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from services.data.models import AnchorDefinition, Mode, PositionEstimate, SignalObservation, utc_now

from .engine import PositioningError, RangeMeasurement, estimate_rssi_position


@dataclass(frozen=True)
class PositionerStatus:
    enabled: bool
    configured_anchors: int
    minimum_anchors: int
    boundary_configured: bool
    emitted: int
    skipped: int
    last_error: str | None


class InternalPositioner:
    def __init__(self, anchors: list[AnchorDefinition], window_seconds: float = 3.0,
                 minimum_anchors: int = 3, boundary: list[tuple[float, float]] | None = None) -> None:
        if len(anchors) < 3:
            raise ValueError("internal positioning needs at least three calibrated anchors")
        if window_seconds <= 0:
            raise ValueError("positioning window must be positive")
        if not 3 <= minimum_anchors <= len(anchors):
            raise ValueError("positioning minimum anchors must be between three and the configured anchor count")
        self._anchors = {anchor.anchor_id: anchor for anchor in anchors}
        if len(self._anchors) != len(anchors):
            raise ValueError("positioning anchor IDs must be unique")
        self._minimum_anchors = minimum_anchors
        self._boundary = self._validate_boundary(boundary)
        self._window = timedelta(seconds=window_seconds)
        self._recent: dict[tuple[str, str, str, str, str, Mode, str], dict[str, SignalObservation]] = defaultdict(dict)
        self._scan_history: dict[
            tuple[str, str, str, str, str, Mode, str], dict[str, list[SignalObservation]]
        ] = defaultdict(lambda: defaultdict(list))
        self._last_fingerprint: dict[tuple[str, str, str, str, str, Mode, str], tuple[tuple[str, str], ...]] = {}
        self._emitted = 0
        self._skipped = 0
        self._last_error: str | None = None

    @classmethod
    def from_json(cls, raw: str, window_seconds: float = 3.0,
                  minimum_anchors: int = 3) -> "InternalPositioner":
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("SEURANTA_POSITIONING_ANCHORS_JSON must contain valid JSON") from exc
        values = decoded.get("anchors") if isinstance(decoded, dict) else decoded
        if not isinstance(values, list):
            raise ValueError("SEURANTA_POSITIONING_ANCHORS_JSON must be a list or an object with an anchors list")
        try:
            anchors = [AnchorDefinition.model_validate(item) for item in values]
        except Exception as exc:
            raise ValueError("SEURANTA_POSITIONING_ANCHORS_JSON contains an invalid anchor") from exc
        boundary = cls._parse_boundary(decoded.get("boundary")) if isinstance(decoded, dict) else None
        return cls(anchors, window_seconds, minimum_anchors, boundary)

    @property
    def status(self) -> PositionerStatus:
        return PositionerStatus(enabled=True, configured_anchors=len(self._anchors), minimum_anchors=self._minimum_anchors,
                                boundary_configured=self._boundary is not None,
                                emitted=self._emitted,
                                skipped=self._skipped, last_error=self._last_error)

    @staticmethod
    def _parse_boundary(raw: object) -> list[tuple[float, float]] | None:
        if raw is None:
            return None
        if not isinstance(raw, list):
            raise ValueError("positioning boundary must be a list of x_m/y_m points")
        try:
            return [(float(item["x_m"]), float(item["y_m"])) for item in raw if isinstance(item, dict)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("positioning boundary points must contain finite x_m and y_m values") from exc

    @staticmethod
    def _validate_boundary(boundary: list[tuple[float, float]] | None) -> tuple[tuple[float, float], ...] | None:
        if boundary is None:
            return None
        if len(boundary) < 3 or any(not isfinite(x_m) or not isfinite(y_m) for x_m, y_m in boundary):
            raise ValueError("positioning boundary needs at least three finite points")
        return tuple(boundary)

    @staticmethod
    def _key(observation: SignalObservation) -> tuple[str, str, str, str, str, Mode, str]:
        return (observation.run_id, observation.deployment_id, observation.building_id, observation.floor_id,
                observation.session_id, observation.mode, observation.source)

    def _aggregate_scan_observations(
        self, observations: list[SignalObservation]
    ) -> list[tuple[tuple[str, str, str, str, str, Mode, str], SignalObservation]]:
        """Reduce a same-anchor scan to its median RSSI measurement.

        A BLE scan can discover the same consented device several times.  The
        edge agent gives all discoveries from that scan one timestamp, so
        retaining only the final packet would make an estimate depend on an
        arbitrary radio fluctuation.  Keep the newest packet's metadata and
        replace its RSSI with the scan median instead.
        """

        grouped: dict[
            tuple[tuple[str, str, str, str, str, Mode, str], str, datetime],
            list[SignalObservation],
        ] = defaultdict(list)
        for observation in observations:
            if observation.anchor_id in self._anchors:
                grouped[(self._key(observation), observation.anchor_id, observation.observed_at)].append(observation)

        aggregated: list[tuple[tuple[str, str, str, str, str, Mode, str], SignalObservation]] = []
        for (key, _anchor_id, _observed_at), scan in grouped.items():
            representative = max(scan, key=lambda item: (item.sequence_number, item.observation_id))
            median_rssi = int(round(median(item.rssi_dbm for item in scan)))
            if representative.rssi_dbm != median_rssi:
                representative = representative.model_copy(update={"rssi_dbm": median_rssi})
            aggregated.append((key, representative))

        return sorted(aggregated, key=lambda item: item[1].observed_at)

    @staticmethod
    def _aggregate_recent_scans(
        key: tuple[str, str, str, str, str, Mode, str], anchor_id: str, scans: list[SignalObservation]
    ) -> SignalObservation:
        """Produce one stable RSSI input from an anchor's recent scans."""

        representative = max(scans, key=lambda item: (item.observed_at, item.sequence_number, item.observation_id))
        scan_ids = ":".join(sorted(item.observation_id for item in scans))
        aggregate_id = str(uuid5(NAMESPACE_URL, f"seuranta-rssi-window:{key}:{anchor_id}:{scan_ids}"))
        return representative.model_copy(update={
            "observation_id": aggregate_id,
            "rssi_dbm": int(round(median(item.rssi_dbm for item in scans))),
        })

    @staticmethod
    def _point_on_segment(x_m: float, y_m: float, start: tuple[float, float], end: tuple[float, float]) -> bool:
        start_x, start_y = start
        end_x, end_y = end
        cross = (x_m - start_x) * (end_y - start_y) - (y_m - start_y) * (end_x - start_x)
        if abs(cross) > 1e-9:
            return False
        return (min(start_x, end_x) - 1e-9 <= x_m <= max(start_x, end_x) + 1e-9
                and min(start_y, end_y) - 1e-9 <= y_m <= max(start_y, end_y) + 1e-9)

    @classmethod
    def _inside_boundary(cls, x_m: float, y_m: float, boundary: tuple[tuple[float, float], ...]) -> bool:
        inside = False
        previous = boundary[-1]
        for current in boundary:
            if cls._point_on_segment(x_m, y_m, previous, current):
                return True
            current_x, current_y = current
            previous_x, previous_y = previous
            crosses = (current_y > y_m) != (previous_y > y_m)
            if crosses and x_m < (previous_x - current_x) * (y_m - current_y) / (previous_y - current_y) + current_x:
                inside = not inside
            previous = current
        return inside

    @staticmethod
    def _nearest_boundary_point(x_m: float, y_m: float,
                                boundary: tuple[tuple[float, float], ...]) -> tuple[float, float]:
        nearest: tuple[float, float] | None = None
        nearest_distance_sq = float("inf")
        previous = boundary[-1]
        for current in boundary:
            start_x, start_y = previous
            end_x, end_y = current
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            length_sq = delta_x ** 2 + delta_y ** 2
            progress = 0.0 if length_sq == 0 else ((x_m - start_x) * delta_x + (y_m - start_y) * delta_y) / length_sq
            progress = max(0.0, min(1.0, progress))
            candidate = (start_x + progress * delta_x, start_y + progress * delta_y)
            distance_sq = (x_m - candidate[0]) ** 2 + (y_m - candidate[1]) ** 2
            if distance_sq < nearest_distance_sq:
                nearest, nearest_distance_sq = candidate, distance_sq
            previous = current
        assert nearest is not None
        return nearest

    def _constrain_to_boundary(self, x_m: float, y_m: float) -> tuple[float, float, bool]:
        if self._boundary is None or self._inside_boundary(x_m, y_m, self._boundary):
            return x_m, y_m, False
        constrained_x, constrained_y = self._nearest_boundary_point(x_m, y_m, self._boundary)
        return constrained_x, constrained_y, True

    def _estimate(self, key: tuple[str, str, str, str, str, Mode, str],
                  observations: list[SignalObservation]) -> PositionEstimate:
        run_id, deployment_id, building_id, floor_id, session_id, mode, source = key
        readings = [
            RangeMeasurement(anchor_id=item.anchor_id, x_m=self._anchors[item.anchor_id].x_m,
                             y_m=self._anchors[item.anchor_id].y_m, rssi_dbm=item.rssi_dbm,
                             tx_power_dbm_at_1m=self._anchors[item.anchor_id].tx_power_dbm_at_1m,
                             path_loss_exponent=self._anchors[item.anchor_id].path_loss_exponent)
            for item in observations
        ]
        result = estimate_rssi_position(readings)
        x_m, y_m, is_outside_map = self._constrain_to_boundary(result.x_m, result.y_m)
        fingerprint = ":".join(f"{item.anchor_id}={item.observation_id}" for item in sorted(observations, key=lambda item: item.anchor_id))
        position_id = str(uuid5(NAMESPACE_URL, f"seuranta-position:{run_id}:{deployment_id}:{building_id}:{floor_id}:{session_id}:{source}:{fingerprint}"))
        return PositionEstimate(
            position_id=position_id,
            calculated_at=utc_now(),
            window_start=min(item.observed_at for item in observations),
            window_end=max(item.observed_at for item in observations),
            run_id=run_id,
            deployment_id=deployment_id,
            building_id=building_id,
            floor_id=floor_id,
            session_id=session_id,
            raw_x_m=result.x_m,
            raw_y_m=result.y_m,
            x_m=x_m,
            y_m=y_m,
            confidence=result.confidence,
            accuracy_radius_m=result.accuracy_radius_m,
            position_method=f"rssi_log_distance_multilateration/{source}",
            smoothing_method="median_rssi_scan_window",
            anchors_used=list(result.anchors_used),
            observation_count=len(observations),
            mode=mode,
            sequence_number=max(item.sequence_number for item in observations),
            is_outside_map=is_outside_map,
        )

    def ingest(self, observations: list[SignalObservation]) -> list[PositionEstimate]:
        changed: set[tuple[str, str, str, str, str, Mode, str]] = set()
        for key, observation in self._aggregate_scan_observations(observations):
            current = self._recent[key].get(observation.anchor_id)
            if current is None or observation.observed_at >= current.observed_at:
                self._recent[key][observation.anchor_id] = observation
                history = self._scan_history[key][observation.anchor_id]
                history[:] = [item for item in history if item.observed_at != observation.observed_at]
                history.append(observation)
                history.sort(key=lambda item: item.observed_at)
                changed.add(key)

        positions: list[PositionEstimate] = []
        for key in changed:
            per_anchor = self._recent[key]
            latest_at = max(item.observed_at for item in per_anchor.values())
            fresh = []
            for anchor_id in per_anchor:
                scans = [
                    item for item in self._scan_history[key][anchor_id]
                    if latest_at - item.observed_at <= self._window
                ]
                if scans:
                    fresh.append(self._aggregate_recent_scans(key, anchor_id, scans))
            if len(fresh) < self._minimum_anchors:
                self._skipped += 1
                continue
            fingerprint = tuple(sorted((item.anchor_id, item.observation_id) for item in fresh))
            if self._last_fingerprint.get(key) == fingerprint:
                continue
            try:
                position = self._estimate(key, fresh)
            except PositioningError as exc:
                self._skipped += 1
                self._last_error = str(exc)
                continue
            self._last_fingerprint[key] = fingerprint
            self._emitted += 1
            self._last_error = None
            positions.append(position)

        self._discard_stale()
        return positions

    def _discard_stale(self) -> None:
        cutoff = utc_now() - self._window * 2
        for key, per_anchor in list(self._scan_history.items()):
            for anchor_id, history in list(per_anchor.items()):
                per_anchor[anchor_id] = [item for item in history if item.observed_at >= cutoff]
                if not per_anchor[anchor_id]:
                    del per_anchor[anchor_id]
            if not per_anchor:
                del self._scan_history[key]
        for key, per_anchor in list(self._recent.items()):
            for anchor_id, observation in list(per_anchor.items()):
                if observation.observed_at < cutoff:
                    del per_anchor[anchor_id]
            if not per_anchor:
                del self._recent[key]
                if key not in self._scan_history:
                    self._last_fingerprint.pop(key, None)
