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
    internal_positioning_enabled: bool = False
    positioning_window_seconds: float = 3.0
    positioning_min_anchors: int = 3
    positioning_anchors_json: str | None = None
    allowed_origins: tuple[str, ...] = ("*",)
    databricks_host: str | None = None
    databricks_token: str | None = None
    databricks_catalog: str = "main"
    databricks_schema: str = "seuranta"
    databricks_warehouse_id: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        def bool_env(name: str, default: bool = False) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        origins = tuple(x.strip() for x in os.getenv("SEURANTA_ALLOWED_ORIGINS", "*").split(",") if x.strip())
        return cls(
            database_path=os.getenv("SEURANTA_DATABASE_PATH", "./seuranta.db"),
            retention_days=max(1, int(os.getenv("SEURANTA_RETENTION_DAYS", "30"))),
            max_batch_size=max(1, int(os.getenv("SEURANTA_MAX_BATCH_SIZE", "500"))),
            positioning_url=os.getenv("POSITIONING_URL") or None,
            positioning_queue_size=max(1, int(os.getenv("POSITIONING_QUEUE_SIZE", "100"))),
            internal_positioning_enabled=bool_env("SEURANTA_INTERNAL_POSITIONING"),
            positioning_window_seconds=max(0.1, float(os.getenv("SEURANTA_POSITIONING_WINDOW_SECONDS", "3"))),
            positioning_min_anchors=max(3, int(os.getenv("SEURANTA_POSITIONING_MIN_ANCHORS", "3"))),
            positioning_anchors_json=os.getenv("SEURANTA_POSITIONING_ANCHORS_JSON") or None,
            allowed_origins=origins or ("*",),
            databricks_host=os.getenv("DATABRICKS_HOST") or None,
            databricks_token=os.getenv("DATABRICKS_TOKEN") or None,
            databricks_catalog=os.getenv("DATABRICKS_CATALOG", "main"),
            databricks_schema=os.getenv("DATABRICKS_SCHEMA", "seuranta"),
            databricks_warehouse_id=os.getenv("DATABRICKS_WAREHOUSE_ID") or None,
        )
