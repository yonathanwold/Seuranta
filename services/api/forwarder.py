from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from services.data.models import ObservationBatch

logger = logging.getLogger("seuranta.positioning")


class PositioningForwarder:
    """Bounded, retrying adapter. Local persistence occurs before enqueueing."""

    def __init__(self, url: str | None, maxsize: int = 100) -> None:
        self.url = url.rstrip("/") if url else None
        self.queue: asyncio.Queue[ObservationBatch] = asyncio.Queue(maxsize=maxsize)
        self._task: asyncio.Task[None] | None = None
        self.failed = 0
        self.forwarded = 0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    async def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._worker(), name="positioning-forwarder")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def enqueue(self, batch: ObservationBatch) -> bool:
        if not self.enabled:
            return False
        try:
            self.queue.put_nowait(batch)
            return True
        except asyncio.QueueFull:
            logger.warning("positioning queue full; local observations retained")
            return False

    async def _worker(self) -> None:
        while True:
            batch = await self.queue.get()
            delivered = False
            for attempt in range(4):
                try:
                    await asyncio.to_thread(self._post, batch)
                    self.forwarded += 1
                    delivered = True
                    break
                except Exception as exc:  # noqa: BLE001 - adapter must not stop ingestion
                    if attempt == 3:
                        logger.warning("positioning unavailable after retries: %s", type(exc).__name__)
                    else:
                        await asyncio.sleep(2**attempt)
            if not delivered:
                self.failed += 1
            self.queue.task_done()

    def _post(self, batch: ObservationBatch) -> None:
        request = urllib.request.Request(
            f"{self.url}/internal/v1/observation-batches",
            data=json.dumps(batch.model_dump(mode="json")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status >= 300:
                raise urllib.error.HTTPError(request.full_url, response.status, "positioning rejected", response.headers, None)
