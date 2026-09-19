"""In-process star-topology positioner.

Each anchor sends observations to the API.  This component groups fresh,
same-session readings by anchor and writes one deterministic position when at
least three calibrated anchors are available.  It is intentionally in-process
for a small four-Pi demo; it can later be replaced by the existing external
positioning forwarder without changing the edge contract.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from services.data.models import AnchorDefinition, Mode, PositionEstimate, SignalObservation, utc_now

from .engine import PositioningError, RangeMeasurement, estimate_rssi_position


@dataclass(frozen=True)
class PositionerStatus:
    enabled: bool
    configured_anchors: int
    emitted: int
    skipped: int
    last_error: str | None


class InternalPositioner:
    def __init__(self, anchors: list[AnchorDefinition], window_seconds: float = 3.0) -> None:
        if len(anchors) < 3:
            raise ValueError("internal positioning needs at least three calibrated anchors")
        if window_seconds <= 0:
            raise ValueError("positioning window must be positive")
        self._anchors = {anchor.anchor_id: anchor for anchor in anchors}
        if len(self._anchors) != len(anchors):
            raise ValueError("positioning anchor IDs must be unique")
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
    def from_json(cls, raw: str, window_seconds: float = 3.0) -> "InternalPositioner":
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
        return cls(anchors, window_seconds)

    @property
    def status(self) -> PositionerStatus:
        return PositionerStatus(enabled=True, configured_anchors=len(self._anchors), emitted=self._emitted,
                                skipped=self._skipped, last_error=self._last_error)

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
            x_m=result.x_m,
            y_m=result.y_m,
            confidence=result.confidence,
            accuracy_radius_m=result.accuracy_radius_m,
            position_method=f"rssi_log_distance_multilateration/{source}",
            smoothing_method="none",
            anchors_used=list(result.anchors_used),
            observation_count=len(observations),
            mode=mode,
            sequence_number=max(item.sequence_number for item in observations),
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
            if len(fresh) < 3:
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
