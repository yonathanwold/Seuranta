from __future__ import annotations

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
