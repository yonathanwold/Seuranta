"""Run-scoped temporary identifiers and consent-aware session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import base64
from datetime import datetime
import hashlib
import hmac
from typing import Optional

from .contracts import Session, utc_now


class RunPseudonymizer:
    """Derive stable short IDs within one run without retaining raw IDs.

    The raw device token is accepted only for the duration of this call.  It
    is never returned, logged, serialized, or kept by this class.
    """

    def __init__(self, run_secret: str | bytes, run_id: str, length: int = 10) -> None:
        secret = run_secret.encode("utf-8") if isinstance(run_secret, str) else bytes(run_secret)
        if len(secret) < 16:
            raise ValueError("run secret must be at least 16 bytes")
        if not run_id:
            raise ValueError("run_id is required")
        if not 6 <= length <= 26:
            raise ValueError("temporary ID length must be between 6 and 26")
        self._run_key = hmac.new(secret, run_id.encode("utf-8"), hashlib.sha256).digest()
        self._length = length

    def temporary_session_id(self, raw_identifier: bytes | str) -> str:
        if isinstance(raw_identifier, str):
            raw = raw_identifier.encode("utf-8")
        else:
            raw = bytes(raw_identifier)
        digest = hmac.new(self._run_key, raw, hashlib.sha256).digest()
        encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
        return encoded[: self._length]


@dataclass
class _ActiveSession:
    session: Session
    raw_identifier: str


class SessionRegistry:
    """Hold active opt-in state and ephemeral raw-token mappings in memory."""

    def __init__(self, *, run_id: str, deployment_id: str, mode: str, anchor_id: str,
                 run_secret: str, raw_retention: bool = True) -> None:
        self.run_id = run_id
        self.deployment_id = deployment_id
        self.mode = mode
        self.anchor_id = anchor_id
        self._pseudonymizer = RunPseudonymizer(run_secret, run_id)
        self._by_session: dict[str, _ActiveSession] = {}
        self._by_raw: dict[str, str] = {}
        self._raw_retention = raw_retention

    def start(self, raw_identifier: str, *, now: Optional[str] = None) -> Session:
        if not raw_identifier:
            raise ValueError("a device token is required for an opted-in session")
        session_id = self._pseudonymizer.temporary_session_id(raw_identifier)
        timestamp = now or utc_now()
        existing = self._by_session.get(session_id)
        if existing:
            session = existing.session
            if session.status != "ACTIVE":
                session = Session(session.session_id, session.run_id, session.deployment_id, session.mode,
                                  "ACTIVE", session.consent_scope, session.started_at, timestamp, session.origin_anchor_id)
            else:
                session = Session(session.session_id, session.run_id, session.deployment_id, session.mode,
                                  "ACTIVE", session.consent_scope, session.started_at, timestamp, session.origin_anchor_id)
        else:
            session = Session(session_id=session_id, run_id=self.run_id, deployment_id=self.deployment_id,
                              mode=self.mode, status="ACTIVE", consent_scope="DEMO_NETWORK",
                              started_at=timestamp, last_seen_at=timestamp, origin_anchor_id=self.anchor_id)
        if self._raw_retention:
            self._by_raw[raw_identifier] = session_id
            self._by_session[session_id] = _ActiveSession(session, raw_identifier)
        else:
            self._by_session[session_id] = _ActiveSession(session, "")
        return session

    def state_for_raw(self, raw_identifier: str) -> Optional[Session]:
        session_id = self._by_raw.get(raw_identifier)
        if not session_id:
            return None
        return self._state_for_session(session_id)

    def session_for_raw(self, raw_identifier: str) -> Optional[Session]:
        """Return a session only for an active opted-in raw token."""

        session = self.state_for_raw(raw_identifier)
        if session is None:
            # A backend-created active session can be synchronized without
            # exposing its raw identifier. Derive the candidate ID in memory
            # and retain the raw token only for this process/run.
            candidate = self._pseudonymizer.temporary_session_id(raw_identifier)
            state = self._by_session.get(candidate)
            if state:
                session = state.session
                if self._raw_retention:
                    self._by_raw[raw_identifier] = candidate
        if not session or session.status != "ACTIVE":
            return None
        return session

    def register_session(self, session: Session, raw_identifier: Optional[str] = None) -> None:
        if (session.run_id != self.run_id or session.deployment_id != self.deployment_id
                or session.mode != self.mode):
            raise ValueError("session belongs to a different run, deployment, or mode")
        self._by_session[session.session_id] = _ActiveSession(session, raw_identifier or "")
        if raw_identifier:
            self._by_raw[raw_identifier] = session.session_id

    def mark_silent(self, session_id: str, *, now: Optional[str] = None) -> Session:
        return self._change(session_id, "SILENT", now=now)

    def end(self, session_id: str, *, now: Optional[str] = None) -> Session:
        result = self._change(session_id, "ENDED", now=now)
        active = self._by_session.pop(session_id, None)
        if active and active.raw_identifier:
            self._by_raw.pop(active.raw_identifier, None)
        return result

    def all_sessions(self) -> list[Session]:
        return [state.session for state in self._by_session.values()]

    def _state_for_session(self, session_id: str) -> Optional[Session]:
        state = self._by_session.get(session_id)
        return state.session if state else None

    def _change(self, session_id: str, status: str, *, now: Optional[str]) -> Session:
        state = self._by_session.get(session_id)
        if not state:
            raise KeyError("unknown session")
        if state.session.status == "ENDED" and status != "ENDED":
            raise ValueError("ended sessions cannot become active")
        timestamp = now or utc_now()
        current = state.session
        state.session = Session(current.session_id, current.run_id, current.deployment_id, current.mode,
                                status, current.consent_scope, current.started_at, timestamp, current.origin_anchor_id)
        return state.session

    def touch(self, session_id: str, *, now: Optional[str] = None) -> Session:
        state = self._by_session.get(session_id)
        if not state or state.session.status != "ACTIVE":
            raise ValueError("only active sessions can be observed")
        timestamp = now or utc_now()
        try:
            current_time = datetime.fromisoformat(state.session.last_seen_at[:-1] + "+00:00")
            observed_time = datetime.fromisoformat(timestamp[:-1] + "+00:00")
            if observed_time < current_time:
                timestamp = state.session.last_seen_at
        except (ValueError, TypeError):
            pass
        return self._change(session_id, "ACTIVE", now=timestamp)

    def rotate(self, run_id: str, run_secret: str) -> "SessionRegistry":
        """Create a fresh registry for a new run; old mappings are discarded."""

        return SessionRegistry(run_id=run_id, deployment_id=self.deployment_id, mode=self.mode,
                                anchor_id=self.anchor_id, run_secret=run_secret, raw_retention=self._raw_retention)
