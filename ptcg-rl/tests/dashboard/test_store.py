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
    token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"
    secret.write_text("# no\n" + token + "\n", encoding="utf-8")
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


def test_audit_reports_are_first_class_dashboard_records(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "audits" / "complete.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_id": "audit-complete",
                "created_at_utc": "2026-07-19T00:00:00Z",
                "source_path": "reports/audits/complete.json",
                "producer": "test",
                "kind": "AUDIT",
                "status": "SUCCEEDED",
                "decision": "PASS",
            }
        ),
        encoding="utf-8",
    )
    dashboard = DashboardStore(tmp_path)
    result = dashboard.ingest(rebuild=True)
    assert result["quarantined"] == 0
    audit = dashboard.list("audit")["items"][0]
    assert audit["record_id"] == "audit-complete"
    assert audit["status"] == "SUCCEEDED"


def test_auto_sync_detects_new_modified_and_deleted_sources(tmp_path: Path) -> None:
    write_gate(tmp_path)
    store = DashboardStore(tmp_path, refresh_interval_seconds=0)
    assert store.sync_if_needed(force=True)["ingested"] == 1

    g2 = tmp_path / "reports" / "gates" / "g2.json"
    payload = {
        "schema_version": 1,
        "record_id": "gate-g2",
        "created_at_utc": "2026-07-19T00:00:00Z",
        "source_path": "reports/gates/g2.json",
        "producer": "test",
        "gate_id": "G2",
        "status": "QUEUED",
        "decision": "NOT_REVIEWED",
    }
    g2.write_text(json.dumps(payload), encoding="utf-8")
    assert store.list("gate")["total"] == 2

    payload["status"] = "RUNNING"
    g2.write_text(json.dumps(payload), encoding="utf-8")
    g2_record = next(item for item in store.list("gate")["items"] if item["gate_id"] == "G2")
    assert g2_record["status"] == "RUNNING"

    g2.unlink()
    assert store.list("gate")["total"] == 1


def test_experiment_manifest_emits_experiment_and_run_records(tmp_path: Path) -> None:
    manifest = tmp_path / "experiments" / "E001" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "experiment_id": "E001",
                "title": "Fixture",
                "hypothesis": "A measurable claim",
                "status": "designed",
                "created_at": "2026-07-19T00:00:00Z",
                "updated_at": "2026-07-19T00:00:00Z",
                "runs": [
                    {
                        "run_id": "R001",
                        "status": "complete",
                        "started_at": "2026-07-19T00:01:00Z",
                        "metrics": [{"name": "score", "value": 0.5}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = DashboardStore(tmp_path, refresh_interval_seconds=0)
    store.ingest(rebuild=True)
    assert store.list("experiment")["items"][0]["status"] == "PLANNED"
    assert store.list("run")["items"][0]["status"] == "SUCCEEDED"
