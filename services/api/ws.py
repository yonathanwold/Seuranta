from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket


SnapshotFactory = Callable[[], Awaitable[dict[str, Any]]]


class LiveConnection:
    def __init__(self, websocket: WebSocket, max_queue: int = 50) -> None:
        self.websocket = websocket
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)


class LiveManager:
    def __init__(self, snapshot_factory: SnapshotFactory) -> None:
        self._snapshot_factory = snapshot_factory
        self._connections: set[LiveConnection] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> LiveConnection:
        await websocket.accept()
        connection = LiveConnection(websocket)
        async with self._lock:
            self._connections.add(connection)
        return connection

    async def disconnect(self, connection: LiveConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)

    async def publish(self, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = tuple(self._connections)
        for connection in connections:
            try:
                connection.queue.put_nowait(message)
            except asyncio.QueueFull:
                # A slow client receives a fresh snapshot instead of an
                # unbounded backlog of deltas.
                with contextlib.suppress(asyncio.QueueEmpty):
                    while True:
                        connection.queue.get_nowait()
            if connection.queue.empty():
                with contextlib.suppress(asyncio.QueueFull):
                    connection.queue.put_nowait({"type": "snapshot_required"})

    async def send_initial(self, connection: LiveConnection, since_revision: int | None) -> None:
        snapshot = await self._snapshot_factory()
        snapshot_revision = int(snapshot.get("state_revision", 0))
        await connection.websocket.send_json({"type": "snapshot", "state_revision": snapshot_revision, "data": snapshot,
                                              "since_revision": since_revision})
