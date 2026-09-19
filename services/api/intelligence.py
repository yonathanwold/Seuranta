from __future__ import annotations

from datetime import timedelta
from typing import Any

from services.data.models import IntelligenceSummary, Mode, QueryRequest, utc_now
from services.data.store import LocalStore


def answer_query(store: LocalStore, request: QueryRequest) -> IntelligenceSummary:
    end = utc_now()
    start = end - timedelta(minutes=request.window_minutes)
    analytics = store.analytics(request.run_id, request.deployment_id, request.building_id, request.floor_id, request.window_minutes)
    occupancy = analytics["occupancy"]
    facts: list[dict[str, Any]] = []
    for metric, value in (("active_sessions", occupancy["active_sessions"]), ("total_positions", occupancy["total_positions"]),
                          ("event_rate_per_second", analytics["event_rate"]), ("observation_count", analytics["observations"])):
        facts.append({"source_ref": "local.sqlite.analytics", "metric": metric, "value": value,
                      "freshness": analytics.get("data_through") or end.isoformat()})
    query = request.query.lower()
    highlights: list[str] = []
    if not analytics["observations"] and not analytics["occupancy"]["active_sessions"]:
        answer = "Insufficient data: no local telemetry is available for the requested scope and window."
    elif any(term in query for term in ("busiest", "busy", "occupancy")):
        by_zone = occupancy["by_zone"]
        if not by_zone:
            answer = "Insufficient data: no zone-tagged positions are available."
        else:
            zone, count = max(by_zone.items(), key=lambda item: item[1])
            highlights.append(f"{zone}: {count} position observations")
            answer = f"The busiest observed zone is {zone} with {count} position observations in the last {request.window_minutes} minutes."
            facts.append({"source_ref": "local.sqlite.positions", "metric": "busiest_zone", "value": zone,
                          "count": count, "freshness": analytics.get("data_through")})
    elif any(term in query for term in ("moving", "transition")):
        count = analytics["transitions"]["count"]
        answer = f"There were {count} recorded movement or boundary events in the last {request.window_minutes} minutes."
        highlights.append(f"{count} transitions/events")
        facts.append({"source_ref": "local.sqlite.events", "metric": "transition_count", "value": count,
                      "freshness": analytics.get("data_through")})
    elif any(term in query for term in ("health", "happen", "happening", "changed", "change")):
        answer = (f"Current local state: {occupancy['active_sessions']} active sessions, "
                  f"{occupancy['total_positions']} position observations, and "
                  f"{analytics['transitions']['count']} movement events in the selected window.")
        highlights.append("Local deterministic analytics used")
    elif "dwell" in query:
        answer = f"Average dwell is {analytics['dwell']['average_ms']:.0f} ms and p95 dwell is {analytics['dwell']['p95_ms']:.0f} ms."
        facts.append({"source_ref": "local.sqlite.events", "metric": "dwell_ms", "average": analytics["dwell"]["average_ms"],
                      "p95": analytics["dwell"]["p95_ms"], "freshness": analytics.get("data_through")})
    else:
        answer = "Insufficient data: this deterministic backend supports occupancy, busiest zone, changes, movement, dwell, and health questions."
    return IntelligenceSummary(window_start=start, window_end=end, data_through=analytics.get("data_through"),
                               run_id=request.run_id, deployment_id=request.deployment_id, building_id=request.building_id,
                               floor_id=request.floor_id, mode=request.mode, query=request.query, answer=answer,
                               facts=facts, highlights=highlights, grounded=True)
