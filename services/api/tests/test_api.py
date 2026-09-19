from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.main import app


def observation(observation_id: str = "o-1", sequence: int = 1) -> dict:
    return {
        "observation_id": observation_id,
        "observed_at": "2026-01-01T12:00:00Z",
        "timestamp_ms": 1767268800000,
        "run_id": "run-1",
        "deployment_id": "dep-1",
        "building_id": "building-1",
        "floor_id": "floor-1",
        "anchor_id": "anchor-1",
        "session_id": "session-1",
        "rssi_dbm": -62,
        "channel": 6,
        "source": "wifi",
        "mode": "simulated",
        "sequence_number": sequence,
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEURANTA_DATABASE_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_batch_accepts_and_deduplicates(client):
    payload = {
        "producer_id": "simulator",
        "batch_sequence": 1,
        "sent_at": "2026-01-01T12:00:01Z",
        "run_id": "run-1",
        "deployment_id": "dep-1",
        "mode": "simulated",
        "observations": [observation()],
    }
    first = client.post("/api/v1/observations/batch", json=payload)
    assert first.status_code == 200
    assert first.json()["data"]["accepted"] == 1
    second = client.post("/api/v1/observations/batch", json=payload)
    assert second.status_code == 200
    assert second.json()["data"]["duplicate"] == 1


def test_partial_batch_rejection(client):
    payload = {
        "producer_id": "simulator",
        "batch_sequence": 2,
        "run_id": "run-1",
        "deployment_id": "dep-1",
        "mode": "simulated",
        "observations": [observation("good", 2), {**observation("bad", 3), "rssi_dbm": -200}],
    }
    response = client.post("/api/v1/observations/batch", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["accepted"] == 1
    assert response.json()["data"]["rejected"] == 1


def test_validation_and_state_recovery(client):
    invalid = client.post("/api/v1/observations", json={"rssi_dbm": -200})
    assert invalid.status_code == 422
    client.post("/api/v1/observations", json=observation())
    state = client.get("/api/v1/state", params={"run_id": "run-1", "deployment_id": "dep-1",
                                                  "building_id": "building-1", "floor_id": "floor-1",
                                                  "mode": "simulated"})
    assert state.status_code == 200
    assert state.json()["data"]["counts"]["observations"] == 1


def test_session_and_grounded_intelligence(client):
    session = client.post("/api/v1/sessions", json={"session_id": "session-1", "run_id": "run-1",
                                                     "deployment_id": "dep-1", "building_id": "building-1",
                                                     "floor_id": "floor-1", "mode": "simulated"})
    assert session.status_code == 201
    response = client.post("/api/v1/intelligence/query", json={"query": "What is happening right now?",
                                                                 "run_id": "run-1", "mode": "simulated"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["grounded"] is True
    assert data["facts"]
    assert "source_ref" in data["facts"][0]


def test_websocket_snapshot_and_delta(client):
    url = "/api/v1/live?run_id=run-1&deployment_id=dep-1&building_id=building-1&floor_id=floor-1&mode=simulated"
    with client.websocket_connect(url) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["data"]["building_id"] == "building-1"
        client.post("/api/v1/observations", json=observation("ws-observation", 4))
        delta = websocket.receive_json()
        assert delta["type"] in {"observation", "anomaly"}
        assert delta["state_revision"] > snapshot["state_revision"]


def test_rssi_positioning_endpoint_persists_a_position(client):
    payload = {
        "window_start": "2026-01-01T12:00:00Z",
        "window_end": "2026-01-01T12:00:01Z",
        "run_id": "run-1",
        "deployment_id": "dep-1",
        "building_id": "building-1",
        "floor_id": "floor-1",
        "session_id": "iphone-demo",
        "source": "ble",
        "mode": "simulated",
        "anchors": [
            {"anchor_id": "pi-1", "x_m": 0, "y_m": 0, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
            {"anchor_id": "pi-2", "x_m": 6, "y_m": 0, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
            {"anchor_id": "pi-3", "x_m": 0, "y_m": 4, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
            {"anchor_id": "pi-4", "x_m": 6, "y_m": 4, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
        ],
        "rssi_by_anchor": {"pi-1": -67, "pi-2": -72, "pi-3": -69, "pi-4": -72},
    }
    response = client.post("/api/v1/positioning/estimate", json=payload)

    assert response.status_code == 200
    estimate = response.json()["data"]
    assert estimate["position_method"] == "rssi_log_distance_multilateration/ble"
    assert estimate["observation_count"] == 4
    assert estimate["anchors_used"] == ["pi-1", "pi-2", "pi-3", "pi-4"]
    positions = client.get("/api/v1/positions", params={"run_id": "run-1"})
    assert len(positions.json()["data"]) == 1


def test_internal_positioner_writes_a_position_from_four_anchor_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("SEURANTA_DATABASE_PATH", str(tmp_path / "positioning.db"))
    monkeypatch.setenv("SEURANTA_INTERNAL_POSITIONING", "true")
    monkeypatch.setenv("SEURANTA_POSITIONING_WINDOW_SECONDS", "3")
    monkeypatch.setenv("SEURANTA_POSITIONING_ANCHORS_JSON", json.dumps([
        {"anchor_id": "pi-1", "x_m": 0, "y_m": 0, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
        {"anchor_id": "pi-2", "x_m": 6, "y_m": 0, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
        {"anchor_id": "pi-3", "x_m": 0, "y_m": 4, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
        {"anchor_id": "pi-4", "x_m": 6, "y_m": 4, "tx_power_dbm_at_1m": -59, "path_loss_exponent": 2},
    ]))
    observations = [
        {**observation("auto-1", 10), "anchor_id": "pi-1", "rssi_dbm": -67, "source": "ble", "channel": 37},
        {**observation("auto-2", 11), "anchor_id": "pi-2", "rssi_dbm": -72, "source": "ble", "channel": 37},
        {**observation("auto-3", 12), "anchor_id": "pi-3", "rssi_dbm": -69, "source": "ble", "channel": 37},
        {**observation("auto-4", 13), "anchor_id": "pi-4", "rssi_dbm": -72, "source": "ble", "channel": 37},
    ]
    batch = {"producer_id": "ble-simulator", "batch_sequence": 10, "run_id": "run-1",
             "deployment_id": "dep-1", "mode": "simulated", "observations": observations}

    with TestClient(app) as configured_client:
        response = configured_client.post("/api/v1/observations/batch", json=batch)
        assert response.status_code == 200
        positions = configured_client.get("/api/v1/positions", params={"run_id": "run-1"})
        assert len(positions.json()["data"]) == 1
        position = positions.json()["data"][0]
        assert position["position_method"] == "rssi_log_distance_multilateration/ble"
        health = configured_client.get("/api/v1/health").json()
        assert health["positioning"]["internal"]["status"] == "enabled"
        assert health["positioning"]["internal"]["emitted"] == 1


def test_api_accepts_legacy_edge_mode_and_status_values(client):
    response = client.post("/api/v1/observations", json={**observation("legacy", 8), "mode": "SIMULATION"})
    assert response.status_code == 200
    heartbeat = client.post("/api/v1/nodes/heartbeat", json={
        "heartbeat_id": "00000000-0000-4000-8000-000000000002",
        "emitted_at": "2026-01-01T12:00:00Z",
        "run_id": "run-1", "deployment_id": "dep-1", "building_id": "building-1", "floor_id": "floor-1",
        "anchor_id": "anchor-1", "node_kind": "REAL", "mode": "LIVE", "status": "ONLINE", "agent_version": "0.1",
        "uptime_s": 1, "buffer_depth": 0, "observations_sent_total": 0, "last_observation_at": None,
        "capture_ok": True, "error_codes": [],
    })
    assert heartbeat.status_code == 200
    assert heartbeat.json()["data"]["mode"] == "real"
    assert heartbeat.json()["data"]["status"] == "online"
