"""Edge agent orchestration: capture, anonymize, batch, queue, and heartbeat."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import subprocess
import time
from typing import Callable, Iterable, Optional
from uuid import uuid4

from .buffer import FlushResult, SQLiteBuffer
from .collectors import CollectorError, MockCollector, ObservationCollector
from .config import EdgeConfig
from .contracts import NodeHeartbeat, ObservationBatch, SignalObservation, Session, utc_now
from .pseudonym import SessionRegistry
from .transport import ApiTransport

AGENT_VERSION = "0.1.0"


class BatchAccumulator:
    """Count- and age-based batching with monotonic sequence boundaries."""

    def __init__(self, *, max_size: int, max_age_ms: int, clock: Callable[[], float] = time.monotonic) -> None:
        if max_size <= 0 or max_age_ms <= 0:
            raise ValueError("batch bounds must be positive")
        self.max_size = max_size
        self.max_age_s = max_age_ms / 1000.0
        self.clock = clock
        self._items: list[SignalObservation] = []
        self._opened_at: Optional[float] = None

    def add(self, observation: SignalObservation) -> Optional[list[SignalObservation]]:
        if self._opened_at is None:
            self._opened_at = self.clock()
        self._items.append(observation)
        if len(self._items) >= self.max_size:
            return self._take()
        return None

    def flush_due(self) -> Optional[list[SignalObservation]]:
        if self._items and self._opened_at is not None and self.clock() - self._opened_at >= self.max_age_s:
            return self._take()
        return None

    def flush(self) -> Optional[list[SignalObservation]]:
        return self._take() if self._items else None

    def _take(self) -> list[SignalObservation]:
        result = self._items
        self._items = []
        self._opened_at = None
        return result

    @property
    def size(self) -> int:
        return len(self._items)


def _timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1000)


def read_cpu_temp_c() -> Optional[float]:
    """Read the standard Pi thermal-zone file, if exposed by the kernel."""

    for path in ("/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input"):
        try:
            raw = Path(path).read_text(encoding="ascii").strip()
            value = float(raw)
            return value / 1000.0 if value > 200 else value
        except (OSError, ValueError):
            continue
    return None


def clock_offset_s() -> Optional[float]:
    """Best-effort offset from chrony/timedatectl without logging output."""

    for command in (("chronyc", "tracking"), ("timedatectl", "show-timesync", "--value")):
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode != 0:
            continue
        match = re.search(r"(?:Last offset|System time|Offset)[^\n:]*:\s*([-+]?\d+(?:\.\d+)?)", completed.stdout, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


class EdgeAgent:
    def __init__(self, config: EdgeConfig, *, run_id: str, collector: ObservationCollector,
                 buffer: Optional[SQLiteBuffer] = None, transport: Optional[ApiTransport] = None,
                 mode: Optional[str] = None, node_kind: Optional[str] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.run_id = run_id
        self.mode = mode or ("SIMULATION" if config.capture_strategy == "MOCK" else "LIVE")
        self.node_kind = node_kind or ("SIMULATED" if self.mode == "SIMULATION" else "REAL")
        self.collector = collector
        self.buffer = buffer or SQLiteBuffer(config.buffer_path, max_batches=500)
        self.transport = transport
        self.clock = clock
        self.started_monotonic = clock()
        self.registry = SessionRegistry(run_id=run_id, deployment_id=config.deployment_id,
                                        mode=self.mode, anchor_id=config.anchor_id,
                                        run_secret=config.demo_run_secret)
        self.batcher = BatchAccumulator(max_size=config.batch_max_size,
                                        max_age_ms=config.observation_interval_ms, clock=clock)
        self._observation_sequence = 0
        self._batch_sequence = 0
        self._heartbeat_errors: set[str] = set()
        self._sent_total = 0
        self._last_observation_at: Optional[str] = None
        self._last_capture_ok = True

    def start_session(self, raw_identifier: str, *, now: Optional[str] = None) -> Session:
        session = self.registry.start(raw_identifier, now=now)
        if self.transport:
            self.transport.start_session(session)
        return session

    def end_session(self, session_id: str, *, now: Optional[str] = None) -> Session:
        current = next((item for item in self.registry.all_sessions() if item.session_id == session_id), None)
        if not current:
            raise KeyError("unknown session")
        ended = Session(current.session_id, current.run_id, current.deployment_id, current.mode,
                        "ENDED", current.consent_scope, current.started_at, now or utc_now(), current.origin_anchor_id)
        if self.transport:
            self.transport.end_session(session_id)
        self.registry.end(session_id, now=ended.last_seen_at)
        return ended

    def collect_once(self) -> list[SignalObservation]:
        try:
            raw_observations = self.collector.collect()
        except CollectorError as exc:
            self._heartbeat_errors.add(self._safe_error_code(str(exc)))
            self._last_capture_ok = False
            return []
        except OSError:
            self._heartbeat_errors.add("CAPTURE_ERROR")
            self._last_capture_ok = False
            return []
        converted: list[SignalObservation] = []
        self._last_capture_ok = True
        for raw in raw_observations:
            session = self.registry.session_for_raw(raw.device_token)
            if not session:
                # Unknown/non-active station observations are dropped before
                # the contract layer.  The token is not put in any diagnostic.
                self._heartbeat_errors.add("INACTIVE_SESSION")
                continue
            self.registry.touch(session.session_id, now=raw.observed_at)
            source = "MOCK_RSSI" if self.mode == "SIMULATION" else "WIFI_RSSI"
            try:
                observation = SignalObservation(
                    observation_id=str(uuid4()), observed_at=raw.observed_at,
                    timestamp_ms=_timestamp_ms(raw.observed_at), run_id=self.run_id,
                    deployment_id=self.config.deployment_id, building_id=self.config.building_id,
                    floor_id=self.config.anchor_floor, anchor_id=self.config.anchor_id,
                    session_id=session.session_id, rssi_dbm=raw.rssi_dbm, channel=raw.channel,
                    source=source, mode=self.mode, sequence_number=self._observation_sequence,
                )
            except (TypeError, ValueError):
                self._heartbeat_errors.add("MALFORMED_SAMPLE")
                continue
            self._observation_sequence += 1
            self._last_observation_at = raw.observed_at
            converted.append(observation)
            ready = self.batcher.add(observation)
            if ready:
                self._queue_batch(ready)
        self._flush_age_batch()
        return converted

    def _flush_age_batch(self) -> None:
        ready = self.batcher.flush_due()
        if ready:
            self._queue_batch(ready)

    def flush_pending_batch(self) -> Optional[ObservationBatch]:
        ready = self.batcher.flush()
        return self._queue_batch(ready) if ready else None

    def _queue_batch(self, observations: Iterable[SignalObservation]) -> ObservationBatch:
        batch = ObservationBatch.from_observations(self.config.anchor_id, self._batch_sequence,
                                                    self.run_id, self.config.deployment_id,
                                                    self.mode, tuple(observations))
        self._batch_sequence += 1
        if not self.buffer.enqueue(batch):
            self._heartbeat_errors.add("BUFFER_FULL")
        return batch

    def flush_buffer(self, *, limit: int = 50) -> FlushResult:
        if not self.transport:
            return FlushResult(retained=self.buffer.depth())
        sent_observations = 0

        def send(payload: dict) -> None:
            nonlocal sent_observations
            self.transport.send_batch(payload)
            sent_observations += len(payload.get("observations", []))

        result = self.buffer.flush(send, limit=limit)
        self._sent_total += sent_observations
        if result.failed:
            self._heartbeat_errors.add("BACKEND_UNAVAILABLE")
        return result

    def build_heartbeat(self) -> NodeHeartbeat:
        errors = set(self._heartbeat_errors)
        offset = clock_offset_s()
        if offset is not None and abs(offset) > 2.0:
            errors.add("CLOCK_SKEW")
        temperature = read_cpu_temp_c()
        if temperature is not None and temperature >= 80.0:
            errors.add("CPU_TEMP_HIGH")
        status = "ONLINE" if self._last_capture_ok and not errors else "DEGRADED"
        return NodeHeartbeat(
            heartbeat_id=str(uuid4()), emitted_at=utc_now(), run_id=self.run_id,
            deployment_id=self.config.deployment_id, building_id=self.config.building_id,
            floor_id=self.config.anchor_floor, anchor_id=self.config.anchor_id,
            node_kind=self.node_kind, mode=self.mode, status=status, agent_version=AGENT_VERSION,
            uptime_s=max(0, int(self.clock() - self.started_monotonic)), buffer_depth=self.buffer.depth(),
            observations_sent_total=self._sent_total, last_observation_at=self._last_observation_at,
            capture_ok=self._last_capture_ok, error_codes=tuple(sorted(errors)),
        )

    def diagnostics(self) -> dict[str, object]:
        """Return local diagnostics; this structure is never sent as V1 data."""

        return {
            "config": self.config.redacted_diagnostics(),
            "buffer_depth": self.buffer.depth(),
            "buffer_bytes": self.buffer.bytes_pending(),
            "clock_offset_s": clock_offset_s(),
            "cpu_temp_c": read_cpu_temp_c(),
            "heartbeat_errors": sorted(self._heartbeat_errors),
        }

    def send_heartbeat(self) -> NodeHeartbeat:
        heartbeat = self.build_heartbeat()
        if self.transport:
            try:
                self.transport.heartbeat(heartbeat)
            except Exception:
                self._heartbeat_errors.add("BACKEND_UNAVAILABLE")
        return heartbeat

    def sync_sessions(self) -> int:
        """Pull backend session state without ever pulling raw identifiers."""

        if not self.transport:
            return 0
        try:
            payloads = self.transport.list_sessions()
            count = 0
            for payload in payloads:
                try:
                    session = Session.from_dict(payload)
                except (KeyError, TypeError, ValueError):
                    self._heartbeat_errors.add("MALFORMED_SESSION")
                    continue
                if session.run_id == self.run_id and session.deployment_id == self.config.deployment_id:
                    try:
                        self.registry.register_session(session)
                    except ValueError:
                        self._heartbeat_errors.add("MALFORMED_SESSION")
                        continue
                    count += 1
            return count
        except Exception:
            self._heartbeat_errors.add("BACKEND_UNAVAILABLE")
            return 0

    def run_forever(self, *, max_cycles: Optional[int] = None) -> None:
        """Run capture/delivery/heartbeat loops until interrupted or bounded."""

        cycles = 0
        next_heartbeat = self.clock()
        while max_cycles is None or cycles < max_cycles:
            self.sync_sessions()
            self.collect_once()
            self.flush_buffer()
            now = self.clock()
            if now >= next_heartbeat:
                self.send_heartbeat()
                next_heartbeat = now + self.config.heartbeat_interval_ms / 1000.0
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                self.flush_pending_batch()
                self.flush_buffer()
                return
            time.sleep(self.config.observation_interval_ms / 1000.0)

    @staticmethod
    def _safe_error_code(message: str) -> str:
        upper = message.upper()
        if "CHANNEL" in upper:
            return "WRONG_CHANNEL"
        if "PERMISSION" in upper:
            return "CAPTURE_PERMISSION"
        if "MISSING" in upper:
            return "CAPTURE_COMMAND_MISSING"
        if "TIME" in upper:
            return "CAPTURE_TIMEOUT"
        return "CAPTURE_ERROR"


def create_collector(config: EdgeConfig) -> ObservationCollector:
    """Select a collector without importing hardware-specific dependencies."""

    from .collectors import APStationCollector, MonitorModeCollector
    if config.capture_strategy == "MOCK":
        return MockCollector(channel=config.wifi_channel)
    if config.capture_strategy == "AP_STATIONS":
        return APStationCollector(config.wifi_interface, config.wifi_channel)
    if config.capture_strategy == "MONITOR":
        return MonitorModeCollector(config.wifi_interface, config.wifi_channel)
    # AUTO is conservative: AP station mode is the only mode that can be
    # selected without first changing an interface into monitor mode.
    return APStationCollector(config.wifi_interface, config.wifi_channel)
