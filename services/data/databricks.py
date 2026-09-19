"""Optional Databricks SQL adapter.

The API never imports a Databricks SDK at runtime.  This adapter reports the
disabled state honestly and leaves local SQLite as the source for live reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatabricksStatus:
    enabled: bool
    available: bool
    reason: str


class DatabricksAdapter:
    def __init__(self, host: str | None, token: str | None, catalog: str, schema: str, warehouse_id: str | None) -> None:
        self.host = host
        self.token = token
        self.catalog = catalog
        self.schema = schema
        self.warehouse_id = warehouse_id

    @property
    def status(self) -> DatabricksStatus:
        if not self.host or not self.token or not self.warehouse_id:
            return DatabricksStatus(False, False, "credentials_or_warehouse_not_configured")
        return DatabricksStatus(True, False, "connectivity_checked_only_by_batch_worker")

    def parameterized_statement(self, statement: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Return a SQL statement envelope for a batch worker.

        Callers pass values separately rather than interpolating user input.
        The actual submission is intentionally kept out of the live API path.
        """
        return {"statement": statement, "parameters": parameters, "catalog": self.catalog, "schema": self.schema,
                "warehouse_id": self.warehouse_id}
