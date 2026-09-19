"""Operator diagnostics CLI (all commands are safe to run without hardware)."""

from __future__ import annotations

import argparse
import json
import sys

from .agent import EdgeAgent, create_collector
from .buffer import SQLiteBuffer
from .collectors import inspect_interface, validate_channel
from .config import config_from_defaults, load_config
from .transport import HttpTransport, RecordingTransport


def _config(args: argparse.Namespace):
    if args.defaults:
        return config_from_defaults()
    return load_config(config_file=args.config_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seuranta-edge")
    parser.add_argument("--config-file", help="JSON config path; environment values override it")
    parser.add_argument("--defaults", action="store_true", help="safe local mock config")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config")
    sub.add_parser("inspect-interface")
    sub.add_parser("validate-channel")
    sub.add_parser("connectivity")
    sub.add_parser("time-sync")
    sub.add_parser("sample")
    mock = sub.add_parser("mock-stream")
    mock.add_argument("--count", type=int, default=3)
    run = sub.add_parser("run")
    run.add_argument("--cycles", type=int, default=None, help="bounded cycles for validation; omit for service mode")
    sub.add_parser("buffer-status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = _config(args)
        if args.command == "validate-config":
            print(json.dumps(config.redacted_diagnostics(), indent=2, sort_keys=True))
            return 0
        if args.command == "buffer-status":
            with SQLiteBuffer(config.buffer_path) as buffer:
                print(json.dumps({"path": config.buffer_path, "depth": buffer.depth(),
                                  "bytes_pending": buffer.bytes_pending()}, sort_keys=True))
            return 0
        if args.command == "inspect-interface":
            print(json.dumps(inspect_interface(config.wifi_interface), sort_keys=True))
            return 0
        if args.command == "validate-channel":
            validate_channel(config.wifi_interface, config.wifi_channel)
            print(json.dumps({"interface": config.wifi_interface, "channel": config.wifi_channel,
                              "valid": True}, sort_keys=True))
            return 0
        if args.command == "connectivity":
            transport = HttpTransport(config.api_url)
            print(json.dumps({"sessions": transport.list_sessions(), "reachable": True}, sort_keys=True))
            return 0
        if args.command == "time-sync":
            from .agent import clock_offset_s
            offset = clock_offset_s()
            payload = {"offset_s": offset, "synchronized": offset is not None and abs(offset) <= 2.0}
            print(json.dumps(payload, sort_keys=True))
            return 0 if payload["synchronized"] else 2
        collector = create_collector(config)
        transport = RecordingTransport() if config.capture_strategy == "MOCK" else HttpTransport(config.api_url)
        run_id = "demo-run"
        with SQLiteBuffer(config.buffer_path) as buffer:
            agent = EdgeAgent(config, run_id=run_id, collector=collector, buffer=buffer, transport=transport)
            if config.capture_strategy == "MOCK":
                # The mock tokens are documented and exist only in memory.
                agent.start_session("mock-session-a")
                agent.start_session("mock-session-b")
            if args.command == "sample":
                observations = agent.collect_once()
                agent.flush_pending_batch()
                result = {"observation_count": len(observations), "buffer_depth": buffer.depth(),
                          "heartbeat": agent.build_heartbeat().to_dict()}
                print(json.dumps(result, sort_keys=True))
                return 0
            if args.command == "mock-stream":
                if args.count <= 0:
                    raise ValueError("--count must be positive")
                all_observations = []
                for _ in range(args.count):
                    all_observations.extend(agent.collect_once())
                agent.flush_pending_batch()
                print(json.dumps({"observations": len(all_observations), "buffer_depth": buffer.depth(),
                                  "heartbeat": agent.build_heartbeat().to_dict()}, sort_keys=True))
                return 0
            if args.command == "run":
                if args.cycles is not None and args.cycles <= 0:
                    raise ValueError("--cycles must be positive")
                agent.run_forever(max_cycles=args.cycles)
                print(json.dumps({"buffer_depth": buffer.depth(),
                                  "heartbeat": agent.build_heartbeat().to_dict()}, sort_keys=True))
                return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
