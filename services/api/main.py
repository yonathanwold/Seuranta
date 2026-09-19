from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from services.data.models import (
    Anomaly,
    BuildingState,
    DevPositionRequest,
    Mode,
    NodeHeartbeat,
    ObservationBatch,
    PositionEstimate,
    QueryRequest,
    SessionCreate,
    SessionEnd,
    SignalObservation,
    SpatialEvent,
    TrackerCalibration,
    TrackerHello,
    TrackerLocation,
)
from services.data.anomalies import detect_anomalies
from services.data.databricks import DatabricksAdapter
from services.data.store import LocalStore

from .forwarder import PositioningForwarder
from .intelligence import answer_query
from .settings import Settings
from .tracking import IngestResult, TrackingEngine, TrackingScope
from .ws import LiveManager


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seuranta.api")


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = LocalStore(settings.database_path, settings.retention_days)
        self.forwarder = PositioningForwarder(settings.positioning_url, settings.positioning_queue_size)
        self.databricks = DatabricksAdapter(
            settings.databricks_host,
            settings.databricks_token,
            settings.databricks_catalog,
            settings.databricks_schema,
            settings.databricks_warehouse_id,
        )
        self.state_revision = 0
        self.started_at = time.monotonic()
        self.live: LiveManager | None = None
        self.tracking = TrackingEngine(settings)
        self._expiry_task: asyncio.Task[None] | None = None
        self._tracker_signature: tuple[tuple[str, str, int], ...] = ()

    async def snapshot(self, request: Request | None = None) -> dict[str, Any]:
        # A reconnect without scope gets a deliberately explicit partial snapshot.
        return {"state_revision": self.state_revision, "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_partial": True, "reason": "scope_required"}

    def scope(self, run_id: str, deployment_id: str, building_id: str, floor_id: str, mode: Any) -> BuildingState:
        state = self.store.reconstruct_state(run_id, deployment_id, building_id, floor_id, mode, self.state_revision)
        if mode != Mode.REAL:
            return state

        tracker_scope = TrackingScope(run_id, deployment_id, building_id, floor_id)
        tracker_ids = self.tracking.session_ids_for(tracker_scope)
        if not tracker_ids:
            return state

        # The legacy SQLite state keeps the historical position stream.  The
        # tracker overlay replaces only anonymous phone sessions with their
        # current (active or degraded) position so the dashboard receives the
        # latest state while existing ingest contracts remain intact.
        state.positions = [
            position for position in state.positions
            if position.get("session_id") not in tracker_ids
        ]
        state.positions.extend(
            position.model_dump(mode="json")
            for position in self.tracking.positions_for(tracker_scope)
        )
        state.positions.sort(key=lambda position: position.get("calculated_at", ""), reverse=True)

        state.sessions = [
            session for session in state.sessions
            if session.get("session_id") not in tracker_ids
        ]
        tracker_sessions = self.tracking.sessions_for(tracker_scope)
        state.sessions.extend(tracker_sessions)
        state.counts["active_sessions"] = sum(
            1 for session in state.sessions if session.get("status") in {"active", "degraded"}
        )
        state.counts["stale_sessions"] = sum(
            1 for session in tracker_sessions if session.get("status") == "degraded"
        )

        zone_counts: dict[str, int] = {}
        for position in state.positions:
            zone_id = position.get("zone_id")
            if zone_id:
                zone_counts[zone_id] = zone_counts.get(zone_id, 0) + 1
        state.zones = [{"zone_id": zone_id} for zone_id in sorted(zone_counts)]
        state.zone_metrics = [
            {"zone_id": zone_id, "occupancy": count}
            for zone_id, count in sorted(zone_counts.items())
        ]
        return state

    async def expire_tracker_sessions(self) -> None:
        """Publish a fresh state when a phone changes active/stale/expired state."""

        scope = self.tracking.default_scope
        session_views = self.tracking.sessions_for(scope)
        signature = tuple(
            (view["session_id"], view["status"], int(view["observation_count"]))
            for view in session_views
        )
        if signature == self._tracker_signature:
            return
        self._tracker_signature = signature
        if session_views:
            await self.publish("state", self.scope(
                scope.run_id,
                scope.deployment_id,
                scope.building_id,
                scope.floor_id,
                Mode.REAL,
            ))

    async def expiry_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            await self.expire_tracker_sessions()

    async def publish(self, event_type: str, data: Any) -> None:
        self.state_revision += 1
        if self.live:
            await self.live.publish({"type": event_type, "state_revision": self.state_revision,
                                     "data": data.model_dump(mode="json") if hasattr(data, "model_dump") else data})


def runtime(request: Request) -> Runtime:
    return request.app.state.runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    rt = Runtime(settings)
    app.state.runtime = rt
    rt.live = LiveManager(rt.snapshot)
    await rt.forwarder.start()
    rt._expiry_task = asyncio.create_task(rt.expiry_loop(), name="seuranta-tracker-expiry")
    try:
        yield
    finally:
        if rt._expiry_task:
            rt._expiry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await rt._expiry_task
        await rt.forwarder.stop()
        rt.store.close()


app = FastAPI(title="Seuranta Atlas API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(Settings.from_env().allowed_origins), allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

tracker_directory = Path(__file__).resolve().parents[2] / "tracker"
if tracker_directory.exists():
    app.mount("/tracker", StaticFiles(directory=tracker_directory, html=True), name="tracker")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
        raise
    response.headers["x-request-id"] = request_id
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.2f", request_id, request.method,
                request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    return response


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "request_error", **detail}})


@app.exception_handler(ValidationError)
async def validation_error(_: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "details": exc.errors()}})


def list_params(run_id: str = Query(...), deployment_id: str | None = Query(None), building_id: str | None = Query(None),
                floor_id: str | None = Query(None), limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    return {"run_id": run_id, "deployment_id": deployment_id, "building_id": building_id, "floor_id": floor_id,
            "limit": limit, "offset": offset}


def parse_mode(value: str) -> Mode:
    normalized = value.strip().lower()
    if normalized in {"real", "live", "production"}:
        return Mode.REAL
    if normalized in {"simulated", "simulation"}:
        return Mode.SIMULATED
    raise ValueError("invalid mode")


def tracker_scope(rt: Runtime, payload: Any) -> TrackingScope:
    try:
        return rt.tracking.resolve_scope(
            getattr(payload, "run_id", None),
            getattr(payload, "deployment_id", None),
            getattr(payload, "building_id", None),
            getattr(payload, "floor_id", None),
        )
    except ValueError as exc:
        raise HTTPException(422, {"message": str(exc), "code": "scope_mismatch"}) from exc


async def persist_tracker_result(rt: Runtime, result: IngestResult) -> dict[str, Any]:
    session_view: dict[str, Any] | None = None
    if result.session_created:
        rt.store.add_session(rt.tracking.session_create(result.session))
        session_view = next(
            (item for item in rt.tracking.sessions_for(result.session.scope) if item["session_id"] == result.session.session_id),
            None,
        )
        logger.info("tracker connected %s", result.session.session_id)

    if result.position is None:
        if session_view is not None:
            await rt.publish("session", session_view)
        return {
            "status": "calibration_required" if result.calibration_required else "accepted",
            "session_id": result.session.session_id,
            "calibration": rt.tracking.config_payload()["calibration"],
        }

    inserted = rt.store.add_position(result.position)
    if inserted:
        await rt.publish("position", result.position)
        logger.info("position updated %s", result.session.session_id)
    if session_view is not None:
        session_view = next(
            (item for item in rt.tracking.sessions_for(result.session.scope) if item["session_id"] == result.session.session_id),
            session_view,
        )
        await rt.publish("session", session_view)
    return {
        "status": "live",
        "session_id": result.session.session_id,
        "state_revision": rt.state_revision,
        "position": result.position.model_dump(mode="json"),
    }


async def materialize_calibrated_position(
    rt: Runtime,
    session: Any,
    scope: TrackingScope,
) -> dict[str, Any] | None:
    latest_location = session.latest_location
    if latest_location is None:
        return None
    result = rt.tracking.ingest_location(latest_location, scope)
    return await persist_tracker_result(rt, result)


@app.post("/api/v1/sessions", status_code=201)
async def create_session(session: SessionCreate, rt: Runtime = Depends(runtime)):
    payload, duplicate = rt.store.add_session(session)
    await rt.publish("session", payload)
    return {"data": payload, "duplicate": duplicate}


@app.get("/api/v1/sessions")
async def get_sessions(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    return {"data": rt.store.list_sessions(**params)}


@app.post("/api/v1/sessions/{session_id}/end")
async def end_session(session_id: str, body: SessionEnd, rt: Runtime = Depends(runtime)):
    payload = rt.store.end_session(session_id, body.ended_at)
    if payload is None:
        raise HTTPException(404, {"message": "session not found", "session_id": session_id})
    # Browser tracker sessions live in the in-memory overlay as well as the
    # durable session history.  Revoke that overlay immediately so Stop
    # Sharing removes the marker without waiting for expiry.
    tracker_scope = TrackingScope(
        payload["run_id"], payload["deployment_id"], payload["building_id"], payload["floor_id"]
    )
    try:
        rt.tracking.end_session(session_id, tracker_scope, body.ended_at)
    except ValueError:
        # Durable non-tracker sessions retain the existing sessions API
        # behavior; only anonymous browser tracker IDs are in this overlay.
        pass
    await rt.expire_tracker_sessions()
    await rt.publish("session_ended", payload)
    return {"data": payload}


@app.post("/api/v1/observations")
async def create_observation(observation: SignalObservation, rt: Runtime = Depends(runtime)):
    batch = ObservationBatch(producer_id="api", batch_sequence=observation.sequence_number, sent_at=datetime.now(timezone.utc),
                             run_id=observation.run_id, deployment_id=observation.deployment_id, mode=observation.mode,
                             observations=[observation])
    result = rt.store.write_observation_batch(batch)
    if result["accepted"]:
        rt.forwarder.enqueue(batch)
        await rt.publish("observation", observation)
    return {"data": result}


@app.post("/api/v1/observations/batch")
async def create_observation_batch(payload: dict[str, Any], rt: Runtime = Depends(runtime)):
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        raise HTTPException(422, {"message": "observations must be a non-empty list"})
    if len(raw_observations) > rt.settings.max_batch_size:
        raise HTTPException(413, {"message": "batch exceeds configured limit", "max_batch_size": rt.settings.max_batch_size})
    rejected: list[dict[str, Any]] = []
    observations: list[SignalObservation] = []
    batch_run_id = payload.get("run_id")
    batch_deployment_id = payload.get("deployment_id")
    batch_mode = payload.get("mode", "real")
    for index, raw in enumerate(raw_observations):
        try:
            item = SignalObservation.model_validate(raw)
            if item.run_id != batch_run_id or item.deployment_id != batch_deployment_id or item.mode.value != batch_mode:
                raise ValueError("observation scope does not match batch")
            observations.append(item)
        except (ValidationError, ValueError) as exc:
            rejected.append({"index": index, "observation_id": raw.get("observation_id") if isinstance(raw, dict) else None,
                             "reason": str(exc)})
    if not observations:
        raise HTTPException(422, {"message": "all observations were rejected", "rejected": rejected})
    try:
        batch = ObservationBatch.model_validate({**payload, "observations": observations})
    except ValidationError as exc:
        raise HTTPException(422, {"message": "invalid batch metadata", "details": exc.errors()}) from exc
    result = rt.store.write_observation_batch(batch)
    result["rejected"] = len(rejected)
    if result["accepted"]:
        rt.forwarder.enqueue(batch)
        await rt.publish("observations", {"batch_id": batch.batch_id, **result})
        for anomaly in detect_anomalies(rt.store, batch.run_id, batch.deployment_id,
                                        batch.observations[0].building_id, batch.observations[0].floor_id, batch.mode):
            await rt.publish("anomaly", anomaly)
    return {"data": {"batch_id": batch.batch_id, **result, "rejections": rejected,
                      "positioning_forwarded": bool(rt.settings.positioning_url)}}


@app.get("/api/v1/observations")
async def get_observations(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    return {"data": rt.store.list_observations(**params)}


@app.post("/api/v1/positions")
async def create_position(position: PositionEstimate, rt: Runtime = Depends(runtime)):
    inserted = rt.store.add_position(position)
    if inserted:
        await rt.publish("position", position)
        for anomaly in detect_anomalies(rt.store, position.run_id, position.deployment_id, position.building_id, position.floor_id, position.mode):
            await rt.publish("anomaly", anomaly)
    return {"data": position.model_dump(mode="json"), "duplicate": not inserted}


@app.get("/api/v1/positions")
async def get_positions(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    return {"data": rt.store.list_positions(**params)}


@app.post("/api/v1/events")
async def create_event(event: SpatialEvent, rt: Runtime = Depends(runtime)):
    inserted = rt.store.add_event(event)
    if inserted:
        await rt.publish("event", event)
        for anomaly in detect_anomalies(rt.store, event.run_id, event.deployment_id, event.building_id, event.floor_id, event.mode):
            await rt.publish("anomaly", anomaly)
    return {"data": event.model_dump(mode="json"), "duplicate": not inserted}


@app.get("/api/v1/events")
async def get_events(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    return {"data": rt.store.list_events(**params)}


@app.post("/api/v1/nodes/heartbeat")
async def heartbeat(node: NodeHeartbeat, rt: Runtime = Depends(runtime)):
    inserted = rt.store.add_heartbeat(node)
    if inserted:
        await rt.publish("node", node)
        for anomaly in detect_anomalies(rt.store, node.run_id, node.deployment_id, node.building_id, node.floor_id, node.mode):
            await rt.publish("anomaly", anomaly)
    return {"data": node.model_dump(mode="json"), "duplicate": not inserted}


@app.get("/api/v1/nodes")
async def get_nodes(run_id: str = Query(...), deployment_id: str | None = Query(None), building_id: str | None = Query(None),
                    floor_id: str | None = Query(None), rt: Runtime = Depends(runtime)):
    return {"data": rt.store.list_nodes(run_id, deployment_id, building_id, floor_id)}


@app.get("/api/v1/tracker/config")
async def tracker_config(rt: Runtime = Depends(runtime)):
    return {"data": rt.tracking.config_payload()}


@app.get("/api/v1/tracker/qr")
async def tracker_qr(url: str = Query(..., min_length=1, max_length=2_000)):
    """Render a local QR image without sending the tracker URL to a third party."""

    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - dependency is listed in requirements
        raise HTTPException(503, {"message": "QR rendering dependency is not installed"}) from exc
    image = qrcode.make(url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/v1/tracker/calibrate")
async def calibrate_tracker(payload: TrackerCalibration, rt: Runtime = Depends(runtime)):
    scope = tracker_scope(rt, payload)
    try:
        session = rt.tracking.calibrate(
            payload.session_id,
            scope,
            payload.latitude,
            payload.longitude,
            payload.calibration_id,
        )
    except ValueError as exc:
        code = "tracker_session_ended" if "session has ended" in str(exc).lower() else "calibration_error"
        raise HTTPException(409 if code == "tracker_session_ended" else 422, {"message": str(exc), "code": code}) from exc
    _, duplicate = rt.store.add_session(rt.tracking.session_create(session))
    if not duplicate:
        session_view = next(
            (item for item in rt.tracking.sessions_for(scope) if item["session_id"] == session.session_id),
            None,
        )
        if session_view is not None:
            await rt.publish("session", session_view)
    position_response = await materialize_calibrated_position(rt, session, scope)
    logger.info("session calibrated %s", session.session_id)
    return {
        "data": {
            "status": "calibrated",
            "session_id": session.session_id,
            "calibration": rt.tracking.config_payload()["calibration"],
            "position": position_response.get("position") if position_response else None,
        }
    }


@app.post("/api/v1/telemetry/location")
async def tracker_location_rest(payload: TrackerLocation, rt: Runtime = Depends(runtime)):
    scope = tracker_scope(rt, payload)
    try:
        result = rt.tracking.ingest_location(payload, scope)
    except ValueError as exc:
        raise HTTPException(409, {"message": str(exc), "code": "tracker_session_ended"}) from exc
    return {"data": await persist_tracker_result(rt, result)}


@app.post("/api/v1/dev/position")
async def dev_position(payload: DevPositionRequest, rt: Runtime = Depends(runtime)):
    if not rt.settings.dev_mode:
        raise HTTPException(404, {"message": "development position injection is disabled"})
    scope = tracker_scope(rt, payload)
    try:
        result = rt.tracking.ingest_dev_position(payload, scope)
    except ValueError as exc:
        raise HTTPException(409, {"message": str(exc), "code": "tracker_session_ended"}) from exc
    return {"data": await persist_tracker_result(rt, result)}


@app.get("/api/v1/state")
async def get_state(run_id: str = Query(...), deployment_id: str = Query(...), building_id: str = Query(...),
    floor_id: str = Query(...), mode: str = Query("real"),
                    since_revision: int | None = Query(None, ge=0), rt: Runtime = Depends(runtime)):
    try:
        state = rt.scope(run_id, deployment_id, building_id, floor_id, parse_mode(mode))
    except ValueError as exc:
        raise HTTPException(422, {"message": "invalid mode"}) from exc
    data = state.model_dump(mode="json")
    if since_revision is not None and since_revision >= state.state_revision:
        data.update({
            "positions": [],
            "nodes": [],
            "recent_events": [],
            "zone_metrics": [],
            "zones": [],
            "is_partial": True,
        })
    return {"data": data, "since_revision": since_revision}


@app.get("/api/v1/zones")
async def get_zones(run_id: str = Query(...), deployment_id: str = Query(...), building_id: str = Query(...),
                    floor_id: str = Query(...), mode: str = Query("real"), rt: Runtime = Depends(runtime)):
    try:
        state = rt.scope(run_id, deployment_id, building_id, floor_id, parse_mode(mode))
    except ValueError as exc:
        raise HTTPException(422, {"message": "invalid mode"}) from exc
    return {"data": state.zone_metrics}


async def analytics_endpoint(params: dict[str, Any], rt: Runtime) -> dict[str, Any]:
    return {"data": rt.store.analytics(params["run_id"], params["deployment_id"], params["building_id"], params["floor_id"])}


@app.get("/api/v1/analytics/occupancy")
async def occupancy(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    result = await analytics_endpoint(params, rt)
    return {"data": result["data"]["occupancy"]}


@app.get("/api/v1/analytics/transitions")
async def transitions(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    result = await analytics_endpoint(params, rt)
    return {"data": result["data"]["transitions"]}


@app.get("/api/v1/analytics/dwell")
async def dwell(params: dict[str, Any] = Depends(list_params), rt: Runtime = Depends(runtime)):
    result = await analytics_endpoint(params, rt)
    return {"data": result["data"]["dwell"]}


@app.post("/api/v1/intelligence/query")
async def intelligence(query: QueryRequest, rt: Runtime = Depends(runtime)):
    return {"data": answer_query(rt.store, query).model_dump(mode="json")}


@app.get("/api/v1/health")
async def health(rt: Runtime = Depends(runtime)):
    databricks = rt.databricks.status
    return {"status": "ok", "local": {"status": "ok", "database": "sqlite", "wal": True},
            "positioning": {"status": "configured" if rt.forwarder.enabled else "disabled", "queue_depth": rt.forwarder.queue.qsize(),
                            "forwarded": rt.forwarder.forwarded, "failed": rt.forwarder.failed},
            "databricks": {"status": "configured" if databricks.enabled else "disabled",
                            "enabled": databricks.enabled, "available": databricks.available,
                            "reason": databricks.reason, "catalog": rt.settings.databricks_catalog,
                            "schema": rt.settings.databricks_schema}}


@app.websocket("/api/v1/live")
async def live(websocket: WebSocket, run_id: str | None = None, deployment_id: str | None = None,
               building_id: str | None = None, floor_id: str | None = None, mode: str = "real"):
    rt: Runtime = websocket.app.state.runtime
    assert rt.live is not None
    connection = await rt.live.connect(websocket)

    async def send_snapshot(since_revision: int | None) -> None:
        if all(value is not None for value in (run_id, deployment_id, building_id, floor_id)):
            try:
                data = rt.scope(run_id, deployment_id, building_id, floor_id, parse_mode(mode)).model_dump(mode="json")
            except ValueError:
                data = {"state_revision": rt.state_revision, "is_partial": True, "reason": "invalid_mode"}
        else:
            data = await rt.snapshot()
        await websocket.send_json({"type": "snapshot", "state_revision": data.get("state_revision", rt.state_revision),
                                   "data": data, "since_revision": since_revision})

    try:
        since = websocket.query_params.get("since_revision")
        await send_snapshot(int(since) if since and since.isdigit() else None)
        while True:
            try:
                message = await asyncio.wait_for(connection.queue.get(), timeout=15)
                if message.get("type") == "snapshot_required":
                    await send_snapshot(None)
                else:
                    await websocket.send_json(message)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "state_revision": rt.state_revision})
    except WebSocketDisconnect:
        pass
    finally:
        await rt.live.disconnect(connection)


@app.websocket("/api/v1/tracker")
async def tracker(websocket: WebSocket):
    """Preferred live telemetry transport for the consenting phone page."""

    rt: Runtime = websocket.app.state.runtime
    await websocket.accept()
    connected_session: str | None = None
    connected_scope: TrackingScope | None = None

    async def error(code: str, message: str) -> None:
        await websocket.send_json({"type": "error", "code": code, "message": message})

    async def resolve_ws_scope(payload: Any) -> TrackingScope | None:
        try:
            return rt.tracking.resolve_scope(
                getattr(payload, "run_id", None),
                getattr(payload, "deployment_id", None),
                getattr(payload, "building_id", None),
                getattr(payload, "floor_id", None),
            )
        except ValueError as exc:
            await error("scope_mismatch", str(exc))
            return None

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                await error("malformed_packet", "Message must be valid JSON.")
                continue
            if not isinstance(raw, dict):
                await error("malformed_packet", "Message must be a JSON object.")
                continue

            message_type = raw.get("type")
            try:
                if message_type == "hello":
                    hello = TrackerHello.model_validate(raw)
                    scope = await resolve_ws_scope(hello)
                    if scope is None:
                        continue
                    session, created = rt.tracking.register(hello.session_id, scope)
                    connected_session = session.session_id
                    connected_scope = scope
                    if created:
                        rt.store.add_session(rt.tracking.session_create(session))
                        session_view = next(
                            (item for item in rt.tracking.sessions_for(scope) if item["session_id"] == session.session_id),
                            None,
                        )
                        if session_view is not None:
                            await rt.publish("session", session_view)
                    logger.info("tracker connected %s", session.session_id)
                    await websocket.send_json({
                        "type": "connected",
                        "status": "connected",
                        "session_id": session.session_id,
                        "calibration": rt.tracking.config_payload()["calibration"],
                    })
                    continue

                if message_type == "location":
                    location = TrackerLocation.model_validate(raw)
                    scope = connected_scope or await resolve_ws_scope(location)
                    if scope is None:
                        continue
                    if connected_session and location.session_id.lower() != connected_session:
                        await error("session_mismatch", "This socket is already bound to another anonymous session.")
                        continue
                    result = rt.tracking.ingest_location(location, scope)
                    response = await persist_tracker_result(rt, result)
                    await websocket.send_json({
                        "type": "ack",
                        **response,
                    })
                    connected_session = result.session.session_id
                    connected_scope = scope
                    continue

                if message_type == "calibrate":
                    calibration = TrackerCalibration.model_validate(raw)
                    scope = connected_scope or await resolve_ws_scope(calibration)
                    if scope is None:
                        continue
                    if connected_session and calibration.session_id.lower() != connected_session:
                        await error("session_mismatch", "This socket is already bound to another anonymous session.")
                        continue
                    session = rt.tracking.calibrate(
                        calibration.session_id,
                        scope,
                        calibration.latitude,
                        calibration.longitude,
                        calibration.calibration_id,
                    )
                    _, duplicate = rt.store.add_session(rt.tracking.session_create(session))
                    if not duplicate:
                        session_view = next(
                            (item for item in rt.tracking.sessions_for(scope) if item["session_id"] == session.session_id),
                            None,
                        )
                        if session_view is not None:
                            await rt.publish("session", session_view)
                    position_response = await materialize_calibrated_position(rt, session, scope)
                    connected_session = session.session_id
                    connected_scope = scope
                    logger.info("session calibrated %s", session.session_id)
                    await websocket.send_json({
                        "type": "calibrated",
                        "status": "calibrated",
                        "session_id": session.session_id,
                        "calibration": rt.tracking.config_payload()["calibration"],
                        "position": position_response.get("position") if position_response else None,
                    })
                    continue

                if message_type == "ping":
                    await websocket.send_json({"type": "pong", "state_revision": rt.state_revision})
                    continue

                await error("unknown_message", "Supported messages are hello, location, calibrate, and ping.")
            except ValidationError as exc:
                await error("malformed_packet", "Telemetry packet failed validation.")
                logger.info("malformed tracker packet fields=%s", len(exc.errors()))
            except ValueError as exc:
                code = "tracker_session_ended" if "session has ended" in str(exc).lower() else "tracker_error"
                await error(code, str(exc))
    except WebSocketDisconnect:
        if connected_session:
            logger.info("tracker disconnected %s", connected_session)
