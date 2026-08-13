from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: dict) -> str:
    payload = copy.deepcopy(value)
    payload.pop("review_sha256", None)
    return hashlib.sha256(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def main() -> int:
    request_path = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"
    preflight_path = ROOT / "reports/artifacts/e01-bc-engineering-canary-preflight-v1.json"
    out = ROOT / "reports/artifacts/e01-bc-engineering-canary-preflight-review-v1.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert request["authorized"] is False
    assert request["authorization"]["optimizer_steps"] is False
    assert request["execution"]["maximum_optimizer_steps"] == 64
    assert request["execution"]["checkpoint_at_optimizer_step"] == 32
    assert request["execution"]["platform"] == "local_cpu_only"
    assert preflight["status"] == "PASS"
    assert preflight["request"]["sha256"] == sha(request_path)
    assert preflight["coverage"]["episodes"] == 8
    assert preflight["coverage"]["teacher_decisions"] == 665
    assert preflight["coverage"]["forced_decisions"] == 56
    assert preflight["coverage"]["meaningful_decisions"] == 609
    assert preflight["coverage"]["stop_targets"] == 17
    assert preflight["coverage"]["ordered_requests"] == 5
    assert preflight["gradient_probe"]["episodes"] == 8
    assert preflight["gradient_probe"]["optimizer_constructed"] is False
    assert preflight["gradient_probe"]["optimizer_steps"] == 0
    assert preflight["gradient_probe"]["parameters_changed"] is False
    assert preflight["execution_boundary"]["optimizer_steps_executed"] == 0
    assert preflight["execution_boundary"]["checkpoint_output_exists"] is False
    assert preflight["semantics"]["episode_split_leakage"] == 0
    for name in (
        "forced_calls_advance_recurrence",
        "lag_alignment",
        "legal_option_mask_verified",
        "ordered_selection_preserved",
        "stop_first_class",
    ):
        assert preflight["semantics"][name] is True
    assert preflight["semantics"]["forced_calls_create_policy_loss"] is False
    report = {
        "schema_version": 1,
        "record_id": "e01-bc-engineering-canary-preflight-review-v1",
        "source_path": "reports/artifacts/e01-bc-engineering-canary-preflight-review-v1.json",
        "created_at_utc": "2026-08-04T10:00:34Z",
        "producer": "scripts/e01_bc_engineering_canary_review.py",
        "status": "PASS",
        "decision": "ACCEPT_HASH_BOUND_ZERO_UPDATE_BC_CANARY_PREFLIGHT",
        "reviewed_decision": "DEC-025",
        "inputs": {
            "request": {"path": request["source_path"], "sha256": sha(request_path)},
            "preflight": {"path": preflight["source_path"], "sha256": sha(preflight_path)},
            "runner": {
                "path": "scripts/e01_bc_engineering_canary.py",
                "sha256": sha(ROOT / "scripts/e01_bc_engineering_canary.py"),
            },
            "implementation": {
                "path": "src/ptcg_rl/g3/bc_canary.py",
                "sha256": sha(ROOT / "src/ptcg_rl/g3/bc_canary.py"),
            },
        },
        "qualification": {
            "all_eight_episodes_hash_verified": True,
            "all_609_meaningful_targets_replayed": True,
            "ordered_multiselect_stop_and_masks_verified": True,
            "forced_recurrence_without_policy_loss_verified": True,
            "finite_gradient_path_verified": True,
            "optimizer_constructed": False,
            "optimizer_steps": 0,
            "execution_request_ready": True,
            "execution_authorized": False,
            "production_training_authorized": False,
        },
        "next_action": "REQUEST_SEPARATE_EXPLICIT_APPROVAL_FOR_THE_EXACT_64_STEP_LOCAL_BC_ENGINEERING_CANARY",
        "review_sha256": None,
    }
    report["review_sha256"] = self_hash(report)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
