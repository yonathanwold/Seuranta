"""Bounded SQLite-backed FIFO delivery queue."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time
from typing import Callable, Optional

from .contracts import ObservationBatch, dumps


@dataclass(frozen=True)
class FlushResult:
    sent: int = 0
    retained: int = 0
    dropped: int = 0
    failed: int = 0


class SQLiteBuffer:
    """Persist batches before delivery and preserve IDs across restarts."""

    def __init__(self, path: str | Path, *, max_batches: int = 500, max_bytes: int = 20_000_000,
                 base_backoff_s: float = 1.0, max_backoff_s: float = 300.0,
                 clock: Callable[[], float] = time.time) -> None:
        if max_batches <= 0 or max_bytes <= 0:
            raise ValueError("buffer bounds must be positive")
        self.path = str(path)
        self.max_batches = max_batches
        self.max_bytes = max_bytes
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self.clock = clock
        parent = Path(self.path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS batches ("
            "batch_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL, payload TEXT NOT NULL, "
            "payload_bytes INTEGER NOT NULL, enqueued_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
            "next_attempt REAL NOT NULL)"
        )
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_batches_fifo ON batches(sequence, enqueued_at)")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteBuffer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def depth(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0])

    def bytes_pending(self) -> int:
        return int(self._connection.execute("SELECT COALESCE(SUM(payload_bytes),0) FROM batches").fetchone()[0])

    def contains(self, batch_id: str) -> bool:
        return self._connection.execute("SELECT 1 FROM batches WHERE batch_id=?", (batch_id,)).fetchone() is not None

    def enqueue(self, batch: ObservationBatch) -> bool:
        """Insert once.  Return False for a duplicate or a full bounded queue."""

        payload = dumps(batch)
        size = len(payload.encode("utf-8"))
        if size > self.max_bytes:
            raise ValueError("batch exceeds configured buffer byte bound")
        if self.contains(batch.batch_id):
            return False
        if self.depth() >= self.max_batches or self.bytes_pending() + size > self.max_bytes:
            return False
        now = self.clock()
        self._connection.execute("INSERT INTO batches(batch_id,sequence,payload,payload_bytes,enqueued_at,next_attempt) VALUES(?,?,?,?,?,?)",
                                 (batch.batch_id, batch.batch_sequence, payload, size, now, now))
        self._connection.commit()
        return True

    def _rows_fifo(self, limit: int) -> list[sqlite3.Row]:
        self._connection.row_factory = sqlite3.Row
        return list(self._connection.execute(
            "SELECT * FROM batches ORDER BY sequence ASC,enqueued_at ASC LIMIT ?", (limit,)))

    def flush(self, send: Callable[[dict], None], *, limit: int = 50) -> FlushResult:
        """Send FIFO-ready batches; failures remain with exponential backoff."""

        if limit <= 0:
            return FlushResult()
        sent = retained = dropped = failed = 0
        now = self.clock()
        # Inspect the head regardless of readiness. If it is in backoff, do
        # not allow a newer ready batch to overtake it.
        for row in self._rows_fifo(limit):
            if float(row["next_attempt"]) > now:
                break
            try:
                payload = json.loads(row["payload"])
                send(payload)
            except Exception:
                failed += 1
                attempts = int(row["attempts"]) + 1
                delay = min(self.max_backoff_s, self.base_backoff_s * (2 ** min(attempts - 1, 16)))
                self._connection.execute("UPDATE batches SET attempts=?,next_attempt=? WHERE batch_id=?",
                                         (attempts, now + delay, row["batch_id"]))
                retained += 1
                # Preserve FIFO delivery: do not overtake a failed batch.
                break
            else:
                self._connection.execute("DELETE FROM batches WHERE batch_id=?", (row["batch_id"],))
                sent += 1
        self._connection.commit()
        return FlushResult(sent=sent, retained=retained, dropped=dropped, failed=failed)

    def pending(self) -> list[dict]:
        self._connection.row_factory = sqlite3.Row
        rows = self._connection.execute("SELECT payload FROM batches ORDER BY sequence ASC,enqueued_at ASC").fetchall()
        return [json.loads(row["payload"]) for row in rows]
