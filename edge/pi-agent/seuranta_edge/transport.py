"""HTTP and test transports for the V1 API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from .contracts import ObservationBatch, NodeHeartbeat, Session


class TransportError(RuntimeError):
    pass


class ApiTransport:
    def start_session(self, session: Session) -> dict[str, Any]:
        raise NotImplementedError

    def end_session(self, session_id: str, ended_at: Optional[str] = None) -> dict[str, Any]:
        raise NotImplementedError

    def send_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def heartbeat(self, heartbeat: NodeHeartbeat) -> dict[str, Any]:
        raise NotImplementedError

    def list_sessions(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class HttpTransport(ApiTransport):
    """Small urllib-only client with the required API routes."""

    def __init__(self, base_url: str, *, timeout_s: float = 5.0, building_id: str | None = None,
                 floor_id: str | None = None, run_id: str | None = None,
                 deployment_id: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.building_id = building_id
        self.floor_id = floor_id
        self.run_id = run_id
        self.deployment_id = deployment_id

    @staticmethod
    def _api_mode(mode: str) -> str:
        return {"LIVE": "real", "SIMULATION": "simulated", "REPLAY": "simulated"}.get(mode, mode.lower())

    @staticmethod
    def _edge_mode(mode: str) -> str:
        return {"real": "LIVE", "simulated": "SIMULATION"}.get(mode, mode.upper())

    @staticmethod
    def _rfc3339(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise TransportError("backend returned an invalid session timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> Any:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        req = request.Request(self.base_url + path, data=body, method=method,
                              headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                raw = response.read()
        except HTTPError as exc:
            raise TransportError(f"backend returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TransportError("backend unavailable") from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError("backend returned invalid JSON") from exc
        return decoded

    def start_session(self, session: Session) -> dict[str, Any]:
        if not self.building_id or not self.floor_id:
            raise TransportError("building_id and floor_id are required to create an API session")
        payload = {
            "session_id": session.session_id,
            "run_id": session.run_id,
            "deployment_id": session.deployment_id,
            "building_id": self.building_id,
            "floor_id": self.floor_id,
            "mode": self._api_mode(session.mode),
            "started_at": session.started_at,
        }
        return self._request("POST", "/api/v1/sessions", payload)

    def end_session(self, session_id: str, ended_at: Optional[str] = None) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/sessions/{session_id}/end", {"ended_at": ended_at} if ended_at else {})

    def send_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        payload = {**batch, "mode": self._api_mode(str(batch.get("mode", "LIVE")))}
        payload["observations"] = [{**item, "mode": self._api_mode(str(item.get("mode", batch.get("mode", "LIVE"))))}
                                   for item in batch.get("observations", [])]
        return self._request("POST", "/api/v1/observations/batch", payload)

    def heartbeat(self, heartbeat: NodeHeartbeat) -> dict[str, Any]:
        payload = heartbeat.to_dict()
        payload["mode"] = self._api_mode(heartbeat.mode)
        payload["status"] = heartbeat.status.lower()
        return self._request("POST", "/api/v1/nodes/heartbeat", payload)

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.run_id:
            return []
        query = {"run_id": self.run_id}
        if self.deployment_id:
            query["deployment_id"] = self.deployment_id
        if self.building_id:
            query["building_id"] = self.building_id
        if self.floor_id:
            query["floor_id"] = self.floor_id
        result = self._request("GET", "/api/v1/sessions?" + urlencode(query))
        payloads = result.get("data") if isinstance(result, dict) else None
        if not isinstance(payloads, list):
            raise TransportError("backend returned an invalid session list")
        sessions: list[dict[str, Any]] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            try:
                started_at = self._rfc3339(str(payload["started_at"]))
                ended_at = payload.get("ended_at")
                last_seen_at = self._rfc3339(str(ended_at or payload["started_at"]))
                sessions.append({
                    "schema_version": "1.0",
                    "session_id": payload["session_id"],
                    "run_id": payload["run_id"],
                    "deployment_id": payload["deployment_id"],
                    "mode": self._edge_mode(str(payload["mode"])),
                    "status": "ENDED" if ended_at else "ACTIVE",
                    "consent_scope": "DEMO_NETWORK",
                    "started_at": started_at,
                    "last_seen_at": last_seen_at,
                    "origin_anchor_id": "api",
                })
            except (KeyError, TransportError):
                raise TransportError("backend returned an invalid session record") from None
        return sessions


class RecordingTransport(ApiTransport):
    """No-network transport used by mock mode and tests."""

    def __init__(self, *, fail_sends: int = 0) -> None:
        self.requests: list[tuple[str, Any]] = []
        self.fail_sends = fail_sends

    def start_session(self, session: Session) -> dict[str, Any]:
        self.requests.append(("POST /api/v1/sessions", session.to_dict()))
        return {"accepted": True}

    def end_session(self, session_id: str, ended_at: Optional[str] = None) -> dict[str, Any]:
        self.requests.append((f"POST /api/v1/sessions/{session_id}/end", {"ended_at": ended_at} if ended_at else {}))
        return {"accepted": True}

    def send_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        if self.fail_sends:
            self.fail_sends -= 1
            raise TransportError("simulated backend outage")
        self.requests.append(("POST /api/v1/observations/batch", batch))
        return {"accepted": True}

    def heartbeat(self, heartbeat: NodeHeartbeat) -> dict[str, Any]:
        self.requests.append(("POST /api/v1/nodes/heartbeat", heartbeat.to_dict()))
        return {"accepted": True}

    def list_sessions(self) -> list[dict[str, Any]]:
        self.requests.append(("GET /api/v1/sessions", None))
        return []
