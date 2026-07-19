from __future__ import annotations

import json
from pathlib import Path


def test_tracked_card_table_report_preserves_private_content_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads(
        (root / "reports" / "artifacts" / "g2-card-table-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["source_commit"] == "bc7f1433fc710c33c2c27d41463d201f1183194a"
    assert report["table_sha256"] == (
        "7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0"
    )
    assert report["private_output_tracked"] is False
    assert report["counts"]["cards"] == 1267
    assert report["counts"]["attacks"] == 1556
    excluded = set(report["content_boundary"]["excluded"])
    assert {"card names", "move names", "effect explanations"} <= excluded
