from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from ptcg_rl.replay.independent_review import (
    ReplayReviewError,
    independently_review_semantic_report,
)
from ptcg_rl.replay.semantic_loader import audit_semantic_loader

from .test_semantic_loader import CARD_HASH, write_fixture


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def test_independent_review_recalculates_and_matches_loader(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    semantic_report = audit_semantic_loader(
        plan,
        episodes,
        card_data_sha256=CARD_HASH,
        created_at_utc="2026-07-19T00:00:00Z",
    )
    review = independently_review_semantic_report(
        plan,
        episodes,
        semantic_report,
        created_at_utc="2026-07-19T00:01:00Z",
        source_commit="a" * 40,
    )
    assert review["status"] == "PASS"
    assert review["decision"] == "PASS"
    assert review["semantic_stream_sha256"] == semantic_report["semantic_stream_sha256"]
    assert review["recalculated_coverage"] == semantic_report["coverage"]
    assert set(review["checks"].values()) == {"PASS"}


def test_independent_review_rejects_a_validly_rehashed_coverage_tamper(
    tmp_path: Path,
) -> None:
    plan, episodes = write_fixture(tmp_path)
    semantic_report = audit_semantic_loader(
        plan,
        episodes,
        card_data_sha256=CARD_HASH,
        created_at_utc="2026-07-19T00:00:00Z",
    )
    semantic_report["coverage"]["decisions"] += 1
    semantic_report.pop("audit_sha256")
    semantic_report["audit_sha256"] = hashlib.sha256(canonical(semantic_report)).hexdigest()
    with pytest.raises(ReplayReviewError, match="coverage"):
        independently_review_semantic_report(plan, episodes, semantic_report)


def test_independent_reviewer_does_not_import_loader_implementation() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "src" / "ptcg_rl" / "replay" / "independent_review.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert "semantic_loader" not in source
    assert all("semantic_loader" not in name for name in imported_modules)
    assert all(name is None or "semantic_loader" not in name for name in imported_from)


def test_independent_review_rejects_nonofficial_card_data_provenance(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    semantic_report = audit_semantic_loader(
        plan,
        episodes,
        card_data_sha256=CARD_HASH,
        created_at_utc="2026-07-19T00:00:00Z",
    )
    with pytest.raises(ReplayReviewError, match="verified official asset"):
        independently_review_semantic_report(
            plan,
            episodes,
            semantic_report,
            expected_card_data_sha256="d" * 64,
        )
