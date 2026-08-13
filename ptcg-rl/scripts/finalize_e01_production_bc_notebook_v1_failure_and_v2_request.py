from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-06T15:11:18Z"

TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"
NOTEBOOK_REQUEST_V1 = ROOT / "configs/e01_production_recurrent_bc_notebook_request_v1.json"
WRAPPER_V1 = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v1.py"
BUILDER_V1 = ROOT / "scripts/kaggle/build_e01_production_recurrent_bc_notebook.py"
WRAPPER_V2 = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v2.py"
BUILDER_V2 = ROOT / "scripts/kaggle/build_e01_production_recurrent_bc_notebook_v2.py"
TEST_V2 = ROOT / "tests/g3/test_e01_production_bc_notebook_v2.py"
NOTEBOOK_REQUEST_V2 = ROOT / "configs/e01_production_recurrent_bc_notebook_request_v2.json"
INCIDENT = ROOT / "reports/incidents/e01-production-recurrent-bc-notebook-v1-august3-mount-count-v1.json"
EXECUTION_REVIEW = ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-execution-review-v1.json"
CONTRACT_REVIEW_V2 = ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v2.json"
DEC042 = ROOT / "docs/decisions/DEC-042_E01_PRODUCTION_BC_NOTEBOOK_V1_MOUNT_COUNT_MISMATCH.md"
DEC043 = ROOT / "docs/decisions/DEC-043_E01_PRODUCTION_BC_NOTEBOOK_V2_MOUNT_COUNT_REMEDIATION.md"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

TRAINING_REQUEST_SHA = "297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d"
NOTEBOOK_REQUEST_V1_SHA = "6d50e6b70c2a144948342bf8366ea481ee1330744bd96f6b82924500cc735d30"
RUNNER_SHA = "92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413"
IMPLEMENTATION_SHA = "4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde"
WRAPPER_V1_SHA = "44dfdc02b0c0f180c2929fa3fca4bb32426a99721d9892f129b7ffdc4bca0ebe"
BUILDER_V1_SHA = "8c8ba2194138d14d139157dfce3c0ecf40f7079c74a92303ff51f0c615fcc026"
WRAPPER_V2_SHA = "59db2271582b45f886347755ef7e401af1603ac761977ba2d6600e70233bcf52"
BUILDER_V2_SHA = "289d1eaf8de9eaf5d0805bc088045f78c1882556d508883ba834dbf95ca07a17"
TEST_V2_SHA = "d5ceb8b9e0352ed85c3db0c3ea0c3d0cdc941548f0ef976dc87bc7ab286fa11e"
APPROVAL_RECEIPT_SHA = "9285504a6bb6324413daccad6b60d1d58d3801e2d417f17360b091ccfbbfdd1d"
SOURCE_SHA = "566c1624e0d5726d561a91b5ec66d4902f96403b028e65e049f4e9937921c02d"
CHECKPOINT_SHA = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
SOURCE_BUNDLE_INVENTORY_SHA = "2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab"
RETAINED_INVENTORY_SHA = "d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_self_hashed(path: Path, value: dict[str, object], field: str) -> tuple[str, str]:
    payload = dict(value)
    payload[field] = hashlib.sha256(canonical_bytes(value)).hexdigest()
    write_json(path, payload)
    return sha(path), str(payload[field])


def assert_hashes() -> None:
    expected = {
        TRAINING_REQUEST: TRAINING_REQUEST_SHA,
        NOTEBOOK_REQUEST_V1: NOTEBOOK_REQUEST_V1_SHA,
        WRAPPER_V1: WRAPPER_V1_SHA,
        BUILDER_V1: BUILDER_V1_SHA,
        WRAPPER_V2: WRAPPER_V2_SHA,
        BUILDER_V2: BUILDER_V2_SHA,
        TEST_V2: TEST_V2_SHA,
        ROOT / "scripts/e01_production_recurrent_bc_v2.py": RUNNER_SHA,
        ROOT / "src/ptcg_rl/g3/bc_production_v2.py": IMPLEMENTATION_SHA,
    }
    for path, expected_sha in expected.items():
        actual = sha(path)
        if actual != expected_sha:
            raise ValueError(f"hash differs for {path.relative_to(ROOT)}: {actual}")


def replace_prefix(text: str, prefix: str, line: str) -> str:
    lines = text.splitlines()
    for index, existing in enumerate(lines):
        if existing.startswith(prefix):
            lines[index] = line
            return "\n".join(lines).rstrip() + "\n"
    raise ValueError(f"missing prefix: {prefix}")


def append_section(text: str, marker: str, section: str) -> str:
    if marker in text:
        start = text.index(marker)
        following = text.find("\n## ", start + len(marker))
        if following < 0:
            return text[:start].rstrip() + "\n\n" + section.strip() + "\n"
        return text[:start].rstrip() + "\n\n" + section.strip() + "\n\n" + text[following + 1 :].lstrip()
    return text.rstrip() + "\n\n" + section.strip() + "\n"


def main() -> None:
    assert_hashes()

    incident_base: dict[str, object] = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-v1-august3-mount-count-v1",
        "created_at_utc": CREATED_AT,
        "status": "FAILED_CLOSED_AUGUST3_MOUNT_FILE_COUNT_MISMATCH",
        "approved_notebook_request": {
            "path": NOTEBOOK_REQUEST_V1.relative_to(ROOT).as_posix(),
            "sha256": NOTEBOOK_REQUEST_V1_SHA,
        },
        "notebook": {
            "id": 129904937,
            "ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
            "version": 1,
            "private": True,
            "kernel_type": "script",
            "gpu": False,
            "tpu": False,
            "internet": False,
            "status": "ERROR",
            "output_kernel_file_id": 340611521,
            "dataset_sources": [
                "ashok205/kptcg-e01-majkel-corpus-review-inputs",
                "ashok205/kptcg-e01-production-bc-retained-inputs",
                "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03",
                "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04",
            ],
        },
        "failure": {
            "phase": "AUGUST_3_MOUNT_INVENTORY_PREFLIGHT",
            "exception": "NotebookContractError",
            "message": "August 3 daily dataset inventory aggregate differs: 4721 files/21451850075 bytes",
            "expected_files_v1": 4724,
            "actual_mounted_files": 4721,
            "expected_and_actual_bytes": 21451850075,
            "official_file_summary": {
                "files": 4721,
                "json_files": 4720,
                "json_bytes": 21451459378,
                "csv_files": 1,
                "csv_bytes": 390697,
            },
            "root_cause": "The v1 wrapper used a historical API inventory row count of 4724 instead of the current Kaggle notebook-mount file summary of 4721. The total bytes and all selected replay identities were unchanged.",
        },
        "downloaded_outputs": [
            {
                "path": "e01-production-recurrent-bc-bootstrap-v1/e01-production-recurrent-bc-approval-v1.json",
                "bytes": 1306,
                "sha256": APPROVAL_RECEIPT_SHA,
                "matches_local": True,
            },
            {
                "path": "e01-production-recurrent-bc-bootstrap-v1/e01_production_recurrent_bc_notebook_v1.py",
                "bytes": 65227,
                "sha256": WRAPPER_V1_SHA,
                "matches_local": True,
            },
        ],
        "boundary": {
            "notebook_creations": 1,
            "notebook_versions": 1,
            "notebook_retries": 0,
            "replay_bodies_read": 0,
            "replay_bytes_read": 0,
            "agent_logs_read": 0,
            "checkpoint_reconstructed": False,
            "labels_materialized": 0,
            "optimizer_constructed": False,
            "optimizer_steps": 0,
            "training": False,
            "evaluation": False,
            "model_mutation": False,
            "submission": False,
            "dataset_mutations": 0,
            "git_commit": False,
            "git_push": False,
        },
        "retained_incident_evidence": [
            "ashok205/new-benchmark-task-b1c52",
            "ashok205/new-benchmark-task-daa06",
            "ashok205/new-benchmark-task-4abba",
        ],
    }
    incident_sha, incident_self_hash = write_self_hashed(INCIDENT, incident_base, "incident_sha256")

    execution_base: dict[str, object] = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-execution-review-v1",
        "created_at_utc": CREATED_AT,
        "status": "FAILED_CLOSED_PREFLIGHT_NO_REPLAY_OR_TRAINING",
        "approval_consumed": True,
        "notebook_request_sha256": NOTEBOOK_REQUEST_V1_SHA,
        "notebook_source_sha256": SOURCE_SHA,
        "approval_receipt_sha256": APPROVAL_RECEIPT_SHA,
        "wrapper_sha256": WRAPPER_V1_SHA,
        "builder_sha256": BUILDER_V1_SHA,
        "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
        "notebook_id": 129904937,
        "notebook_version": 1,
        "notebook_status": "ERROR",
        "incident_path": INCIDENT.relative_to(ROOT).as_posix(),
        "incident_file_sha256": incident_sha,
        "incident_self_hash": incident_self_hash,
        "result": {
            "failure_phase": "AUGUST_3_MOUNT_INVENTORY_PREFLIGHT",
            "replay_bodies_read": 0,
            "optimizer_steps": 0,
            "training": False,
            "execution_report_emitted": False,
            "notebook_envelope_emitted": False,
            "epoch_checkpoints_emitted": 0,
            "output_files": 2,
        },
        "remediation": {
            "kind": "MOUNT_METADATA_COUNT_ONLY",
            "august_3_files_before": 4724,
            "august_3_files_after": 4721,
            "all_replay_hashes_unchanged": True,
            "all_training_hyperparameters_unchanged": True,
            "new_notebook_slug_required": True,
        },
    }
    execution_sha, execution_self_hash = write_self_hashed(EXECUTION_REVIEW, execution_base, "review_sha256")

    request_v2: dict[str, object] = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-request-v2",
        "decision_id": "DEC-043",
        "created_at_utc": CREATED_AT,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "purpose": "Run the unchanged production recurrent-BC contract in one new private Kaggle CPU notebook after correcting only the August 3 notebook-mount file count from 4724 to 4721.",
        "prior_failed_run": {
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
            "notebook_id": 129904937,
            "version": 1,
            "status": "ERROR",
            "execution_review": EXECUTION_REVIEW.relative_to(ROOT).as_posix(),
            "execution_review_sha256": execution_sha,
            "must_remain_unchanged": True,
        },
        "training_contract": {
            "request_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "request_sha256": TRAINING_REQUEST_SHA,
            "runner_path": "scripts/e01_production_recurrent_bc_v2.py",
            "runner_sha256": RUNNER_SHA,
            "implementation_path": "src/ptcg_rl/g3/bc_production_v2.py",
            "implementation_sha256": IMPLEMENTATION_SHA,
            "selected_replay_files": 316,
            "selected_replay_bytes": 1327994902,
            "test_episodes_sealed": 46,
            "maximum_epochs": 4,
            "maximum_optimizer_steps": 844,
            "maximum_wall_seconds": 14400,
        },
        "notebook": {
            "owner": "ashok205",
            "slug": "kptcg-e01-production-recurrent-bc-v2",
            "title": "KPTCG E01 Production Recurrent BC V2",
            "private": True,
            "language": "python",
            "kernel_type": "script",
            "execution_type": "SaveAndRunAll",
            "cpu_only": True,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "session_timeout_seconds": 14400,
            "fail_if_slug_exists": True,
        },
        "wrapper": {
            "path": WRAPPER_V2.relative_to(ROOT).as_posix(),
            "sha256": WRAPPER_V2_SHA,
            "builder_path": BUILDER_V2.relative_to(ROOT).as_posix(),
            "builder_sha256": BUILDER_V2_SHA,
            "focused_test_path": TEST_V2.relative_to(ROOT).as_posix(),
            "focused_test_sha256": TEST_V2_SHA,
            "approval_kind": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2",
        },
        "dataset_mounts": [
            {
                "ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs",
                "dataset_id": 11501808,
                "version": 2,
                "files": 79,
                "bytes": 7645589,
                "inventory_sha256": SOURCE_BUNDLE_INVENTORY_SHA,
                "private": True,
            },
            {
                "ref": "ashok205/kptcg-e01-production-bc-retained-inputs",
                "dataset_id": 11514316,
                "version": 1,
                "files": 58,
                "bytes": 341559745,
                "inventory_sha256": RETAINED_INVENTORY_SHA,
                "private": True,
            },
            {
                "ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03",
                "dataset_id": 11490894,
                "version": 1,
                "files": 4721,
                "bytes": 21451850075,
                "json_files": 4720,
                "csv_files": 1,
                "private": False,
            },
            {
                "ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04",
                "dataset_id": 11506836,
                "version": 1,
                "files": 4812,
                "bytes": 21457813826,
                "json_files": 4811,
                "csv_files": 1,
                "private": False,
            },
        ],
        "checkpoint_contract": {
            "delivery": "verified_extracted_directory_reconstructed_locally",
            "bytes": 5429190,
            "sha256": CHECKPOINT_SHA,
        },
        "execution": {
            "optimizer": "AdamW",
            "learning_rate": 0.0001,
            "weight_decay": 0.0,
            "recurrent_sequence_length": 32,
            "seed": 20260805,
            "validation_before_training": True,
            "validation_after_each_epoch": True,
            "checkpoint_after_each_epoch": True,
            "test_evaluation": False,
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
        "requested_authorization_for_later_exact_approval": {
            "notebook_create": True,
            "notebook_save_and_run": True,
            "replay_body_read": True,
            "optimizer_steps": True,
            "training": True,
            "private_kaggle_cpu": True,
            "notebook_output_download": True,
        },
        "stop_conditions": [
            "Fail if the exact v2 slug already exists.",
            "Fail on any dataset id, version, mount count, byte count, path, replay hash, checkpoint, wrapper, request, environment, loss, gradient, optimizer-step, wall-time or output mismatch.",
            "Stop after downloading and independently reviewing notebook outputs; do not evaluate, promote or submit a candidate under the run approval.",
        ],
    }
    write_json(NOTEBOOK_REQUEST_V2, request_v2)
    request_v2_sha = sha(NOTEBOOK_REQUEST_V2)

    approval_text = f"""I approve consumption of `configs/e01_production_recurrent_bc_notebook_request_v2.json` at SHA-256 `{request_v2_sha}` and authorize exactly one private Kaggle CPU production recurrent-BC notebook run under the following scope:

* Bind training to `configs/e01_production_recurrent_bc_request_v2.json` at SHA-256 `{TRAINING_REQUEST_SHA}`, runner SHA-256 `{RUNNER_SHA}`, and implementation SHA-256 `{IMPLEMENTATION_SHA}`.
* Bind notebook execution to corrected wrapper `scripts/kaggle/e01_production_recurrent_bc_notebook_v2.py` at SHA-256 `{WRAPPER_V2_SHA}` and deterministic source builder `scripts/kaggle/build_e01_production_recurrent_bc_notebook_v2.py` at SHA-256 `{BUILDER_V2_SHA}`.
* Create exactly one new private Kaggle script notebook `ashok205/kptcg-e01-production-recurrent-bc-v2` titled `KPTCG E01 Production Recurrent BC V2`. Fail closed if that slug already exists. Leave failed notebook `ashok205/kptcg-e01-production-recurrent-bc-v1`, version 1, unchanged and do not rerun it.
* Configure `SaveAndRunAll`, CPU only, internet disabled, GPU disabled, TPU disabled, and a session timeout of exactly `14,400` seconds.
* Attach exactly these dataset sources: `ashok205/kptcg-e01-majkel-corpus-review-inputs` dataset ID `11501808` version `2`; `ashok205/kptcg-e01-production-bc-retained-inputs` dataset ID `11514316` version `1`; `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03` dataset ID `11490894` version `1`; and `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04` dataset ID `11506836` version `1`.
* Require the mounted dataset aggregates to be exactly: source bundle `79` files / `7,645,589` bytes / inventory SHA-256 `{SOURCE_BUNDLE_INVENTORY_SHA}`; retained dataset `58` files / `341,559,745` bytes / inventory SHA-256 `{RETAINED_INVENTORY_SHA}`; August 3 dataset `4,721` files / `21,451,850,075` bytes; and August 4 dataset `4,812` files / `21,457,813,826` bytes.
* Accept source-bundle version 2 only through deterministic reconstruction of the `5,429,190`-byte checkpoint at SHA-256 `{CHECKPOINT_SHA}` before training.
* Verify every selected replay before semantic loading. Authorize reading, hashing and parsing exactly `316` train/validation replay bodies totaling `1,327,994,902` bytes: `237` files from the August 3 dataset, `21` files from the August 4 dataset, and `58` files from the retained private dataset.
* Authorize validation and production recurrent behavior cloning for at most `4` epochs and at most `844` optimizer steps using AdamW, learning rate `0.0001`, weight decay `0.0`, sequence length `32`, seed `20260805`, and the existing deterministic 80/20 primary/legacy schedule.
* Authorize construction of the optimizer, recurrent semantic loading, on-the-fly compound-action supervision, gradient updates, validation before training and after each epoch, and one checkpoint after each completed epoch. Do not create a separate persistent label dataset.
* Keep all `46` test episodes sealed. Do not read any test replay body or any simulation agent log. Do not perform held-out test, on-policy, tournament, or submission evaluation under this approval.
* After completion, download the notebook outputs, independently hash and review `execution-report.json`, `notebook-execution-envelope.json`, and all emitted epoch checkpoints, then stop and prepare the separate candidate-evaluation approval.
* Do not promote or publish a model, create or update a Kaggle model or dataset, submit to the competition, or make a Git commit or push.
* Retain `ashok205/new-benchmark-task-b1c52`, `ashok205/new-benchmark-task-daa06`, and `ashok205/new-benchmark-task-4abba` unchanged as incident evidence.
* Fail closed immediately on any authorization, notebook, dataset, version, privacy, mount, path, file, byte count, SHA-256, replay, checkpoint, environment, loss, gradient, optimizer-step, wall-time, output, or download mismatch.
"""
    approval_text_sha = hashlib.sha256((approval_text + "\n").encode()).hexdigest()

    review_v2_base: dict[str, object] = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-notebook-contract-review-v2",
        "created_at_utc": CREATED_AT,
        "status": "PASS_CORRECTED_NOTEBOOK_REQUEST_READY_UNAUTHORIZED",
        "request_path": NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix(),
        "request_sha256": request_v2_sha,
        "prior_execution_review_path": EXECUTION_REVIEW.relative_to(ROOT).as_posix(),
        "prior_execution_review_sha256": execution_sha,
        "wrapper_path": WRAPPER_V2.relative_to(ROOT).as_posix(),
        "wrapper_sha256": WRAPPER_V2_SHA,
        "builder_path": BUILDER_V2.relative_to(ROOT).as_posix(),
        "builder_sha256": BUILDER_V2_SHA,
        "focused_test_path": TEST_V2.relative_to(ROOT).as_posix(),
        "focused_test_sha256": TEST_V2_SHA,
        "correction": {
            "field": "AUGUST_3_FILES",
            "before": 4724,
            "after": 4721,
            "bytes_unchanged": 21451850075,
            "replay_records_unchanged": 316,
            "replay_hashes_unchanged": True,
            "training_contract_unchanged": True,
        },
        "authorization": {
            "notebook_create": False,
            "notebook_run": False,
            "replay_body_read": False,
            "optimizer_steps": False,
            "training": False,
        },
        "approval_text": approval_text,
        "approval_text_sha256": approval_text_sha,
    }
    contract_review_sha, contract_review_self_hash = write_self_hashed(CONTRACT_REVIEW_V2, review_v2_base, "review_sha256")

    dec042_text = f"""# DEC-042 — Production BC notebook v1 failed on August 3 mount count

- **Status:** ACCEPTED_FAILED_CLOSED
- **Created:** {CREATED_AT}
- **Notebook:** `ashok205/kptcg-e01-production-recurrent-bc-v1`, ID `129904937`, version `1`, private
- **Approved request SHA-256:** `{NOTEBOOK_REQUEST_V1_SHA}`

## Decision

Reject the v1 notebook execution because its preflight expected `4,724` August 3 mount files while Kaggle mounted the officially summarized `4,721` files at the same exact `21,451,850,075` bytes. The failure occurred before selected replay verification, checkpoint reconstruction, optimizer construction, or training.

## Boundary

- Notebook creations/runs: `1`
- Replay bodies/bytes read: `0` / `0`
- Agent logs: `0`
- Optimizer steps: `0`
- Training/evaluation/model/submission: none
- Retry, dataset mutation, commit, push: none

Evidence: `{INCIDENT.relative_to(ROOT).as_posix()}` at file SHA-256 `{incident_sha}` and `{EXECUTION_REVIEW.relative_to(ROOT).as_posix()}` at file SHA-256 `{execution_sha}`.
"""
    DEC042.parent.mkdir(parents=True, exist_ok=True)
    DEC042.write_text(dec042_text, encoding="utf-8")
    dec042_sha = sha(DEC042)

    dec043_text = f"""# DEC-043 — Prepare production BC notebook v2 mount-count remediation

- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED
- **Created:** {CREATED_AT}
- **Corrected notebook request SHA-256:** `{request_v2_sha}`
- **Approval text SHA-256:** `{approval_text_sha}`

## Decision

Prepare, but do not execute, a new private CPU notebook contract at slug `ashok205/kptcg-e01-production-recurrent-bc-v2`. Change only the August 3 mount aggregate from `4,724` to the official mounted summary of `4,721` files. Preserve every replay, checkpoint, dataset version, hyperparameter, four-epoch limit, 844-step cap, test seal, and output-review boundary.

## Boundary

No replay body, agent log, optimizer step, training, notebook retry, remote mutation, model operation, submission, commit, or push is authorized by this decision.

Evidence: `{NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix()}` and `{CONTRACT_REVIEW_V2.relative_to(ROOT).as_posix()}` at file SHA-256 `{contract_review_sha}`, self-hash `{contract_review_self_hash}`.
"""
    DEC043.write_text(dec043_text, encoding="utf-8")
    dec043_sha = sha(DEC043)

    decisions = json.loads(DECISIONS.read_text())
    decisions = [item for item in decisions if item.get("decision_id") not in {"DEC-042", "DEC-043"}]
    decisions.extend([
        {
            "schema_version": 1,
            "record_id": "decision-dec-042",
            "decision_id": "DEC-042",
            "title": "Fail closed on production BC notebook v1 August 3 mount-count mismatch",
            "status": "ACCEPTED_FAILED_CLOSED",
            "created_at_utc": CREATED_AT,
            "decision": "Reject the one approved notebook run because August 3 mounted 4721 files rather than the wrapper's historical 4724 count, before any replay or optimizer activity.",
            "rationale": "The exact total bytes matched and the official file summary confirms 4721 mounted files; fail closed and require a versioned metadata-only wrapper correction.",
            "source_path": DEC042.relative_to(ROOT).as_posix(),
            "source_sha256": dec042_sha,
            "incident_path": INCIDENT.relative_to(ROOT).as_posix(),
            "incident_sha256": incident_sha,
            "execution_review_path": EXECUTION_REVIEW.relative_to(ROOT).as_posix(),
            "execution_review_sha256": execution_sha,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
            "notebook_version": 1,
            "replay_bodies_read": 0,
            "optimizer_steps": 0,
            "training": False,
            "revisit_trigger": "A corrected versioned notebook request is exactly approved.",
        },
        {
            "schema_version": 1,
            "record_id": "decision-dec-043",
            "decision_id": "DEC-043",
            "title": "Prepare corrected production BC notebook v2 request",
            "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
            "created_at_utc": CREATED_AT,
            "decision": "Prepare one new private CPU notebook request with only the August 3 mounted-file count corrected to 4721.",
            "rationale": "The official Kaggle file summary and failed notebook mount agree exactly on 4721 files and 21451850075 bytes; all training identities remain unchanged.",
            "source_path": DEC043.relative_to(ROOT).as_posix(),
            "source_sha256": dec043_sha,
            "notebook_request_path": NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix(),
            "notebook_request_sha256": request_v2_sha,
            "contract_review_path": CONTRACT_REVIEW_V2.relative_to(ROOT).as_posix(),
            "contract_review_sha256": contract_review_sha,
            "approval_text_sha256": approval_text_sha,
            "notebook_authorized": False,
            "optimizer_steps": 0,
            "training": False,
            "revisit_trigger": "The exact v2 notebook approval is accepted, or any bound identity changes.",
        },
    ])
    write_json(DECISIONS, decisions)

    tasks = json.loads(TASKS.read_text())
    tasks = [item for item in tasks if item.get("task_id") not in {
        "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-042",
        "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-REMEDIATION-043",
    }]
    tasks.extend([
        {
            "schema_version": 1,
            "record_id": "task-e01-production-recurrent-bc-notebook-run-042",
            "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-042",
            "title": "Run production recurrent BC notebook v1",
            "phase": "E01-B",
            "priority": 20,
            "status": "FAILED_CLOSED_AUGUST3_MOUNT_COUNT_MISMATCH",
            "created_at_utc": CREATED_AT,
            "updated_at_utc": CREATED_AT,
            "completed_at_utc": CREATED_AT,
            "decision_id": "DEC-042",
            "decision_path": DEC042.relative_to(ROOT).as_posix(),
            "decision_sha256": dec042_sha,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
            "notebook_version": 1,
            "approval_consumed": True,
            "replay_bodies": 0,
            "optimizer_steps": 0,
            "training": False,
            "blocker": "The v1 wrapper used a 4724-file historical inventory count while the notebook mount and official summary contain 4721 files.",
            "done_when": "A corrected v2 request is exactly approved and run once.",
        },
        {
            "schema_version": 1,
            "record_id": "task-e01-production-recurrent-bc-notebook-remediation-043",
            "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-REMEDIATION-043",
            "title": "Prepare corrected production BC notebook v2",
            "phase": "E01-B",
            "priority": 20,
            "status": "SUCCEEDED_RERUN_READY_UNAUTHORIZED",
            "created_at_utc": CREATED_AT,
            "updated_at_utc": CREATED_AT,
            "completed_at_utc": CREATED_AT,
            "decision_id": "DEC-043",
            "decision_path": DEC043.relative_to(ROOT).as_posix(),
            "decision_sha256": dec043_sha,
            "notebook_request": NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix(),
            "notebook_request_sha256": request_v2_sha,
            "approval_text_sha256": approval_text_sha,
            "notebook_authorized": False,
            "replay_bodies": 0,
            "optimizer_steps": 0,
            "training": False,
            "blocker": "Exact v2 notebook approval is required.",
            "done_when": "The exact v2 notebook runs and its outputs are downloaded and independently verified.",
        },
    ])
    write_json(TASKS, tasks)

    gate = json.loads(GATE.read_text())
    gate["updated_at_utc"] = CREATED_AT
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-043_PRODUCTION_BC_NOTEBOOK_V2_READY_UNAUTHORIZED"
    gate["authorization"] = "CORRECTED_NOTEBOOK_V2_READY_NO_NOTEBOOK_REPLAY_OPTIMIZER_TRAINING_EVALUATION_PROMOTION_OR_SUBMISSION_AUTHORIZED"
    gate["approved_next_action"] = f"Obtain exact approval for `{NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix()}` at SHA-256 `{request_v2_sha}`, then create and run exactly one new private CPU notebook v2 and verify outputs."
    gate["blockers"] = [
        "Notebook v1 failed before replay reads because the August 3 mounted-file count is 4721, not 4724.",
        "The corrected v2 wrapper and request pass focused tests but are not authorized.",
        "Training still requires exact approval for 316 train/validation bodies and at most 844 optimizer steps.",
        "Test replay reads, candidate evaluation, model promotion and submission remain blocked.",
    ]
    checks = [item for item in gate.setdefault("technical_checks", []) if item.get("name") not in {
        "DEC-042 production BC notebook v1 execution",
        "DEC-043 corrected production BC notebook v2 contract",
    }]
    checks.extend([
        {"name": "DEC-042 production BC notebook v1 execution", "status": "FAILED_CLOSED", "evidence": EXECUTION_REVIEW.relative_to(ROOT).as_posix()},
        {"name": "DEC-043 corrected production BC notebook v2 contract", "status": "PASS", "evidence": CONTRACT_REVIEW_V2.relative_to(ROOT).as_posix()},
    ])
    gate["technical_checks"] = checks
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = replace_prefix(project, "Last updated UTC:", "Last updated UTC: 2026-08-06")
    project = replace_prefix(project, "Last completed milestone:", "Last completed milestone: DEC-043 prepared corrected production BC notebook v2 after DEC-042 mount-count preflight failure")
    project = replace_prefix(project, "Current gate:", f"Current gate: corrected notebook request `{NOTEBOOK_REQUEST_V2.relative_to(ROOT).as_posix()}` at SHA-256 `{request_v2_sha}` is READY_UNAUTHORIZED; v1 failed before replay reads or training")
    project = replace_prefix(project, "Gold-path status:", "Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / RETAINED DATASET VALID / SOURCE BUNDLE V2 VALID / PRODUCTION BC NOTEBOOK V2 READY / TEST SEALED / TRAINING BLOCKED")
    project = replace_prefix(project, "Next review required before:", "Next review required before: creating/running corrected notebook v2, any replay-body read, optimizer step, training/evaluation, model promotion, submission, commit, or push")
    project_section = f"""## DEC-042/043 Production BC Notebook Mount-Count Remediation

The exact v1 notebook was created private and CPU-only, but failed in roughly ten seconds at the August 3 mount preflight: Kaggle mounted `4,721` files and `21,451,850,075` bytes while the wrapper expected a historical `4,724` count. No replay body, checkpoint reconstruction, optimizer step or training occurred.

The corrected v2 request changes only that mounted-file count. Request SHA-256: `{request_v2_sha}`; wrapper SHA-256: `{WRAPPER_V2_SHA}`; approval text SHA-256: `{approval_text_sha}`. A separate exact approval is required before the new v2 notebook can run.
"""
    project = append_section(project, "## DEC-042/043 Production BC Notebook Mount-Count Remediation", project_section)
    PROJECT.write_text(project.rstrip() + "\n", encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress_section = f"""## DEC-042/043 Production BC Notebook V1 Failure And V2 Preparation

Private notebook `ashok205/kptcg-e01-production-recurrent-bc-v1` version 1 failed closed before replay reads because its August 3 aggregate expected `4,724` files; both the live mount and official Kaggle file summary contain `4,721` files at the exact approved byte total. Output contained only the original hash-matching wrapper and approval receipt. Optimizer steps and training remained zero.

Corrected notebook request v2 is `{request_v2_sha}` and remains unauthorized. The only contract change is `AUGUST_3_FILES: 4724 -> 4721`; all 316 replay records, hashes, four epochs, 844-step cap, checkpoint, test seal and output-review boundaries are unchanged.
"""
    progress = append_section(progress, "## DEC-042/043 Production BC Notebook V1 Failure And V2 Preparation", progress_section)
    PROGRESS.write_text(progress.rstrip() + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "PASS_V1_FAILED_CLOSED_V2_REQUEST_READY_UNAUTHORIZED",
        "incident_sha256": incident_sha,
        "incident_self_hash": incident_self_hash,
        "execution_review_sha256": execution_sha,
        "execution_review_self_hash": execution_self_hash,
        "notebook_request_v2_sha256": request_v2_sha,
        "contract_review_v2_sha256": contract_review_sha,
        "contract_review_v2_self_hash": contract_review_self_hash,
        "approval_text_sha256": approval_text_sha,
        "dec042_sha256": dec042_sha,
        "dec043_sha256": dec043_sha,
        "replay_bodies": 0,
        "optimizer_steps": 0,
        "training": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
