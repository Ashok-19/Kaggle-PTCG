from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EXPANSION_REQUEST = ROOT / "configs/e01_majkel_corpus_expansion_request_v1.json"
RUN = ROOT / "reports/artifacts/e01-majkel-corpus-review-v1.json"
MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json"
CORPUS_REVIEW = ROOT / "reports/artifacts/e01-approved-replay-corpus-review-v2.json"
OUTPUT_MANIFEST = ROOT / "reports/artifacts/e01-majkel-corpus-review-v1-output-manifest.json"
CANARY_REQUEST = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"
CANARY_EXECUTION = ROOT / "reports/evaluations/e01-bc-engineering-canary-v1.json"
CANARY_REVIEW = ROOT / "reports/artifacts/e01-bc-engineering-canary-execution-review-v1.json"
JOB = ROOT / "reports/jobs/e01-majkel-corpus-review-v1.json"
INDEPENDENT_REVIEW = ROOT / "reports/artifacts/e01-majkel-corpus-review-independent-review-v1.json"
DECISION = ROOT / "docs/decisions/DEC-028_E01_CORPUS_V2_AND_BC_CANARY_RESULTS.md"
TASKS = ROOT / "reports/tasks/current.json"
DECISIONS = ROOT / "reports/decisions/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

APPROVED_EXPANSION_SHA256 = "7652f617e9bba2cd5a18a3d4b9956d348438989359e0fb200ef0f6066a590d3c"
OUTPUT_SHA256 = {
    RUN: "31fdff1a40de058407b07de5975e2bf531fdc417aae456f54e88759386918d16",
    MANIFEST: "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f",
    CORPUS_REVIEW: "87eaee15513189d7f2ff4ca44e631016b3f937165df31db8696383a30c1cad56",
    OUTPUT_MANIFEST: "ef8ce73b6185e183ac8f32ea8267e50b3e3bb67e161cee22016c25d4ee7ef2ed",
}
CANARY_REQUEST_SHA256 = "8b3242f6d38f4d20c00403f9b013f3d1d6a62b3ed7ceaa137bb49c3d04583f9d"
CANARY_EXECUTION_SHA256 = "51e06333619f1e8fc34ebb889d84cb196997632b0e347c731fe558df7813c1ee"
CANARY_REVIEW_SHA256 = "1f25828a78400801f6dc5d2d8630890579e29584762ad95b18af795ca810c100"
CREATED_AT = "2026-08-04T15:55:00Z"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: Mapping[str, Any], field: str = "review_sha256") -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return hashlib.sha256(canonical(payload)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(pretty(value))
    partial.replace(path)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label} replacement count differs: {text.count(old)}")
    return text.replace(old, new)


def upsert(items: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    positions = [index for index, item in enumerate(items) if item.get(key) == value]
    if len(positions) > 1:
        raise ValueError(f"duplicate ledger record for {value}")
    if positions:
        items[positions[0]] = record
    else:
        items.append(record)


def verify_outputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    for path, expected in OUTPUT_SHA256.items():
        if sha(path) != expected:
            raise ValueError(f"output hash differs: {path}")
    run = load(RUN)
    manifest = load(MANIFEST)
    review = load(CORPUS_REVIEW)
    output = load(OUTPUT_MANIFEST)
    for value, field in ((run, "review_sha256"), (manifest, "manifest_sha256"), (review, "review_sha256"), (output, "manifest_sha256")):
        if self_hash(value, field) != value[field]:
            raise ValueError(f"self hash differs: {field}")
    if run["status"] != "PASS" or run["transfer"] != {
        "additional_replay_bodies_read": 0,
        "agent_logs_read": 0,
        "maximum_new_bytes": 1_030_207_171,
        "named_replay_bodies_read": 269,
        "new_bytes_read": 1_030_207_171,
        "replay_body_outputs": 0,
        "reused_probe_bodies_without_reread": 2,
    }:
        raise ValueError("run transfer boundary differs")
    if any(run["authorization"].values()):
        raise ValueError("run authorization boundary differs")
    corpus = manifest["qualified_training_corpus"]
    if (
        corpus["episodes"] != 337
        or corpus["policy_loss_targets"] != 23_460
        or corpus["teacher_active_requests"] != 25_058
        or corpus["forced_teacher_requests"] != 1_598
        or corpus["bytes"] != 1_414_841_670
        or len(corpus["episode_records"]) != 337
        or len({item["episode_id"] for item in corpus["episode_records"]}) != 337
        or len({item["sha256"] for item in corpus["episode_records"]}) != 337
    ):
        raise ValueError("corpus-v2 counts or uniqueness differ")
    if review["status"] != "BLOCKED_FLOORS" or review["counts"] != {
        "bytes": 1_414_841_670,
        "episodes": 337,
        "forced_teacher_requests": 1_598,
        "meaningful_teacher_decisions": 23_460,
        "policy_loss_targets": 23_460,
        "teacher_active_requests": 25_058,
    }:
        raise ValueError("corpus-v2 floor review differs")
    if review["qualification"]["minimum_200_episodes"] is not True or review["qualification"]["minimum_25000_policy_loss_targets"] is not False:
        raise ValueError("corpus-v2 floor flags differ")
    return run, manifest, review, output


def main() -> int:
    run, manifest, review, output = verify_outputs()
    if sha(CANARY_REQUEST) != CANARY_REQUEST_SHA256 or sha(CANARY_EXECUTION) != CANARY_EXECUTION_SHA256 or sha(CANARY_REVIEW) != CANARY_REVIEW_SHA256:
        raise ValueError("canary evidence hash differs")
    canary_request = load(CANARY_REQUEST)
    canary_execution = load(CANARY_EXECUTION)
    canary_review = load(CANARY_REVIEW)
    if canary_request["status"] != "CONSUMED_PASS_NON_PROMOTABLE" or canary_execution["optimizer_steps"] != 64 or canary_review["status"] != "PASS":
        raise ValueError("canary completion state differs")

    job: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "job-e01-majkel-corpus-review-v1",
        "source_path": "reports/jobs/e01-majkel-corpus-review-v1.json",
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "SUCCEEDED",
        "decision": "PRIVATE_KAGGLE_CPU_EXACT_269_FILE_REVIEW_COMPLETE",
        "notebook": {
            "owner": "ashok205",
            "slug": "kptcg-e01-majkel-corpus-review-v1",
            "kernel_id": 129_704_016,
            "saved_version": 2,
            "private": True,
            "internet": False,
            "gpu": False,
            "tpu": False,
            "source_code_sha256": "4669730a0943ea669fb9b75db90b9452f57ab03d1adf9767b7b98723d72fd89a",
            "docker_image": "gcr.io/kaggle-images/python@sha256:dafd4ce5668bbf1ad422e4c109e0f18c9623c3a7c7f48b0235f13142755c40b9",
        },
        "inputs": {
            "approved_request_sha256": APPROVED_EXPANSION_SHA256,
            "source_dataset": "ashok205/kptcg-e01-majkel-corpus-review-inputs/1",
            "source_dataset_id": 11_501_808,
            "source_bundle_sha256": "ceec17e0a76097af8f25de4ecddfa627f509f44a58bb67e2528a2c0696f3a97a",
            "daily_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
            "competition_attachment": "pokemon-tcg-ai-battle",
        },
        "execution": {
            "named_replay_bodies_read": 269,
            "bytes_read": 1_030_207_171,
            "qualified": 269,
            "rejected": 0,
            "replay_body_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "submission": False,
            "wall_seconds_from_notebook_log": 96.548250296,
            "log_sha256": "9d32086a220d8384a3f64812e96f9d287706d8e3c7cd33b279b63f44af998e29",
        },
        "outputs": {
            "run": {"path": str(RUN.relative_to(ROOT)), "sha256": sha(RUN)},
            "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST), "self_hash": manifest["manifest_sha256"]},
            "review": {"path": str(CORPUS_REVIEW.relative_to(ROOT)), "sha256": sha(CORPUS_REVIEW), "self_hash": review["review_sha256"]},
            "output_manifest": {"path": str(OUTPUT_MANIFEST.relative_to(ROOT)), "sha256": sha(OUTPUT_MANIFEST), "self_hash": output["manifest_sha256"]},
        },
        "cost_usd": 0.0,
    }
    write_json(JOB, job)

    independent: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-corpus-review-independent-review-v1",
        "source_path": "reports/artifacts/e01-majkel-corpus-review-independent-review-v1.json",
        "created_at_utc": CREATED_AT,
        "producer": "scripts/finalize_e01_corpus_v2_and_canary.py",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_TRANSFER_AND_QUALIFIED_CORPUS_V2_RETAIN_PRODUCTION_TARGET_FLOOR_BLOCK",
        "reviewed_decision": "DEC-028",
        "inputs": {
            "job": {"path": str(JOB.relative_to(ROOT)), "sha256": sha(JOB)},
            "run": {"path": str(RUN.relative_to(ROOT)), "sha256": sha(RUN), "self_hash": run["review_sha256"]},
            "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": sha(MANIFEST), "self_hash": manifest["manifest_sha256"]},
            "corpus_review": {"path": str(CORPUS_REVIEW.relative_to(ROOT)), "sha256": sha(CORPUS_REVIEW), "self_hash": review["review_sha256"]},
            "canary_execution": {"path": str(CANARY_EXECUTION.relative_to(ROOT)), "sha256": sha(CANARY_EXECUTION)},
            "canary_review": {"path": str(CANARY_REVIEW.relative_to(ROOT)), "sha256": sha(CANARY_REVIEW), "self_hash": canary_review["review_sha256"]},
        },
        "recalculation": {
            "new_files_read": 269,
            "new_bytes_read": 1_030_207_171,
            "new_files_qualified": 269,
            "new_files_rejected": 0,
            "corpus_v2_episodes": 337,
            "corpus_v2_policy_loss_targets": 23_460,
            "episode_floor_shortfall": 0,
            "target_floor_shortfall": 1_540,
            "episode_ids_unique": True,
            "content_hashes_unique": True,
            "replay_body_outputs": 0,
            "canary_cumulative_optimizer_steps": 64,
            "canary_non_promotable": True,
        },
        "authorization": {
            "additional_replay_transfer": False,
            "training_label_materialization": False,
            "production_training": False,
            "optimizer_steps": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "next_action": "RESOLVE_EXACT_1540_TARGET_SHORTFALL_THEN_REQUEST_SEPARATE_PRODUCTION_BC_APPROVAL",
        "review_sha256": None,
    }
    independent["review_sha256"] = self_hash(independent)
    write_json(INDEPENDENT_REVIEW, independent)

    request = load(EXPANSION_REQUEST)
    if request.get("authorization_consumed") is not True:
        if sha(EXPANSION_REQUEST) != APPROVED_EXPANSION_SHA256 or request.get("status") != "READY_UNAUTHORIZED":
            raise ValueError("expansion request changed before consumption")
        request["approval"] = {
            "approved_by": "user",
            "approved_at_utc": "2026-08-04T15:19:00Z",
            "one_time": True,
            "approved_prior_request_sha256": APPROVED_EXPANSION_SHA256,
            "scope": "EXACT_269_FILE_PRIVATE_KAGGLE_CPU_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION_ONLY",
            "maximum_new_files": 269,
            "maximum_new_bytes": 1_030_207_171,
            "training_authorized": False,
            "optimizer_steps_authorized": False,
            "model_promotion_authorized": False,
            "submission_authorized": False,
            "git_commit_authorized": False,
            "git_push_authorized": False,
        }
        request["authorized"] = False
        request["authorization_consumed"] = True
        request["request_ready"] = False
        request["status"] = "CONSUMED_PASS_CORPUS_V2_BLOCKED_TARGET_FLOOR"
        request["completed_at_utc"] = CREATED_AT
        request["execution_receipt"] = {
            "job": str(JOB.relative_to(ROOT)),
            "job_sha256": sha(JOB),
            "independent_review": str(INDEPENDENT_REVIEW.relative_to(ROOT)),
            "independent_review_sha256": sha(INDEPENDENT_REVIEW),
            "independent_review_self_hash": independent["review_sha256"],
            "new_files_read": 269,
            "new_bytes_read": 1_030_207_171,
            "qualified_new_files": 269,
            "rejected_new_files": 0,
            "corpus_v2_episodes": 337,
            "corpus_v2_policy_loss_targets": 23_460,
            "target_floor_shortfall": 1_540,
            "replay_body_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        }
        write_json(EXPANSION_REQUEST, request)
    elif request.get("status") != "CONSUMED_PASS_CORPUS_V2_BLOCKED_TARGET_FLOOR":
        raise ValueError("consumed expansion request differs")

    decision_text = f"""# DEC-028: Accept Corpus v2 and the BC Engineering Canary, Retain the Production Target Floor\n\nDate: 2026-08-04  \nStatus: Accepted\n\n## Decision\n\nAccept the exact private Kaggle CPU review of all 269 newly authorized Majkel replay bodies and freeze qualified corpus v2. Accept the bounded local BC engineering canary as a non-promotable engineering PASS. Do not start production training because corpus v2 contains 23,460 policy-loss targets, 1,540 below the frozen 25,000-target floor.\n\n## Evidence\n\n- 269/269 new Majkel files qualified, zero rejected, exactly 1,030,207,171 newly read bytes.\n- Corpus v2: 337 unique episodes, 1,414,841,670 bytes, 25,058 active teacher requests, 1,598 forced recurrent calls, and 23,460 policy-loss targets.\n- Deterministic split: 266 train, 29 validation, 42 test episodes.\n- Teacher composition: 271 Majkel, 52 flg, and 14 Dries episodes.\n- BC canary: exactly 64 cumulative AdamW steps, finite loss and gradients, step-32 checkpoint and exact restore, non-promotable. The first attempt failed closed after 10 steps on a forced-only chunk; the scheduler was corrected to skip that chunk and only the remaining 54 steps were executed.\n\n## Authorization boundary\n\nNo additional replay transfer, label materialization, production optimizer step, GPU/TPU use, external training, model promotion, submission, commit, or push is authorized. The next smallest action is metadata-only selection of enough version-pinned qualified source candidates to cover the remaining 1,540-target shortfall, followed by separate exact replay approval. Production BC requires another explicit approval after the floor passes.\n\n## Frozen hashes\n\n- corpus-v2 manifest file: `{sha(MANIFEST)}`\n- corpus-v2 manifest self-hash: `{manifest['manifest_sha256']}`\n- corpus-v2 review file: `{sha(CORPUS_REVIEW)}`\n- corpus-v2 review self-hash: `{review['review_sha256']}`\n- independent review file: `{sha(INDEPENDENT_REVIEW)}`\n- independent review self-hash: `{independent['review_sha256']}`\n- BC canary execution: `{sha(CANARY_EXECUTION)}`\n- BC canary execution review: `{sha(CANARY_REVIEW)}`\n"""
    DECISION.write_text(decision_text, encoding="utf-8")

    tasks = load(TASKS)
    if not isinstance(tasks, list):
        raise ValueError("task ledger differs")
    upsert(tasks, "task_id", "T-E01-MAJKEL-CORPUS-EXPANSION-027", {
        "schema_version": 1,
        "record_id": "task-e01-majkel-corpus-expansion-027",
        "source_path": "reports/tasks/current.json",
        "task_id": "T-E01-MAJKEL-CORPUS-EXPANSION-027",
        "title": "Review exact Majkel corpus expansion and finalize corpus v2",
        "phase": "E01-A",
        "priority": 15,
        "status": "SUCCEEDED",
        "created_at_utc": "2026-08-04T14:45:26Z",
        "completed_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "request": str(EXPANSION_REQUEST.relative_to(ROOT)),
        "approved_prior_request_sha256": APPROVED_EXPANSION_SHA256,
        "consumed_request_sha256": sha(EXPANSION_REQUEST),
        "authorization_consumed": True,
        "new_files_read": 269,
        "new_bytes_read": 1_030_207_171,
        "qualified_new_files": 269,
        "rejected_new_files": 0,
        "corpus_v2_episodes": 337,
        "corpus_v2_policy_loss_targets": 23_460,
        "target_floor_shortfall": 1_540,
        "production_training_ready": False,
        "replay_transfer_authorized": False,
        "training_authorized": False,
        "optimizer_steps_authorized": False,
        "model_promotion_authorized": False,
        "submission_authorized": False,
        "completion_evidence": [str(JOB.relative_to(ROOT)), str(RUN.relative_to(ROOT)), str(MANIFEST.relative_to(ROOT)), str(CORPUS_REVIEW.relative_to(ROOT)), str(INDEPENDENT_REVIEW.relative_to(ROOT))],
    })
    upsert(tasks, "task_id", "T-E01-BC-ENGINEERING-CANARY-025", {
        "schema_version": 1,
        "record_id": "task-e01-bc-engineering-canary-025",
        "source_path": "reports/tasks/current.json",
        "task_id": "T-E01-BC-ENGINEERING-CANARY-025",
        "title": "Execute bounded BC engineering canary",
        "phase": "E01-BC",
        "priority": 14,
        "status": "SUCCEEDED",
        "created_at_utc": "2026-08-04T10:40:05Z",
        "completed_at_utc": "2026-08-04T15:44:42Z",
        "updated_at_utc": CREATED_AT,
        "request": str(CANARY_REQUEST.relative_to(ROOT)),
        "consumed_request_sha256": sha(CANARY_REQUEST),
        "authorization_consumed": True,
        "failed_attempt_optimizer_steps": 10,
        "recovery_optimizer_steps": 54,
        "cumulative_optimizer_steps": 64,
        "checkpoint_step": 32,
        "checkpoint_payload_sha256": canary_execution["resume"]["payload_sha256"],
        "deterministic_resume_passed": True,
        "production_checkpoint_eligible": False,
        "policy_competence_claimed": False,
        "production_training_authorized": False,
        "optimizer_steps_authorized": False,
        "model_promotion_authorized": False,
        "submission_authorized": False,
        "completion_evidence": [str(CANARY_EXECUTION.relative_to(ROOT)), str(CANARY_REVIEW.relative_to(ROOT))],
    })
    upsert(tasks, "task_id", "T-E01-CORPUS-TARGET-SHORTFALL-028", {
        "schema_version": 1,
        "record_id": "task-e01-corpus-target-shortfall-028",
        "source_path": "reports/tasks/current.json",
        "task_id": "T-E01-CORPUS-TARGET-SHORTFALL-028",
        "title": "Resolve the remaining 1540 policy-target corpus floor shortfall",
        "phase": "E01-A",
        "priority": 16,
        "status": "BLOCKED_SOURCE_SELECTION",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "depends_on": ["DEC-028", "T-E01-MAJKEL-CORPUS-EXPANSION-027"],
        "current_episodes": 337,
        "minimum_episodes": 200,
        "current_policy_loss_targets": 23_460,
        "minimum_policy_loss_targets": 25_000,
        "target_floor_shortfall": 1_540,
        "done_when": "Version-pinned candidates are body-qualified and corpus v3 contains at least 25000 policy-loss targets with no leakage or semantic failures.",
        "replay_transfer_authorized": False,
        "training_authorized": False,
        "optimizer_steps_authorized": False,
        "submission_authorized": False,
    })
    write_json(TASKS, tasks)

    decisions = load(DECISIONS)
    if not isinstance(decisions, list):
        raise ValueError("decision ledger differs")
    upsert(decisions, "decision_id", "DEC-028", {
        "schema_version": 1,
        "record_id": "decision-dec-028",
        "source_path": "reports/decisions/current.json",
        "decision_id": "DEC-028",
        "title": "Accept corpus v2 and BC canary while retaining production target floor",
        "status": "ACCEPTED_CORPUS_V2_CANARY_PASS_PRODUCTION_TRAINING_BLOCKED",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "decision_path": str(DECISION.relative_to(ROOT)),
        "decision_sha256": sha(DECISION),
        "corpus_v2_manifest_sha256": sha(MANIFEST),
        "corpus_v2_manifest_self_hash": manifest["manifest_sha256"],
        "corpus_v2_review_sha256": sha(CORPUS_REVIEW),
        "corpus_v2_review_self_hash": review["review_sha256"],
        "independent_review_sha256": sha(INDEPENDENT_REVIEW),
        "independent_review_self_hash": independent["review_sha256"],
        "corpus_v2_episodes": 337,
        "corpus_v2_policy_loss_targets": 23_460,
        "target_floor_shortfall": 1_540,
        "bc_canary_optimizer_steps": 64,
        "bc_canary_passed": True,
        "production_training_authorized": False,
        "replay_transfer_authorized": False,
        "model_promotion_authorized": False,
        "submission_authorized": False,
    })
    write_json(DECISIONS, decisions)

    gate = load(GATE)
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-028_CORPUS_V2_337_EPISODES_23460_TARGETS_BC_CANARY_PASS_PRODUCTION_TRAINING_BLOCKED"
    gate["authorization"] = "CORPUS_V2_FROZEN_CANARY_CONSUMED_NO_FURTHER_TRANSFER_OR_TRAINING_AUTHORIZED"
    gate["approved_next_action"] = "Prepare the smallest version-pinned metadata-only candidate request expected to cover the remaining 1540 policy-loss targets. Do not read replay bodies or start production BC until separately approved."
    gate["blockers"] = [
        "Corpus v2 passes the 200-episode floor with 337 unique episodes but has 23460 policy-loss targets, leaving a 1540-target shortfall against the frozen 25000 floor.",
        "The 64-step BC engineering canary passed and is consumed, but its checkpoint is explicitly non-promotable and establishes no policy competence.",
        "Production recurrent BC, GPU/TPU use, model promotion and submission remain separately unauthorized.",
    ]
    gate["updated_at_utc"] = CREATED_AT
    checks = gate.setdefault("technical_checks", [])
    for name, evidence, status in (
        ("DEC-027 exact Majkel 269-file private Kaggle CPU review", str(INDEPENDENT_REVIEW.relative_to(ROOT)), "PASS"),
        ("qualified-only corpus v2 episode floor", str(CORPUS_REVIEW.relative_to(ROOT)), "PASS"),
        ("qualified-only corpus v2 25000-target floor", str(CORPUS_REVIEW.relative_to(ROOT)), "BLOCKED"),
        ("bounded recurrent BC engineering canary", str(CANARY_REVIEW.relative_to(ROOT)), "PASS"),
    ):
        positions = [i for i, item in enumerate(checks) if item.get("name") == name]
        record = {"name": name, "evidence": evidence, "status": status}
        if positions:
            checks[positions[0]] = record
        else:
            checks.append(record)
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project_replacements = (
        (
            "Last completed milestone: DEC-027 froze Majkel submission 55186239 as the primary teacher, its reviewed Mega Lucario deck as the initial BC deck, the 970,022-parameter architecture, the data-selection universe and the gold execution sequence",
            "Last completed milestone: all 269 remaining Majkel replay bodies passed exact private Kaggle CPU review, corpus v2 was frozen at 337 episodes and 23,460 targets, and the non-promotable 64-step BC engineering canary passed",
        ),
        (
            "Current gate: exact approvals are required for the 64-step BC engineering canary and the 269-file Majkel corpus expansion; these bounded stages may run in parallel",
            "Current gate: corpus v2 and the 64-step engineering canary are complete; production training remains blocked only by the frozen 1,540-target corpus shortfall and separate production-BC approval",
        ),
        (
            "Gold-path status: DEC-027 INITIAL TRAINING CONFIGURATION FROZEN / MAJKEL PRIMARY SOURCE LOCKED / 269-FILE DATA REVIEW READY UNAUTHORIZED / BC CANARY READY UNAUTHORIZED / PRODUCTION TRAINING BLOCKED / SUBMISSION BLOCKED",
            "Gold-path status: DEC-028 CORPUS V2 337 EPISODES / 23,460 TARGETS / 1,540 TARGET SHORTFALL / BC CANARY 64-STEP PASS NON-PROMOTABLE / TRAINING BLOCKED / SUBMISSION BLOCKED",
        ),
        (
            "Next review required before: the 269-file replay transfer and corpus-v2 review, the 64 BC optimizer steps, production BC, GPU/TPU use, model promotion, final D1 deck freeze, submission, commit or push",
            "Next review required before: any additional replay or agent-log transfer, label materialization, production optimizer-backed run, GPU/TPU use, model promotion, final D1 deck freeze, submission, commit or push",
        ),
    )
    for old, new in project_replacements:
        if old in project:
            project = replace_once(project, old, new, "project status")
        elif new not in project:
            raise ValueError("project status wording differs")
    marker = "## Active Experiments And Jobs\n"
    insertion = "\nCorpus v2 evidence is complete: all 269 newly authorized Majkel files qualified with zero rejects at the exact 1,030,207,171-byte cap. The combined corpus contains 337 unique episodes, 23,460 policy-loss targets and 1,598 forced recurrent calls; the episode floor passes and the target floor remains 1,540 short. The 64-step local CPU BC engineering canary passed after a fail-closed 10-step scheduler incident and bounded 54-step recovery; the checkpoint is non-promotable. Production training remains unauthorized.\n"
    if insertion.strip() not in project:
        project = replace_once(project, marker, marker + insertion, "project active insertion")
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress_section = f"""\n## 2026-08-04 — Corpus v2 and BC engineering canary\n\n- Exact Majkel expansion: 269/269 qualified, 0 rejected, 1,030,207,171 newly read bytes, no replay-body exports.\n- Corpus v2: 337 episodes, 23,460 policy-loss targets, 1,598 forced recurrence calls; target shortfall 1,540.\n- BC canary: 64 cumulative AdamW steps, finite losses/gradients, deterministic step-32 restore, non-promotable.\n- Production training, further replay transfer, accelerators, model promotion and submission remain unauthorized.\n- DEC-028: `{sha(DECISION)}`.\n- Independent review: `{sha(INDEPENDENT_REVIEW)}` / self `{independent['review_sha256']}`.\n"""
    if "## 2026-08-04 — Corpus v2 and BC engineering canary" not in progress:
        progress += progress_section
    PROGRESS.write_text(progress, encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "consumed_expansion_request_sha256": sha(EXPANSION_REQUEST),
        "job_sha256": sha(JOB),
        "independent_review_sha256": sha(INDEPENDENT_REVIEW),
        "independent_review_self_hash": independent["review_sha256"],
        "decision_sha256": sha(DECISION),
        "corpus_v2_episodes": 337,
        "policy_loss_targets": 23_460,
        "target_shortfall": 1_540,
        "canary_optimizer_steps": 64,
        "production_training_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
