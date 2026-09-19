from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from services.data.models import (
    Anomaly,
    BuildingState,
    NodeHeartbeat,
    ObservationBatch,
    PositionEstimate,
    QueryRequest,
    RssiPositionRequest,
    SessionCreate,
    SessionEnd,
    SignalObservation,
    SpatialEvent,
)
from services.data.anomalies import detect_anomalies
from services.data.store import LocalStore
from services.positioning.engine import PositioningError, RangeMeasurement, estimate_rssi_position
from services.positioning.runtime import InternalPositioner

from .forwarder import PositioningForwarder
from .intelligence import answer_query
from .settings import Settings
from .ws import LiveManager


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seuranta.api")


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = LocalStore(settings.database_path, settings.retention_days)
        self.forwarder = PositioningForwarder(settings.positioning_url, settings.positioning_queue_size)
        self.positioner: InternalPositioner | None = None
        if settings.internal_positioning_enabled:
            if not settings.positioning_anchors_json:
                raise ValueError("SEURANTA_INTERNAL_POSITIONING requires SEURANTA_POSITIONING_ANCHORS_JSON")
            self.positioner = InternalPositioner.from_json(settings.positioning_anchors_json,
                                                            settings.positioning_window_seconds,
                                                            settings.positioning_min_anchors)
        self.state_revision = 0
        self.started_at = time.monotonic()
        self.live: LiveManager | None = None

    async def snapshot(self, request: Request | None = None) -> dict[str, Any]:
        # A reconnect without scope gets a deliberately explicit partial snapshot.
        return {"state_revision": self.state_revision, "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_partial": True, "reason": "scope_required"}

    def scope(self, run_id: str, deployment_id: str, building_id: str, floor_id: str, mode: Any) -> BuildingState:
        return self.store.reconstruct_state(run_id, deployment_id, building_id, floor_id, mode, self.state_revision)

    async def publish(self, event_type: str, data: Any) -> None:
        self.state_revision += 1
        if self.live:
            await self.live.publish({"type": event_type, "state_revision": self.state_revision,
                                     "data": data.model_dump(mode="json") if hasattr(data, "model_dump") else data})

    async def process_positions(self, observations: list[SignalObservation]) -> list[PositionEstimate]:
        if not self.positioner:
            return []
        positions = self.positioner.ingest(observations)
        for position in positions:
            if self.store.add_position(position):
                await self.publish("position", position)
        return positions


def runtime(request: Request) -> Runtime:
    return request.app.state.runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    rt = Runtime(settings)
    app.state.runtime = rt
    rt.live = LiveManager(rt.snapshot)
    await rt.forwarder.start()
    try:
        yield
    finally:
        await rt.forwarder.stop()
        rt.store.close()


app = FastAPI(title="Seuranta Atlas API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(Settings.from_env().allowed_origins), allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)


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
        await rt.process_positions([observation])
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
        await rt.process_positions(observations)
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


@app.post("/api/v1/positioning/estimate")
async def estimate_position(payload: RssiPositionRequest, rt: Runtime = Depends(runtime)):
    """Estimate a calibration/test position from a simultaneous RSSI snapshot."""
    readings = [
        RangeMeasurement(anchor_id=anchor.anchor_id, x_m=anchor.x_m, y_m=anchor.y_m,
                         rssi_dbm=payload.rssi_by_anchor[anchor.anchor_id],
                         tx_power_dbm_at_1m=anchor.tx_power_dbm_at_1m,
                         path_loss_exponent=anchor.path_loss_exponent)
        for anchor in payload.anchors if anchor.anchor_id in payload.rssi_by_anchor
    ]
    try:
        result = estimate_rssi_position(readings)
    except PositioningError as exc:
        raise HTTPException(422, {"message": str(exc)}) from exc
    position = PositionEstimate(
        window_start=payload.window_start,
        window_end=payload.window_end,
        run_id=payload.run_id,
        deployment_id=payload.deployment_id,
        building_id=payload.building_id,
        floor_id=payload.floor_id,
        session_id=payload.session_id,
        raw_x_m=result.x_m,
        raw_y_m=result.y_m,
        x_m=result.x_m,
        y_m=result.y_m,
        confidence=result.confidence,
        accuracy_radius_m=result.accuracy_radius_m,
        position_method=f"rssi_log_distance_multilateration/{payload.source}",
        smoothing_method="none",
        anchors_used=list(result.anchors_used),
        observation_count=len(readings),
        mode=payload.mode,
        sequence_number=payload.sequence_number,
    )
    inserted = rt.store.add_position(position)
    if inserted:
        await rt.publish("position", position)
    return {"data": position.model_dump(mode="json"), "duplicate": not inserted}


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


@app.get("/api/v1/state")
async def get_state(run_id: str = Query(...), deployment_id: str = Query(...), building_id: str = Query(...),
                    floor_id: str = Query(...), mode: str = Query("real"), rt: Runtime = Depends(runtime)):
    from services.data.models import Mode
    try:
        state = rt.scope(run_id, deployment_id, building_id, floor_id, Mode(mode))
    except ValueError as exc:
        raise HTTPException(422, {"message": "invalid mode"}) from exc
    return {"data": state.model_dump(mode="json")}


@app.get("/api/v1/zones")
async def get_zones(run_id: str = Query(...), deployment_id: str = Query(...), building_id: str = Query(...),
                    floor_id: str = Query(...), mode: str = Query("real"), rt: Runtime = Depends(runtime)):
    from services.data.models import Mode
    state = rt.scope(run_id, deployment_id, building_id, floor_id, Mode(mode))
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
    internal = rt.positioner.status if rt.positioner else None
    return {"status": "ok", "local": {"status": "ok", "database": "sqlite", "wal": True},
            "positioning": {"status": "configured" if rt.forwarder.enabled else "disabled", "queue_depth": rt.forwarder.queue.qsize(),
                            "forwarded": rt.forwarder.forwarded, "failed": rt.forwarder.failed,
                            "internal": {"status": "enabled" if internal else "disabled",
                                         "configured_anchors": internal.configured_anchors if internal else 0,
                                         "emitted": internal.emitted if internal else 0,
                                         "skipped": internal.skipped if internal else 0,
                                         "last_error": internal.last_error if internal else None}},
            "databricks": {"status": "configured" if rt.settings.databricks_host and rt.settings.databricks_token else "disabled"}}


@app.websocket("/api/v1/live")
async def live(websocket: WebSocket, run_id: str | None = None, deployment_id: str | None = None,
               building_id: str | None = None, floor_id: str | None = None, mode: str = "real"):
    rt: Runtime = websocket.app.state.runtime
    assert rt.live is not None
    connection = await rt.live.connect(websocket)

    async def send_snapshot(since_revision: int | None) -> None:
        if all(value is not None for value in (run_id, deployment_id, building_id, floor_id)):
            from services.data.models import Mode
            try:
                data = rt.scope(run_id, deployment_id, building_id, floor_id, Mode(mode)).model_dump(mode="json")
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
