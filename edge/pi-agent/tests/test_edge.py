from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from seuranta_edge.agent import BatchAccumulator, EdgeAgent
from seuranta_edge.buffer import FlushResult, SQLiteBuffer
from seuranta_edge.collectors import (
    APStationCollector,
    BLEAdvertisementCollector,
    CommandAdapter,
    MockCollector,
    MonitorModeCollector,
    RawObservation,
    CollectorError,
    parse_station_dump,
    parse_bluetooth_scan,
)
from seuranta_edge.config import EdgeConfig, config_from_defaults, load_config
from seuranta_edge.contracts import NodeHeartbeat, ObservationBatch, Session, SignalObservation, utc_now
from seuranta_edge.pseudonym import RunPseudonymizer, SessionRegistry
from seuranta_edge.transport import HttpTransport, RecordingTransport, TransportError


class FakeAdapter(CommandAdapter):
    def __init__(self, output: str):
        self.output = output

    def run(self, args, timeout_s=5.0):
        return self.output


class CapturingHttpTransport(HttpTransport):
    def __init__(self):
        super().__init__("http://api.invalid", building_id="building-1", floor_id="1",
                         run_id="run-1", deployment_id="dep-1")
        self.calls = []
        self.response = {}

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return self.response


def observation(sequence=0, *, rssi=-50, channel=6):
    return SignalObservation(
        observation_id="00000000-0000-4000-8000-000000000001", observed_at=utc_now(),
        timestamp_ms=1, run_id="run-1", deployment_id="dep-1", building_id="bld-1",
        floor_id="1", anchor_id="anchor-1", session_id="ABCDEF", rssi_dbm=rssi,
        channel=channel, source="MOCK_RSSI", mode="SIMULATION", sequence_number=sequence,
    )


class EdgeTests(unittest.TestCase):
    def test_config_validation_and_redaction(self):
        config = config_from_defaults(secret="0123456789abcdef")
        diagnostics = config.redacted_diagnostics()
        self.assertEqual(diagnostics["demo_run_secret"], "<redacted>")
        with self.assertRaises(ValueError):
            EdgeConfig(**{**config.__dict__, "wifi_channel": 0})
        with self.assertRaises(ValueError):
            EdgeConfig(**{**config.__dict__, "demo_run_secret": "short"})
        with self.assertRaises(ValueError):
            EdgeConfig(**{**config.__dict__, "capture_strategy": "BLE"})
        ble = EdgeConfig(**{**config.__dict__, "capture_strategy": "BLE", "ble_target_name": "Seuranta-iPhone"})
        self.assertEqual(ble.redacted_diagnostics()["ble_target_name"], "<configured>")

    def test_env_config(self):
        config = load_config({
            "ANCHOR_ID": "anchor-1", "ANCHOR_X": "2", "ANCHOR_Y": "3", "ANCHOR_FLOOR": "2",
            "DEPLOYMENT_ID": "dep", "BUILDING_ID": "building", "SEURANTA_API_URL": "http://localhost:1",
            "SEURANTA_WIFI_SSID": "ssid", "SEURANTA_WIFI_CHANNEL": "6", "WIFI_INTERFACE": "wlan0",
            "CAPTURE_STRATEGY": "mock", "OBSERVATION_INTERVAL_MS": "1000", "HEARTBEAT_INTERVAL_MS": "2000",
            "BATCH_MAX_SIZE": "10", "BUFFER_PATH": "buffer.sqlite3", "DEMO_RUN_SECRET": "0123456789abcdef",
        })
        self.assertEqual(config.capture_strategy, "MOCK")

    def test_mock_is_seeded_and_valid(self):
        first = MockCollector(seed=11).collect()
        second = MockCollector(seed=11).collect()
        self.assertEqual([(x.rssi_dbm, x.channel) for x in first], [(x.rssi_dbm, x.channel) for x in second])
        self.assertTrue(all(-127 <= x.rssi_dbm <= 0 for x in first))

    def test_rssi_and_channel_validation(self):
        with self.assertRaises(ValueError):
            observation(rssi=-128)
        with self.assertRaises(ValueError):
            observation(channel=0)
        with self.assertRaises(CollectorError):
            parse_station_dump("Station aa:bb:cc:dd:ee:ff\n\tsignal: -200 dBm", expected_channel=6)

    def test_hmac_stability_and_rotation(self):
        left = RunPseudonymizer("0123456789abcdef", "run-a").temporary_session_id("raw")
        same = RunPseudonymizer("0123456789abcdef", "run-a").temporary_session_id("raw")
        other = RunPseudonymizer("0123456789abcdef", "run-b").temporary_session_id("raw")
        self.assertEqual(left, same)
        self.assertNotEqual(left, other)
        self.assertTrue(left.isupper())

    def test_registry_drops_inactive_sessions(self):
        registry = SessionRegistry(run_id="run", deployment_id="dep", mode="SIMULATION",
                                   anchor_id="anchor", run_secret="0123456789abcdef")
        session = registry.start("raw-device", now="2026-09-19T00:00:00Z")
        self.assertIsNotNone(registry.session_for_raw("raw-device"))
        registry.mark_silent(session.session_id, now="2026-09-19T00:00:01Z")
        self.assertIsNone(registry.session_for_raw("raw-device"))
        registry.end(session.session_id, now="2026-09-19T00:00:02Z")
        self.assertIsNone(registry.session_for_raw("raw-device"))

    def test_wireless_malformed_output_and_metadata_only(self):
        output = "Station aa:bb:cc:dd:ee:ff (on wlan0)\n\tsignal: -55 dBm\n"
        self.assertEqual(parse_station_dump(output, expected_channel=6)[0][1:], (-55, 6))
        collector = APStationCollector("wlan0", 6, adapter=FakeAdapter(output))
        result = collector.collect()
        self.assertEqual(result[0].rssi_dbm, -55)
        monitor = MonitorModeCollector("mon0", 6, line_source=lambda: ["aa:bb:cc:dd:ee:ff signal -60 dBm channel 6"])
        self.assertEqual(monitor.collect()[0].rssi_dbm, -60)

    def test_bluetooth_collector_uses_only_target_rssi_metadata(self):
        scan = "\n".join((
            "[NEW] Device aa:bb:cc:dd:ee:ff Seuranta-iPhone",
            "[CHG] Device aa:bb:cc:dd:ee:ff RSSI: -58",
            "[NEW] Device 11:22:33:44:55:66 Someone-Else",
            "[CHG] Device 11:22:33:44:55:66 RSSI: -41",
        ))
        rows = parse_bluetooth_scan(scan, target_name="Seuranta-iPhone", device_token="Seuranta-iPhone")
        self.assertEqual(rows, [("Seuranta-iPhone", -58, 37)])
        collector = BLEAdvertisementCollector("Seuranta-iPhone", adapter=FakeAdapter(scan))
        readings = collector.collect()
        self.assertEqual([(item.device_token, item.rssi_dbm, item.channel) for item in readings],
                         [("Seuranta-iPhone", -58, 37)])

    def test_http_transport_normalizes_edge_values_for_the_api(self):
        transport = CapturingHttpTransport()
        session = Session("ABCDEF", "run-1", "dep-1", "LIVE", "ACTIVE", "DEMO_NETWORK",
                          "2026-09-19T00:00:00Z", "2026-09-19T00:00:00Z", "anchor-1")
        transport.start_session(session)
        self.assertEqual(transport.calls[-1], ("POST", "/api/v1/sessions", {
            "session_id": "ABCDEF", "run_id": "run-1", "deployment_id": "dep-1",
            "building_id": "building-1", "floor_id": "1", "mode": "real",
            "started_at": "2026-09-19T00:00:00Z",
        }))
        batch = ObservationBatch.from_observations("anchor-1", 0, "run-1", "dep-1", "SIMULATION", [observation()])
        transport.send_batch(batch.to_dict())
        self.assertEqual(transport.calls[-1][2]["mode"], "simulated")
        self.assertEqual(transport.calls[-1][2]["observations"][0]["mode"], "simulated")
        heartbeat = NodeHeartbeat("00000000-0000-4000-8000-000000000002", utc_now(), "run-1", "dep-1", "building-1",
                                  "1", "anchor-1", "REAL", "LIVE", "ONLINE", "0.1", 1, 0, 0, None, True, ())
        transport.heartbeat(heartbeat)
        self.assertEqual(transport.calls[-1][2]["status"], "online")
        self.assertEqual(transport.calls[-1][2]["mode"], "real")

        transport.response = {"data": [{"session_id": "ABCDEF", "run_id": "run-1", "deployment_id": "dep-1",
                                         "mode": "real", "started_at": "2026-09-19T00:00:00+00:00", "ended_at": None}]}
        sessions = transport.list_sessions()
        self.assertEqual(sessions[0]["mode"], "LIVE")
        self.assertEqual(sessions[0]["status"], "ACTIVE")

    def test_batch_count_and_age(self):
        current = [0.0]
        accumulator = BatchAccumulator(max_size=2, max_age_ms=1000, clock=lambda: current[0])
        self.assertIsNone(accumulator.add(observation(0)))
        self.assertEqual(len(accumulator.add(observation(1))), 2)
        accumulator.add(observation(2))
        current[0] = 2.0
        self.assertEqual(len(accumulator.flush_due()), 1)

    def test_sqlite_dedupe_retry_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "buffer.sqlite3"
            clock = [0.0]
            batch = ObservationBatch.from_observations("anchor", 0, "run-1", "dep-1", "SIMULATION", [observation()])
            with SQLiteBuffer(path, clock=lambda: clock[0], base_backoff_s=2) as buffer:
                self.assertTrue(buffer.enqueue(batch))
                self.assertFalse(buffer.enqueue(batch))
                self.assertEqual(buffer.depth(), 1)
                self.assertEqual(buffer.flush(lambda _: (_ for _ in ()).throw(TransportError("down"))).failed, 1)
                self.assertEqual(buffer.depth(), 1)
            with SQLiteBuffer(path, clock=lambda: clock[0]) as restarted:
                self.assertEqual(restarted.depth(), 1)
                clock[0] = 3.0
                sent = []
                result = restarted.flush(sent.append)
                self.assertEqual(result.sent, 1)
                self.assertEqual(sent[0]["batch_id"], batch.batch_id)

    def test_fifo_stops_after_oldest_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "buffer.sqlite3"
            first = ObservationBatch.from_observations("anchor", 0, "run-1", "dep-1", "SIMULATION", [observation(0)])
            second = ObservationBatch.from_observations("anchor", 1, "run-1", "dep-1", "SIMULATION", [observation(1)])
            with SQLiteBuffer(path) as buffer:
                buffer.enqueue(first)
                buffer.enqueue(second)
                seen = []

                def fail_first(payload):
                    seen.append(payload["batch_id"])
                    raise TransportError("down")

                result = buffer.flush(fail_first)
                self.assertEqual(result.failed, 1)
                self.assertEqual(seen, [first.batch_id])

    def test_fifo_head_backoff_blocks_newer_ready_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "buffer.sqlite3"
            clock = [0.0]
            first = ObservationBatch.from_observations("anchor", 0, "run-1", "dep-1", "SIMULATION", [observation(0)])
            second = ObservationBatch.from_observations("anchor", 1, "run-1", "dep-1", "SIMULATION", [observation(1)])
            with SQLiteBuffer(path, clock=lambda: clock[0], base_backoff_s=2) as buffer:
                buffer.enqueue(first)
                buffer.enqueue(second)
                successful = []
                failed_once = [False]

                def fail_first_once(payload):
                    if payload["batch_id"] == first.batch_id and not failed_once[0]:
                        failed_once[0] = True
                        raise TransportError("down")
                    successful.append(payload["batch_id"])

                self.assertEqual(buffer.flush(fail_first_once).failed, 1)
                clock[0] = 1.0
                self.assertEqual(buffer.flush(fail_first_once), FlushResult())
                self.assertEqual(successful, [])
                clock[0] = 2.0
                result = buffer.flush(fail_first_once)
                self.assertEqual(result.sent, 2)
                self.assertEqual(successful, [first.batch_id, second.batch_id])

    def test_backend_synced_active_session_matches_without_raw_token(self):
        with tempfile.TemporaryDirectory() as directory:
            config = EdgeConfig(**{**config_from_defaults(secret="0123456789abcdef").__dict__,
                                   "buffer_path": str(Path(directory) / "queue.sqlite3")})
            token = "backend-device"
            seed_registry = SessionRegistry(run_id="run-1", deployment_id=config.deployment_id, mode="SIMULATION",
                                            anchor_id="anchor", run_secret=config.demo_run_secret)
            session = seed_registry.start(token, now="2026-09-19T00:00:00Z")
            transport = RecordingTransport()
            transport.list_sessions = lambda: [session.to_dict()]
            collector = MockCollector(sessions=[token], seed=3)
            with SQLiteBuffer(config.buffer_path) as buffer:
                agent = EdgeAgent(config, run_id="run-1", collector=collector, buffer=buffer, transport=transport)
                self.assertEqual(agent.sync_sessions(), 1)
                observations = agent.collect_once()
                self.assertEqual(len(observations), 1)
                self.assertNotIn(token, json.dumps(observations[0].to_dict()))

    def test_agent_persists_before_delivery_and_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            config = EdgeConfig(**{**config_from_defaults(secret="0123456789abcdef").__dict__,
                                   "buffer_path": str(Path(directory) / "queue.sqlite3"), "batch_max_size": 2})
            collector = MockCollector(sessions=["device-a", "device-b"], seed=2)
            transport = RecordingTransport()
            with SQLiteBuffer(config.buffer_path) as buffer:
                agent = EdgeAgent(config, run_id="run-1", collector=collector, buffer=buffer, transport=transport)
                agent.start_session("device-a")
                agent.start_session("device-b")
                result = agent.collect_once()
                self.assertEqual(len(result), 2)
                self.assertEqual(buffer.depth(), 1)
                self.assertTrue(agent.build_heartbeat().capture_ok)
                flush = agent.flush_buffer()
                self.assertEqual(flush.sent, 1)
                self.assertEqual(agent.build_heartbeat().observations_sent_total, 2)
                payload_text = json.dumps(transport.requests)
                self.assertNotIn("device-a", payload_text)
                self.assertNotIn("device-b", payload_text)

    def test_heartbeat_shape_and_sequence(self):
        heartbeat = NodeHeartbeat(
            heartbeat_id="00000000-0000-4000-8000-000000000002", emitted_at=utc_now(), run_id="run",
            deployment_id="dep", building_id="b", floor_id="1", anchor_id="a", node_kind="SIMULATED",
            mode="SIMULATION", status="ONLINE", agent_version="0.1.0", uptime_s=1, buffer_depth=0,
            observations_sent_total=0, last_observation_at=None, capture_ok=True, error_codes=[],
        )
        self.assertEqual(heartbeat.to_dict()["schema_version"], "1.0")
        self.assertEqual(observation(4).sequence_number, 4)


if __name__ == "__main__":
    unittest.main()
