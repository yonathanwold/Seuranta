from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from services.api.coordinates import CalibrationReference, geographic_to_floor, is_outside_map
from services.api.settings import Settings
from services.api.smoothing import ExponentialSmoother, confidence_from_accuracy
from services.api.tracking import TrackingEngine
from services.api.zones import assign_zone
from services.api.main import app
from services.data.models import DevPositionRequest, TrackerLocation


UTC = timezone.utc


def test_coordinate_conversion_and_yaw_rotation() -> None:
    reference = CalibrationReference(37.0, -80.0, 12.0, 18.0)
    x_m, y_m = geographic_to_floor(37.0, -79.99999, reference)
    assert x_m == pytest.approx(12.889, abs=0.02)
    assert y_m == pytest.approx(18.0, abs=0.02)

    rotated = CalibrationReference(37.0, -80.0, 0.0, 0.0, yaw_deg=90.0)
    x_m, y_m = geographic_to_floor(37.00001, -80.0, rotated)
    assert x_m == pytest.approx(-1.113, abs=0.02)
    assert y_m == pytest.approx(0.0, abs=0.02)


def test_smoothing_confidence_and_outside_map() -> None:
    smoother = ExponentialSmoother()
    assert smoother.update(0, 0, 3) == (0, 0)
    assert smoother.update(10, 0, 3)[0] == pytest.approx(4.0)
    assert smoother.update(20, 0, 20)[0] == pytest.approx(5.28)
    assert 0 < confidence_from_accuracy(5.7) < 1
    assert confidence_from_accuracy(5.7) == pytest.approx(0.814, abs=0.01)
    assert is_outside_map(77, 2, 76.9, 44.6)
    assert not is_outside_map(20, 15, 76.9, 44.6)
    assert assign_zone(30, 30) == "main-circulation"
    assert assign_zone(30, 10) is None


def test_tracking_engine_calibration_position_and_expiration() -> None:
    settings = Settings(
        calibration_latitude=37.0,
        calibration_longitude=-80.0,
        calibration_x_m=12.0,
        calibration_y_m=18.0,
        tracker_stale_after_seconds=10,
        tracker_expire_after_seconds=30,
    )
    engine = TrackingEngine(settings)
    captured = datetime(2026, 9, 19, 18, 0, tzinfo=UTC)
    packet = TrackerLocation(
        session_id="session-test",
        captured_at=captured,
        latitude=37.0,
        longitude=-79.99999,
        accuracy_m=5.7,
    )
    result = engine.ingest_location(packet, engine.default_scope, captured)
    assert result.position is not None
    assert result.position.position_method == "phone-geolocation"
    assert result.position.accuracy_radius_m == 5.7
    assert result.position.raw_x_m > result.position.x_m - 0.01
    assert len(engine.positions_for(engine.default_scope, captured + timedelta(seconds=11))) == 1
    assert engine.sessions_for(engine.default_scope, captured + timedelta(seconds=11))[0]["status"] == "degraded"
    assert len(engine.positions_for(engine.default_scope, captured + timedelta(seconds=31))) == 0


@pytest.fixture()
def tracking_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEURANTA_DATABASE_PATH", str(tmp_path / "tracking.db"))
    monkeypatch.setenv("SEURANTA_DEV_MODE", "true")
    with TestClient(app) as test_client:
        yield test_client


def scope_params() -> dict[str, str]:
    return {
        "run_id": "vt-acb-floor1",
        "deployment_id": "vt-acb-pilot",
        "building_id": "vt-academic-classroom-building",
        "floor_id": "floor-1",
        "mode": "real",
    }


def test_dev_position_reaches_state_and_dashboard_websocket(tracking_client) -> None:
    live_url = "/api/v1/live?" + "&".join(f"{key}={value}" for key, value in scope_params().items())
    with tracking_client.websocket_connect(live_url) as websocket:
        initial = websocket.receive_json()
        response = tracking_client.post(
            "/api/v1/dev/position",
            json={"session_id": "session-test", "x_m": 20, "y_m": 15, "accuracy_radius_m": 2},
        )
        assert response.status_code == 200
        message = websocket.receive_json()
        assert message["type"] == "position"
        assert message["data"]["session_id"] == "session-test"
        assert message["state_revision"] > initial["state_revision"]

    state = tracking_client.get("/api/v1/state", params=scope_params())
    assert state.status_code == 200
    assert state.json()["data"]["positions"][0]["position_method"] == "dev-simulation"
    assert state.json()["data"]["positions"][0]["x_m"] == 20


def test_tracker_rest_calibration_and_location_fallback(tracking_client) -> None:
    calibration = tracking_client.post(
        "/api/v1/tracker/calibrate",
        json={"session_id": "session-a7f3", "latitude": 37.0, "longitude": -80.0},
    )
    assert calibration.status_code == 200
    location = tracking_client.post(
        "/api/v1/telemetry/location",
        json={
            "session_id": "session-a7f3",
            "captured_at": "2026-09-19T18:17:41.231Z",
            "latitude": 37.0,
            "longitude": -79.99999,
            "accuracy_m": 5.7,
            "heading_deg": 87.4,
            "speed_mps": 1.21,
        },
    )
    assert location.status_code == 200
    assert location.json()["data"]["status"] == "live"
    position = location.json()["data"]["position"]
    assert position["position_method"] == "phone-geolocation"
    assert position["accuracy_radius_m"] == 5.7
    assert position["raw_x_m"] > 0.8


def test_calibration_materializes_the_latest_unplaced_fix(tracking_client) -> None:
    first = tracking_client.post(
        "/api/v1/telemetry/location",
        json={"session_id": "session-pre1", "latitude": 37.0, "longitude": -80.0, "accuracy_m": 4},
    )
    assert first.json()["data"]["status"] == "calibration_required"
    calibrated = tracking_client.post(
        "/api/v1/tracker/calibrate",
        json={"session_id": "session-pre1", "latitude": 37.0, "longitude": -80.0},
    )
    assert calibrated.status_code == 200
    assert calibrated.json()["data"]["position"]["session_id"] == "session-pre1"


def test_tracker_websocket_rejects_malformed_packets_and_broadcasts_position(tracking_client) -> None:
    with tracking_client.websocket_connect("/api/v1/tracker") as tracker_socket:
        tracker_socket.send_text("not-json")
        assert tracker_socket.receive_json()["code"] == "malformed_packet"
        tracker_socket.send_json({
            "type": "hello",
            "session_id": "session-ws01",
        })
        assert tracker_socket.receive_json()["type"] == "connected"
        tracker_socket.send_json({
            "type": "location",
            "session_id": "session-ws01",
            "latitude": 37.0,
            "longitude": -80.0,
            "accuracy_m": 4.0,
        })
        assert tracker_socket.receive_json()["status"] == "calibration_required"
        tracker_socket.send_json({
            "type": "calibrate",
            "session_id": "session-ws01",
            "latitude": 37.0,
            "longitude": -80.0,
        })
        assert tracker_socket.receive_json()["type"] == "calibrated"
        tracker_socket.send_json({
            "type": "location",
            "session_id": "session-ws01",
            "latitude": 37.0,
            "longitude": -80.0,
            "accuracy_m": 4.0,
        })
        ack = tracker_socket.receive_json()
        assert ack["type"] == "ack"
        assert ack["status"] == "live"


def test_tracker_scope_validation_and_dev_guard(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEURANTA_DATABASE_PATH", str(tmp_path / "guard.db"))
    monkeypatch.setenv("SEURANTA_DEV_MODE", "false")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/dev/position",
            json={"session_id": "session-test", "x_m": 20, "y_m": 15},
        )
        assert response.status_code == 404
        response = client.post(
            "/api/v1/telemetry/location",
            json={
                "session_id": "session-test",
                "latitude": 37.0,
                "longitude": -80.0,
                "accuracy_m": 4,
                "run_id": "wrong-run",
            },
        )
        assert response.status_code == 422


def test_state_since_revision_returns_partial_when_current_revision_is_known(tracking_client) -> None:
    response = tracking_client.get("/api/v1/state", params={**scope_params(), "since_revision": 0})
    assert response.status_code == 200
    assert response.json()["data"]["is_partial"] is True
    assert response.json()["since_revision"] == 0
