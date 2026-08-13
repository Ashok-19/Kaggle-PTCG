from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-06T16:21:21Z"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_self_hashed(path: Path, value: dict[str, Any], field: str) -> tuple[str, str]:
    payload = dict(value)
    payload.pop(field, None)
    canonical = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    self_hash = sha256_bytes(canonical)
    payload[field] = self_hash
    write_json(path, payload)
    return sha256_file(path), self_hash


def upsert(items: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    matches = [index for index, item in enumerate(items) if item.get(key) == value]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate ledger key {key}={value}")
    if matches:
        items[matches[0]] = record
    else:
        items.append(record)


def replace_section(path: Path, heading: str, body: str) -> None:
    text = path.read_text().rstrip() + "\n"
    marker = f"## {heading}\n"
    if marker in text:
        start = text.index(marker)
        next_heading = text.find("\n## ", start + len(marker))
        if next_heading == -1:
            text = text[:start]
        else:
            text = text[:start] + text[next_heading + 1 :]
    text = text.rstrip() + "\n\n" + marker + "\n" + body.strip() + "\n"
    path.write_text(text)


def main() -> None:
    wrapper_path = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v3.py"
    builder_path = ROOT / "scripts/kaggle/build_e01_production_recurrent_bc_notebook_v3.py"
    test_path = ROOT / "tests/g3/test_e01_production_bc_notebook_v3.py"
    wrapper_sha = sha256_file(wrapper_path)
    builder_sha = sha256_file(builder_path)
    test_sha = sha256_file(test_path)
    expected = {
        "wrapper": "7f63cf6331ef0ee8122522cf2849e765e247f6f9a1a4c77bf4677101c1cf0b8d",
        "builder": "425ee2fe2ed3674424a0e432b95ea45327cf89676f553dca41cfd73e663d8421",
        "test": "3ff70ea20c6446bd5f375cbcdd1efd3a6f09f02ac03a28535fb2a0b2cdd645d5",
    }
    if {"wrapper": wrapper_sha, "builder": builder_sha, "test": test_sha} != expected:
        raise RuntimeError("v3 wrapper/builder/test identity differs")

    request_v2 = json.loads((ROOT / "configs/e01_production_recurrent_bc_notebook_request_v2.json").read_text())
    request_v3 = json.loads(json.dumps(request_v2))
    request_v3["created_at_utc"] = CREATED_AT
    request_v3["decision_id"] = "DEC-045"
    request_v3["purpose"] = (
        "Run the unchanged production recurrent-BC contract in one new private Kaggle CPU notebook after "
        "aligning the notebook wrapper and production implementation on the shared "
        "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1 receipt identity."
    )
    request_v3["record_id"] = "e01-production-recurrent-bc-notebook-request-v3"
    request_v3["notebook"].update(
        {
            "slug": "kptcg-e01-production-recurrent-bc-v3",
            "title": "KPTCG E01 Production Recurrent BC V3",
        }
    )
    request_v3.pop("prior_failed_run", None)
    request_v3["prior_failed_runs"] = [
        {
            "failure_phase": "AUGUST_3_MOUNT_INVENTORY_PREFLIGHT",
            "must_remain_unchanged": True,
            "notebook_id": 129904937,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v1",
            "replay_bodies_read": 0,
            "status": "ERROR",
            "version": 1,
        },
        {
            "failure_phase": "SHARED_APPROVAL_KIND_VALIDATION_BEFORE_SEMANTIC_LOADING",
            "must_remain_unchanged": True,
            "notebook_id": 129909738,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v2",
            "replay_bodies_hash_verified": 316,
            "replay_bytes_hash_verified": 1327994902,
            "status": "ERROR",
            "version": 1,
        },
    ]
    request_v3["stop_conditions"] = [
        "Fail if the exact v3 slug already exists.",
        "Fail on any dataset id, version, mount count, byte count, path, replay hash, checkpoint, wrapper, request, approval-kind, environment, loss, gradient, optimizer-step, wall-time or output mismatch.",
        "Stop after downloading and independently reviewing notebook outputs; do not evaluate, promote or submit a candidate under the run approval.",
    ]
    request_v3["wrapper"] = {
        "approval_kind": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
        "builder_path": "scripts/kaggle/build_e01_production_recurrent_bc_notebook_v3.py",
        "builder_sha256": builder_sha,
        "focused_test_path": "tests/g3/test_e01_production_bc_notebook_v3.py",
        "focused_test_sha256": test_sha,
        "path": "scripts/kaggle/e01_production_recurrent_bc_notebook_v3.py",
        "sha256": wrapper_sha,
    }
    request_v3["remediation"] = {
        "changed_field": "wrapper approval kind",
        "from": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2",
        "production_implementation_changed": False,
        "replay_contract_changed": False,
        "to": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
        "training_hyperparameters_changed": False,
    }
    request_path = ROOT / "configs/e01_production_recurrent_bc_notebook_request_v3.json"
    write_json(request_path, request_v3)
    request_sha = sha256_file(request_path)

    approval_text = f"""I approve consumption of `configs/e01_production_recurrent_bc_notebook_request_v3.json` at SHA-256 `{request_sha}` and authorize exactly one private Kaggle CPU production recurrent-BC notebook run under the following scope:

* Bind training to `configs/e01_production_recurrent_bc_request_v2.json` at SHA-256 `297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d`, runner SHA-256 `92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413`, and unchanged implementation SHA-256 `4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde`.
* Bind notebook execution to wrapper `scripts/kaggle/e01_production_recurrent_bc_notebook_v3.py` at SHA-256 `{wrapper_sha}`, deterministic source builder `scripts/kaggle/build_e01_production_recurrent_bc_notebook_v3.py` at SHA-256 `{builder_sha}`, and focused compatibility test `tests/g3/test_e01_production_bc_notebook_v3.py` at SHA-256 `{test_sha}`.
* Require one shared approval receipt kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1` that is accepted by both the v3 wrapper and the unchanged production implementation, while also binding the exact v3 notebook-request SHA-256 and wrapper SHA-256. Do not modify the production implementation under this approval.
* Create exactly one new private Kaggle script notebook `ashok205/kptcg-e01-production-recurrent-bc-v3` titled `KPTCG E01 Production Recurrent BC V3`. Fail closed if that slug already exists. Leave failed notebooks `ashok205/kptcg-e01-production-recurrent-bc-v1` and `ashok205/kptcg-e01-production-recurrent-bc-v2`, each at version 1, unchanged and do not rerun them.
* Configure `SaveAndRunAll`, CPU only, internet disabled, GPU disabled, TPU disabled, and a session timeout of exactly `14,400` seconds.
* Attach exactly these dataset sources: `ashok205/kptcg-e01-majkel-corpus-review-inputs` dataset ID `11501808` version `2`; `ashok205/kptcg-e01-production-bc-retained-inputs` dataset ID `11514316` version `1`; `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03` dataset ID `11490894` version `1`; and `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04` dataset ID `11506836` version `1`.
* Require the mounted dataset aggregates to remain exactly: source bundle `79` files / `7,645,589` bytes / inventory SHA-256 `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`; retained dataset `58` files / `341,559,745` bytes / inventory SHA-256 `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`; August 3 dataset `4,721` files / `21,451,850,075` bytes; and August 4 dataset `4,812` files / `21,457,813,826` bytes.
* Accept source-bundle version 2 only through deterministic reconstruction of the `5,429,190`-byte checkpoint at SHA-256 `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` before training.
* Verify every selected replay before semantic loading. Authorize reading, hashing and parsing exactly `316` train/validation replay bodies totaling `1,327,994,902` bytes: `237` files from the August 3 dataset, `21` files from the August 4 dataset, and `58` files from the retained private dataset.
* Authorize validation and production recurrent behavior cloning for at most `4` epochs and at most `844` optimizer steps using AdamW, learning rate `0.0001`, weight decay `0.0`, sequence length `32`, seed `20260805`, and the existing deterministic 80/20 primary/legacy schedule.
* Authorize construction of the optimizer, recurrent semantic loading, on-the-fly compound-action supervision, gradient updates, validation before training and after each epoch, and one checkpoint after each completed epoch. Do not create a separate persistent label dataset.
* Keep all `46` test episodes sealed. Do not read any test replay body or any simulation agent log. Do not perform held-out test, on-policy, tournament, or submission evaluation under this approval.
* After completion, download the notebook outputs, independently hash and review `execution-report.json`, `notebook-execution-envelope.json`, and all emitted epoch checkpoints, then stop and prepare the separate candidate-evaluation approval.
* Do not promote or publish a model, create or update a Kaggle model or dataset, submit to the competition, or make a Git commit or push.
* Retain `ashok205/new-benchmark-task-b1c52`, `ashok205/new-benchmark-task-daa06`, and `ashok205/new-benchmark-task-4abba` unchanged; all three currently have no Kaggle runs.
* Fail closed immediately on any authorization, notebook, dataset, version, privacy, mount, path, file, byte count, SHA-256, replay, checkpoint, approval-kind, environment, loss, gradient, optimizer-step, wall-time, output, or download mismatch."""
    approval_text = approval_text.rstrip() + "\n"
    approval_text_sha = sha256_bytes(approval_text.encode())

    incident_path = ROOT / "reports/incidents/e01-production-recurrent-bc-notebook-v2-approval-kind-mismatch-v1.json"
    incident_file_sha, incident_self_hash = write_self_hashed(
        incident_path,
        {
            "approval_kind_actual": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2",
            "approval_kind_expected_by_production": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
            "authorization_expanded": False,
            "checkpoint_reconstruction_report_sha256": "1e87ce65c0339f9d5132b5f964f0e6ad8df3f349a999c0a6a70776d656ed73fb",
            "checkpoint_reconstruction_status": "PASS_EXACT_PACKAGE_RECONSTRUCTED",
            "created_at_utc": CREATED_AT,
            "failure_phase": "PRODUCTION_APPROVAL_IDENTITY_VALIDATION_AFTER_REPLAY_HASH_PREFLIGHT",
            "incident_id": "e01-production-recurrent-bc-notebook-v2-approval-kind-mismatch-v1",
            "notebook_id": 129909738,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v2",
            "notebook_source_sha256": "0438eb695925a23a2a6cfe8eba65af3192814095922b0ad2129392ec4dd65860",
            "notebook_status": "ERROR",
            "notebook_version": 1,
            "optimizer_constructed": False,
            "optimizer_steps": 0,
            "production_implementation_sha256": "4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde",
            "replay_bodies_hash_verified": 316,
            "replay_bytes_hash_verified": 1327994902,
            "replay_semantic_parsing_started": False,
            "schema_version": 1,
            "test_replay_bodies_read": 0,
            "training": False,
        },
        "incident_sha256",
    )

    execution_review_path = ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-execution-review-v2.json"
    execution_review_file_sha, execution_review_self_hash = write_self_hashed(
        execution_review_path,
        {
            "approval_consumed": True,
            "approval_receipt_sha256": "194e9de3a434088d289672d9f3d81810cf2c285cf098567335392f4d5a021184",
            "builder_sha256": "425ee2fe2ed3674424a0e432b95ea45327cf89676f553dca41cfd73e663d8421",
            "created_at_utc": CREATED_AT,
            "downloaded_audit_outputs": [
                {
                    "path": "private/g3/e01/production-recurrent-bc-notebook-run-v2/remote-outputs/e01-production-recurrent-bc-approval-v2.json",
                    "sha256": "194e9de3a434088d289672d9f3d81810cf2c285cf098567335392f4d5a021184",
                },
                {
                    "path": "private/g3/e01/production-recurrent-bc-notebook-run-v2/remote-outputs/e01_production_recurrent_bc_notebook_v2.py",
                    "sha256": "59db2271582b45f886347755ef7e401af1603ac761977ba2d6600e70233bcf52",
                },
                {
                    "path": "private/g3/e01/production-recurrent-bc-notebook-run-v2/remote-outputs/e01-notebook-checkpoint-reconstruction-v1.json",
                    "sha256": "1e87ce65c0339f9d5132b5f964f0e6ad8df3f349a999c0a6a70776d656ed73fb",
                },
            ],
            "incident_file_sha256": incident_file_sha,
            "incident_path": str(incident_path.relative_to(ROOT)),
            "incident_self_hash": incident_self_hash,
            "notebook_id": 129909738,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v2",
            "notebook_request_sha256": "93ad27ae290bdf56f0e6259a252625d7bd15150054d85139f29c9cae7fb7f4eb",
            "notebook_source_sha256": "0438eb695925a23a2a6cfe8eba65af3192814095922b0ad2129392ec4dd65860",
            "notebook_status": "ERROR",
            "notebook_version": 1,
            "record_id": "e01-production-recurrent-bc-notebook-execution-review-v2",
            "result": {
                "checkpoint_reconstructed": True,
                "epoch_checkpoints_emitted": 0,
                "execution_report_emitted": False,
                "failure_phase": "SHARED_APPROVAL_KIND_VALIDATION",
                "notebook_envelope_emitted": False,
                "optimizer_constructed": False,
                "optimizer_steps": 0,
                "replay_bodies_hash_verified": 316,
                "replay_bytes_hash_verified": 1327994902,
                "semantic_parsing_started": False,
                "training": False,
            },
            "schema_version": 1,
            "status": "FAILED_CLOSED_AFTER_REPLAY_HASH_PREFLIGHT_NO_OPTIMIZER_OR_TRAINING",
            "wrapper_sha256": "59db2271582b45f886347755ef7e401af1603ac761977ba2d6600e70233bcf52",
        },
        "review_sha256",
    )

    contract_review_path = ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v3.json"
    contract_review_file_sha, contract_review_self_hash = write_self_hashed(
        contract_review_path,
        {
            "approval_text": approval_text,
            "approval_text_sha256": approval_text_sha,
            "authorization": {
                "notebook_create": False,
                "notebook_run": False,
                "optimizer_steps": False,
                "replay_body_read": False,
                "training": False,
            },
            "builder_path": str(builder_path.relative_to(ROOT)),
            "builder_sha256": builder_sha,
            "compatibility": {
                "production_approval_kind": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
                "production_implementation_changed": False,
                "shared_receipt_test_passed": True,
                "wrapper_approval_kind": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
            },
            "created_at_utc": CREATED_AT,
            "focused_test_path": str(test_path.relative_to(ROOT)),
            "focused_test_sha256": test_sha,
            "prior_execution_review_path": str(execution_review_path.relative_to(ROOT)),
            "prior_execution_review_sha256": execution_review_file_sha,
            "record_id": "e01-production-recurrent-bc-notebook-contract-review-v3",
            "request_path": str(request_path.relative_to(ROOT)),
            "request_sha256": request_sha,
            "schema_version": 1,
            "status": "PASS_SHARED_APPROVAL_KIND_NOTEBOOK_REQUEST_READY_UNAUTHORIZED",
            "training_contract_changed": False,
            "wrapper_path": str(wrapper_path.relative_to(ROOT)),
            "wrapper_sha256": wrapper_sha,
        },
        "review_sha256",
    )

    dec044_path = ROOT / "docs/decisions/DEC-044_E01_PRODUCTION_BC_NOTEBOOK_V2_APPROVAL_KIND_MISMATCH.md"
    dec044_path.write_text(
        f"""# DEC-044 — Production BC notebook v2 approval-kind mismatch

Status: `ACCEPTED_FAILED_CLOSED`

The exact private CPU notebook `ashok205/kptcg-e01-production-recurrent-bc-v2`, notebook ID `129909738`, version `1`, passed dataset-mount checks, reconstructed the approved checkpoint exactly, and read/hash-verified all `316` authorized train/validation replay bodies totaling `1,327,994,902` bytes.

Execution then failed before semantic parsing and optimizer construction because the v2 wrapper required approval kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2`, while unchanged production implementation `src/ptcg_rl/g3/bc_production_v2.py` requires `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`.

Optimizer steps, labels, training, epoch checkpoints, test replay reads, agent-log reads, model promotion, submission, commit and push remained zero. The failed notebook is retained unchanged and is not authorized for rerun.

Evidence:

- `{incident_path.relative_to(ROOT)}` — file SHA-256 `{incident_file_sha}`, self-hash `{incident_self_hash}`.
- `{execution_review_path.relative_to(ROOT)}` — file SHA-256 `{execution_review_file_sha}`, self-hash `{execution_review_self_hash}`.
"""
    )
    dec044_sha = sha256_file(dec044_path)

    dec045_path = ROOT / "docs/decisions/DEC-045_E01_PRODUCTION_BC_NOTEBOOK_V3_SHARED_APPROVAL_KIND_REMEDIATION.md"
    dec045_path.write_text(
        f"""# DEC-045 — Prepare production BC notebook v3 shared-approval remediation

Status: `ACCEPTED_REQUEST_READY_UNAUTHORIZED`

Prepare a new versioned wrapper and notebook request that change only the notebook-side approval kind from `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2` to the production implementation's existing `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`.

The production implementation, training request, runner, dataset mounts, `316` replay records, `1,327,994,902` replay bytes, checkpoint, hyperparameters, four-epoch limit, `844`-step cap, and `46` sealed test episodes are unchanged.

- Request: `{request_path.relative_to(ROOT)}` — SHA-256 `{request_sha}`.
- Wrapper: `{wrapper_path.relative_to(ROOT)}` — SHA-256 `{wrapper_sha}`.
- Builder: `{builder_path.relative_to(ROOT)}` — SHA-256 `{builder_sha}`.
- Focused test: `{test_path.relative_to(ROOT)}` — SHA-256 `{test_sha}`.
- Contract review: `{contract_review_path.relative_to(ROOT)}` — file SHA-256 `{contract_review_file_sha}`, self-hash `{contract_review_self_hash}`.
- Approval text SHA-256: `{approval_text_sha}`.

No notebook creation, replay access, optimizer step, training, evaluation, model mutation, submission, commit or push is authorized by this decision.
"""
    )
    dec045_sha = sha256_file(dec045_path)

    decisions_path = ROOT / "reports/decisions/current.json"
    decisions = json.loads(decisions_path.read_text())
    upsert(
        decisions,
        "decision_id",
        "DEC-044",
        {
            "created_at_utc": CREATED_AT,
            "decision": "Reject notebook v2 after all approved replay hashes passed because the wrapper and production implementation required different approval kinds.",
            "decision_id": "DEC-044",
            "execution_review_path": str(execution_review_path.relative_to(ROOT)),
            "execution_review_sha256": execution_review_file_sha,
            "incident_path": str(incident_path.relative_to(ROOT)),
            "incident_sha256": incident_file_sha,
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v2",
            "notebook_version": 1,
            "optimizer_steps": 0,
            "rationale": "Fail closed before semantic loading or optimizer construction and require a versioned shared-approval-kind wrapper.",
            "record_id": "decision-dec-044",
            "replay_bodies_read": 316,
            "replay_bytes_read": 1327994902,
            "revisit_trigger": "A shared-approval-kind v3 notebook request is exactly approved.",
            "schema_version": 1,
            "source_path": str(dec044_path.relative_to(ROOT)),
            "source_sha256": dec044_sha,
            "status": "ACCEPTED_FAILED_CLOSED",
            "title": "Fail closed on production BC notebook v2 approval-kind mismatch",
            "training": False,
        },
    )
    upsert(
        decisions,
        "decision_id",
        "DEC-045",
        {
            "approval_text_sha256": approval_text_sha,
            "contract_review_path": str(contract_review_path.relative_to(ROOT)),
            "contract_review_sha256": contract_review_file_sha,
            "created_at_utc": CREATED_AT,
            "decision": "Prepare one new private CPU notebook request whose wrapper and unchanged production implementation share approval kind V1.",
            "decision_id": "DEC-045",
            "notebook_authorized": False,
            "notebook_request_path": str(request_path.relative_to(ROOT)),
            "notebook_request_sha256": request_sha,
            "optimizer_steps": 0,
            "rationale": "The v2 failure was solely an approval-kind mismatch; an integration test proves one V1 receipt passes both validators.",
            "record_id": "decision-dec-045",
            "revisit_trigger": "The exact v3 notebook approval is accepted, or any bound identity changes.",
            "schema_version": 1,
            "source_path": str(dec045_path.relative_to(ROOT)),
            "source_sha256": dec045_sha,
            "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
            "title": "Prepare production BC notebook v3 shared-approval remediation",
            "training": False,
        },
    )
    write_json(decisions_path, decisions)

    tasks_path = ROOT / "reports/tasks/current.json"
    tasks = json.loads(tasks_path.read_text())
    upsert(
        tasks,
        "task_id",
        "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-044",
        {
            "approval_consumed": True,
            "blocker": "The v2 wrapper and production implementation required different approval receipt kinds.",
            "completed_at_utc": CREATED_AT,
            "created_at_utc": CREATED_AT,
            "decision_id": "DEC-044",
            "decision_path": str(dec044_path.relative_to(ROOT)),
            "decision_sha256": dec044_sha,
            "done_when": "A shared-approval-kind v3 request is exactly approved and run once.",
            "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v2",
            "notebook_version": 1,
            "optimizer_steps": 0,
            "phase": "E01-B",
            "priority": 20,
            "record_id": "task-e01-production-recurrent-bc-notebook-run-044",
            "replay_bodies": 316,
            "replay_bytes": 1327994902,
            "schema_version": 1,
            "status": "FAILED_CLOSED_APPROVAL_KIND_MISMATCH",
            "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-044",
            "title": "Run production recurrent BC notebook v2",
            "training": False,
            "updated_at_utc": CREATED_AT,
        },
    )
    upsert(
        tasks,
        "task_id",
        "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-REMEDIATION-045",
        {
            "approval_text_sha256": approval_text_sha,
            "blocker": "Exact v3 notebook approval is required.",
            "completed_at_utc": CREATED_AT,
            "created_at_utc": CREATED_AT,
            "decision_id": "DEC-045",
            "decision_path": str(dec045_path.relative_to(ROOT)),
            "decision_sha256": dec045_sha,
            "done_when": "The exact v3 notebook runs and its outputs are downloaded and independently verified.",
            "notebook_authorized": False,
            "notebook_request": str(request_path.relative_to(ROOT)),
            "notebook_request_sha256": request_sha,
            "optimizer_steps": 0,
            "phase": "E01-B",
            "priority": 20,
            "record_id": "task-e01-production-recurrent-bc-notebook-remediation-045",
            "replay_bodies": 0,
            "schema_version": 1,
            "status": "SUCCEEDED_RERUN_READY_UNAUTHORIZED",
            "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-REMEDIATION-045",
            "title": "Prepare production BC notebook v3 shared-approval remediation",
            "training": False,
            "updated_at_utc": CREATED_AT,
        },
    )
    write_json(tasks_path, tasks)

    gate_path = ROOT / "reports/gates/g3b.json"
    gate = json.loads(gate_path.read_text())
    gate.update(
        {
            "approved_next_action": f"Obtain exact approval for `{request_path.relative_to(ROOT)}` at SHA-256 `{request_sha}`, then create and run exactly one new private CPU notebook v3 and verify outputs.",
            "authorization": "SHARED_APPROVAL_KIND_NOTEBOOK_V3_READY_NO_NOTEBOOK_REPLAY_OPTIMIZER_TRAINING_EVALUATION_PROMOTION_OR_SUBMISSION_AUTHORIZED",
            "blockers": [
                "Notebook v2 read/hash-verified all 316 approved replays but failed before semantic parsing because wrapper and production approval kinds differed.",
                "The v3 wrapper uses the unchanged production V1 approval kind and passes shared-receipt integration tests but is not authorized.",
                "Training still requires exact approval for 316 train/validation bodies and at most 844 optimizer steps.",
                "Test replay reads, candidate evaluation, model promotion and submission remain blocked.",
            ],
            "decision": "DEC-045_PRODUCTION_BC_NOTEBOOK_V3_READY_UNAUTHORIZED",
            "status": "BLOCKED",
            "updated_at_utc": CREATED_AT,
        }
    )
    checks = gate.setdefault("technical_checks", [])
    names = {item.get("name") for item in checks}
    additions = [
        {
            "evidence": str(execution_review_path.relative_to(ROOT)),
            "name": "DEC-044 production BC notebook v2 approval-kind failure boundary",
            "status": "FAILED_CLOSED",
        },
        {
            "evidence": str(contract_review_path.relative_to(ROOT)),
            "name": "DEC-045 shared V1 approval-kind notebook wrapper and request",
            "status": "PASS",
        },
    ]
    for item in additions:
        if item["name"] not in names:
            checks.append(item)
    warnings = gate.setdefault("warnings", [])
    warning = "Notebook v2 read/hash-verified 316 approved replay bodies before failing on approval-kind identity; semantic parsing and optimizer construction did not begin."
    if warning not in warnings:
        warnings.append(warning)
    write_json(gate_path, gate)

    status_body = f"""
Private CPU notebook `ashok205/kptcg-e01-production-recurrent-bc-v2`, version 1, passed all dataset and checkpoint preflights and read/hash-verified exactly `316` approved train/validation replay bodies totaling `1,327,994,902` bytes. It then failed before semantic parsing because the wrapper required approval kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2` while the unchanged production implementation requires `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`. Optimizer construction, optimizer steps, labels, training, epoch checkpoints, test replay reads and agent-log reads remained zero.

The v3 remediation changes only the wrapper-side approval kind and adds a focused integration test proving one V1 receipt passes both validators. Request SHA-256: `{request_sha}`; wrapper SHA-256: `{wrapper_sha}`; builder SHA-256: `{builder_sha}`; approval text SHA-256: `{approval_text_sha}`. A separate exact approval is required before notebook v3 can run.
"""
    replace_section(ROOT / "PROJECT_STATUS.md", "DEC-044/045 Production BC Notebook Approval-Kind Remediation", status_body)
    replace_section(ROOT / "PROGRESS_REPORT.md", "DEC-044/045 Production BC Notebook V2 Failure And V3 Preparation", status_body)

    print(
        json.dumps(
            {
                "approval_text_sha256": approval_text_sha,
                "contract_review_file_sha256": contract_review_file_sha,
                "contract_review_self_hash": contract_review_self_hash,
                "dec044_sha256": dec044_sha,
                "dec045_sha256": dec045_sha,
                "execution_review_file_sha256": execution_review_file_sha,
                "execution_review_self_hash": execution_review_self_hash,
                "incident_file_sha256": incident_file_sha,
                "incident_self_hash": incident_self_hash,
                "notebook_request_v3_sha256": request_sha,
                "optimizer_steps": 0,
                "replay_bodies_hash_verified": 316,
                "status": "PASS_V2_FAILED_CLOSED_V3_REQUEST_READY_UNAUTHORIZED",
                "training": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
