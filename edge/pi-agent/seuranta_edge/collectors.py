"""Hardware-neutral observation collectors and Linux wireless adapters.

Collectors expose only RSSI metadata and an in-memory opaque token.  They do
not parse packet payloads, record captures, or emit raw station identifiers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import random
import re
import subprocess
from typing import Callable, Iterable, Optional, Sequence


@dataclass(frozen=True)
class RawObservation:
    """Internal-only sample.  ``device_token`` never leaves the process."""

    device_token: str
    rssi_dbm: int
    channel: int
    observed_at: str


class CollectorError(RuntimeError):
    """A recoverable capture/adapter problem with a safe message."""


class ObservationCollector(ABC):
    @abstractmethod
    def collect(self) -> list[RawObservation]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class MockCollector(ObservationCollector):
    """Deterministic multiple-session RSSI source for no-hardware demos."""

    def __init__(self, sessions: Optional[Sequence[str]] = None, *, seed: int = 7,
                 channel: int = 6, base_rssi: Optional[Sequence[int]] = None) -> None:
        self._sessions = tuple(sessions or ("mock-session-a", "mock-session-b"))
        if not self._sessions:
            raise ValueError("MockCollector requires at least one session token")
        if not 1 <= channel <= 196:
            raise ValueError("channel must be between 1 and 196")
        self._channel = channel
        self._base = tuple(base_rssi or tuple(-45 - index * 13 for index in range(len(self._sessions))))
        if len(self._base) != len(self._sessions):
            raise ValueError("base_rssi must match sessions")
        if any(not -127 <= value <= 0 for value in self._base):
            raise ValueError("base RSSI values must be from -127 through 0")
        self._random = random.Random(seed)
        self.sample_number = 0

    def collect(self) -> list[RawObservation]:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        values: list[RawObservation] = []
        for index, token in enumerate(self._sessions):
            # Deterministic pseudo-noise sequence across collector instances.
            noise = self._random.choice((-2, -1, 0, 0, 1, 2))
            values.append(RawObservation(token, max(-127, min(0, self._base[index] + noise)),
                                         self._channel, now))
        self.sample_number += 1
        return values


class CommandAdapter(ABC):
    @abstractmethod
    def run(self, args: Sequence[str], timeout_s: float = 5.0) -> str:
        raise NotImplementedError


class SubprocessCommandAdapter(CommandAdapter):
    """Constrained subprocess wrapper; only caller-provided argv is executed."""

    def run(self, args: Sequence[str], timeout_s: float = 5.0) -> str:
        if not args or any(not isinstance(arg, str) or not arg for arg in args):
            raise ValueError("wireless command arguments must be non-empty strings")
        try:
            result = subprocess.run(list(args), capture_output=True, text=True,
                                    timeout=timeout_s, check=False)
        except FileNotFoundError as exc:
            raise CollectorError(f"missing wireless command: {args[0]}") from exc
        except PermissionError as exc:
            raise CollectorError("wireless command permission denied") from exc
        except subprocess.TimeoutExpired as exc:
            raise CollectorError("wireless command timed out") from exc
        if result.returncode != 0:
            # Do not include command output: it can contain station addresses.
            raise CollectorError(f"wireless command failed with exit code {result.returncode}")
        return result.stdout


_SIGNAL = re.compile(r"(?:signal|dBm)\s*[:=]?\s*(-?\d{1,3})(?:\.\d+)?\s*dBm", re.IGNORECASE)
_STATION = re.compile(r"^\s*Station\s+([0-9a-fA-F:]{17})\b")
_MAC = re.compile(r"\b([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b")
_CHANNEL = re.compile(r"\bchannel\s+(\d{1,3})\b", re.IGNORECASE)


def _safe_channel(value: int) -> int:
    if not 1 <= value <= 196:
        raise CollectorError("wireless output contained an invalid channel")
    return value


def parse_station_dump(output: str, *, expected_channel: int) -> list[tuple[str, int, int]]:
    """Parse only station signal metadata from ``iw station dump`` output."""

    if not isinstance(output, str):
        raise CollectorError("wireless output was not text")
    rows: list[tuple[str, int, int]] = []
    current: Optional[str] = None
    for line in output.splitlines():
        station = _STATION.match(line)
        if station:
            current = station.group(1)
            continue
        if current is None:
            continue
        signal_match = _SIGNAL.search(line)
        if not signal_match:
            if "signal" in line.lower():
                raise CollectorError("wireless output contained malformed RSSI")
            continue
        try:
            rssi = int(signal_match.group(1))
        except ValueError as exc:
            raise CollectorError("wireless output contained malformed RSSI") from exc
        if not -127 <= rssi <= 0:
            raise CollectorError("wireless output contained out-of-range RSSI")
        rows.append((current, rssi, _safe_channel(expected_channel)))
        current = None
    return rows


def parse_monitor_line(line: str, *, expected_channel: int) -> Optional[tuple[str, int, int]]:
    """Parse radiotap signal/channel metadata from a line without payloads."""

    if not isinstance(line, str):
        raise CollectorError("monitor output was not text")
    signal_match = _SIGNAL.search(line)
    if not signal_match:
        if "signal" in line.lower():
            raise CollectorError("monitor output contained malformed RSSI")
        return None
    rssi = int(signal_match.group(1))
    if not -127 <= rssi <= 0:
        raise CollectorError("monitor output contained out-of-range RSSI")
    # The token is used only in memory and is deliberately never returned to
    # the wire layer.  tcpdump is restricted to link/radiotap metadata by the
    # command assembled in MonitorModeCollector.
    station = _STATION.search(line) or _MAC.search(line)
    token = station.group(1) if station else "monitor-unknown"
    channel_match = _CHANNEL.search(line)
    channel = int(channel_match.group(1)) if channel_match else expected_channel
    return token, rssi, _safe_channel(channel)


class APStationCollector(ObservationCollector):
    """Collect associated-station RSSI from an access point interface."""

    def __init__(self, interface: str, channel: int, *, adapter: Optional[CommandAdapter] = None) -> None:
        self.interface, self.channel = interface, _safe_channel(channel)
        self.adapter = adapter or SubprocessCommandAdapter()
        if not interface:
            raise ValueError("wireless interface is required")

    def collect(self) -> list[RawObservation]:
        output = self.adapter.run(("iw", "dev", self.interface, "station", "dump"))
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return [RawObservation(token, rssi, channel, now)
                for token, rssi, channel in parse_station_dump(output, expected_channel=self.channel)]


class MonitorModeCollector(ObservationCollector):
    """Collect radiotap RSSI metadata from a monitor-capable interface.

    This implementation intentionally consumes line-oriented metadata from a
    constrained ``tcpdump`` invocation.  It does not inspect or persist packet
    payload bytes; adapters are injectable for deterministic unit tests.
    """

    def __init__(self, interface: str, channel: int, *, adapter: Optional[CommandAdapter] = None,
                 line_source: Optional[Callable[[], Iterable[str]]] = None) -> None:
        self.interface, self.channel = interface, _safe_channel(channel)
        self.adapter = adapter or SubprocessCommandAdapter()
        self.line_source = line_source
        if not interface:
            raise ValueError("wireless interface is required")

    def validate(self) -> None:
        info = self.adapter.run(("iw", "dev", self.interface, "info"))
        match = _CHANNEL.search(info)
        if match and int(match.group(1)) != self.channel:
            raise CollectorError(f"interface is on channel {match.group(1)}, expected configured channel")

    def collect(self) -> list[RawObservation]:
        if self.line_source:
            lines = self.line_source()
        else:
            # -I requests monitor mode; -e emits link metadata and -tt emits
            # timestamps.  No payload filter or capture file is used.
            output = self.adapter.run(("tcpdump", "-I", "-i", self.interface, "-e", "-tt",
                                       "-c", "32"), timeout_s=8.0)
            lines = output.splitlines()
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        observations: list[RawObservation] = []
        for line in lines:
            parsed = parse_monitor_line(line, expected_channel=self.channel)
            if parsed:
                token, rssi, channel = parsed
                observations.append(RawObservation(token, rssi, channel, now))
        return observations


def inspect_interface(interface: str, *, adapter: Optional[CommandAdapter] = None) -> dict[str, object]:
    if not interface:
        raise ValueError("interface is required")
    output = (adapter or SubprocessCommandAdapter()).run(("iw", "dev", interface, "info"))
    channel = None
    match = _CHANNEL.search(output)
    if match:
        channel = int(match.group(1))
    return {"interface": interface, "channel": channel, "info_available": True}


def validate_channel(interface: str, expected_channel: int, *, adapter: Optional[CommandAdapter] = None) -> bool:
    observed = inspect_interface(interface, adapter=adapter)["channel"]
    if observed is None:
        raise CollectorError("interface output did not report a channel")
    if observed != expected_channel:
        raise CollectorError(f"interface is on channel {observed}, expected configured channel {expected_channel}")
    return True
