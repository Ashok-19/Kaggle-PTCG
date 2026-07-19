from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException

from ptcg_rl.dashboard.app import create_app


def write_record(repo: Path, directory: str, name: str, value: dict[str, object]) -> None:
    path = repo / "reports" / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def gate(gate_id: str, status: str, decision: str, created: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "record_id": f"gate-{gate_id.lower()}",
        "created_at_utc": created,
        "source_path": f"reports/gates/{gate_id.lower()}.json",
        "producer": "test",
        "gate_id": gate_id,
        "title": gate_id,
        "status": status,
        "decision": decision,
        "blockers": [],
        "warnings": [],
    }


def endpoint(app: Any, path: str) -> Callable[..., Any]:
    return next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)


def test_state_reports_parallel_active_gates_and_auto_refresh(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "official.json").write_text(
        json.dumps({"close_instant_utc": "2026-08-16T23:59:00Z", "runtime": {}}),
        encoding="utf-8",
    )
    write_record(
        tmp_path,
        "gates",
        "g1r.json",
        gate("G1R", "SUCCEEDED", "PASS", "2026-07-18T00:00:00Z"),
    )
    write_record(
        tmp_path,
        "gates",
        "r1.json",
        gate("R1", "QUEUED", "NOT_REVIEWED", "2026-07-19T00:00:00Z"),
    )
    write_record(
        tmp_path,
        "gates",
        "g2.json",
        gate("G2", "QUEUED", "NOT_REVIEWED", "2026-07-19T00:00:01Z"),
    )

    app = create_app(tmp_path, refresh_interval_seconds=0)
    state_endpoint = endpoint(app, "/api/v1/state")
    state = state_endpoint()
    assert [item["gate_id"] for item in state["overview"]["active_gates"]] == ["R1", "G2"]
    assert state["overview"]["latest_completed_gate"]["gate_id"] == "G1R"
    assert len(state["review"]) == 2

    g2_path = tmp_path / "reports" / "gates" / "g2.json"
    value = gate("G2", "RUNNING", "NOT_REVIEWED", "2026-07-19T00:00:01Z")
    g2_path.write_text(json.dumps(value), encoding="utf-8")
    refreshed = state_endpoint()
    assert next(item for item in refreshed["gates"] if item["gate_id"] == "G2")["status"] == "RUNNING"


def test_evidence_endpoint_serves_only_allowlisted_sources(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "official.json").write_text(json.dumps({"runtime": {}}), encoding="utf-8")
    write_record(
        tmp_path,
        "gates",
        "g0.json",
        gate("G0", "SUCCEEDED", "PASS", "2026-07-17T00:00:00Z"),
    )
    private = tmp_path / "private" / "secret.md"
    private.parent.mkdir()
    private.write_text("not dashboard evidence", encoding="utf-8")

    app = create_app(tmp_path, refresh_interval_seconds=0)
    evidence_endpoint = endpoint(app, "/api/v1/evidence")
    allowed = evidence_endpoint(path="reports/gates/g0.json")
    assert allowed["source_path"] == "reports/gates/g0.json"
    with pytest.raises(HTTPException) as error:
        evidence_endpoint(path="private/secret.md")
    assert error.value.status_code == 404
