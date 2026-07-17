from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from ptcg_rl.dashboard.store import DashboardStore, SourceError


def write_gate(repo: Path) -> None:
    path = repo / "reports" / "gates" / "g0.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_id": "gate-g0",
                "created_at_utc": "2026-07-17T00:00:00Z",
                "source_path": "PROGRESS_REPORT.md",
                "producer": "test",
                "gate_id": "G0",
                "status": "BLOCKED",
                "decision": "BLOCKED",
                "technical_checks": [{"name": "native", "status": "PASS"}],
            }
        ),
        encoding="utf-8",
    )


def test_rebuild_is_deterministic_and_keeps_gate_decision_separate(tmp_path: Path) -> None:
    (tmp_path / "PROJECT_STATUS.md").write_text("# Project Status\nGate status: blocked\n", encoding="utf-8")
    (tmp_path / "PROGRESS_REPORT.md").write_text(
        "# Progress Report\nMilestone/gate: G0 Repository/environment  \nStatus: BLOCKED\n",
        encoding="utf-8",
    )
    write_gate(tmp_path)
    store = DashboardStore(tmp_path)
    assert store.ingest(rebuild=True)["quarantined"] == 0
    first = store.snapshot()
    store.ingest(rebuild=True)
    assert store.snapshot() == first
    gate = store.list("gate")["items"][0]
    assert gate["decision"] == "BLOCKED"
    assert gate["technical_checks"][0]["status"] == "PASS"


def test_allowlist_rejects_escape_symlink_secret_and_oversized_source(tmp_path: Path) -> None:
    store = DashboardStore(tmp_path)
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(SourceError, match="escapes"):
        store._safe_relative(outside)

    reports = tmp_path / "reports" / "gates"
    reports.mkdir(parents=True)
    link = reports / "link.md"
    link.symlink_to(outside)
    with pytest.raises(SourceError, match="escapes|symlink"):
        store._safe_relative(link)

    secret = reports / "secret.md"
    secret.write_text("# no\n" + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    with pytest.raises(SourceError, match="credential"):
        store._read(secret)

    huge = reports / "huge.md"
    huge.write_bytes(b"x" * 1_048_577)
    with pytest.raises(SourceError, match="1 MiB"):
        store._safe_relative(huge)


def test_malformed_source_is_quarantined_without_hiding_valid_record(tmp_path: Path) -> None:
    write_gate(tmp_path)
    bad = tmp_path / "reports" / "incidents" / "bad.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{broken", encoding="utf-8")
    result = DashboardStore(tmp_path).ingest(rebuild=True)
    assert result["ingested"] == 1
    assert result["quarantined"] == 1
