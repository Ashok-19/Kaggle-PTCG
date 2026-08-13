from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-05T05:39:27Z"
REQUEST = ROOT / "configs/e01_corpus_v2_target_shortfall_supplement_request_v1.json"
BASE_MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json"
RUNNER = ROOT / "scripts/e01_corpus_target_supplement_review.py"
NOTEBOOK = ROOT / "private/kaggle/e01-corpus-target-supplement-notebook-v1/e01_corpus_target_supplement.py"
LOG_V1 = ROOT / "private/kaggle/e01-corpus-target-supplement-output-v1/kptcg-e01-corpus-target-supplement-v1.log"
LOG_V2 = ROOT / "private/kaggle/e01-corpus-target-supplement-output-v2/kptcg-e01-corpus-target-supplement-v1.log"
DECISION = ROOT / "docs/decisions/DEC-030_E01_MODULE_1324_CONTRACT_DRIFT.md"
PROBE_REQUEST = ROOT / "configs/e01_majkel_module_1324_compatibility_probe_request_v1.json"
PROBE_CONTRACT = ROOT / "reports/artifacts/e01-majkel-module-1324-compatibility-probe-contract-review-v1.json"
JOB = ROOT / "reports/jobs/e01-corpus-target-supplement-v1.json"
FAILURE_REVIEW = ROOT / "reports/artifacts/e01-corpus-target-supplement-failure-review-v1.json"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

REQUEST_SHA256 = "d94c12e424ba26a06a4085c7273faeadd512351828b2b2aa84b85bf014a2f92e"
BASE_MANIFEST_SHA256 = "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f"
RUNNER_SHA256 = "900cc6e705061c8782d07b7d50cc1a8252d48db49be7c39a78243324457881e9"
NOTEBOOK_SHA256 = "41b5df82016f4d7a068b0d4defa15bdd738193d4d1cd7c9eeca852df2994d0c7"
LOG_V1_SHA256 = "4622e9cbb96cfc5a6c6a822744aac6128fec9803b2f4bd12ea364d63d52eb37d"
LOG_V2_SHA256 = "0ebfbfc5acbc37150bd4771d81e9451af39e5b7cf1b7326237ef86798e104acd"
FAILED_EPISODE_ID = 90_037_133
FAILED_FILE = "90037133.json"
FAILED_BYTES = 4_882_237
OBSERVED_MODULE = "1.32.4"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return hashlib.sha256(canonical(payload)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")


def update_prefixed_line(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise ValueError(f"missing line prefix: {prefix}")


def main() -> int:
    expected = {
        REQUEST: REQUEST_SHA256,
        BASE_MANIFEST: BASE_MANIFEST_SHA256,
        RUNNER: RUNNER_SHA256,
        NOTEBOOK: NOTEBOOK_SHA256,
        LOG_V1: LOG_V1_SHA256,
        LOG_V2: LOG_V2_SHA256,
    }
    for path, digest in expected.items():
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"input hash differs: {path}")
    if list(LOG_V1.parent.glob("*.json")) or list(LOG_V2.parent.glob("*.json")):
        raise ValueError("failed notebook unexpectedly produced JSON metadata outputs")
    log_v1 = LOG_V1.read_text(encoding="utf-8")
    log_v2 = LOG_V2.read_text(encoding="utf-8")
    if "ModuleNotFoundError: No module named 'e01_majkel_corpus_expansion_review'" not in log_v1:
        raise ValueError("saved-version-1 failure differs")
    if "ValueError: module version differs: 1.32.4" not in log_v2:
        raise ValueError("saved-version-2 failure differs")

    request = load(REQUEST)
    first = request["files"][0]
    if (
        int(first["review_order"]) != 1
        or int(first["episode_id"]) != FAILED_EPISODE_ID
        or first["file_name"] != FAILED_FILE
        or int(first["declared_bytes"]) != FAILED_BYTES
    ):
        raise ValueError("approved first-file identity differs")
    base = load(BASE_MANIFEST)["qualified_training_corpus"]
    if int(base["episodes"]) != 337 or int(base["policy_loss_targets"]) != 23_460:
        raise ValueError("base corpus-v2 counts differ")

    decision_text = f"""# DEC-030 - Stop corpus supplement on module 1.32.4 contract drift

- Status: accepted fail-closed stop; compatibility probe prepared but unauthorized
- Date: 2026-08-05

## Decision

Treat the exact DEC-029 supplemental authorization as consumed after one approved replay-body read. Saved version 1 failed before any replay-body read because the temporary runner import path was incomplete. Saved version 2 verified the frozen dataset inventory and manifest, read only review-order-1 file `{FAILED_FILE}` ({FAILED_BYTES} bytes), observed module `{OBSERVED_MODULE}`, and stopped before action/deck qualification because the approved module set was `1.32.2` and `1.32.3`.

Corpus v2 remains unchanged at 337 episodes and 23,460 policy-loss targets. No corpus-v3 file, replay-body export, agent log, training label, optimizer step, model mutation, promotion, submission, commit or push was produced.

## Next boundary

Prepare exactly one unauthorized compatibility probe for `{FAILED_FILE}`. It may re-read only that body on private Kaggle CPU to evaluate module `{OBSERVED_MODULE}` against the existing Mega Lucario deck and full action contract. It must not promote any corpus record or continue the 48-file supplement. A new explicit approval binding the probe request SHA-256 is required.
"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")

    authorization = {
        "agent_logs": False,
        "corpus_promotion": False,
        "external_compute_private_kaggle_cpu": False,
        "git_commit": False,
        "git_push": False,
        "gpu": False,
        "label_materialization": False,
        "model_mutation": False,
        "model_promotion": False,
        "optimizer_steps": False,
        "raw_exports": False,
        "replay_body_exports": False,
        "replay_body_reads_exact_named_files": False,
        "submission": False,
        "tpu": False,
        "training": False,
    }
    requested_authorization = dict(authorization)
    requested_authorization["external_compute_private_kaggle_cpu"] = True
    requested_authorization["replay_body_reads_exact_named_files"] = True
    probe_request = {
        "schema_version": 1,
        "source_path": str(PROBE_REQUEST.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "decision_id": "DEC-030",
        "decision_path": str(DECISION.relative_to(ROOT)),
        "decision_sha256": sha(DECISION),
        "status": "READY_UNAUTHORIZED",
        "authorized": False,
        "authorization_consumed": False,
        "authorization": authorization,
        "requested_authorization": requested_authorization,
        "authorization_scope": "UNAUTHORIZED_EXACT_ONE_FILE_PRIVATE_KAGGLE_CPU_MODULE_1324_COMPATIBILITY_REVIEW_ONLY_NO_CORPUS_PROMOTION",
        "compute": {
            "platform": "private-kaggle-cpu",
            "internet": False,
            "gpu": False,
            "tpu": False,
            "cpu_threads_maximum": 4,
            "wall_seconds_maximum": 1800,
            "notebook_slug": "kptcg-e01-majkel-module-1324-compatibility-v1",
        },
        "source": request["source"],
        "teacher": request["teacher"],
        "files": [first],
        "maximum_files": 1,
        "maximum_declared_bytes": FAILED_BYTES,
        "review_contract": {
            "observed_module_version": OBSERVED_MODULE,
            "accepted_for_probe_only": [OBSERVED_MODULE],
            "body_checks": request["review_contract"]["body_checks"],
            "corpus_promotion": False,
            "supplement_continuation": False,
        },
        "output_contract": {
            "metadata_files": [
                "e01-majkel-module-1324-compatibility-probe-review-v1.json",
                "e01-majkel-module-1324-compatibility-probe-output-manifest-v1.json",
            ],
            "raw_replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
        },
        "fail_closed_if": [
            "request, source, teacher, filename or declared bytes differ",
            "module version is not exactly 1.32.4",
            "deck, current-card construction, terminal, reward or action alignment fails",
            "any corpus promotion, label, optimizer, training, accelerator, submission, commit or push is attempted",
        ],
    }
    write_json(PROBE_REQUEST, probe_request)

    probe_contract = {
        "schema_version": 1,
        "record_id": "e01-majkel-module-1324-compatibility-probe-contract-review-v1",
        "source_path": str(PROBE_CONTRACT.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "PASS_READY_UNAUTHORIZED",
        "decision": "ACCEPT_SMALLEST_EXACT_ONE_FILE_MODULE_1324_COMPATIBILITY_PROBE_READY_UNAUTHORIZED",
        "reviewed_decision": "DEC-030",
        "inputs": {
            "decision": {"path": str(DECISION.relative_to(ROOT)), "sha256": sha(DECISION)},
            "failed_request": {"path": str(REQUEST.relative_to(ROOT)), "sha256": REQUEST_SHA256},
            "probe_request": {"path": str(PROBE_REQUEST.relative_to(ROOT)), "sha256": sha(PROBE_REQUEST)},
            "base_manifest": {"path": str(BASE_MANIFEST.relative_to(ROOT)), "sha256": BASE_MANIFEST_SHA256},
        },
        "qualification": {
            "exact_files": 1,
            "exact_bytes": FAILED_BYTES,
            "same_failed_episode_only": True,
            "observed_module_version": OBSERVED_MODULE,
            "corpus_promotion": False,
            "replay_bodies_read_during_preparation": 0,
            "optimizer_steps": 0,
            "training": False,
        },
        "authorization": authorization,
        "review_sha256": None,
    }
    probe_contract["review_sha256"] = self_hash(probe_contract, "review_sha256")
    write_json(PROBE_CONTRACT, probe_contract)

    job = {
        "schema_version": 1,
        "record_id": "job-e01-corpus-target-supplement-v1",
        "source_path": str(JOB.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "FAILED_CLOSED_MODULE_VERSION_DRIFT",
        "decision": "STOP_EXACT_SUPPLEMENT_AFTER_FIRST_APPROVED_BODY_REVEALS_UNAPPROVED_MODULE_1324",
        "cost_usd": 0.0,
        "inputs": {
            "approved_request": {"path": str(REQUEST.relative_to(ROOT)), "sha256": REQUEST_SHA256},
            "base_manifest": {"path": str(BASE_MANIFEST.relative_to(ROOT)), "sha256": BASE_MANIFEST_SHA256},
            "daily_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04/1",
            "dataset_id": 11_506_836,
            "dataset_inventory_sha256": "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77",
            "dataset_manifest_sha256": "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1",
        },
        "notebook": {
            "owner": "ashok205",
            "slug": "kptcg-e01-corpus-target-supplement-v1",
            "private": True,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "source_code_sha256_saved_version_2": NOTEBOOK_SHA256,
            "runner_sha256_saved_version_2": RUNNER_SHA256,
            "saved_versions": [
                {"version": 1, "status": "ERROR_IMPORT_PATH", "replay_bodies_read": 0, "log_sha256": LOG_V1_SHA256},
                {"version": 2, "status": "ERROR_MODULE_VERSION_DRIFT", "replay_bodies_read": 1, "replay_body_bytes_read": FAILED_BYTES, "log_sha256": LOG_V2_SHA256},
            ],
        },
        "execution": {
            "authorization_consumed": True,
            "named_replay_bodies_read": 1,
            "replay_body_bytes_read": FAILED_BYTES,
            "failed_review_order": 1,
            "failed_episode_id": FAILED_EPISODE_ID,
            "failed_file_name": FAILED_FILE,
            "expected_module_versions": ["1.32.2", "1.32.3"],
            "observed_module_version": OBSERVED_MODULE,
            "failure_stage": "MODULE_VERSION_CHECK_BEFORE_DECK_AND_ACTION_QUALIFICATION",
            "additional_replay_bodies_read": 0,
            "replay_body_outputs": 0,
            "agent_logs_read": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
        },
        "outputs": {
            "expected_metadata_files": request["output_contract"]["metadata_files"],
            "actual_metadata_files": 0,
            "corpus_v3_finalized": False,
            "corpus_v2_unchanged": True,
        },
        "job_sha256": None,
    }
    job["job_sha256"] = self_hash(job, "job_sha256")
    write_json(JOB, job)

    failure_review = {
        "schema_version": 1,
        "record_id": "e01-corpus-target-supplement-failure-review-v1",
        "source_path": str(FAILURE_REVIEW.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "PASS_FAILED_CLOSED",
        "decision": "ACCEPT_STOP_AND_RETAIN_CORPUS_V2_PREPARE_ONE_FILE_COMPATIBILITY_PROBE_UNAUTHORIZED",
        "reviewed_decision": "DEC-030",
        "inputs": {
            "job": {"path": str(JOB.relative_to(ROOT)), "sha256": sha(JOB), "self_hash": job["job_sha256"]},
            "decision": {"path": str(DECISION.relative_to(ROOT)), "sha256": sha(DECISION)},
            "request": {"path": str(REQUEST.relative_to(ROOT)), "sha256": REQUEST_SHA256},
            "base_manifest": {"path": str(BASE_MANIFEST.relative_to(ROOT)), "sha256": BASE_MANIFEST_SHA256},
            "saved_version_1_log": {"path": str(LOG_V1.relative_to(ROOT)), "sha256": LOG_V1_SHA256},
            "saved_version_2_log": {"path": str(LOG_V2.relative_to(ROOT)), "sha256": LOG_V2_SHA256},
            "probe_request": {"path": str(PROBE_REQUEST.relative_to(ROOT)), "sha256": sha(PROBE_REQUEST)},
            "probe_contract": {"path": str(PROBE_CONTRACT.relative_to(ROOT)), "sha256": sha(PROBE_CONTRACT), "self_hash": probe_contract["review_sha256"]},
        },
        "recalculation": {
            "saved_version_1_replay_bodies_read": 0,
            "saved_version_2_replay_bodies_read": 1,
            "saved_version_2_replay_body_bytes_read": FAILED_BYTES,
            "first_approved_file_identity_matches": True,
            "module_contract_drift": {"expected": ["1.32.2", "1.32.3"], "observed": OBSERVED_MODULE},
            "metadata_outputs_created": 0,
            "corpus_v3_finalized": False,
            "corpus_v2_episodes": 337,
            "corpus_v2_policy_loss_targets": 23_460,
            "target_floor_shortfall": 1_540,
            "optimizer_steps": 0,
            "training": False,
            "submission": False,
        },
        "authorization": {
            "failed_request_authorization_consumed": True,
            "additional_replay_reads": False,
            "compatibility_probe_authorized": False,
            "corpus_promotion": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "gpu": False,
            "tpu": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "review_sha256": None,
    }
    failure_review["review_sha256"] = self_hash(failure_review, "review_sha256")
    write_json(FAILURE_REVIEW, failure_review)

    decisions = load(DECISIONS)
    decisions = [row for row in decisions if row.get("decision_id") != "DEC-030"]
    decisions.append({
        "schema_version": 1,
        "record_id": "decision-dec-030",
        "decision_id": "DEC-030",
        "source_path": str(DECISION.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "decision-sidecar",
        "title": "Stop supplement on module 1.32.4 drift",
        "status": "ACCEPTED_FAIL_CLOSED_PROBE_READY_UNAUTHORIZED",
        "decision": "Consume the failed DEC-029 execution after one approved body read, retain corpus v2, and prepare only the exact one-file module-1.32.4 compatibility probe without authorization.",
        "rationale": "The first selected August 4 Majkel replay is module 1.32.4, outside the approved 1.32.2/1.32.3 contract, so continuing would violate the user's fail-closed boundary.",
        "request_path": str(PROBE_REQUEST.relative_to(ROOT)),
        "request_sha256": sha(PROBE_REQUEST),
        "review_path": str(FAILURE_REVIEW.relative_to(ROOT)),
        "review_sha256": sha(FAILURE_REVIEW),
        "review_self_hash": failure_review["review_sha256"],
        "revisit_trigger": "The exact one-file compatibility request is explicitly approved or rejected.",
    })
    write_json(DECISIONS, decisions)

    tasks = load(TASKS)
    task = next(row for row in tasks if row.get("task_id") == "T-E01-CORPUS-TARGET-SHORTFALL-028")
    task.update({
        "status": "BLOCKED_CONTRACT_DRIFT",
        "blocker": "The consumed DEC-029 run stopped after review-order-1 replay 90037133.json exposed module 1.32.4, outside the approved 1.32.2/1.32.3 set. Corpus v2 remains 1540 targets short. The exact one-file compatibility probe is ready but unauthorized.",
        "authorization_consumed": True,
        "consumed_request_sha256": REQUEST_SHA256,
        "request_ready": False,
        "replay_transfer_authorized": False,
        "replay_bodies_read": 1,
        "replay_body_bytes_read": FAILED_BYTES,
        "additional_replay_bodies_read": 0,
        "failed_episode_id": FAILED_EPISODE_ID,
        "failed_file_name": FAILED_FILE,
        "expected_module_versions": ["1.32.2", "1.32.3"],
        "observed_module_version": OBSERVED_MODULE,
        "corpus_v3_finalized": False,
        "supplement_job": str(JOB.relative_to(ROOT)),
        "supplement_job_sha256": sha(JOB),
        "supplement_failure_review": str(FAILURE_REVIEW.relative_to(ROOT)),
        "supplement_failure_review_sha256": sha(FAILURE_REVIEW),
        "supplement_failure_review_self_hash": failure_review["review_sha256"],
        "compatibility_probe_request": str(PROBE_REQUEST.relative_to(ROOT)),
        "compatibility_probe_request_sha256": sha(PROBE_REQUEST),
        "compatibility_probe_request_ready": True,
        "compatibility_probe_request_authorized": False,
        "compatibility_probe_contract_review": str(PROBE_CONTRACT.relative_to(ROOT)),
        "compatibility_probe_contract_review_sha256": sha(PROBE_CONTRACT),
        "compatibility_probe_contract_review_self_hash": probe_contract["review_sha256"],
        "training_authorized": False,
        "optimizer_steps_authorized": False,
        "submission_authorized": False,
        "updated_at_utc": CREATED_AT,
    })
    write_json(TASKS, tasks)

    gate = load(GATE)
    gate["decision"] = "DEC-030_MODULE_1324_CONTRACT_DRIFT_FAIL_CLOSED"
    gate["authorization"] = "NO_FURTHER_REPLAY_READ_OR_TRAINING_AUTHORIZED_ONE_FILE_COMPATIBILITY_PROBE_READY_UNAUTHORIZED"
    gate["approved_next_action"] = f"Request separate exact approval for {PROBE_REQUEST.relative_to(ROOT)} at SHA-256 {sha(PROBE_REQUEST)}. If approved, re-read only {FAILED_FILE} ({FAILED_BYTES} bytes) on private Kaggle CPU, review module 1.32.4 compatibility, emit metadata only, and stop without corpus promotion or supplement continuation."
    gate["blockers"] = [
        "Corpus v2 remains at 337 episodes and 23460 policy-loss targets, 1540 below the frozen floor.",
        "The consumed DEC-029 run failed closed after one approved body exposed module 1.32.4 outside the approved module contract.",
        "The exact one-file module-1.32.4 compatibility probe is READY_UNAUTHORIZED; further supplement reads and all training remain blocked.",
    ]
    checks = [row for row in gate.get("technical_checks", []) if row.get("name") != "DEC-030 module 1.32.4 compatibility gate"]
    checks.append({"evidence": str(FAILURE_REVIEW.relative_to(ROOT)), "name": "DEC-030 module 1.32.4 compatibility gate", "status": "BLOCKED"})
    gate["technical_checks"] = checks
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = update_prefixed_line(project, "Last completed milestone:", "Last completed milestone: DEC-030 recorded the fail-closed module-1.32.4 drift after one approved replay-body read; corpus v2 remains unchanged")
    project = update_prefixed_line(project, "Current gate:", "Current gate: the exact one-file module-1.32.4 compatibility probe is READY_UNAUTHORIZED; no further replay read or training is authorized")
    project = update_prefixed_line(project, "Gold-path status:", "Gold-path status: DEC-030 FAIL-CLOSED MODULE 1.32.4 DRIFT / 1 BODY 4,882,237 BYTES READ / CORPUS V2 23,460 TARGETS / ONE-FILE COMPATIBILITY PROBE READY_UNAUTHORIZED / TRAINING BLOCKED")
    section = f"""
### DEC-030 - Stop supplement on module 1.32.4 drift

- Saved version 1 failed before replay reads on an import-path defect.
- Saved version 2 verified source identity, read only `{FAILED_FILE}` at {FAILED_BYTES} bytes, observed module `{OBSERVED_MODULE}`, and failed closed before deck/action qualification.
- Corpus v2 remains 337 episodes and 23,460 targets; corpus v3 does not exist.
- Exact compatibility request `{PROBE_REQUEST.relative_to(ROOT)}` SHA-256 `{sha(PROBE_REQUEST)}` is READY_UNAUTHORIZED and permits no corpus promotion or training.
"""
    if "### DEC-030 - Stop supplement on module 1.32.4 drift" not in project:
        project = project.replace("\n## Immediate Next Actions\n", section + "\n## Immediate Next Actions\n", 1)
    start = project.index("## Immediate Next Actions\n")
    end_marker = "\n<!-- E01_SOURCE_WAIT_V2:START -->"
    end = project.index(end_marker, start)
    actions = f"""## Immediate Next Actions

1. Obtain separate exact approval for `{PROBE_REQUEST.relative_to(ROOT)}` at SHA-256 `{sha(PROBE_REQUEST)}`.
2. If approved, re-read only `{FAILED_FILE}` on private Kaggle CPU, evaluate module `{OBSERVED_MODULE}` compatibility, emit two metadata files and stop without corpus promotion.
3. Only after an independently reviewed compatibility PASS may a new supplemental corpus request be prepared; production BC remains separately approval-gated.
"""
    project = project[:start] + actions + project[end:]
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress = update_prefixed_line(progress, "Current gate:", "Current gate: **DEC-030 stopped the approved supplement on module 1.32.4 drift; exact one-file compatibility probe requires separate approval**")
    progress = update_prefixed_line(progress, "Gold-path status:", "Gold-path status: **ONE APPROVED BODY / 4,882,237 BYTES READ; MODULE 1.32.4 DRIFT; CORPUS V2 UNCHANGED AT 23,460 TARGETS; TRAINING BLOCKED**")
    progress = update_prefixed_line(progress, "Latest completed milestone:", "Latest completed milestone: **fail-closed supplement execution recorded with zero corpus-v3 outputs and zero training**")
    progress_section = f"""
## 2026-08-05 — Module 1.32.4 supplement stop

- Saved version 1 failed before replay-body access because of a temporary import path.
- Saved version 2 read exactly review-order-1 `{FAILED_FILE}` ({FAILED_BYTES} bytes) and stopped on module `{OBSERVED_MODULE}`, outside the approved `1.32.2`/`1.32.3` set.
- Metadata outputs: 0. Corpus v3: not finalized. Corpus v2 remains 337 episodes / 23,460 targets.
- Compatibility probe request: `{PROBE_REQUEST.relative_to(ROOT)}`, SHA-256 `{sha(PROBE_REQUEST)}`, READY_UNAUTHORIZED.
- No further replay reads, labels, optimizer steps, training, accelerators, promotion, submission, commit or push are authorized.
"""
    if "## 2026-08-05 — Module 1.32.4 supplement stop" not in progress:
        progress += progress_section
    PROGRESS.write_text(progress, encoding="utf-8")

    print(json.dumps({
        "status": "PASS_FAILED_CLOSED",
        "failed_request_sha256": REQUEST_SHA256,
        "replay_bodies_read": 1,
        "replay_body_bytes_read": FAILED_BYTES,
        "observed_module_version": OBSERVED_MODULE,
        "corpus_v3_finalized": False,
        "corpus_v2_policy_loss_targets": 23_460,
        "target_shortfall": 1_540,
        "job_sha256": sha(JOB),
        "job_self_hash": job["job_sha256"],
        "failure_review_sha256": sha(FAILURE_REVIEW),
        "failure_review_self_hash": failure_review["review_sha256"],
        "compatibility_probe_request": str(PROBE_REQUEST.relative_to(ROOT)),
        "compatibility_probe_request_sha256": sha(PROBE_REQUEST),
        "compatibility_probe_contract_sha256": sha(PROBE_CONTRACT),
        "compatibility_probe_contract_self_hash": probe_contract["review_sha256"],
        "training_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
