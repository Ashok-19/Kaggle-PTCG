from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_dashboard_ingests_g1r_manifest_without_api_call(tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    from ptcg_rl.dashboard.store import DashboardStore

    report = tmp_path / "reports" / "runs" / "g1.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_id": "g1r-test-run",
                "created_at_utc": "2026-07-18T00:00:00+00:00",
                "source_path": "reports/runs/g1.json",
                "producer": "test",
                "run_id": "g1r-test",
                "gate_id": "G1R",
                "kind": "run",
                "status": "SUCCEEDED",
                "decision": "NOT_REVIEWED",
            }
        ),
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path)
    result = store.ingest(rebuild=True)
    assert result["ingested"] == 1
    item = store.list("run", 10, 0)["items"][0]
    assert item["gate_id"] == "G1R"
    assert item["decision"] == "NOT_REVIEWED"


def test_dashboard_adapts_legacy_self_verdict_without_promoting_gate(tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    from ptcg_rl.dashboard.store import DashboardStore

    report = tmp_path / "runs" / "legacy-g1" / "run_manifest.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"schema_version": 1, "run_id": "legacy-g1", "status": "PASS"}))
    store = DashboardStore(tmp_path)
    assert store.ingest(rebuild=True)["quarantined"] == 0
    item = store.list("run", 10, 0)["items"][0]
    assert item["status"] == "SUCCEEDED"
    assert item["decision"] == "NOT_REVIEWED"
    assert item["internal_verdict"] == "PASS"
