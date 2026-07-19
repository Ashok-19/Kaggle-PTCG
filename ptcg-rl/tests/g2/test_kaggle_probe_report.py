from __future__ import annotations

import json
from pathlib import Path


def test_kaggle_probe_report_does_not_claim_submission_parity() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads(
        (
            root
            / "reports"
            / "jobs"
            / "g2-kaggle-environment-probe-v163.json"
        ).read_text(encoding="utf-8")
    )
    assert report["notebook"]["private"] is True
    assert report["requested"]["internet"] is False
    assert report["requested"]["gpu"] is False
    assert report["observed"]["torch"] == "2.10.0+cpu"
    assert report["verdict"] == "PASS_FOR_KAGGLE_DEVELOPMENT_ONLY"
    assert any("submission-runtime" in warning for warning in report["warnings"])
