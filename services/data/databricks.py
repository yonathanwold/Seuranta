"""Optional Databricks SQL adapter.

The API never imports a Databricks SDK at runtime.  This adapter reports the
disabled state honestly and leaves local SQLite as the source for live reads.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
        return DatabricksStatus(True, False, "configured_batch_sink_not_probed")

    @property
    def qualified_schema(self) -> str:
        """Return the configured schema after validating it as an identifier.

        Catalog and schema are deployment configuration, never request data.
        Failing closed here prevents an accidental SQL identifier injection if
        an environment is misconfigured.
        """
        for value, label in ((self.catalog, "catalog"), (self.schema, "schema")):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid Databricks {label} identifier")
        return f"{self.catalog}.{self.schema}"

    def table_name(self, table: str) -> str:
        """Return a fully-qualified table name for a controlled table name."""
        if not _IDENTIFIER.fullmatch(table):
            raise ValueError("invalid Databricks table identifier")
        return f"{self.qualified_schema}.{table}"

    def parameterized_statement(self, statement: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Return a SQL statement envelope for a batch worker.

        Callers pass values separately rather than interpolating user input.
        The actual submission is intentionally kept out of the live API path.
        """
        if not statement.strip():
            raise ValueError("statement must not be empty")
        return {"statement": statement, "parameters": parameters, "catalog": self.catalog, "schema": self.schema,
                "warehouse_id": self.warehouse_id}
