from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = "./seuranta.db"
    retention_days: int = 30
    max_batch_size: int = 500
    positioning_url: str | None = None
    positioning_queue_size: int = 100
    allowed_origins: tuple[str, ...] = (
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    run_id: str = "vt-acb-floor1"
    deployment_id: str = "vt-acb-pilot"
    building_id: str = "vt-academic-classroom-building"
    floor_id: str = "floor-1"
    dev_mode: bool = False
    floor_width_m: float = 76.9195
    floor_depth_m: float = 44.6473
    floor_origin_x_m: float = 0.0
    floor_origin_y_m: float = 0.0
    calibration_latitude: float | None = None
    calibration_longitude: float | None = None
    calibration_x_m: float = 0.0
    calibration_y_m: float = 0.0
    building_yaw_deg: float = 0.0
    calibration_id: str = "demo-origin"
    calibration_label: str = "Demo Start"
    public_tracker_url: str | None = None
    tracker_stale_after_seconds: float = 10.0
    tracker_expire_after_seconds: float = 30.0
    host: str = "0.0.0.0"
    port: int = 8000
    databricks_host: str | None = None
    databricks_token: str | None = None
    databricks_catalog: str = "main"
    databricks_schema: str = "seuranta"
    databricks_warehouse_id: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(x.strip() for x in os.getenv(
            "SEURANTA_ALLOWED_ORIGINS",
            "http://localhost:4173,http://127.0.0.1:4173,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",") if x.strip())

        def as_bool(name: str, default: bool = False) -> bool:
            return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

        def as_float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        def optional_float(name: str) -> float | None:
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        return cls(
            database_path=os.getenv("SEURANTA_DATABASE_PATH", "./seuranta.db"),
            retention_days=max(1, int(os.getenv("SEURANTA_RETENTION_DAYS", "30"))),
            max_batch_size=max(1, int(os.getenv("SEURANTA_MAX_BATCH_SIZE", "500"))),
            positioning_url=os.getenv("POSITIONING_URL") or None,
            positioning_queue_size=max(1, int(os.getenv("POSITIONING_QUEUE_SIZE", "100"))),
            allowed_origins=origins or cls.allowed_origins,
            run_id=os.getenv("SEURANTA_RUN_ID", "vt-acb-floor1"),
            deployment_id=os.getenv("SEURANTA_DEPLOYMENT_ID", "vt-acb-pilot"),
            building_id=os.getenv("SEURANTA_BUILDING_ID", "vt-academic-classroom-building"),
            floor_id=os.getenv("SEURANTA_FLOOR_ID", "floor-1"),
            dev_mode=as_bool("SEURANTA_DEV_MODE"),
            floor_width_m=as_float("SEURANTA_FLOOR_WIDTH_M", 76.9195),
            floor_depth_m=as_float("SEURANTA_FLOOR_DEPTH_M", 44.6473),
            floor_origin_x_m=as_float("SEURANTA_FLOOR_ORIGIN_X_M", 0.0),
            floor_origin_y_m=as_float("SEURANTA_FLOOR_ORIGIN_Y_M", 0.0),
            calibration_latitude=optional_float("SEURANTA_CALIBRATION_LAT"),
            calibration_longitude=optional_float("SEURANTA_CALIBRATION_LON"),
            calibration_x_m=as_float("SEURANTA_CALIBRATION_X_M", 0.0),
            calibration_y_m=as_float("SEURANTA_CALIBRATION_Y_M", 0.0),
            building_yaw_deg=as_float("SEURANTA_BUILDING_YAW_DEG", 0.0),
            calibration_id=os.getenv("SEURANTA_CALIBRATION_ID", "demo-origin"),
            calibration_label=os.getenv("SEURANTA_CALIBRATION_LABEL", "Demo Start"),
            public_tracker_url=os.getenv("SEURANTA_PUBLIC_TRACKER_URL") or None,
            tracker_stale_after_seconds=max(1.0, as_float("SEURANTA_TRACKER_STALE_SECONDS", 10.0)),
            tracker_expire_after_seconds=max(2.0, as_float("SEURANTA_TRACKER_EXPIRE_SECONDS", 30.0)),
            host=os.getenv("SEURANTA_HOST", "0.0.0.0"),
            port=max(1, int(os.getenv("SEURANTA_PORT", "8000"))),
            databricks_host=os.getenv("DATABRICKS_HOST") or None,
            databricks_token=os.getenv("DATABRICKS_TOKEN") or None,
            databricks_catalog=os.getenv("DATABRICKS_CATALOG", "main"),
            databricks_schema=os.getenv("DATABRICKS_SCHEMA", "seuranta"),
            databricks_warehouse_id=os.getenv("DATABRICKS_WAREHOUSE_ID") or None,
        )
