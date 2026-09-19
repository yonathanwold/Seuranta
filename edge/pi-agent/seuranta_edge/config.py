"""Typed, validated configuration for the Raspberry Pi edge agent."""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Optional
import secrets
from urllib.parse import urlparse

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ENV_NAMES = {
    "anchor_id": "ANCHOR_ID",
    "anchor_x": "ANCHOR_X",
    "anchor_y": "ANCHOR_Y",
    "anchor_floor": "ANCHOR_FLOOR",
    "deployment_id": "DEPLOYMENT_ID",
    "building_id": "BUILDING_ID",
    "api_url": "SEURANTA_API_URL",
    "wifi_ssid": "SEURANTA_WIFI_SSID",
    "wifi_channel": "SEURANTA_WIFI_CHANNEL",
    "wifi_interface": "WIFI_INTERFACE",
    "capture_strategy": "CAPTURE_STRATEGY",
    "observation_interval_ms": "OBSERVATION_INTERVAL_MS",
    "heartbeat_interval_ms": "HEARTBEAT_INTERVAL_MS",
    "batch_max_size": "BATCH_MAX_SIZE",
    "buffer_path": "BUFFER_PATH",
    "demo_run_secret": "DEMO_RUN_SECRET",
    "ble_target_name": "BLE_TARGET_NAME",
    "ble_scan_seconds": "BLE_SCAN_SECONDS",
}

_REQUIRED_FIELDS = (
    "anchor_id", "anchor_x", "anchor_y", "anchor_floor", "deployment_id", "building_id", "api_url",
    "wifi_ssid", "wifi_channel", "wifi_interface", "capture_strategy", "observation_interval_ms",
    "heartbeat_interval_ms", "batch_max_size", "buffer_path", "demo_run_secret",
)


@dataclass(frozen=True)
class EdgeConfig:
    anchor_id: str
    anchor_x: float
    anchor_y: float
    anchor_floor: str
    deployment_id: str
    building_id: str
    api_url: str
    wifi_ssid: str
    wifi_channel: int
    wifi_interface: str
    capture_strategy: str
    observation_interval_ms: int
    heartbeat_interval_ms: int
    batch_max_size: int
    buffer_path: str
    demo_run_secret: str
    ble_target_name: str = ""
    ble_scan_seconds: int = 3

    def __post_init__(self) -> None:
        errors = self.validation_errors()
        if errors:
            raise ValueError("invalid edge configuration: " + "; ".join(errors))

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        for name in ("anchor_id", "anchor_floor", "deployment_id", "building_id", "wifi_interface"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or not _SAFE_ID.fullmatch(value):
                errors.append(f"{name} must match {_SAFE_ID.pattern}")
        if not isinstance(self.anchor_x, (int, float)) or isinstance(self.anchor_x, bool) or not math.isfinite(self.anchor_x):
            errors.append("anchor_x must be a finite number")
        if not isinstance(self.anchor_y, (int, float)) or isinstance(self.anchor_y, bool) or not math.isfinite(self.anchor_y):
            errors.append("anchor_y must be a finite number")
        parsed = urlparse(self.api_url) if isinstance(self.api_url, str) else None
        if not parsed or parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("api_url must be an absolute http(s) URL")
        if not isinstance(self.wifi_ssid, str) or not self.wifi_ssid or len(self.wifi_ssid) > 32:
            errors.append("wifi_ssid must be non-empty and at most 32 characters")
        if not isinstance(self.wifi_channel, int) or isinstance(self.wifi_channel, bool) or not 1 <= self.wifi_channel <= 196:
            errors.append("wifi_channel must be an integer from 1 through 196")
        if self.capture_strategy not in ("MOCK", "AP_STATIONS", "MONITOR", "BLE", "AUTO"):
            errors.append("capture_strategy must be MOCK, AP_STATIONS, MONITOR, BLE, or AUTO")
        for name in ("observation_interval_ms", "heartbeat_interval_ms", "batch_max_size"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                errors.append(f"{name} must be a positive integer")
        if not isinstance(self.buffer_path, str) or not self.buffer_path:
            errors.append("buffer_path must be a non-empty path")
        if not isinstance(self.demo_run_secret, str) or len(self.demo_run_secret.encode("utf-8")) < 16:
            errors.append("demo_run_secret must be at least 16 UTF-8 bytes and is never logged")
        if not isinstance(self.ble_scan_seconds, int) or isinstance(self.ble_scan_seconds, bool) or not 1 <= self.ble_scan_seconds <= 30:
            errors.append("ble_scan_seconds must be an integer from 1 through 30")
        if self.capture_strategy == "BLE":
            if not isinstance(self.ble_target_name, str) or not _SAFE_ID.fullmatch(self.ble_target_name):
                errors.append(f"ble_target_name must match {_SAFE_ID.pattern} when capture_strategy is BLE")
        return errors

    def redacted_diagnostics(self) -> dict[str, Any]:
        """Return safe diagnostics with the run secret excluded."""

        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["demo_run_secret"] = "<redacted>"
        if result["ble_target_name"]:
            result["ble_target_name"] = "<configured>"
        return result

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "EdgeConfig":
        normalized = dict(values)
        for key, env_name in _ENV_NAMES.items():
            if key not in normalized and env_name in normalized:
                normalized[key] = normalized[env_name]

        def value(name: str, default: Any = None) -> Any:
            return normalized.get(name, default)

        def as_float(name: str) -> float:
            raw = value(name)
            try:
                return float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a number") from exc

        def as_int(name: str) -> int:
            raw = value(name)
            try:
                return int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc

        missing = [name for name in _REQUIRED_FIELDS if value(name) is None]
        if missing:
            raise ValueError("missing configuration values: " + ", ".join(_ENV_NAMES[name] for name in missing))
        return cls(
            anchor_id=str(value("anchor_id")), anchor_x=as_float("anchor_x"), anchor_y=as_float("anchor_y"),
            anchor_floor=str(value("anchor_floor")), deployment_id=str(value("deployment_id")),
            building_id=str(value("building_id")), api_url=str(value("api_url")),
            wifi_ssid=str(value("wifi_ssid")), wifi_channel=as_int("wifi_channel"),
            wifi_interface=str(value("wifi_interface")), capture_strategy=str(value("capture_strategy")).upper(),
            observation_interval_ms=as_int("observation_interval_ms"), heartbeat_interval_ms=as_int("heartbeat_interval_ms"),
            batch_max_size=as_int("batch_max_size"), buffer_path=str(value("buffer_path")),
            demo_run_secret=str(value("demo_run_secret")), ble_target_name=str(value("ble_target_name", "")),
            ble_scan_seconds=as_int("ble_scan_seconds") if value("ble_scan_seconds") is not None else 3,
        )


def _load_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read config file {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"config file {file_path} must be JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("config file must contain a JSON object")
    return {key.lower(): value for key, value in payload.items()}


def load_config(env: Optional[Mapping[str, str]] = None, config_file: Optional[str | Path] = None) -> EdgeConfig:
    """Load JSON config first, then uppercase environment overrides."""

    source: dict[str, Any] = _load_file(config_file) if config_file else {}
    environment = env if env is not None else __import__("os").environ
    for name, env_name in _ENV_NAMES.items():
        if env_name in environment:
            source[name] = environment[env_name]
    return EdgeConfig.from_mapping(source)


def config_from_defaults(*, secret: Optional[str] = None) -> EdgeConfig:
    """Build a safe local mock configuration for CLI demonstrations/tests."""

    return EdgeConfig(
        anchor_id="mock-anchor", anchor_x=0.0, anchor_y=0.0, anchor_floor="1",
        deployment_id="demo-deployment", building_id="demo-building", api_url="http://127.0.0.1:8000",
        wifi_ssid="seuranta-demo", wifi_channel=6, wifi_interface="wlan0", capture_strategy="MOCK",
        observation_interval_ms=1000, heartbeat_interval_ms=10000, batch_max_size=10,
        buffer_path="edge-buffer.sqlite3", demo_run_secret=secret or secrets.token_hex(32),
    )
