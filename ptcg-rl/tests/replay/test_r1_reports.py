from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


STREAM_SHA256 = "68da24b6d530f206987840079acffbe01e6d398bbc993427ae5a55e37d47c9a4"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def load(root: Path, relative: str) -> Any:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_r1_loader_and_independent_review_are_cryptographically_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    semantic = load(root, "reports/replays/r1-semantic-loader.json")
    review = load(root, "reports/replays/r1-independent-review.json")

    semantic_payload = dict(semantic)
    semantic_claim = semantic_payload.pop("audit_sha256")
    assert hashlib.sha256(canonical(semantic_payload)).hexdigest() == semantic_claim

    review_payload = dict(review)
    review_claim = review_payload.pop("review_sha256")
    assert hashlib.sha256(canonical(review_payload)).hexdigest() == review_claim

    assert semantic["status"] == "PASS"
    assert review["status"] == "PASS"
    assert review["decision"] == "PASS"
    assert semantic["semantic_stream_sha256"] == STREAM_SHA256
    assert review["semantic_stream_sha256"] == STREAM_SHA256
    assert review["reviewed_audit_sha256"] == semantic["audit_sha256"]
    assert review["recalculated_coverage"] == semantic["coverage"]
    assert set(review["checks"].values()) == {"PASS"}
    assert review["mismatches"] == []


def test_r1_gate_and_task_close_only_on_full_evidence() -> None:
    root = Path(__file__).resolve().parents[2]
    gate = load(root, "reports/gates/r1.json")
    tasks = load(root, "reports/tasks/current.json")
    learning = load(root, "reports/learning/r1-semantic-findings.json")

    assert gate["status"] == "SUCCEEDED"
    assert gate["decision"] == "PASS"
    assert gate["blockers"] == []
    assert all(check["status"] == "PASS" for check in gate["technical_checks"])
    evidence = {check["evidence"] for check in gate["technical_checks"]}
    assert "reports/replays/r1-semantic-loader.json" in evidence
    assert "reports/replays/r1-independent-review.json" in evidence

    task = next(item for item in tasks if item.get("task_id") == "T-R1-004")
    assert task["status"] == "SUCCEEDED"
    assert task["semantic_stream_sha256"] == STREAM_SHA256
    assert task["implementation_commit"] == "225f23aa705b061a6f98e24796cbb68ea0fc51f0"
    assert task["review_commit"] == "ce19b581c61d87e66b32118f3e63a7b2076aad50"

    assert learning["status"] == "SUCCEEDED"
    assert learning["coverage"]["decisions"] == 2999
    assert learning["coverage"]["chosen_options"] == 3275
    assert learning["coverage"]["stop_markers"] == 21
    assert learning["semantic_stream_sha256"] == STREAM_SHA256
