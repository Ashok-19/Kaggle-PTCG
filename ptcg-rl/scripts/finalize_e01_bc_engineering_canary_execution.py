from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"
PRIVATE_DIR = ROOT / "private/g3/e01/bc-engineering-canary-v1"
PRIVATE_REPORT = PRIVATE_DIR / "execution-report.json"
CHECKPOINT = PRIVATE_DIR / "step-32.pt"
CHECKPOINT_MANIFEST = PRIVATE_DIR / "step-32.pt.manifest.json"
CANONICAL_REPORT = ROOT / "reports/evaluations/e01-bc-engineering-canary-v1.json"
REVIEW = ROOT / "reports/artifacts/e01-bc-engineering-canary-execution-review-v1.json"
APPROVED_PRIOR_SHA256 = "5e78bcd7595a1f30b5eba5ab179203aa53ecad43f0ef3275a773a4b0ee4f2299"
AUTHORIZED_RECOVERY_SHA256 = "30bb97782cf898c06782e27345ca3f37e3d44f37c9528b54b73165e2c32f1edb"
COMPLETED_AT_UTC = "2026-08-04T15:44:42Z"


def pretty(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop("review_sha256", None)
    return hashlib.sha256(canonical(payload)).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(pretty(value))
    partial.replace(path)


def main() -> int:
    request = load(REQUEST)
    report = load(PRIVATE_REPORT)
    checkpoint_manifest = load(CHECKPOINT_MANIFEST)
    if report.get("status") != "PASS" or report.get("optimizer_steps") != 64:
        raise ValueError("BC canary execution report differs")
    if report.get("successful_attempt_optimizer_steps") != 54 or report.get("prior_failed_attempt_optimizer_steps") != 10:
        raise ValueError("BC canary recovery accounting differs")
    if report.get("request_sha256") != AUTHORIZED_RECOVERY_SHA256:
        raise ValueError("BC canary authorized recovery request hash differs")
    if report.get("production_checkpoint_eligible") is not False or report.get("policy_competence_claimed") is not False:
        raise ValueError("BC canary promotion boundary differs")
    if report.get("resume", {}).get("checkpoint_step") != 32 or report.get("resume", {}).get("state_match_after_restore") is not True:
        raise ValueError("BC canary deterministic resume differs")
    payload = checkpoint_manifest.get("payload")
    if not isinstance(payload, dict) or payload.get("sha256") != report["resume"]["payload_sha256"]:
        raise ValueError("BC canary checkpoint manifest differs")
    if CHECKPOINT.stat().st_size != int(payload["bytes"]) or sha(CHECKPOINT) != payload["sha256"]:
        raise ValueError("BC canary checkpoint payload differs")
    if len(report.get("skipped_forced_only_chunks", [])) != 1:
        raise ValueError("BC canary forced-only chunk accounting differs")
    canonical_bytes = pretty(report)
    if CANONICAL_REPORT.exists() and CANONICAL_REPORT.read_bytes() != canonical_bytes:
        raise ValueError("existing canonical BC canary report differs")
    CANONICAL_REPORT.parent.mkdir(parents=True, exist_ok=True)
    CANONICAL_REPORT.write_bytes(canonical_bytes)

    review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-bc-engineering-canary-execution-review-v1",
        "source_path": "reports/artifacts/e01-bc-engineering-canary-execution-review-v1.json",
        "created_at_utc": COMPLETED_AT_UTC,
        "producer": "scripts/finalize_e01_bc_engineering_canary_execution.py",
        "status": "PASS",
        "decision": "ACCEPT_NON_PROMOTABLE_64_STEP_BC_ENGINEERING_CANARY_WITH_FAIL_CLOSED_10_PLUS_54_RECOVERY",
        "reviewed_decision": "DEC-027",
        "inputs": {
            "approved_prior_request_sha256": APPROVED_PRIOR_SHA256,
            "authorized_recovery_request_sha256": AUTHORIZED_RECOVERY_SHA256,
            "execution_report": {
                "path": "reports/evaluations/e01-bc-engineering-canary-v1.json",
                "sha256": sha(CANONICAL_REPORT),
            },
            "checkpoint": {
                "path": "private/g3/e01/bc-engineering-canary-v1/step-32.pt",
                "bytes": CHECKPOINT.stat().st_size,
                "sha256": sha(CHECKPOINT),
            },
            "checkpoint_manifest": {
                "path": "private/g3/e01/bc-engineering-canary-v1/step-32.pt.manifest.json",
                "sha256": sha(CHECKPOINT_MANIFEST),
            },
            "implementation": {
                "path": "src/ptcg_rl/g3/bc_canary.py",
                "sha256": sha(ROOT / "src/ptcg_rl/g3/bc_canary.py"),
            },
        },
        "execution": {
            "failed_attempt_optimizer_steps": 10,
            "recovery_optimizer_steps": 54,
            "cumulative_optimizer_steps": 64,
            "step_32_checkpoint_created": True,
            "deterministic_resume_state_match": True,
            "forced_only_chunks_skipped": 1,
            "loss_first": report["loss"]["first"],
            "loss_last": report["loss"]["last"],
            "all_loss_finite": report["loss"]["all_finite"],
            "maximum_pre_clip_gradient_norm": report["gradient_norm"]["maximum_pre_clip"],
            "all_gradients_finite": report["gradient_norm"]["all_finite"],
            "final_state_sha256": report["final_state_sha256"],
        },
        "qualification": {
            "data_path_and_masking_engineering": "PASS",
            "checkpoint_resume_engineering": "PASS",
            "optimizer_cap_respected": True,
            "production_checkpoint_eligible": False,
            "policy_competence_claimed": False,
            "production_training_authorized": False,
            "model_promotion_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "next_action": "STOP_CANARY; PRODUCTION_BC_REQUIRES_FINAL_CORPUS_V2_AND_NEW_EXPLICIT_APPROVAL",
        "review_sha256": None,
    }
    review["review_sha256"] = self_hash(review)
    if REVIEW.exists() and REVIEW.read_bytes() != pretty(review):
        raise ValueError("existing BC canary execution review differs")
    write(REVIEW, review)

    if request.get("authorization_consumed") is not True:
        if sha(REQUEST) != AUTHORIZED_RECOVERY_SHA256:
            raise ValueError("request changed before canary authorization consumption")
        request["authorized"] = False
        request["authorization_consumed"] = True
        request["authorization"]["optimizer_steps"] = False
        request["status"] = "CONSUMED_PASS_NON_PROMOTABLE"
        request["completed_at_utc"] = COMPLETED_AT_UTC
        request["execution_receipt"] = {
            "approved_prior_request_sha256": APPROVED_PRIOR_SHA256,
            "authorized_recovery_request_sha256": AUTHORIZED_RECOVERY_SHA256,
            "failed_attempt_optimizer_steps": 10,
            "recovery_optimizer_steps": 54,
            "cumulative_optimizer_steps": 64,
            "checkpoint_step": 32,
            "checkpoint_payload_sha256": sha(CHECKPOINT),
            "execution_report_sha256": sha(CANONICAL_REPORT),
            "execution_review_sha256": sha(REVIEW),
            "execution_review_self_hash": review["review_sha256"],
            "production_checkpoint_eligible": False,
            "training_continuation_authorized": False,
            "model_promotion_authorized": False,
            "submission_authorized": False,
            "git_commit": False,
            "git_push": False,
        }
        write(REQUEST, request)
    else:
        if request.get("status") != "CONSUMED_PASS_NON_PROMOTABLE":
            raise ValueError("consumed BC canary request differs")
    print(json.dumps({
        "status": review["status"],
        "consumed_request_sha256": sha(REQUEST),
        "execution_report_sha256": sha(CANONICAL_REPORT),
        "execution_review_sha256": sha(REVIEW),
        "execution_review_self_hash": review["review_sha256"],
        "optimizer_steps": 64,
        "production_checkpoint_eligible": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
