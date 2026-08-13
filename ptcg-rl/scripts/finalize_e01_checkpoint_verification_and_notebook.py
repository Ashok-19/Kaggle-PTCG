from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-06T14:52:03Z"
DECISION_ID = "DEC-041"
TASK_ID = "T-E01-SOURCE-BUNDLE-V2-CHECKPOINT-DIRECTORY-VERIFICATION-041"

REQUEST = ROOT / "configs/e01_production_recurrent_bc_notebook_request_v1.json"
VERIFY_REVIEW = ROOT / "reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v2.json"
NOTEBOOK_REVIEW = ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v1.json"
DECISION = ROOT / "docs/decisions/DEC-041_E01_SOURCE_BUNDLE_V2_ACCEPTED_AND_NOTEBOOK_WRAPPER_PREPARED.md"
WRAPPER = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v1.py"
BUILDER = ROOT / "scripts/kaggle/build_e01_production_recurrent_bc_notebook.py"
TEST = ROOT / "tests/g3/test_e01_production_bc_notebook.py"
TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"
VERIFIER = ROOT / "scripts/e01_verify_extracted_checkpoint_delivery.py"
RECONSTRUCTION_REPORT = ROOT / "private/g3/e01/checkpoint-directory-verification-v1/checkpoint-reconstruction-report.json"
RECONSTRUCTED = ROOT / "private/g3/e01/checkpoint-directory-verification-v1/reconstructed-g2-policy-checkpoint-v1.zip"
LOCAL_CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

TRAINING_REQUEST_SHA = "297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d"
RUNNER_SHA = "92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413"
IMPLEMENTATION_SHA = "4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde"
VERIFIER_SHA = "bd2ae5820fee1fd39675eb326a22ad206f3ad6796c57a039504d586c62948870"
WRAPPER_SHA = "44dfdc02b0c0f180c2929fa3fca4bb32426a99721d9892f129b7ffdc4bca0ebe"
BUILDER_SHA = "8c8ba2194138d14d139157dfce3c0ecf40f7079c74a92303ff51f0c615fcc026"
TEST_SHA = "b1e25f9b961dab96234fa59674b9aeaea20a1832342229e7da62f9f954cef25f"
CHECKPOINT_SHA = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
CHECKPOINT_BYTES = 5_429_190
SOURCE_INVENTORY_SHA = "2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab"
RETAINED_INVENTORY_SHA = "d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43"

MEMBERS = [
    {
        "path": "private/g2/checkpoint-v1/g2-policy-checkpoint-v1/card-table-v1.json",
        "bytes": 1_056_442,
        "sha256": "5fc3a1cf31dd5f4b1b3542fc1baa91fe2b68b772cb5748f50f0f75c9a74f7714",
    },
    {
        "path": "private/g2/checkpoint-v1/g2-policy-checkpoint-v1/manifest.json",
        "bytes": 26_493,
        "sha256": "1185c97d1fca8cb795e2c5f84f5d0a915cf41fac242aefed888b4e0dd84b267c",
    },
    {
        "path": "private/g2/checkpoint-v1/g2-policy-checkpoint-v1/reference-v1.json",
        "bytes": 24_378,
        "sha256": "cf0fe3bb2e47ff3644f6ea2a8647ca47472e698e1fedd2f14f9156de063bb1c3",
    },
    {
        "path": "private/g2/checkpoint-v1/g2-policy-checkpoint-v1/state-v1.bin",
        "bytes": 4_321_431,
        "sha256": "bb91fa17ea74101cc70e02b6ef85cefe8f90e096478bf63e1cc63384c23f3e5c",
    },
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def upsert(items: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    matches = [index for index, item in enumerate(items) if item.get(key) == value]
    if len(matches) > 1:
        raise ValueError(f"duplicate ledger key {key}={value}")
    if matches:
        items[matches[0]] = record
    else:
        items.append(record)


def replace_prefix(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return "\n".join(lines).rstrip() + "\n"
    raise ValueError(f"missing prefix {prefix}")


def append_section(text: str, heading: str, section: str) -> str:
    marker = heading + "\n"
    if marker in text:
        start = text.index(marker)
        next_heading = text.find("\n## ", start + len(marker))
        if next_heading == -1:
            return text[:start].rstrip() + "\n\n" + section.rstrip() + "\n"
        return text[:start].rstrip() + "\n\n" + section.rstrip() + "\n" + text[next_heading + 1 :]
    return text.rstrip() + "\n\n" + section.rstrip() + "\n"


def main() -> None:
    expected = {
        TRAINING_REQUEST: TRAINING_REQUEST_SHA,
        WRAPPER: WRAPPER_SHA,
        BUILDER: BUILDER_SHA,
        TEST: TEST_SHA,
        VERIFIER: VERIFIER_SHA,
        RECONSTRUCTED: CHECKPOINT_SHA,
        LOCAL_CHECKPOINT: CHECKPOINT_SHA,
    }
    for path, expected_sha in expected.items():
        if sha(path) != expected_sha:
            raise ValueError(f"identity differs: {path}")
    if RECONSTRUCTED.read_bytes() != LOCAL_CHECKPOINT.read_bytes():
        raise ValueError("reconstructed checkpoint is not byte-identical to local checkpoint")
    reconstruction = json.loads(RECONSTRUCTION_REPORT.read_text())
    if reconstruction.get("status") != "PASS_EXACT_PACKAGE_RECONSTRUCTED":
        raise ValueError("checkpoint reconstruction report is not PASS")
    if reconstruction.get("package_bytes") != CHECKPOINT_BYTES or reconstruction.get("package_sha256") != CHECKPOINT_SHA:
        raise ValueError("checkpoint reconstruction report identity differs")

    notebook_request = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-request-v1",
        "source_path": REQUEST.relative_to(ROOT).as_posix(),
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "created_at_utc": CREATED_AT,
        "decision_id": DECISION_ID,
        "purpose": "Create and run exactly one private Kaggle CPU notebook for the frozen E01 production recurrent behavior-cloning request after a separate hash-bound approval.",
        "training_request": {
            "path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "sha256": TRAINING_REQUEST_SHA,
            "runner_sha256": RUNNER_SHA,
            "implementation_sha256": IMPLEMENTATION_SHA,
            "maximum_epochs": 4,
            "maximum_optimizer_steps": 844,
            "maximum_wall_seconds": 14_400,
        },
        "checkpoint_delivery": {
            "dataset_ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs",
            "dataset_id": 11_501_808,
            "dataset_version": 2,
            "dataset_private": True,
            "dataset_status": "READY",
            "dataset_files": 79,
            "dataset_bytes": 7_645_589,
            "dataset_inventory_sha256": SOURCE_INVENTORY_SHA,
            "remote_members": MEMBERS,
            "reconstructed_package_bytes": CHECKPOINT_BYTES,
            "reconstructed_package_sha256": CHECKPOINT_SHA,
            "byte_equal_to_approved_local_checkpoint": True,
        },
        "notebook": {
            "owner": "ashok205",
            "slug": "kptcg-e01-production-recurrent-bc-v1",
            "title": "KPTCG E01 Production Recurrent BC V1",
            "private": True,
            "language": "python",
            "kernel_type": "script",
            "kernel_execution_type": "SaveAndRunAll",
            "internet": False,
            "gpu": False,
            "tpu": False,
            "session_timeout_seconds": 14_400,
            "collision_policy": "FAIL_IF_EXISTS",
            "existing_exact_slug_found_during_preparation": False,
            "data_sources": [
                {"ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs", "dataset_id": 11_501_808, "version": 2, "private": True},
                {"ref": "ashok205/kptcg-e01-production-bc-retained-inputs", "dataset_id": 11_514_316, "version": 1, "private": True},
                {"ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03", "dataset_id": 11_490_894, "version": 1, "private": False},
                {"ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04", "dataset_id": 11_506_836, "version": 1, "private": False},
            ],
        },
        "wrapper": {
            "path": WRAPPER.relative_to(ROOT).as_posix(),
            "sha256": WRAPPER_SHA,
            "builder_path": BUILDER.relative_to(ROOT).as_posix(),
            "builder_sha256": BUILDER_SHA,
            "focused_test_path": TEST.relative_to(ROOT).as_posix(),
            "focused_test_sha256": TEST_SHA,
            "checkpoint_verifier_path": VERIFIER.relative_to(ROOT).as_posix(),
            "checkpoint_verifier_sha256": VERIFIER_SHA,
        },
        "replay_scope": {
            "selected_files": 316,
            "selected_bytes": 1_327_994_902,
            "train_files": 284,
            "validation_files": 32,
            "test_files": 0,
            "policy_loss_targets": 21_964,
            "by_source": {
                "august_3_daily": {"files": 237, "bytes": 901_024_255},
                "august_4_daily": {"files": 21, "bytes": 85_410_902},
                "retained_private": {"files": 58, "bytes": 341_559_745},
            },
        },
        "execution": {
            "platform": "private_kaggle_cpu",
            "optimizer": "AdamW",
            "learning_rate": 0.0001,
            "weight_decay": 0.0,
            "recurrent_sequence_length": 32,
            "seed": 20_260_805,
            "maximum_epochs": 4,
            "maximum_optimizer_steps": 844,
            "maximum_wall_seconds": 14_400,
            "validation_before_training": True,
            "validation_after_each_epoch": True,
            "checkpoint_after_each_epoch": True,
            "test_evaluation": False,
        },
        "output_contract": {
            "required": [
                "execution-report.json",
                "notebook-execution-envelope.json",
                "epoch-1.pt",
                "epoch-2.pt",
                "epoch-3.pt",
                "epoch-4.pt",
            ],
            "download_and_hash_after_completion": True,
            "candidate_is_evaluation_only": True,
            "model_promotion": False,
            "submission": False,
        },
        "requested_authorization_for_later_exact_approval": {
            "notebook_create": True,
            "notebook_save_and_run": True,
            "replay_body_read": True,
            "optimizer_steps": True,
            "training": True,
            "private_kaggle_cpu": True,
            "notebook_output_download": True,
            "agent_logs": False,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "test_replay_read": False,
            "label_materialization": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "authorization": {
            "notebook_create": False,
            "notebook_save_and_run": False,
            "replay_body_read": False,
            "optimizer_steps": False,
            "training": False,
            "private_kaggle_cpu": False,
            "notebook_output_download": False,
            "agent_logs": False,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "test_replay_read": False,
            "label_materialization": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "stop_conditions": [
            "any request, wrapper, builder, runner, implementation, dataset, mount, path, file, byte count or SHA-256 mismatch",
            "notebook slug already exists",
            "GPU or TPU visible",
            "internet enabled",
            "selected replay mismatch or any test replay access",
            "nonfinite loss or gradient",
            "optimizer steps above 844",
            "wall time above 14400 seconds",
            "output or download verification failure",
        ],
    }
    write_json(REQUEST, notebook_request)
    request_sha = sha(REQUEST)

    approval_text = f"""I approve consumption of `configs/e01_production_recurrent_bc_notebook_request_v1.json` at SHA-256 `{request_sha}` and authorize exactly one private Kaggle CPU production recurrent-BC notebook run under the following scope:

* Bind training to `configs/e01_production_recurrent_bc_request_v2.json` at SHA-256 `{TRAINING_REQUEST_SHA}`, runner SHA-256 `{RUNNER_SHA}`, and implementation SHA-256 `{IMPLEMENTATION_SHA}`.
* Bind notebook execution to wrapper `scripts/kaggle/e01_production_recurrent_bc_notebook_v1.py` at SHA-256 `{WRAPPER_SHA}` and deterministic source builder `scripts/kaggle/build_e01_production_recurrent_bc_notebook.py` at SHA-256 `{BUILDER_SHA}`.
* Create exactly one new private Kaggle script notebook `ashok205/kptcg-e01-production-recurrent-bc-v1` titled `KPTCG E01 Production Recurrent BC V1`. Fail closed if that slug already exists. Do not modify or run any other notebook or benchmark task.
* Configure `SaveAndRunAll`, CPU only, internet disabled, GPU disabled, TPU disabled, and a session timeout of exactly `14,400` seconds.
* Attach exactly these dataset sources: `ashok205/kptcg-e01-majkel-corpus-review-inputs` dataset ID `11501808` version `2`; `ashok205/kptcg-e01-production-bc-retained-inputs` dataset ID `11514316` version `1`; `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03` dataset ID `11490894` version `1`; and `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04` dataset ID `11506836` version `1`.
* Accept source-bundle version 2 only through the verified extracted-checkpoint contract: `79` files, `7,645,589` bytes, inventory SHA-256 `{SOURCE_INVENTORY_SHA}`, four exact checkpoint members, and deterministic reconstruction of the `5,429,190`-byte checkpoint at SHA-256 `{CHECKPOINT_SHA}` before training.
* Verify every selected replay before semantic loading. Authorize reading, hashing and parsing exactly `316` train/validation replay bodies totaling `1,327,994,902` bytes: `237` files from the August 3 dataset, `21` files from the August 4 dataset, and `58` files from the retained private dataset.
* Authorize validation and production recurrent behavior cloning for at most `4` epochs and at most `844` optimizer steps using AdamW, learning rate `0.0001`, weight decay `0.0`, sequence length `32`, seed `20260805`, and the existing deterministic 80/20 primary/legacy schedule.
* Authorize construction of the optimizer, recurrent semantic loading, on-the-fly compound-action supervision, gradient updates, validation before training and after each epoch, and one checkpoint after each completed epoch. Do not create a separate persistent label dataset.
* Keep all `46` test episodes sealed. Do not read any test replay body or any agent log. Do not perform held-out test, on-policy, tournament, or submission evaluation under this approval.
* After completion, download the notebook outputs, independently hash and review `execution-report.json`, `notebook-execution-envelope.json`, and all emitted epoch checkpoints, then stop and prepare the separate candidate-evaluation approval.
* Do not promote or publish a model, create or update a Kaggle model or dataset, submit to the competition, or make a Git commit or push.
* Retain `ashok205/new-benchmark-task-b1c52`, `ashok205/new-benchmark-task-daa06`, and `ashok205/new-benchmark-task-4abba` unchanged as incident evidence.
* Fail closed immediately on any authorization, notebook, dataset, version, privacy, mount, path, file, byte count, SHA-256, replay, checkpoint, environment, loss, gradient, optimizer-step, wall-time, output, or download mismatch.
"""
    approval_text_sha = hashlib.sha256((approval_text + "\n").encode()).hexdigest()

    verify_review = {
        "schema_version": 1,
        "record_id": "e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v2",
        "created_at_utc": CREATED_AT,
        "status": "PASS_EXACT_REMOTE_CHECKPOINT_RECONSTRUCTED",
        "approved_request": {
            "path": "configs/e01_source_bundle_v2_checkpoint_directory_verification_request_v1.json",
            "sha256": "443098120fa03dcbaa1d430e3f74505926d2e45fa5ea382856b80422816bba78",
            "consumed": True,
        },
        "dataset": {
            "ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs",
            "dataset_id": 11_501_808,
            "version": 2,
            "private": True,
            "status": "READY",
            "files": 79,
            "bytes": 7_645_589,
            "inventory_sha256": SOURCE_INVENTORY_SHA,
        },
        "remote_members": MEMBERS,
        "remote_files_downloaded": 4,
        "remote_bytes_downloaded": sum(item["bytes"] for item in MEMBERS),
        "reconstruction": {
            "verifier_path": VERIFIER.relative_to(ROOT).as_posix(),
            "verifier_sha256": VERIFIER_SHA,
            "report_path": RECONSTRUCTION_REPORT.relative_to(ROOT).as_posix(),
            "report_sha256": sha(RECONSTRUCTION_REPORT),
            "package_path": RECONSTRUCTED.relative_to(ROOT).as_posix(),
            "package_bytes": CHECKPOINT_BYTES,
            "package_sha256": CHECKPOINT_SHA,
            "byte_equal_to_approved_local_checkpoint": True,
        },
        "source_bundle_version_2_accepted": True,
        "acceptance_method": "verified_extracted_checkpoint_delivery_and_deterministic_reconstruction",
        "retained_incident_objects": [
            "ashok205/new-benchmark-task-b1c52",
            "ashok205/new-benchmark-task-daa06",
            "ashok205/new-benchmark-task-4abba",
        ],
        "boundary": {
            "replay_bodies": 0,
            "agent_logs": 0,
            "labels": 0,
            "optimizer_steps": 0,
            "training": False,
            "evaluation": False,
            "notebook_created_or_run": False,
            "remote_mutations": 0,
            "model_mutation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "review_sha256": "",
    }
    verify_review["review_sha256"] = self_hash(verify_review, "review_sha256")
    write_json(VERIFY_REVIEW, verify_review)

    notebook_review = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-contract-review-v1",
        "created_at_utc": CREATED_AT,
        "status": "PASS_NOTEBOOK_REQUEST_READY_UNAUTHORIZED",
        "notebook_request_path": REQUEST.relative_to(ROOT).as_posix(),
        "notebook_request_sha256": request_sha,
        "training_request_sha256": TRAINING_REQUEST_SHA,
        "wrapper_path": WRAPPER.relative_to(ROOT).as_posix(),
        "wrapper_sha256": WRAPPER_SHA,
        "builder_path": BUILDER.relative_to(ROOT).as_posix(),
        "builder_sha256": BUILDER_SHA,
        "focused_test_path": TEST.relative_to(ROOT).as_posix(),
        "focused_test_sha256": TEST_SHA,
        "checkpoint_verifier_sha256": VERIFIER_SHA,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "approval_text": approval_text,
        "approval_text_sha256": approval_text_sha,
        "authorization": {key: False for key in notebook_request["authorization"]},
        "boundary": {
            "notebook_created_or_run": False,
            "replay_bodies": 0,
            "agent_logs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "review_sha256": "",
    }
    notebook_review["review_sha256"] = self_hash(notebook_review, "review_sha256")
    write_json(NOTEBOOK_REVIEW, notebook_review)

    decision_text = f"""# DEC-041 — Accept source-bundle v2 checkpoint delivery and prepare production BC notebook

- **Status:** ACCEPTED_SOURCE_BUNDLE_VALID_NOTEBOOK_READY_UNAUTHORIZED
- **Created:** {CREATED_AT}
- **Source-bundle dataset:** `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`
- **Checkpoint:** `{CHECKPOINT_SHA}` / `{CHECKPOINT_BYTES}` bytes
- **Notebook request SHA-256:** `{request_sha}`
- **Approval text SHA-256:** `{approval_text_sha}`

## Decision

Accept source-bundle version 2 through exact verification of the four extracted checkpoint members and deterministic byte-for-byte reconstruction of the approved checkpoint ZIP. Prepare one private Kaggle CPU notebook wrapper for production recurrent BC, but do not create or run it without the separate exact approval.

The planned run is capped at four epochs, 844 optimizer steps and 14,400 seconds. It may read only the exact 316 train/validation replay bodies after approval; all 46 test episodes remain sealed.

## Boundaries

- Verification files downloaded: `4` / `{sum(item['bytes'] for item in MEMBERS)}` bytes
- Replay bodies and agent logs read during this step: `0`
- Optimizer steps and training: `0`
- Notebook creation or execution: none
- Model promotion, submission, commit or push: none
- Three benchmark-task incident objects remain unchanged as evidence

## Evidence

- `{VERIFY_REVIEW.relative_to(ROOT).as_posix()}`
- `{NOTEBOOK_REVIEW.relative_to(ROOT).as_posix()}`
- `{REQUEST.relative_to(ROOT).as_posix()}`
- `{WRAPPER.relative_to(ROOT).as_posix()}`
- `{BUILDER.relative_to(ROOT).as_posix()}`
"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")
    decision_sha = sha(DECISION)

    decisions = json.loads(DECISIONS.read_text())
    decision_record = {
        "schema_version": 1,
        "record_id": "decision-dec-041",
        "decision_id": DECISION_ID,
        "title": "Accept source-bundle v2 checkpoint reconstruction and prepare production BC notebook",
        "status": "ACCEPTED_SOURCE_BUNDLE_VALID_NOTEBOOK_READY_UNAUTHORIZED",
        "created_at_utc": CREATED_AT,
        "decision": "Accept source-bundle version 2 through exact checkpoint reconstruction and prepare, but do not run, one private CPU production-BC notebook.",
        "rationale": "All four remote checkpoint members match and reproduce the approved checkpoint byte-for-byte; the wrapper and one-click notebook contract pass focused regression tests.",
        "source_path": DECISION.relative_to(ROOT).as_posix(),
        "source_sha256": decision_sha,
        "verification_review_path": VERIFY_REVIEW.relative_to(ROOT).as_posix(),
        "verification_review_sha256": sha(VERIFY_REVIEW),
        "notebook_request_path": REQUEST.relative_to(ROOT).as_posix(),
        "notebook_request_sha256": request_sha,
        "notebook_review_path": NOTEBOOK_REVIEW.relative_to(ROOT).as_posix(),
        "notebook_review_sha256": sha(NOTEBOOK_REVIEW),
        "approval_text_sha256": approval_text_sha,
        "source_bundle_version_2_accepted": True,
        "notebook_authorized": False,
        "training": False,
        "optimizer_steps": 0,
        "revisit_trigger": "The exact notebook approval is accepted, or any bound request, wrapper, dataset, environment or authorization identity changes.",
    }
    upsert(decisions, "decision_id", DECISION_ID, decision_record)
    write_json(DECISIONS, decisions)

    tasks = json.loads(TASKS.read_text())
    task_record = {
        "schema_version": 1,
        "record_id": "task-e01-source-bundle-v2-checkpoint-directory-verification-041",
        "task_id": TASK_ID,
        "title": "Verify extracted checkpoint and prepare production BC notebook",
        "phase": "E01-B",
        "priority": 20,
        "status": "SUCCEEDED_NOTEBOOK_READY_UNAUTHORIZED",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "completed_at_utc": CREATED_AT,
        "decision_id": DECISION_ID,
        "decision_path": DECISION.relative_to(ROOT).as_posix(),
        "decision_sha256": decision_sha,
        "verification_files_downloaded": 4,
        "verification_bytes_downloaded": sum(item["bytes"] for item in MEMBERS),
        "source_bundle_version_2_valid": True,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "notebook_request": REQUEST.relative_to(ROOT).as_posix(),
        "notebook_request_sha256": request_sha,
        "approval_text_sha256": approval_text_sha,
        "notebook_created_or_run": False,
        "replay_bodies": 0,
        "agent_logs": 0,
        "optimizer_steps": 0,
        "training": False,
        "blocker": "One exact notebook/training approval is required before creating and running the private CPU notebook.",
        "done_when": "The notebook request is exactly approved, run once, and its outputs are downloaded and independently verified.",
    }
    upsert(tasks, "task_id", TASK_ID, task_record)
    write_json(TASKS, tasks)

    gate = json.loads(GATE.read_text())
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-041_PRODUCTION_BC_NOTEBOOK_READY_UNAUTHORIZED"
    gate["updated_at_utc"] = CREATED_AT
    gate["approved_next_action"] = f"Obtain exact approval for `{REQUEST.relative_to(ROOT).as_posix()}` at SHA-256 `{request_sha}`, then create and run exactly one private CPU notebook and verify outputs."
    gate["authorization"] = "SOURCE_BUNDLE_V2_ACCEPTED_NOTEBOOK_READY_NO_NOTEBOOK_REPLAY_OPTIMIZER_TRAINING_EVALUATION_PROMOTION_OR_SUBMISSION_AUTHORIZED"
    gate["blockers"] = [
        "Source-bundle version 2 is accepted through exact extracted-checkpoint reconstruction.",
        "The production BC notebook wrapper is ready and tested but not authorized.",
        "Training requires one exact approval for 316 train/validation bodies, four epochs and at most 844 optimizer steps.",
        "Test replay reads, candidate evaluation, model promotion and submission remain blocked.",
    ]
    checks = [item for item in gate.get("technical_checks", []) if item.get("name") != "DEC-041 extracted checkpoint verification and production BC notebook wrapper"]
    checks.append({
        "name": "DEC-041 extracted checkpoint verification and production BC notebook wrapper",
        "status": "PASS",
        "evidence": NOTEBOOK_REVIEW.relative_to(ROOT).as_posix(),
    })
    gate["technical_checks"] = checks
    write_json(GATE, gate)

    project = PROJECT.read_text()
    project = replace_prefix(project, "Last updated UTC:", "Last updated UTC: 2026-08-06")
    project = replace_prefix(project, "Last completed milestone:", "Last completed milestone: DEC-041 accepted source-bundle v2 checkpoint reconstruction and prepared the exact production BC notebook")
    project = replace_prefix(project, "Current gate:", f"Current gate: production BC notebook request `{REQUEST.relative_to(ROOT).as_posix()}` at SHA-256 `{request_sha}` is READY_UNAUTHORIZED")
    project = replace_prefix(project, "Gold-path status:", "Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / RETAINED DATASET VALID / SOURCE BUNDLE V2 VALID BY CHECKPOINT RECONSTRUCTION / PRODUCTION BC NOTEBOOK READY / TEST SEALED / TRAINING BLOCKED")
    project = replace_prefix(project, "Next review required before:", "Next review required before: creating or running the production BC notebook, any replay-body read, optimizer step, training/evaluation, model promotion, submission, commit, or push")
    project_section = f"""## DEC-041 Source Bundle Accepted And Production BC Notebook Ready

The four extracted checkpoint members from private source-bundle dataset ID `11501808`, version `2`, were downloaded and matched their exact hashes. Deterministic reconstruction produced the approved `5,429,190`-byte checkpoint at SHA-256 `{CHECKPOINT_SHA}` and was byte-identical to the local approved checkpoint.

The exact private CPU notebook request is `{request_sha}`. Its wrapper is `{WRAPPER_SHA}`, builder `{BUILDER_SHA}`, and approval text `{approval_text_sha}`. The planned run is 316 train/validation replay bodies, four epochs, and at most 844 optimizer steps. No notebook was created or run and training remains unauthorized.
"""
    project = append_section(project, "## DEC-041 Source Bundle Accepted And Production BC Notebook Ready", project_section)
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text()
    progress_section = f"""## DEC-041 Checkpoint Verification And Notebook Preparation

Source-bundle version 2 is accepted through four-file remote verification and exact deterministic checkpoint reconstruction. Reconstruction SHA-256 is `{CHECKPOINT_SHA}` and the package is byte-identical to the approved local checkpoint.

The one-run private Kaggle CPU production-BC request is `{request_sha}` with approval text SHA-256 `{approval_text_sha}`. Wrapper `{WRAPPER_SHA}` and builder `{BUILDER_SHA}` passed 17 focused/regression tests. No replay body, agent log, optimizer step, training, notebook, model, submission, commit or push occurred during preparation.
"""
    progress = append_section(progress, "## DEC-041 Checkpoint Verification And Notebook Preparation", progress_section)
    PROGRESS.write_text(progress, encoding="utf-8")

    print(json.dumps({
        "status": "PASS_SOURCE_BUNDLE_ACCEPTED_NOTEBOOK_REQUEST_READY_UNAUTHORIZED",
        "verification_review_sha256": sha(VERIFY_REVIEW),
        "verification_review_self_hash": verify_review["review_sha256"],
        "notebook_request_sha256": request_sha,
        "notebook_review_sha256": sha(NOTEBOOK_REVIEW),
        "notebook_review_self_hash": notebook_review["review_sha256"],
        "approval_text_sha256": approval_text_sha,
        "decision_sha256": decision_sha,
        "wrapper_sha256": WRAPPER_SHA,
        "builder_sha256": BUILDER_SHA,
        "replay_bodies": 0,
        "optimizer_steps": 0,
        "training": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
