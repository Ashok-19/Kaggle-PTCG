from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.e01_verify_extracted_checkpoint_delivery import (
    ARCHIVE_MODE,
    ARCHIVE_TIMESTAMP,
    MEMBERS,
    PACKAGE_BYTES,
    PACKAGE_SHA256,
    reconstruct_checkpoint,
)


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-06T10:26:44Z"
REQUEST = ROOT / "configs/e01_source_bundle_v2_checkpoint_directory_verification_request_v1.json"
REVIEW = ROOT / "reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-contract-review-v1.json"
DECISION = ROOT / "docs/decisions/DEC-039_E01_SOURCE_BUNDLE_V2_EXTRACTED_CHECKPOINT_VERIFICATION_PREPARED.md"
VERIFIER = ROOT / "scripts/e01_verify_extracted_checkpoint_delivery.py"
TEST = ROOT / "tests/g3/test_checkpoint_delivery.py"
TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"
RAW_INVENTORY = ROOT / "reports/artifacts/raw/e01-source-bundle-v2-remote-inventory-20260806-v1.json"
EXECUTION_REVIEW = ROOT / "reports/artifacts/e01-source-bundle-v2-publication-execution-review-v1.json"
INCIDENT = ROOT / "reports/incidents/e01-source-bundle-v2-checkpoint-archive-expansion-v1.json"
DEC038 = ROOT / "docs/decisions/DEC-038_E01_SOURCE_BUNDLE_V2_CHECKPOINT_ARCHIVE_EXPANSION.md"
CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

EXPECTED_HASHES = {
    TRAINING_REQUEST: "297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d",
    RAW_INVENTORY: "c6e58fe08c3b65ddd727430e916c8a2622a914989b7b0ca75d30182c323562eb",
    EXECUTION_REVIEW: "16df8736c90c3a44fdf2d023afa821b7c63e3f81b566e69b61266e85414bdd95",
    INCIDENT: "5840125b78b96bde8928067a45e4d5eeb6552ce14ab9e229cd550647623d0a77",
    DEC038: "bb44a6958dbc99da87f6437ec737c67de76dcf176d7c6af749e062e48753d851",
    CHECKPOINT: PACKAGE_SHA256,
}
SELF_HASHES = {
    RAW_INVENTORY: ("inventory_sha256", "69db307c555a904f75131fdce3ba9f19dce6a9672f6b6bf5e7227cf78a135b53"),
    EXECUTION_REVIEW: ("review_sha256", "04295038642c1f1519d635c9b750d5d03cfd2c1957b4e167674949e549caab87"),
    INCIDENT: ("incident_sha256", "0720746464c413b1a893d11427c42cb9cb786e95822feb5d6403a863948ff073"),
}
REMOTE_PREFIX = "private/g2/checkpoint-v1/g2-policy-checkpoint-v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def inventory_hash(records: list[dict[str, Any]]) -> str:
    payload = [{"name": str(item["name"]), "bytes": int(item["bytes"])} for item in records]
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def replace_prefix(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise RuntimeError(f"missing status prefix: {prefix}")


def append_section(text: str, heading: str, section: str) -> str:
    marker = f"\n{heading}\n"
    if marker in text:
        before, _, rest = text.partition(marker)
        next_heading = rest.find("\n## ")
        if next_heading >= 0:
            rest = rest[next_heading:]
            return before.rstrip() + "\n\n" + section.rstrip() + "\n" + rest
        return before.rstrip() + "\n\n" + section.rstrip() + "\n"
    return text.rstrip() + "\n\n" + section.rstrip() + "\n"


def upsert(records: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    matches = [index for index, item in enumerate(records) if item.get(key) == value]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate ledger identity: {key}={value}")
    if matches:
        records[matches[0]] = record
    else:
        records.append(record)


def verify_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], str, str]:
    for path, expected in EXPECTED_HASHES.items():
        observed = sha(path)
        if observed != expected:
            raise RuntimeError(f"input hash differs for {path.relative_to(ROOT)}: {observed}")
    for path, (field, expected) in SELF_HASHES.items():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get(field) != expected or self_hash(value, field) != expected:
            raise RuntimeError(f"input self-hash differs for {path.relative_to(ROOT)}")
    raw = json.loads(RAW_INVENTORY.read_text(encoding="utf-8"))
    actual = raw.get("actual", {})
    records = actual.get("records")
    if not isinstance(records, list) or len(records) != 79:
        raise RuntimeError("DEC-038 remote inventory record set differs")
    if actual.get("files") != 79 or actual.get("bytes") != 7_645_589:
        raise RuntimeError("DEC-038 remote aggregate differs")
    if actual.get("inventory_sha256") != "2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab":
        raise RuntimeError("DEC-038 remote inventory hash field differs")
    if inventory_hash(records) != actual["inventory_sha256"]:
        raise RuntimeError("DEC-038 remote inventory hash does not reproduce")
    by_name = {str(item["name"]): int(item["bytes"]) for item in records}
    remote_members: list[dict[str, Any]] = []
    for member in MEMBERS:
        remote_name = f"{REMOTE_PREFIX}/{member['name']}"
        if by_name.get(remote_name) != int(member["bytes"]):
            raise RuntimeError(f"remote member metadata differs: {remote_name}")
        remote_members.append(
            {
                "remote_name": remote_name,
                "member_name": str(member["name"]),
                "bytes": int(member["bytes"]),
                "expected_sha256": str(member["sha256"]),
                "sha256_verification_status": "UNVERIFIED_REMOTE_DOWNLOAD_REQUIRED",
            }
        )
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        extracted = temp / "members"
        extracted.mkdir()
        with zipfile.ZipFile(CHECKPOINT, "r") as archive:
            archive.extractall(extracted)
        rebuilt = temp / "rebuilt.zip"
        report = reconstruct_checkpoint(extracted, rebuilt)
        if rebuilt.read_bytes() != CHECKPOINT.read_bytes():
            raise RuntimeError("local deterministic reconstruction differs byte-for-byte")
        reconstruction_status = str(report["status"])
    return raw, remote_members, reconstruction_status, sha(VERIFIER)


def main() -> None:
    raw, remote_members, reconstruction_status, verifier_sha = verify_inputs()
    test_sha = sha(TEST)
    request = {
        "schema_version": 1,
        "record_id": "e01-source-bundle-v2-checkpoint-directory-verification-request-v1",
        "source_path": REQUEST.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "purpose": "Verify the four Kaggle-expanded checkpoint members and prove exact deterministic reconstruction of the original sealed checkpoint ZIP without creating another dataset version.",
        "dataset": {
            "ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs",
            "dataset_id": 11_501_808,
            "version": 2,
            "private": True,
            "status": "READY",
            "files": 79,
            "bytes": 7_645_589,
            "remote_inventory_sha256": "2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab",
            "last_updated_utc": "2026-08-06T09:53:15.123Z",
        },
        "remote_members": remote_members,
        "remote_download_scope": {
            "files": 4,
            "bytes": 5_428_744,
            "full_dataset_download": False,
            "download_only_exact_remote_members": True,
            "destination": "private/g3/e01/source-bundle-v2-checkpoint-verification-v1/remote-members",
        },
        "reconstruction": {
            "verifier_path": VERIFIER.relative_to(ROOT).as_posix(),
            "verifier_sha256": verifier_sha,
            "test_path": TEST.relative_to(ROOT).as_posix(),
            "test_sha256": test_sha,
            "local_proof_status": reconstruction_status,
            "archive_timestamp": list(ARCHIVE_TIMESTAMP),
            "archive_mode_octal": "0600",
            "archive_mode_integer": ARCHIVE_MODE,
            "compression": "ZIP_STORED",
            "create_system": 3,
            "internal_attr": 0,
            "flag_bits": 0,
            "member_order": sorted(str(item["name"]) for item in MEMBERS),
            "expected_package_bytes": PACKAGE_BYTES,
            "expected_package_sha256": PACKAGE_SHA256,
            "output_path": "private/g3/e01/source-bundle-v2-checkpoint-verification-v1/reconstructed/g2-policy-checkpoint-v1.zip",
        },
        "renewed_dependency_if_verified": {
            "method": "accept_private_ready_source_bundle_v2_with_verified_extracted_checkpoint_delivery_and_deterministic_local_zip_reconstruction",
            "production_request_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "production_request_sha256": EXPECTED_HASHES[TRAINING_REQUEST],
            "implementation_path": "src/ptcg_rl/g3/bc_production_v2.py",
            "implementation_sha256": "4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde",
            "runner_path": "scripts/e01_production_recurrent_bc_v2.py",
            "runner_sha256": "92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413",
            "notebook_wrapper_must_reconstruct_before_any_replay_body_read": True,
            "source_bundle_version_3_required": False,
            "dataset_mutation_required": False,
            "status": "PENDING_EXACT_REMOTE_MEMBER_SHA256_VERIFICATION",
        },
        "evidence": {
            "raw_remote_inventory": {
                "path": RAW_INVENTORY.relative_to(ROOT).as_posix(),
                "sha256": EXPECTED_HASHES[RAW_INVENTORY],
                "self_hash": SELF_HASHES[RAW_INVENTORY][1],
            },
            "publication_execution_review": {
                "path": EXECUTION_REVIEW.relative_to(ROOT).as_posix(),
                "sha256": EXPECTED_HASHES[EXECUTION_REVIEW],
                "self_hash": SELF_HASHES[EXECUTION_REVIEW][1],
            },
            "incident": {
                "path": INCIDENT.relative_to(ROOT).as_posix(),
                "sha256": EXPECTED_HASHES[INCIDENT],
                "self_hash": SELF_HASHES[INCIDENT][1],
            },
            "decision": {
                "path": DEC038.relative_to(ROOT).as_posix(),
                "sha256": EXPECTED_HASHES[DEC038],
            },
            "approved_local_checkpoint": {
                "path": CHECKPOINT.relative_to(ROOT).as_posix(),
                "bytes": PACKAGE_BYTES,
                "sha256": PACKAGE_SHA256,
            },
        },
        "authorization": {
            "remote_member_download": False,
            "remote_member_hash": False,
            "local_copy_or_stage": False,
            "local_zip_reconstruction": False,
            "local_metadata_update": False,
            "dataset_create": False,
            "dataset_update": False,
            "dataset_version": False,
            "dataset_delete": False,
            "replay_body_read": False,
            "agent_log_read": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "evaluation": False,
            "notebook_create_or_run": False,
            "gpu": False,
            "tpu": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "benchmark_task_mutation": False,
            "git_commit": False,
            "git_push": False,
        },
        "later_exact_approval_may_only": {
            "download_and_hash_exact_four_remote_members": True,
            "write_exact_local_scratch_and_verification_report": True,
            "reconstruct_and_hash_exact_checkpoint_zip": True,
            "record_source_bundle_v2_acceptance_if_all_hashes_match": True,
            "prepare_notebook_wrapper_contract_and_separate_approval_text": True,
            "train": False,
        },
        "stop_conditions": [
            "Fail before any remote download if dataset ID, version, privacy, Ready status, 79-file count, 7645589-byte count, or metadata inventory SHA-256 differs.",
            "Download only the four exact remote member paths; do not download the full source-bundle dataset.",
            "Fail if any remote member path, byte count, or SHA-256 differs from the approved local checkpoint member identity.",
            "Fail if deterministic reconstruction does not produce exactly 5429190 bytes and package SHA-256 4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827.",
            "Do not access replay bodies or agent logs, mutate any remote object, materialize labels, construct an optimizer, train, evaluate, run a notebook, mutate a model, submit, commit, or push.",
            "Stop after recording verification and preparing a separate exact notebook-wrapper approval."
        ],
    }
    write_json(REQUEST, request)
    request_sha = sha(REQUEST)
    approval_text = f"""I approve consumption of `{REQUEST.relative_to(ROOT).as_posix()}` at SHA-256 `{request_sha}`, under exactly the following scope:\n\n* Bind the operation to private Kaggle dataset `ashok205/kptcg-e01-majkel-corpus-review-inputs`, dataset ID `11501808`, version `2`.\n* Require the dataset to remain private and Ready with exactly `79` files, `7,645,589` bytes, and metadata inventory SHA-256 `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`.\n* Download and hash only the following four version-2 files; do not download the full dataset:\n  * `private/g2/checkpoint-v1/g2-policy-checkpoint-v1/card-table-v1.json` — `1,056,442` bytes — expected SHA-256 `5fc3a1cf31dd5f4b1b3542fc1baa91fe2b68b772cb5748f50f0f75c9a74f7714`.\n  * `private/g2/checkpoint-v1/g2-policy-checkpoint-v1/manifest.json` — `26,493` bytes — expected SHA-256 `1185c97d1fca8cb795e2c5f84f5d0a915cf41fac242aefed888b4e0dd84b267c`.\n  * `private/g2/checkpoint-v1/g2-policy-checkpoint-v1/reference-v1.json` — `24,378` bytes — expected SHA-256 `cf0fe3bb2e47ff3644f6ea2a8647ca47472e698e1fedd2f14f9156de063bb1c3`.\n  * `private/g2/checkpoint-v1/g2-policy-checkpoint-v1/state-v1.bin` — `4,321,431` bytes — expected SHA-256 `bb91fa17ea74101cc70e02b6ef85cefe8f90e096478bf63e1cc63384c23f3e5c`.\n* Bind reconstruction to `{VERIFIER.relative_to(ROOT).as_posix()}` at SHA-256 `{verifier_sha}` and its focused test at SHA-256 `{test_sha}`.\n* Reconstruct the checkpoint locally with sorted members, timestamp `1980-01-01 00:00:00`, stored compression, Unix creator system `3`, regular-file mode `0600`, zero flags and zero internal attributes.\n* Require the reconstructed package to be exactly `5,429,190` bytes with SHA-256 `{PACKAGE_SHA256}` and byte-for-byte equal to the approved local checkpoint.\n* If and only if every member and reconstructed package identity matches, record source-bundle version 2 as acceptable through verified extracted-checkpoint delivery and deterministic local reconstruction. Do not modify or create a Kaggle dataset version.\n* May write only local scratch files, the verification report, and local decision/task/gate/project-status/progress metadata needed to record the result.\n* Prepare the exact notebook-wrapper contract and separate approval text after a pass. Do not create, save, or run a notebook under this approval.\n* Do not access, read, hash, parse, copy, stage, transfer, upload, or download any replay body or agent log.\n* Do not create, delete, update, upload to, or otherwise mutate any Kaggle dataset, notebook, model, benchmark task, or competition submission. Retain `ashok205/new-benchmark-task-b1c52` unchanged as incident evidence.\n* Do not materialize labels, construct an optimizer, perform optimizer steps, launch training or evaluation, use GPU or TPU, mutate or promote a model, or submit to the competition.\n* Do not make a Git commit or push.\n* Stop after exact verification is recorded and notebook-wrapper approval text is prepared.\n* Fail closed immediately if any dataset, version, privacy, status, path, file, byte count, SHA-256, reconstruction, request, script, evidence, or authorization identity differs."""
    approval_text_sha = hashlib.sha256((approval_text + "\n").encode("utf-8")).hexdigest()
    review = {
        "schema_version": 1,
        "record_id": "e01-source-bundle-v2-checkpoint-directory-verification-contract-review-v1",
        "source_path": REVIEW.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "status": "PASS_READY_UNAUTHORIZED",
        "request_path": REQUEST.relative_to(ROOT).as_posix(),
        "request_sha256": request_sha,
        "dataset": request["dataset"],
        "remote_members": remote_members,
        "verifier_path": VERIFIER.relative_to(ROOT).as_posix(),
        "verifier_sha256": verifier_sha,
        "test_path": TEST.relative_to(ROOT).as_posix(),
        "test_sha256": test_sha,
        "focused_tests": {"passed": 3, "failed": 0},
        "local_reconstruction": {
            "status": reconstruction_status,
            "package_bytes": PACKAGE_BYTES,
            "package_sha256": PACKAGE_SHA256,
            "byte_for_byte_equal_to_approved_local_package": True,
        },
        "selected_remediation": "verify_only_four_remote_members_then_accept_version_2_with_deterministic_local_checkpoint_reconstruction",
        "source_bundle_version_3_required": False,
        "remote_downloads_performed_during_preparation": 0,
        "remote_mutations_performed_during_preparation": 0,
        "approval_text": approval_text,
        "approval_text_sha256": approval_text_sha,
        "boundary": {
            "replay_bodies": 0,
            "agent_logs": 0,
            "labels": 0,
            "optimizer_steps": 0,
            "training": False,
            "evaluation": False,
            "notebook": False,
            "model_mutation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
    }
    review["review_sha256"] = self_hash(review, "review_sha256")
    write_json(REVIEW, review)
    review_sha = sha(REVIEW)
    decision_text = f"""# DEC-039 — Prepare extracted-checkpoint verification remediation\n\n- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED\n- **Created:** {CREATED_AT}\n- **Dataset:** `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`\n- **Remote inventory:** `79` files / `7,645,589` bytes / `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`\n- **Verification request SHA-256:** `{request_sha}`\n- **Approval text SHA-256:** `{approval_text_sha}`\n\n## Decision\n\nPrepare, but do not consume, a four-file-only verification request for the checkpoint members expanded by Kaggle. Local proof establishes that the four approved member bytes can deterministically reconstruct the original sealed checkpoint package at `{PACKAGE_SHA256}` when the archive mode is `0600`.\n\nThis is the least-invasive path: preserve dataset versions 1 and 2, avoid version 3, verify only 5,428,744 non-replay bytes, and require reconstruction before any replay-body read. Source-bundle version 2 remains unaccepted until exact remote SHA-256 verification passes.\n\n## Boundaries\n\n- Remote files downloaded during preparation: `0`\n- Remote mutations: `0`\n- Replay bodies or agent logs accessed: `0`\n- Labels, optimizer steps, training, evaluation, or notebook execution: `0`\n- Model mutation, promotion, submission, commit, or push: none\n\n## Evidence\n\n- `{REQUEST.relative_to(ROOT).as_posix()}`\n- `{REVIEW.relative_to(ROOT).as_posix()}`\n- `{RAW_INVENTORY.relative_to(ROOT).as_posix()}`\n- `{INCIDENT.relative_to(ROOT).as_posix()}`\n- `{VERIFIER.relative_to(ROOT).as_posix()}`\n"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")
    decision_sha = sha(DECISION)

    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    decision_record = {
        "schema_version": 1,
        "record_id": "decision-dec-039",
        "decision_id": "DEC-039",
        "title": "Prepare extracted-checkpoint verification remediation",
        "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
        "created_at_utc": CREATED_AT,
        "decision": "Verify only the four expanded checkpoint members and accept source-bundle version 2 only after exact hashes reconstruct the original sealed ZIP.",
        "rationale": "This avoids a third dataset version and preserves the frozen production implementation while keeping the fail-before-replay checkpoint identity contract.",
        "request_path": REQUEST.relative_to(ROOT).as_posix(),
        "request_sha256": request_sha,
        "review_path": REVIEW.relative_to(ROOT).as_posix(),
        "review_sha256": review_sha,
        "review_self_hash": review["review_sha256"],
        "approval_text_sha256": approval_text_sha,
        "verifier_sha256": verifier_sha,
        "dataset_id": 11_501_808,
        "dataset_version": 2,
        "remote_files_to_verify": 4,
        "remote_bytes_to_verify": 5_428_744,
        "source_bundle_version_3_required": False,
        "optimizer_steps": 0,
        "training": False,
        "revisit_trigger": "The exact four-file verification approval is accepted or rejected, any bound remote identity changes, or a path-safe alternative is authorized.",
        "source_path": DECISION.relative_to(ROOT).as_posix(),
        "source_sha256": decision_sha,
    }
    upsert(decisions, "decision_id", "DEC-039", decision_record)
    write_json(DECISIONS, decisions)

    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    task_record = {
        "schema_version": 1,
        "record_id": "task-e01-source-bundle-v2-checkpoint-remediation-preparation-039",
        "task_id": "T-E01-SOURCE-BUNDLE-V2-CHECKPOINT-REMEDIATION-PREPARATION-039",
        "title": "Prepare source-bundle v2 checkpoint verification",
        "phase": "E01-B",
        "priority": 19,
        "status": "SUCCEEDED_VERIFICATION_READY_UNAUTHORIZED",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "completed_at_utc": CREATED_AT,
        "decision_id": "DEC-039",
        "decision_path": DECISION.relative_to(ROOT).as_posix(),
        "decision_sha256": decision_sha,
        "request_path": REQUEST.relative_to(ROOT).as_posix(),
        "request_sha256": request_sha,
        "review_path": REVIEW.relative_to(ROOT).as_posix(),
        "review_sha256": review_sha,
        "approval_text_sha256": approval_text_sha,
        "remote_files_downloaded": 0,
        "remote_mutations": 0,
        "replay_bodies": 0,
        "agent_logs": 0,
        "optimizer_steps": 0,
        "training": False,
        "notebook_wrapper_prepared": False,
        "done_when": "The exact four remote checkpoint members are downloaded and hash verified, the original package is reconstructed exactly, source-bundle version 2 is accepted, and notebook-wrapper approval text is prepared.",
        "blocker": "Exact approval is required before downloading the four checkpoint member files; source-bundle version 2 remains unaccepted and training remains blocked.",
    }
    upsert(tasks, "task_id", task_record["task_id"], task_record)
    write_json(TASKS, tasks)

    gate = json.loads(GATE.read_text(encoding="utf-8"))
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-039_EXTRACTED_CHECKPOINT_VERIFICATION_READY_UNAUTHORIZED"
    gate["authorization"] = "CORPUS_V3_FROZEN_RETAINED_REMEDIATION_CONSUMED_FOUR_FILE_CHECKPOINT_VERIFICATION_READY_NO_REMOTE_DOWNLOAD_REPLAY_LABELS_OPTIMIZER_TRAINING_OR_SUBMISSION_AUTHORIZED"
    gate["approved_next_action"] = f"Obtain exact approval for {REQUEST.relative_to(ROOT).as_posix()} at SHA-256 {request_sha}; download and hash only four checkpoint members, reconstruct the exact ZIP, then prepare notebook-wrapper approval. Do not mutate Kaggle or train."
    gate["blockers"] = [
        "Corpus v3 remains frozen at 362 episodes and 25056 policy-loss targets.",
        "Retained dataset ID 11514316/version 1 remains valid under consumed root-basename remediation.",
        "Source-bundle dataset ID 11501808/version 2 remains unaccepted until four extracted checkpoint member SHA-256 identities are verified and the original package is reconstructed exactly.",
        "Notebook wrapper, replay loading, labels, optimizer steps, training, evaluation, model promotion, and submission remain blocked.",
    ]
    gate["updated_at_utc"] = CREATED_AT
    check = {
        "name": "DEC-039 deterministic extracted checkpoint verification request",
        "status": "PASS",
        "evidence": REVIEW.relative_to(ROOT).as_posix(),
    }
    gate["technical_checks"] = [item for item in gate.get("technical_checks", []) if item.get("name") != check["name"]]
    gate["technical_checks"].append(check)
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = replace_prefix(project, "Last completed milestone:", "Last completed milestone: DEC-039 extracted-checkpoint verification remediation prepared")
    project = replace_prefix(project, "Current gate:", "Current gate: retained dataset valid; source-bundle v2 four-member verification request ready unauthorized; deterministic ZIP reconstruction proven locally; training blocked")
    project = replace_prefix(project, "Gold-path status:", "Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / RETAINED DATASET VALID / SOURCE BUNDLE V2 CHECKPOINT VERIFICATION READY UNAUTHORIZED / TEST SEALED / TRAINING BLOCKED")
    project = replace_prefix(project, "Next review required before:", "Next review required before: downloading the four source-bundle checkpoint members, accepting source-bundle v2, freezing/running a notebook wrapper, any replay-body read, label materialization, optimizer step, training/evaluation, model promotion, submission, commit, or push")
    section = f"""## DEC-039 Extracted-Checkpoint Verification Prepared\n\nSource-bundle dataset ID `11501808`, version `2`, remains unchanged, private and Ready at 79 files and 7,645,589 bytes. A four-file-only verification request is frozen at `{request_sha}`. It authorizes nothing currently.\n\nLocal positive and negative tests prove that the four expected checkpoint members reconstruct the exact original 5,429,190-byte package at `{PACKAGE_SHA256}` only under the frozen deterministic archive metadata. A successful remote verification would avoid dataset version 3 and allow notebook preflight to reconstruct the ZIP before any replay-body read.\n\nEvidence: `{REVIEW.relative_to(ROOT).as_posix()}` and `{DECISION.relative_to(ROOT).as_posix()}`.\n"""
    project = append_section(project, "## DEC-039 Extracted-Checkpoint Verification Prepared", section)
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress_section = f"""## DEC-039 Extracted-Checkpoint Verification Preparation\n\nThe least-invasive remediation was prepared without remote download or mutation. The exact request `{request_sha}` permits a later approval to download only four checkpoint members totaling 5,428,744 bytes, verify their SHA-256 identities, and reconstruct the original sealed package at `{PACKAGE_SHA256}`. Three focused tests passed, including extra-file and member-hash negative controls. Source-bundle version 2 remains unaccepted, no notebook wrapper was prepared, and training remains blocked.\n\nEvidence: `{REQUEST.relative_to(ROOT).as_posix()}`, `{REVIEW.relative_to(ROOT).as_posix()}`, and `{DECISION.relative_to(ROOT).as_posix()}`.\n"""
    progress = append_section(progress, "## DEC-039 Extracted-Checkpoint Verification Preparation", progress_section)
    PROGRESS.write_text(progress, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "PASS_VERIFICATION_REQUEST_READY_UNAUTHORIZED",
                "request_sha256": request_sha,
                "review_sha256": review_sha,
                "review_self_hash": review["review_sha256"],
                "decision_sha256": decision_sha,
                "approval_text_sha256": approval_text_sha,
                "verifier_sha256": verifier_sha,
                "test_sha256": test_sha,
                "remote_files_downloaded": 0,
                "remote_mutations": 0,
                "replay_bodies": 0,
                "optimizer_steps": 0,
                "training": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
