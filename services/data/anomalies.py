"""Deterministic anomaly detectors for local fallback operation."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .models import Anomaly, Mode, utc_now
from .store import LocalStore


def detect_anomalies(store: LocalStore, run_id: str, deployment_id: str, building_id: str,
                     floor_id: str, mode: Mode) -> list[Anomaly]:
    now = utc_now()
    observations = store.list_observations(run_id, deployment_id, building_id, floor_id, 10000)
    positions = store.list_positions(run_id, deployment_id, building_id, floor_id, 10000)
    events = store.list_events(run_id, deployment_id, building_id, floor_id, 10000)
    nodes = store.list_nodes(run_id, deployment_id, building_id, floor_id)
    result: list[Anomaly] = []

    for node in nodes:
        emitted = datetime.fromisoformat(node["emitted_at"].replace("Z", "+00:00"))
        if node.get("status") == "offline" or (now - emitted) > timedelta(seconds=90):
            result.append(Anomaly(anomaly_type="anchor_offline", severity="critical", run_id=run_id,
                                  deployment_id=deployment_id, building_id=building_id, floor_id=floor_id,
                                  mode=mode, anchor_id=node.get("anchor_id"), title="Anchor offline",
                                  description=f"Anchor {node.get('anchor_id')} is offline or has not sent a heartbeat recently.",
                                  confidence=0.95, detector="local.anchor_health"))
        if any(code.startswith("CALIBRATION") for code in node.get("error_codes", [])):
            result.append(Anomaly(anomaly_type="calibration_degraded", severity="warning", run_id=run_id,
                                  deployment_id=deployment_id, building_id=building_id, floor_id=floor_id,
                                  mode=mode, anchor_id=node.get("anchor_id"), title="Calibration degraded",
                                  description="A node reported a calibration diagnostic error.", confidence=0.9,
                                  detector="local.heartbeat_diagnostics"))

    if observations:
        latest = max(datetime.fromisoformat(o["observed_at"].replace("Z", "+00:00")) for o in observations)
        if now - latest > timedelta(minutes=2):
            result.append(Anomaly(anomaly_type="data_gap", severity="warning", run_id=run_id,
                                  deployment_id=deployment_id, building_id=building_id, floor_id=floor_id,
                                  mode=mode, observed_value=(now - latest).total_seconds(), threshold=120,
                                  title="Telemetry data gap", description="No observations have arrived for over two minutes.",
                                  confidence=0.92, detector="local.ingestion_liveness"))

    recent_cutoff = now - timedelta(minutes=1)
    recent_events = [e for e in events if datetime.fromisoformat(e["occurred_at"].replace("Z", "+00:00")) >= recent_cutoff]
    if len(recent_events) > 100:
        result.append(Anomaly(anomaly_type="traffic_spike", severity="warning", run_id=run_id,
                              deployment_id=deployment_id, building_id=building_id, floor_id=floor_id, mode=mode,
                              observed_value=len(recent_events), threshold=100, title="Traffic spike",
                              description="Event rate exceeded the deterministic local threshold.", confidence=0.85,
                              detector="local.event_rate"))

    by_zone: dict[str, int] = {}
    for position in positions:
        if position.get("zone_id"):
            by_zone[position["zone_id"]] = by_zone.get(position["zone_id"], 0) + 1
    for zone_id, count in by_zone.items():
        if count > 25:
            result.append(Anomaly(anomaly_type="zone_congestion", severity="warning", run_id=run_id,
                                  deployment_id=deployment_id, building_id=building_id, floor_id=floor_id,
                                  mode=mode, zone_id=zone_id, observed_value=count, threshold=25,
                                  title="Zone congestion", description=f"Zone {zone_id} has unusually high position density.",
                                  confidence=0.8, detector="local.zone_occupancy"))

    by_session: dict[str, list[dict]] = {}
    for position in positions:
        by_session.setdefault(position["session_id"], []).append(position)
    for session_id, items in by_session.items():
        items.sort(key=lambda p: p["calculated_at"])
        for before, after in zip(items, items[1:]):
            t0 = datetime.fromisoformat(before["calculated_at"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(after["calculated_at"].replace("Z", "+00:00"))
            seconds = (t1 - t0).total_seconds()
            distance = math.hypot(after["x_m"] - before["x_m"], after["y_m"] - before["y_m"])
            if 0 <= seconds <= 1 and distance > 50:
                result.append(Anomaly(anomaly_type="impossible_movement", severity="warning", run_id=run_id,
                                      deployment_id=deployment_id, building_id=building_id, floor_id=floor_id,
                                      mode=mode, session_id=session_id, observed_value=distance, threshold=50,
                                      title="Impossible movement", description="A session moved over 50 metres in one second.",
                                      confidence=0.75, detector="local.position_physics"))
                break

    for anomaly in result:
        key = ":".join((anomaly.run_id, anomaly.building_id or "", anomaly.floor_id or "", anomaly.anomaly_type,
                         anomaly.anchor_id or "", anomaly.zone_id or "", anomaly.session_id or ""))
        anomaly.anomaly_id = str(uuid5(NAMESPACE_URL, f"seuranta:{key}"))
        store.upsert_anomaly(anomaly)
    return result
