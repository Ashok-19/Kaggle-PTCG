from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def load(root: Path, path: str) -> Any:
    return json.loads((root / path).read_text(encoding="utf-8"))


def test_complete_pre_g2_audit_is_cryptographically_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, "reports/audits/pre-g2-complete-audit-20260719.json")
    payload = dict(report)
    claimed = payload.pop("audit_sha256")
    assert hashlib.sha256(canonical(payload)).hexdigest() == claimed
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["verdict"] == "PASS_WITH_CORRECTIONS"
    assert report["source_commit"] == "689cd4cc748a0ceb54300d8515a3500dce47b57a"

    matrix = report["test_matrix"]
    assert matrix["python"]["strict_runs"] == 2
    assert matrix["python"]["tests_passed_each_run"] == 123
    assert matrix["python"]["warnings_as_errors"] is True
    assert matrix["replay"]["semantic_decisions"] == 2999
    assert matrix["replay"]["independent_checks_passed"] == 8
    assert matrix["dashboard"]["quarantined_records"] == 0
    assert matrix["sealed_bundle"]["launch_disposition"] == "BLOCKED_REBUILD_REQUIRED"

    semantic = load(root, "reports/replays/r1-semantic-loader.json")
    review = load(root, "reports/replays/r1-independent-review.json")
    incident = load(root, "reports/incidents/r1-card-data-provenance-hash.json")
    gate = load(root, "reports/gates/g2.json")
    assert matrix["replay"]["semantic_stream_sha256"] == semantic["semantic_stream_sha256"]
    assert matrix["replay"]["semantic_audit_sha256"] == semantic["audit_sha256"]
    assert matrix["replay"]["independent_review_sha256"] == review["review_sha256"]
    assert incident["after"]["source_commit"] == review["source_commit"]
    checks = {item["name"]: item["status"] for item in gate["technical_checks"]}
    assert checks["latest-clean-source qualification bundle"] == "PASS"
    assert checks["Kaggle CPU/GPU numerical and latency qualification"] == "PASS"
    assert gate["status"] == "RUNNING"
    assert gate["blockers"] == []
