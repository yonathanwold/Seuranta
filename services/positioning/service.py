"""Small standard-library HTTP server for the internal positioning API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .calibration import CalibrationError, FingerprintSet
from .engine import PositioningEngine
from .models import SCHEMA_VERSION, Zone


MAX_REQUEST_BYTES = 2 * 1024 * 1024


class PositioningHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], engine: PositioningEngine):
        self.engine = engine
        super().__init__(address, PositioningRequestHandler)


class PositioningRequestHandler(BaseHTTPRequestHandler):
    server: PositioningHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/internal/v1/health":
            self._send_json(200, {"schema_version": SCHEMA_VERSION, "service": "positioning", "status": "ok"})
            return
        if self.path == "/internal/v1/ready":
            ready = bool(self.server.engine.ready)
            self._send_json(
                200 if ready else 503,
                {
                    "schema_version": SCHEMA_VERSION,
                    "service": "positioning",
                    "ready": ready,
                    "status": "ready" if ready else "not_ready",
                },
            )
            return
        self._send_json(404, {"schema_version": SCHEMA_VERSION, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != "/internal/v1/observation-batches":
            self._send_json(404, {"schema_version": SCHEMA_VERSION, "error": "not_found"})
            return
        content_length = self.headers.get("Content-Length")
        try:
            length = int(content_length or "0")
        except ValueError:
            self._send_json(400, {"schema_version": SCHEMA_VERSION, "error": "invalid_content_length"})
            return
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._send_json(413, {"schema_version": SCHEMA_VERSION, "error": "request_too_large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = self.server.engine.process_batch(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            self._send_json(
                400,
                {
                    "schema_version": SCHEMA_VERSION,
                    "error": "invalid_observation_batch",
                    "diagnostics": [{"schema_version": SCHEMA_VERSION, "code": "request_validation", "message": str(exc)}],
                },
            )
            return
        self._send_json(200, result.to_dict())

    def log_message(self, format: str, *args: Any) -> None:
        # Keep request logging readable and avoid echoing request payloads.
        super().log_message(format, *args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def load_zones(path: str | Path) -> tuple[Zone, ...]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("zones")
    if not isinstance(value, list):
        raise ValueError("zone file must contain an array or an object with a zones array")
    return tuple(Zone.from_dict(item) for item in value)


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    fingerprints_path: str | Path | None = None,
    zones_path: str | Path | None = None,
) -> PositioningHTTPServer:
    fingerprints = FingerprintSet.load(fingerprints_path) if fingerprints_path else None
    zones = load_zones(zones_path) if zones_path else ()
    return PositioningHTTPServer((host, port), PositioningEngine(fingerprints=fingerprints, zones=zones))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seuranta internal positioning service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--fingerprints")
    parser.add_argument("--zones")
    args = parser.parse_args()
    try:
        server = create_server(
            host=args.host,
            port=args.port,
            fingerprints_path=args.fingerprints,
            zones_path=args.zones,
        )
    except (OSError, ValueError, CalibrationError) as exc:
        parser.error(str(exc))
    print(f"positioning service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
