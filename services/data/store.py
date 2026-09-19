"""Thread-safe SQLite persistence with restart-safe local state."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import (
    Anomaly,
    BuildingState,
    SpatialEvent,
    IntelligenceSummary,
    Mode,
    NodeHeartbeat,
    ObservationBatch,
    PositionEstimate,
    SessionCreate,
    SignalObservation,
    utc_now,
)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value: str) -> dict[str, Any]:
    return json.loads(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class LocalStore:
    """SQLite implementation used by live ingestion and fallback analytics."""

    def __init__(self, path: str | Path = "./seuranta.db", retention_days: int = 30) -> None:
        self.path = str(path)
        self.retention_days = retention_days
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS observations (
                  observation_id TEXT PRIMARY KEY,
                  observed_at TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  deployment_id TEXT NOT NULL,
                  building_id TEXT NOT NULL,
                  floor_id TEXT NOT NULL,
                  anchor_id TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observations_scope_time
                  ON observations (run_id, deployment_id, building_id, floor_id, observed_at);
                CREATE TABLE IF NOT EXISTS positions (
                  position_id TEXT PRIMARY KEY,
                  calculated_at TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  deployment_id TEXT NOT NULL,
                  building_id TEXT NOT NULL,
                  floor_id TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  zone_id TEXT,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_positions_scope_time
                  ON positions (run_id, deployment_id, building_id, floor_id, calculated_at);
                CREATE TABLE IF NOT EXISTS events (
                  event_id TEXT PRIMARY KEY,
                  occurred_at TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  deployment_id TEXT NOT NULL,
                  building_id TEXT NOT NULL,
                  floor_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_scope_time
                  ON events (run_id, deployment_id, building_id, floor_id, occurred_at);
                CREATE TABLE IF NOT EXISTS heartbeats (
                  heartbeat_id TEXT PRIMARY KEY,
                  emitted_at TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  deployment_id TEXT NOT NULL,
                  building_id TEXT NOT NULL,
                  floor_id TEXT NOT NULL,
                  anchor_id TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_heartbeats_scope_time
                  ON heartbeats (run_id, deployment_id, building_id, floor_id, emitted_at);
                CREATE TABLE IF NOT EXISTS sessions (
                  session_id TEXT PRIMARY KEY,
                  started_at TEXT NOT NULL,
                  ended_at TEXT,
                  run_id TEXT NOT NULL,
                  deployment_id TEXT NOT NULL,
                  building_id TEXT NOT NULL,
                  floor_id TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_scope
                  ON sessions (run_id, deployment_id, building_id, floor_id, started_at);
                CREATE TABLE IF NOT EXISTS anomalies (
                  anomaly_id TEXT PRIMARY KEY,
                  detected_at TEXT NOT NULL,
                  status TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  building_id TEXT,
                  floor_id TEXT,
                  mode TEXT NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                  outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_type TEXT NOT NULL,
                  record_id TEXT NOT NULL,
                  payload TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  attempts INTEGER NOT NULL DEFAULT 0,
                  next_attempt_at TEXT NOT NULL,
                  last_error TEXT,
                  UNIQUE(record_type, record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                  ON outbox (status, next_attempt_at);
                """
                )

    def _enqueue_outbox(self, record_type: str, record_id: str, payload: dict[str, Any]) -> None:
        """Queue one accepted contract for an optional downstream batch sink."""
        self._conn.execute(
            "INSERT INTO outbox(record_type,record_id,payload,next_attempt_at) VALUES(?,?,?,?) "
            "ON CONFLICT(record_type,record_id) DO UPDATE SET payload=excluded.payload, "
            "status='pending', attempts=0, next_attempt_at=excluded.next_attempt_at, last_error=NULL",
            (record_type, record_id, _json(payload), _iso(utc_now())),
        )

    def _scope(self, table: str, run_id: str, deployment_id: str | None, building_id: str | None,
               floor_id: str | None, limit: int, offset: int, order_column: str) -> list[dict[str, Any]]:
        clauses = ["run_id = ?"]
        args: list[Any] = [run_id]
        for name, value in (("deployment_id", deployment_id), ("building_id", building_id), ("floor_id", floor_id)):
            if value is not None:
                clauses.append(f"{name} = ?")
                args.append(value)
        args.extend([max(1, min(limit, 1000)), max(0, offset)])
        rows = self._conn.execute(
            f"SELECT payload FROM {table} WHERE {' AND '.join(clauses)} "
            f"ORDER BY {order_column} DESC LIMIT ? OFFSET ?", args
        ).fetchall()
        return [_loads(row[0]) for row in rows]

    def add_session(self, session: SessionCreate) -> tuple[dict[str, Any], bool]:
        payload = session.model_dump(mode="json")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id,started_at,run_id,deployment_id,building_id,floor_id,mode,payload) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (session.session_id, _iso(session.started_at), session.run_id, session.deployment_id,
                 session.building_id, session.floor_id, session.mode.value, _json(payload)),
            )
            if cur.rowcount:
                self._enqueue_outbox("session", session.session_id, payload)
        return payload, cur.rowcount == 0

    def end_session(self, session_id: str, ended_at: datetime) -> dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT payload FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return None
            payload = _loads(row[0])
            payload["ended_at"] = _iso(ended_at)
            self._conn.execute("UPDATE sessions SET ended_at = ?, payload = ? WHERE session_id = ?",
                               (_iso(ended_at), _json(payload), session_id))
            self._enqueue_outbox("session", session_id, payload)
            return payload

    def write_observation_batch(self, batch: ObservationBatch) -> dict[str, int]:
        accepted = duplicate = rejected = 0
        with self._lock, self._conn:
            for observation in batch.observations:
                payload = observation.model_dump(mode="json")
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO observations(observation_id,observed_at,run_id,deployment_id,building_id,floor_id,anchor_id,session_id,mode,payload) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (observation.observation_id, _iso(observation.observed_at), observation.run_id,
                     observation.deployment_id, observation.building_id, observation.floor_id,
                     observation.anchor_id, observation.session_id, observation.mode.value, _json(payload)),
                )
                if cur.rowcount:
                    accepted += 1
                    self._enqueue_outbox("observation", observation.observation_id, payload)
                else:
                    duplicate += 1
        return {"accepted": accepted, "duplicate": duplicate, "rejected": rejected}

    def add_position(self, position: PositionEstimate) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO positions(position_id,calculated_at,run_id,deployment_id,building_id,floor_id,session_id,zone_id,mode,payload) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (position.position_id, _iso(position.calculated_at), position.run_id, position.deployment_id,
                 position.building_id, position.floor_id, position.session_id, position.zone_id,
                 position.mode.value, _json(position)),
            )
            if cur.rowcount:
                self._enqueue_outbox("position", position.position_id, position.model_dump(mode="json"))
            return bool(cur.rowcount)

    def add_event(self, event: SpatialEvent) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO events(event_id,occurred_at,run_id,deployment_id,building_id,floor_id,event_type,mode,payload) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (event.event_id, _iso(event.occurred_at), event.run_id, event.deployment_id,
                 event.building_id, event.floor_id, event.event_type, event.mode.value, _json(event)),
            )
            if cur.rowcount:
                self._enqueue_outbox("event", event.event_id, event.model_dump(mode="json"))
            return bool(cur.rowcount)

    def add_heartbeat(self, heartbeat: NodeHeartbeat) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO heartbeats(heartbeat_id,emitted_at,run_id,deployment_id,building_id,floor_id,anchor_id,mode,payload) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (heartbeat.heartbeat_id, _iso(heartbeat.emitted_at), heartbeat.run_id, heartbeat.deployment_id,
                 heartbeat.building_id, heartbeat.floor_id, heartbeat.anchor_id, heartbeat.mode.value, _json(heartbeat)),
            )
            if cur.rowcount:
                self._enqueue_outbox("heartbeat", heartbeat.heartbeat_id, heartbeat.model_dump(mode="json"))
            return bool(cur.rowcount)

    def list_observations(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                          floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return self._scope("observations", run_id, deployment_id, building_id, floor_id, limit, offset, "observed_at")

    def list_positions(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                       floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return self._scope("positions", run_id, deployment_id, building_id, floor_id, limit, offset, "calculated_at")

    def list_events(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                    floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return self._scope("events", run_id, deployment_id, building_id, floor_id, limit, offset, "occurred_at")

    def list_sessions(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                      floor_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return self._scope("sessions", run_id, deployment_id, building_id, floor_id, limit, offset, "started_at")

    def list_nodes(self, run_id: str, deployment_id: str | None = None, building_id: str | None = None,
                   floor_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            clauses = ["run_id = ?"]
            args: list[Any] = [run_id]
            for name, value in (("deployment_id", deployment_id), ("building_id", building_id), ("floor_id", floor_id)):
                if value is not None:
                    clauses.append(f"{name} = ?")
                    args.append(value)
            inner = " AND ".join(clauses)
            outer = " AND ".join(clause.replace("run_id", "h.run_id").replace("deployment_id", "h.deployment_id")
                                   .replace("building_id", "h.building_id").replace("floor_id", "h.floor_id") for clause in clauses)
            rows = self._conn.execute(
                f"""SELECT h.payload FROM heartbeats h JOIN (
                   SELECT anchor_id, MAX(emitted_at) AS latest FROM heartbeats
                   WHERE {inner} GROUP BY anchor_id
                ) x ON x.anchor_id = h.anchor_id AND x.latest = h.emitted_at
                WHERE {outer}""", args + args).fetchall()
            return [_loads(row[0]) for row in rows]

    def upsert_anomaly(self, anomaly: Anomaly) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR REPLACE INTO anomalies(anomaly_id,detected_at,status,run_id,building_id,floor_id,mode,payload) VALUES(?,?,?,?,?,?,?,?)",
                (anomaly.anomaly_id, _iso(anomaly.detected_at), anomaly.status, anomaly.run_id,
                 anomaly.building_id, anomaly.floor_id, anomaly.mode.value, _json(anomaly)),
            )
            return bool(cur.rowcount)

    def list_anomalies(self, run_id: str, building_id: str | None = None, floor_id: str | None = None) -> list[Anomaly]:
        clauses = ["run_id = ?"]
        args: list[Any] = [run_id]
        if building_id:
            clauses.append("(building_id = ? OR building_id IS NULL)")
            args.append(building_id)
        if floor_id:
            clauses.append("(floor_id = ? OR floor_id IS NULL)")
            args.append(floor_id)
        with self._lock:
            rows = self._conn.execute(f"SELECT payload FROM anomalies WHERE {' AND '.join(clauses)} ORDER BY detected_at DESC", args).fetchall()
        return [Anomaly.model_validate(_loads(row[0])) for row in rows]

    def claim_outbox(self, limit: int = 50) -> list[dict[str, Any]]:
        now = _iso(utc_now())
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM outbox WHERE status = 'pending' AND next_attempt_at <= ? ORDER BY outbox_id LIMIT ?",
                (now, limit),
            ).fetchall()
            items = []
            for row in rows:
                self._conn.execute("UPDATE outbox SET status='processing', attempts=attempts+1 WHERE outbox_id=?", (row["outbox_id"],))
                items.append(dict(row))
            return items

    def complete_outbox(self, outbox_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM outbox WHERE outbox_id = ?", (outbox_id,))

    def fail_outbox(self, outbox_id: int, error: str, attempts: int) -> None:
        delay = min(300, 2 ** min(attempts, 8))
        next_at = utc_now() + timedelta(seconds=delay)
        with self._lock, self._conn:
            self._conn.execute("UPDATE outbox SET status='pending', last_error=?, next_attempt_at=? WHERE outbox_id=?",
                               (error[:500], _iso(next_at), outbox_id))

    def counts(self, run_id: str, building_id: str | None = None, floor_id: str | None = None) -> dict[str, int]:
        with self._lock:
            result: dict[str, int] = {}
            for table, label in (("observations", "observations"), ("positions", "positions"), ("events", "events"),
                                 ("sessions", "sessions"), ("heartbeats", "nodes")):
                clauses = ["run_id = ?"]
                args: list[Any] = [run_id]
                if building_id:
                    clauses.append("building_id = ?")
                    args.append(building_id)
                if floor_id:
                    clauses.append("floor_id = ?")
                    args.append(floor_id)
                result[label] = int(self._conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(clauses)}", args).fetchone()[0])
            return result

    def reconstruct_state(self, run_id: str, deployment_id: str, building_id: str, floor_id: str, mode: Mode,
                          revision: int) -> BuildingState:
        observations = self.list_observations(run_id, deployment_id, building_id, floor_id, 10000)
        sessions = self.list_sessions(run_id, deployment_id, building_id, floor_id, 500)
        positions = self.list_positions(run_id, deployment_id, building_id, floor_id, 500)
        events = self.list_events(run_id, deployment_id, building_id, floor_id, 100)
        nodes = self.list_nodes(run_id, deployment_id, building_id, floor_id)
        latest_observation: dict[str, datetime] = {}
        for observation in observations:
            timestamp = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
            if timestamp > latest_observation.get(observation["session_id"], datetime.min.replace(tzinfo=timezone.utc)):
                latest_observation[observation["session_id"]] = timestamp
        now = utc_now()
        session_view = []
        for session in sessions:
            view = dict(session)
            if session.get("ended_at"):
                view["status"] = "ended"
            elif now - latest_observation.get(session["session_id"], now) > timedelta(seconds=90):
                view["status"] = "silent"
            else:
                view["status"] = "active"
            session_view.append(view)
        zones: dict[str, int] = {}
        for position in positions:
            if position.get("zone_id"):
                zones[position["zone_id"]] = zones.get(position["zone_id"], 0) + 1
        zone_metrics = [{"zone_id": zone_id, "occupancy": count} for zone_id, count in sorted(zones.items())]
        active = sum(1 for session in session_view if session["status"] == "active")
        silent = sum(1 for session in session_view if session["status"] == "silent")
        ended = sum(1 for session in session_view if session["status"] == "ended")
        mode_counts: dict[str, int] = {}
        for table in ("observations", "positions", "events", "sessions", "heartbeats"):
            rows = self._conn.execute(f"SELECT mode, COUNT(*) AS count FROM {table} WHERE run_id = ? GROUP BY mode", (run_id,)).fetchall()
            mode_counts[table] = sum(int(row["count"]) for row in rows if row["mode"] == mode.value)
        return BuildingState(
            state_revision=revision,
            generated_at=now,
            deployment_id=deployment_id,
            building_id=building_id,
            floor_id=floor_id,
            run_id=run_id,
            mode=mode,
            counts={**self.counts(run_id, building_id, floor_id), "active_sessions": active, "silent_sessions": silent,
                    "ended_sessions": ended, "event_rate_per_second": len(events) / 600, "real_simulated_records": mode_counts.get("events", 0)},
            sessions=session_view,
            positions=positions,
            nodes=nodes,
            zones=[{"zone_id": key} for key in sorted(zones)],
            zone_metrics=zone_metrics,
            recent_events=events,
            anomalies=self.list_anomalies(run_id, building_id, floor_id),
            is_partial=False,
        )

    def analytics(self, run_id: str, deployment_id: str | None, building_id: str | None, floor_id: str | None,
                  window_minutes: int = 10) -> dict[str, Any]:
        observations = self.list_observations(run_id, deployment_id, building_id, floor_id, 10000)
        positions = self.list_positions(run_id, deployment_id, building_id, floor_id, 10000)
        events = self.list_events(run_id, deployment_id, building_id, floor_id, 10000)
        sessions = self.list_sessions(run_id, deployment_id, building_id, floor_id, 10000)
        zone_counts: dict[str, int] = {}
        for p in positions:
            if p.get("zone_id"):
                zone_counts[p["zone_id"]] = zone_counts.get(p["zone_id"], 0) + 1
        transitions = [e for e in events if e.get("event_type") in {"zone_transition", "entry", "exit"}]
        dwell = [int(e["dwell_ms"]) for e in events if e.get("dwell_ms") is not None]
        dwell.sort()
        p95 = dwell[min(len(dwell) - 1, int(len(dwell) * 0.95))] if dwell else 0
        entries = [e for e in events if e.get("event_type") == "entry"]
        exits = [e for e in events if e.get("event_type") == "exit"]
        nodes = self.list_nodes(run_id, deployment_id, building_id, floor_id)
        node_modes = {"real": 0, "simulated": 0}
        available_nodes = 0
        for node in nodes:
            node_modes[node.get("mode", "real")] = node_modes.get(node.get("mode", "real"), 0) + 1
            if node.get("status") == "online":
                available_nodes += 1
        return {
            "window_minutes": window_minutes,
            "occupancy": {"total_positions": len(positions), "by_zone": zone_counts, "active_sessions": sum(1 for s in sessions if not s.get("ended_at"))},
            "transitions": {"count": len(transitions), "items": transitions[-100:]},
            "entries_exits": {"entries": len(entries), "exits": len(exits)},
            "dwell": {"count": len(dwell), "average_ms": sum(dwell) / len(dwell) if dwell else 0, "p95_ms": p95},
            "event_rate": len(events) / max(window_minutes * 60, 1),
            "anchor_availability": {"available": available_nodes, "total": len(nodes), "by_mode": node_modes},
            "real_simulated_counts": {"real": sum(1 for x in observations + positions + events if x.get("mode") == "real"),
                                      "simulated": sum(1 for x in observations + positions + events if x.get("mode") == "simulated")},
            "observations": len(observations),
            "data_through": max((x.get("observed_at", "") for x in observations), default=None),
        }

    def prune(self) -> int:
        cutoff = _iso(utc_now() - timedelta(days=self.retention_days))
        with self._lock, self._conn:
            total = 0
            for table, column in (("observations", "observed_at"), ("positions", "calculated_at"), ("events", "occurred_at"), ("heartbeats", "emitted_at")):
                cur = self._conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
                total += cur.rowcount
            return total
