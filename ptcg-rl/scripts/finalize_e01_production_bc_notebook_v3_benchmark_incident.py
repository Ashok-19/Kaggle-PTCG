from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NOW_GENERATED = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
REQUEST_PATH = "configs/e01_production_recurrent_bc_notebook_request_v3.json"
REQUEST_SHA256 = "30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd"
PRIOR_APPROVAL_SHA256 = "4cf80c5be4f1dfa40fbcd0e158dffe4113845862ac2d15421e51e28e8b3f0fbb"
OBJECT_REF = "ashok205/new-benchmark-task-8065e"
OBJECT_URL = "/code/ashok205/new-benchmark-task-8065e/edit/run/340629690"
INCIDENT_PATH = Path("reports/incidents/e01-production-recurrent-bc-notebook-v3-unauthorized-benchmark-task-v1.json")
EXECUTION_REVIEW_PATH = Path("reports/artifacts/e01-production-recurrent-bc-notebook-execution-review-v3.json")
CONTRACT_REVIEW_PATH = Path("reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v4.json")
DEC046_PATH = Path("docs/decisions/DEC-046_E01_PRODUCTION_BC_NOTEBOOK_V3_UNAUTHORIZED_BENCHMARK_TASK.md")
DEC047_PATH = Path("docs/decisions/DEC-047_E01_PRODUCTION_BC_NOTEBOOK_V3_APPROVAL_RENEWED_AFTER_BENCHMARK_INCIDENT.md")

if (ROOT / INCIDENT_PATH).is_file():
    NOW = json.loads((ROOT / INCIDENT_PATH).read_text()).get("created_at_utc", NOW_GENERATED)
else:
    NOW = NOW_GENERATED


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes((ROOT / path).read_bytes())


def write_json_with_self_hash(path: Path, value: dict[str, Any], field: str) -> tuple[str, str]:
    payload = dict(value)
    canonical = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    self_hash = sha256_bytes(canonical)
    payload[field] = self_hash
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return sha256_file(path), self_hash


def write_text(path: Path, text: str) -> str:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip() + "\n")
    return sha256_file(path)


def upsert(items: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    matches = [index for index, item in enumerate(items) if item.get(key) == value]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate {key}={value}")
    if matches:
        items[matches[0]] = record
    else:
        items.append(record)


request_file = ROOT / REQUEST_PATH
if sha256_file(Path(REQUEST_PATH)) != REQUEST_SHA256:
    raise RuntimeError("v3 notebook request hash differs")
request = json.loads(request_file.read_text())
if request.get("status") != "READY_UNAUTHORIZED" or request.get("request_ready") is not True:
    raise RuntimeError("v3 notebook request readiness differs")
if any(request.get("authorization", {}).values()):
    raise RuntimeError("v3 request contains authorization")

prior_contract = json.loads((ROOT / "reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v3.json").read_text())
if prior_contract.get("approval_text_sha256") != PRIOR_APPROVAL_SHA256:
    raise RuntimeError("prior approval text hash differs")

incident = {
    "actual_out_of_scope_operation": "One Kaggle benchmark-task notebook object was created by an incorrect connector invocation during v3 local/remote preflight.",
    "agent_logs_accessed": 0,
    "approved_request_path": REQUEST_PATH,
    "approved_request_sha256": REQUEST_SHA256,
    "approval_consumed": False,
    "created_at_utc": NOW,
    "dataset_mutations": 0,
    "evaluation": False,
    "frozen_approval_text_sha256": PRIOR_APPROVAL_SHA256,
    "git_commit": False,
    "git_push": False,
    "intended_operation": "Build and submit exactly one private Kaggle CPU production recurrent-BC notebook v3 after exact identity preflight.",
    "kind": "UNAUTHORIZED_KAGGLE_BENCHMARK_TASK_CREATION_DURING_NOTEBOOK_V3_PREFLIGHT",
    "labels_materialized": 0,
    "model_mutations": 0,
    "notebook_v3_created": False,
    "notebook_v3_submitted": False,
    "optimizer_constructed": False,
    "optimizer_steps": 0,
    "record_id": "e01-production-recurrent-bc-notebook-v3-unauthorized-benchmark-task-v1",
    "replay_bodies_accessed": 0,
    "replay_bytes_accessed": 0,
    "response": "Stopped immediately, left the new object unchanged, and performed no approved notebook creation or training action.",
    "schema_version": 1,
    "status": "OPEN_FAILED_CLOSED",
    "submissions": 0,
    "training": False,
    "unauthorized_remote_mutations": 1,
    "unauthorized_remote_objects": [
        {
            "deleted_or_modified_after_creation": False,
            "execution_state": "UNRESOLVED",
            "kernel_url": OBJECT_URL,
            "privacy": "UNRESOLVED",
            "ref": OBJECT_REF,
        }
    ],
}
incident_file_sha, incident_self_hash = write_json_with_self_hash(INCIDENT_PATH, incident, "incident_sha256")

execution_review = {
    "approval_consumed": False,
    "approved_request_path": REQUEST_PATH,
    "approved_request_sha256": REQUEST_SHA256,
    "created_at_utc": NOW,
    "incident_path": str(INCIDENT_PATH),
    "incident_self_hash": incident_self_hash,
    "incident_sha256": incident_file_sha,
    "local_identity_preflight_passed": True,
    "notebook_ref": "ashok205/kptcg-e01-production-recurrent-bc-v3",
    "notebook_created": False,
    "notebook_submitted": False,
    "optimizer_constructed": False,
    "optimizer_steps": 0,
    "record_id": "e01-production-recurrent-bc-notebook-execution-review-v3",
    "replay_bodies_read": 0,
    "replay_bytes_read": 0,
    "schema_version": 1,
    "status": "FAILED_CLOSED_UNAUTHORIZED_BENCHMARK_TASK_BEFORE_NOTEBOOK_CREATION",
    "training": False,
    "unauthorized_object_ref": OBJECT_REF,
}
execution_file_sha, execution_self_hash = write_json_with_self_hash(EXECUTION_REVIEW_PATH, execution_review, "review_sha256")

old_text = prior_contract["approval_text"]
old_retain = "* Retain `ashok205/new-benchmark-task-b1c52`, `ashok205/new-benchmark-task-daa06`, and `ashok205/new-benchmark-task-4abba` unchanged; all three currently have no Kaggle runs."
new_retain = "* Retain `ashok205/new-benchmark-task-b1c52`, `ashok205/new-benchmark-task-daa06`, `ashok205/new-benchmark-task-4abba`, and `ashok205/new-benchmark-task-8065e` unchanged. Do not inspect, execute, cancel, delete, or modify any of them under this approval."
if old_retain not in old_text:
    raise RuntimeError("prior retain clause differs")
renewed_text = old_text.replace(old_retain, new_retain)
anchor = "* Create exactly one new private Kaggle script notebook `ashok205/kptcg-e01-production-recurrent-bc-v3` titled `KPTCG E01 Production Recurrent BC V3`. Fail closed if that slug already exists. Leave failed notebooks `ashok205/kptcg-e01-production-recurrent-bc-v1` and `ashok205/kptcg-e01-production-recurrent-bc-v2`, each at version 1, unchanged and do not rerun them."
renewal_clause = anchor + "\n* Acknowledge that the prior v3 approval failed closed before notebook creation after the accidental creation of `ashok205/new-benchmark-task-8065e`; the prior approval is unconsumed and does not authorize a retry. This renewed approval authorizes the one v3 notebook creation and run described here."
if anchor not in renewed_text:
    raise RuntimeError("prior notebook creation clause differs")
renewed_text = renewed_text.replace(anchor, renewal_clause)
renewed_approval_sha = sha256_bytes(renewed_text.encode())

contract_review = {
    "approval_text": renewed_text,
    "approval_text_sha256": renewed_approval_sha,
    "authorization": {
        "notebook_create": False,
        "notebook_run": False,
        "optimizer_steps": False,
        "replay_body_read": False,
        "training": False,
    },
    "created_at_utc": NOW,
    "incident_path": str(INCIDENT_PATH),
    "incident_sha256": incident_file_sha,
    "prior_approval_consumed": False,
    "prior_approval_text_sha256": PRIOR_APPROVAL_SHA256,
    "record_id": "e01-production-recurrent-bc-notebook-contract-review-v4",
    "request_path": REQUEST_PATH,
    "request_sha256": REQUEST_SHA256,
    "schema_version": 1,
    "status": "PASS_SAME_V3_REQUEST_RENEWED_APPROVAL_READY_UNAUTHORIZED",
    "training_contract_changed": False,
    "wrapper_changed": False,
}
contract_file_sha, contract_self_hash = write_json_with_self_hash(CONTRACT_REVIEW_PATH, contract_review, "review_sha256")

DEC046_TEXT = f"""# DEC-046 — Fail closed on unauthorized benchmark-task creation during notebook v3 preflight

- Created at: `{NOW}`
- Approved v3 request: `{REQUEST_PATH}` at `{REQUEST_SHA256}`
- Out-of-scope object: `{OBJECT_REF}`
- Returned URL: `{OBJECT_URL}`
- The object was left unchanged.
- The approved v3 notebook was not created or submitted.
- Replay bodies/bytes read: `0` / `0`
- Optimizer constructed: `false`; optimizer steps: `0`; training: `false`
- The exact v3 approval is unconsumed and invalidated for further execution by its fail-closed clause.
- Evidence: `{INCIDENT_PATH}` and `{EXECUTION_REVIEW_PATH}`.
"""
dec046_sha = write_text(DEC046_PATH, DEC046_TEXT)

DEC047_TEXT = f"""# DEC-047 — Renew notebook v3 approval after benchmark-task incident

- Created at: `{NOW}`
- The production recurrent-BC request, implementation, runner, wrapper, builder, datasets, replay set, checkpoint, hyperparameters, four-epoch limit, and 844-step limit are unchanged.
- The same v3 request remains `{REQUEST_SHA256}`.
- The renewed approval adds `{OBJECT_REF}` only to the retain-unchanged boundary and explicitly records that the prior approval is unconsumed.
- Renewed approval text SHA-256: `{renewed_approval_sha}`.
- No notebook, replay read, optimizer, training, evaluation, model, submission, commit, or push is currently authorized.
- Contract review: `{CONTRACT_REVIEW_PATH}`.
"""
dec047_sha = write_text(DEC047_PATH, DEC047_TEXT)

decisions_path = ROOT / "reports/decisions/current.json"
decisions = json.loads(decisions_path.read_text())
upsert(decisions, "decision_id", "DEC-046", {
    "approval_consumed": False,
    "created_at_utc": NOW,
    "decision": "Stop notebook v3 execution after an out-of-scope Kaggle benchmark-task object was created before the approved notebook existed.",
    "decision_id": "DEC-046",
    "incident_path": str(INCIDENT_PATH),
    "incident_sha256": incident_file_sha,
    "notebook_created": False,
    "optimizer_steps": 0,
    "record_id": "decision-dec-046",
    "replay_bodies_read": 0,
    "revisit_trigger": "The exact renewed v3 approval is accepted.",
    "schema_version": 1,
    "source_path": str(DEC046_PATH),
    "source_sha256": dec046_sha,
    "status": "ACCEPTED_FAILED_CLOSED",
    "title": "Fail closed on notebook v3 benchmark-task incident",
    "training": False,
    "unauthorized_remote_object": OBJECT_REF,
})
upsert(decisions, "decision_id", "DEC-047", {
    "approval_text_sha256": renewed_approval_sha,
    "contract_review_path": str(CONTRACT_REVIEW_PATH),
    "contract_review_sha256": contract_file_sha,
    "created_at_utc": NOW,
    "decision": "Prepare a renewed approval for the unchanged v3 notebook request, adding only the new benchmark object to the retain-unchanged boundary.",
    "decision_id": "DEC-047",
    "notebook_authorized": False,
    "notebook_request_path": REQUEST_PATH,
    "notebook_request_sha256": REQUEST_SHA256,
    "optimizer_steps": 0,
    "record_id": "decision-dec-047",
    "revisit_trigger": "The exact renewed v3 approval is accepted, or any bound identity changes.",
    "schema_version": 1,
    "source_path": str(DEC047_PATH),
    "source_sha256": dec047_sha,
    "status": "ACCEPTED_RENEWED_APPROVAL_READY_UNAUTHORIZED",
    "title": "Renew notebook v3 approval after benchmark incident",
    "training": False,
})
decisions_path.write_text(json.dumps(decisions, indent=2, sort_keys=True) + "\n")

tasks_path = ROOT / "reports/tasks/current.json"
tasks = json.loads(tasks_path.read_text())
upsert(tasks, "task_id", "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-046", {
    "approval_consumed": False,
    "blocker": "An unauthorized benchmark-task object was created before notebook v3 creation.",
    "completed_at_utc": NOW,
    "created_at_utc": NOW,
    "decision_id": "DEC-046",
    "decision_path": str(DEC046_PATH),
    "decision_sha256": dec046_sha,
    "done_when": "The renewed exact v3 approval is consumed and the one notebook run completes or fails closed.",
    "notebook_created": False,
    "optimizer_steps": 0,
    "phase": "E01-B",
    "priority": 20,
    "record_id": "task-e01-production-recurrent-bc-notebook-run-046",
    "replay_bodies": 0,
    "schema_version": 1,
    "status": "FAILED_CLOSED_UNAUTHORIZED_BENCHMARK_TASK",
    "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RUN-046",
    "title": "Run production recurrent BC notebook v3",
    "training": False,
    "updated_at_utc": NOW,
})
upsert(tasks, "task_id", "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RENEWAL-047", {
    "approval_text_sha256": renewed_approval_sha,
    "blocker": "Exact renewed v3 notebook approval is required.",
    "completed_at_utc": NOW,
    "created_at_utc": NOW,
    "decision_id": "DEC-047",
    "decision_path": str(DEC047_PATH),
    "decision_sha256": dec047_sha,
    "done_when": "The exact renewed v3 approval is consumed and the one notebook run completes or fails closed.",
    "notebook_authorized": False,
    "notebook_request": REQUEST_PATH,
    "notebook_request_sha256": REQUEST_SHA256,
    "optimizer_steps": 0,
    "phase": "E01-B",
    "priority": 20,
    "record_id": "task-e01-production-recurrent-bc-notebook-renewal-047",
    "replay_bodies": 0,
    "schema_version": 1,
    "status": "SUCCEEDED_RENEWED_APPROVAL_READY_UNAUTHORIZED",
    "task_id": "T-E01-PRODUCTION-RECURRENT-BC-NOTEBOOK-RENEWAL-047",
    "title": "Renew production BC notebook v3 approval",
    "training": False,
    "updated_at_utc": NOW,
})
tasks_path.write_text(json.dumps(tasks, indent=2, sort_keys=True) + "\n")

gate_path = ROOT / "reports/gates/g3b.json"
gate = json.loads(gate_path.read_text())
gate["approved_next_action"] = f"Obtain exact approval text SHA-256 `{renewed_approval_sha}` for unchanged request `{REQUEST_PATH}` at `{REQUEST_SHA256}`, then create and run exactly one private CPU notebook v3."
gate["authorization"] = "RENEWED_NOTEBOOK_V3_APPROVAL_READY_NO_NOTEBOOK_REPLAY_OPTIMIZER_TRAINING_EVALUATION_PROMOTION_OR_SUBMISSION_AUTHORIZED"
gate["blockers"] = [
    f"The prior v3 approval failed closed before notebook creation after accidental creation of `{OBJECT_REF}`.",
    "The same v3 request and wrapper remain valid, but execution requires the renewed exact approval.",
    "Test replay reads, candidate evaluation, model promotion, and submission remain blocked.",
]
gate["decision"] = "DEC-047_PRODUCTION_BC_NOTEBOOK_V3_RENEWED_APPROVAL_READY_UNAUTHORIZED"
gate["status"] = "BLOCKED"
gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")

status_section = f"""
## DEC-046/047 Notebook V3 Benchmark Incident And Approval Renewal

The exact v3 approval failed closed before notebook creation after an incorrect connector invocation created `{OBJECT_REF}`. The object was left unchanged. The approved notebook, replay reads, optimizer construction, optimizer steps, and training all remained zero.

The unchanged v3 request remains `{REQUEST_SHA256}`. A renewed exact approval is prepared at SHA-256 `{renewed_approval_sha}`; it adds only the new object to the retain-unchanged boundary and authorizes nothing until accepted.
"""
for name in ("PROJECT_STATUS.md", "PROGRESS_REPORT.md"):
    path = ROOT / name
    text = path.read_text().rstrip()
    marker = "## DEC-046/047 Notebook V3 Benchmark Incident And Approval Renewal"
    if marker in text:
        text = text[: text.index(marker)].rstrip()
    path.write_text(text + "\n\n" + status_section.strip() + "\n")

print(json.dumps({
    "status": "PASS_V3_FAILED_CLOSED_RENEWED_APPROVAL_READY_UNAUTHORIZED",
    "incident_file_sha256": incident_file_sha,
    "incident_self_hash": incident_self_hash,
    "execution_review_file_sha256": execution_file_sha,
    "execution_review_self_hash": execution_self_hash,
    "contract_review_file_sha256": contract_file_sha,
    "contract_review_self_hash": contract_self_hash,
    "renewed_approval_text_sha256": renewed_approval_sha,
    "dec046_sha256": dec046_sha,
    "dec047_sha256": dec047_sha,
    "notebook_v3_created": False,
    "replay_bodies": 0,
    "optimizer_steps": 0,
    "training": False,
}, indent=2, sort_keys=True))
