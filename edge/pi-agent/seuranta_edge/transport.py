"""HTTP and test transports for the V1 API."""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib import request
from urllib.error import HTTPError, URLError

from .contracts import ObservationBatch, NodeHeartbeat, Session


class TransportError(RuntimeError):
    pass


class ApiTransport:
    def start_session(self, session: Session) -> dict[str, Any]:
        raise NotImplementedError

    def end_session(self, session_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def send_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def heartbeat(self, heartbeat: NodeHeartbeat) -> dict[str, Any]:
        raise NotImplementedError

    def list_sessions(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class HttpTransport(ApiTransport):
    """Small urllib-only client with the required API routes."""

    def __init__(self, base_url: str, *, timeout_s: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

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
        return self._request("POST", "/api/v1/sessions", session.to_dict())

    def end_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/sessions/{session_id}/end", {})

    def send_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/observations/batch", batch)

    def heartbeat(self, heartbeat: NodeHeartbeat) -> dict[str, Any]:
        return self._request("POST", "/api/v1/nodes/heartbeat", heartbeat.to_dict())

    def list_sessions(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/api/v1/sessions")
        if not isinstance(result, list):
            raise TransportError("backend returned an invalid session list")
        return result


class RecordingTransport(ApiTransport):
    """No-network transport used by mock mode and tests."""

    def __init__(self, *, fail_sends: int = 0) -> None:
        self.requests: list[tuple[str, Any]] = []
        self.fail_sends = fail_sends

    def start_session(self, session: Session) -> dict[str, Any]:
        self.requests.append(("POST /api/v1/sessions", session.to_dict()))
        return {"accepted": True}

    def end_session(self, session_id: str) -> dict[str, Any]:
        self.requests.append((f"POST /api/v1/sessions/{session_id}/end", {}))
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
