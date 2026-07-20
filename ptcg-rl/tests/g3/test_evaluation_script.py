from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ptcg_rl.g3.evaluation import ZERO_TOLERANCE_COUNTERS, derive_declared_seeds, load_evaluation_contract

from .test_evaluation import HASH_A, HASH_B, HASH_C, HASH_D, SOURCE_COMMIT, task_result


def make_evidence(contract_path: Path) -> dict[str, object]:
    contract = load_evaluation_contract(contract_path)
    return {
        "schema_version": 1,
        "contract_id": "g3a-evaluation-v1",
        "contract_file_sha256": contract.file_sha256,
        "run_id": "g3a-script-proof-v1",
        "source_commit": SOURCE_COMMIT,
        "status": "SUCCEEDED",
        "authorization": {
            "user_training_approval": True,
            "private_bounded_run": True,
            "platform": "colab",
            "modal_used": False,
            "submission_created": False,
        },
        "budget": {
            "declared_before_run": True,
            "non_forced_choices_per_seed": [100_000, 100_000, 100_000],
            "task_allocation_sha256": HASH_A,
            "budget_manifest_sha256": HASH_B,
        },
        "seeds": [
            {
                "seed": seed,
                "tasks": {
                    "masked-bandit-v1": task_result("masked-bandit-v1"),
                    "recurrent-cue-v1": task_result("recurrent-cue-v1"),
                    "variable-option-multiselect-v1": task_result(
                        "variable-option-multiselect-v1"
                    ),
                },
                "probability_replay": {
                    "checked_before_first_update": True,
                    "old_compound_log_probability_max_abs_error": 0.0,
                    "initial_ratio_max_abs_error_from_one": 0.0,
                },
                "zero_tolerance": {name: 0 for name in ZERO_TOLERANCE_COUNTERS},
                "checkpoint_resume": {
                    "status": "PASS",
                    "components": {
                        "counters": True,
                        "league": True,
                        "model": True,
                        "optimizer": True,
                        "rollout_boundary": True,
                        "scheduler_or_scaler": True,
                    },
                    "available_rng_states": ["python", "torch_cpu"],
                    "restored_rng_states": ["python", "torch_cpu"],
                    "fixed_tensor_max_abs_diff": 0.0,
                    "fixed_tensor_rtol": 0.0,
                },
            }
            for seed in derive_declared_seeds()
        ],
        "artifacts": {
            "run_manifest_path": "runs/g3a-script-proof-v1/manifest.json",
            "run_manifest_sha256": HASH_A,
            "metrics_sha256": HASH_B,
            "checkpoint_manifest_sha256": HASH_C,
            "independent_review_sha256": HASH_D,
        },
        "claim": {"algorithm_proof_only": True, "policy_strength_claimed": False},
    }


def run_script(root: Path, contract: Path, evidence: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(root / "scripts/g3a_review.py"),
            "--contract",
            str(contract),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_review_script_writes_canonical_pass_and_returns_zero(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    contract = root / "configs/g3a_evaluation_v1.json"
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "review.json"
    evidence_path.write_text(json.dumps(make_evidence(contract)), encoding="utf-8")
    completed = run_script(root, contract, evidence_path, output)
    assert completed.returncode == 0, completed.stderr
    review = json.loads(output.read_text(encoding="utf-8"))
    assert review["decision"] == "PASS"
    assert review["status"] == "SUCCEEDED"
    assert output.read_bytes().endswith(b"\n")


def test_review_script_returns_one_and_retains_completed_fail_review(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    contract = root / "configs/g3a_evaluation_v1.json"
    evidence = make_evidence(contract)
    evidence["seeds"][0]["zero_tolerance"]["invalid_actions"] = 1  # type: ignore[index]
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "review.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    completed = run_script(root, contract, evidence_path, output)
    assert completed.returncode == 1
    review = json.loads(output.read_text(encoding="utf-8"))
    assert review["decision"] == "FAIL"
    assert any("invalid_actions" in failure for failure in review["failures"])


def test_review_script_returns_two_and_does_not_write_on_invalid_evidence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    contract = root / "configs/g3a_evaluation_v1.json"
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "review.json"
    evidence_path.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
    completed = run_script(root, contract, evidence_path, output)
    assert completed.returncode == 2
    assert "duplicate key" in completed.stderr
    assert not output.exists()
