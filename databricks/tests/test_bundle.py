from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "databricks" / "sql"


def test_bundle_contains_ordered_pipeline_and_scope_contract():
    bundle = (ROOT / "databricks" / "resources" / "seuranta_pipeline.yml").read_text()
    config = (ROOT / "databricks" / "databricks.yml").read_text()
    assert 'default: ""' in config
    assert "create_tables" in bundle
    assert "create_silver_tables" in bundle
    assert "gold_metrics" in bundle
    assert "create_silver_tables" in bundle.split("task_key: gold_metrics", 1)[0]

    schema = (SQL / "00_schema.sql").read_text()
    silver = (SQL / "10_silver.sql").read_text()
    gold = (SQL / "30_gold_metrics.sql").read_text()
    for table in ("signal_observations_raw", "position_estimates_raw", "spatial_events_raw", "node_heartbeats_raw", "sessions_raw"):
        assert table in schema
    for table in ("signal_observations_clean", "position_estimates_clean", "spatial_events_clean", "node_heartbeats_clean", "sessions_clean"):
        assert table in silver
    for table in ("current_positions", "zone_occupancy", "anchor_health", "zone_transitions", "dwell_metrics", "anomaly_metrics", "intelligence_facts"):
        assert table in gold
    for scope in ("run_id", "deployment_id", "building_id", "floor_id", "mode"):
        assert scope in gold
