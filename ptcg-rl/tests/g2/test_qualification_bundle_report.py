from __future__ import annotations

import json
from pathlib import Path


BUNDLE_SHA256 = "3718b493e4b218117456c0c2b3eccc8ba76ac9516c37cd75a44e5a0f12eb2e6e"
SOURCE_COMMIT = "76951fb392fa6e3b8f65cb014d9cb7dba0bddf33"


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_current_source_bundle_report_is_sealed_and_no_training() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, "reports/artifacts/g2-policy-qualification-bundle-v2.json")

    assert report["status"] == "SUCCEEDED"
    assert report["source_commit"] == SOURCE_COMMIT
    assert report["bundle_sha256"] == BUNDLE_SHA256
    assert report["bundle_bytes"] == 66851
    assert report["included_files"] == 11
    assert report["tracked_source_files"] == 10
    assert report["private_numeric_tables"] == 1
    assert set(report["archive_validation"].values()) == {"PASS", 0}
    smoke = report["packaged_source_smoke"]
    assert smoke["status"] == "PASS"
    assert smoke["runs"] == 2
    assert smoke["stable_payload_match"] is True
    assert smoke["trainable_parameters"] == 970022
    assert smoke["nonzero_selected_gradients"] == 7
    assert smoke["all_checks"] is True
    assert smoke["no_optimizer"] is True
    assert smoke["no_training_loop"] is True
    assert report["authorization"] == {
        "training_included": False,
        "optimizer_created": False,
        "kaggle_launch_performed": False,
    }


def test_gate_and_task_activate_only_the_current_source_bundle() -> None:
    root = Path(__file__).resolve().parents[2]
    gate = load(root, "reports/gates/g2.json")
    tasks = load(root, "reports/tasks/current.json")

    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["latest-clean-source qualification bundle"]["status"] == "PASS"
    assert checks["Kaggle CPU/GPU numerical and latency qualification"]["status"] == "READY"
    assert gate["blockers"] == []

    task = next(item for item in tasks if item.get("task_id") == "T-G2-003")
    assert task["status"] == "READY"
    assert task["bundle_report"] == "reports/artifacts/g2-policy-qualification-bundle-v2.json"
    assert task["bundle_sha256"] == BUNDLE_SHA256
    assert task["bundle_source_commit"] == SOURCE_COMMIT
    assert task["no_training"] is True
