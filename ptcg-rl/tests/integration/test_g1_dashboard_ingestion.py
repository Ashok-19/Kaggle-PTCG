from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_dashboard_ingests_g1_manifest_without_api_call(tmp_path: Path) -> None:
    pytest.importorskip("pydantic")
    from ptcg_rl.dashboard.store import DashboardStore

    report = tmp_path / "reports" / "runs" / "g1.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_id": "g1-test-run",
                "created_at_utc": "2026-07-18T00:00:00+00:00",
                "source_path": "reports/runs/g1.json",
                "producer": "test",
                "run_id": "g1-test",
                "gate_id": "G1",
                "kind": "run",
                "status": "PASS",
            }
        ),
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path)
    result = store.ingest(rebuild=True)
    assert result["ingested"] == 1
    assert store.list("run", 10, 0)["items"][0]["gate_id"] == "G1"
