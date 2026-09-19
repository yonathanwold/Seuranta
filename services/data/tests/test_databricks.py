from services.data.databricks import DatabricksAdapter


def test_databricks_status_requires_all_batch_sink_settings():
    adapter = DatabricksAdapter("https://workspace.example", "token", "main", "seuranta", None)
    assert adapter.status.enabled is False
    assert adapter.status.reason == "credentials_or_warehouse_not_configured"


def test_databricks_identifiers_are_qualified_and_validated():
    adapter = DatabricksAdapter("https://workspace.example", "token", "main", "seuranta", "warehouse")
    assert adapter.status.enabled is True
    assert adapter.table_name("zone_occupancy") == "main.seuranta.zone_occupancy"

    try:
        adapter.table_name("zone;drop")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe table identifier was accepted")
