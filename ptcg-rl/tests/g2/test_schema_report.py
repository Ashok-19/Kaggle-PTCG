from __future__ import annotations

import json
from pathlib import Path

from ptcg_rl.g2.models import model_schema_descriptor, model_schema_sha256


def test_tracked_g2_schema_report_matches_source() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "reports" / "artifacts" / "g2-model-schema-v3.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["model_schema_sha256"] == model_schema_sha256()
    normalized = json.loads(json.dumps(model_schema_descriptor(), sort_keys=True))
    assert report["descriptor"] == normalized
    assert report["source_commit"] == "787a7f384975769bc6a490790ba0f88f85d0ee0c"
