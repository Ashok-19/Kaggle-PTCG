from __future__ import annotations

import json
from pathlib import Path


def test_tracked_policy_report_respects_sealed_inputs_and_budget() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads(
        (root / "reports" / "artifacts" / "g2-policy-v1.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        (root / "configs" / "g2_policy_v1.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "SUCCEEDED"
    assert report["model_schema_sha256"] == (
        "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68"
    )
    assert report["card_table_sha256"] == (
        "7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0"
    )
    assert report["architecture_sha256"] == (
        "aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf"
    )
    assert report["source_commit"] == "ac25a8807c8351c5ae4c9071c3bdcdbe521b0eae"
    assert report["trainable_parameters"] == 970022
    assert report["trainable_parameters"] < report["target_trainable_parameters"]
    assert report["target_trainable_parameters"] < report["hard_parameter_ceiling"]
    assert report["qualification"]["gradient_reach_nonzero"] == "PASS"
    assert report["qualification"]["packaged_source_cpu_smoke"] == "PASS"
    assert config["policy_config"]["entity_layers"] == 2
    assert config["policy_config"]["public_hidden"] == 160
    assert config["torch_version"].startswith("2.10.0")
    assert "policy strength or learning" in report["not_yet_qualified"]


def test_qualification_bundle_report_is_commit_and_hash_bound() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads(
        (
            root
            / "reports"
            / "artifacts"
            / "g2-policy-qualification-bundle-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert report["status"] == "SUCCEEDED"
    assert report["source_commit"] == "16240fa65fd35f395fc46a6ff7b5eabc9516d70f"
    assert report["bundle_sha256"] == (
        "aa109e4e523d2f287e2a9f9e182669971a38cd53ac93e8d40b16b4a939cdbbb6"
    )
    assert report["included_files"] == 11
    assert report["packaged_source_smoke"]["status"] == "PASS"
    assert report["privacy"]["card_names_or_effect_text_included"] is False
