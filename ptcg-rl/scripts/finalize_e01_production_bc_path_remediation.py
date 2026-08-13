from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g3.bc_production_v2 import (
    CORPUS_MANIFEST_FILE_SHA256,
    CORPUS_MANIFEST_PATH,
    CORPUS_MANIFEST_SELF_HASH,
    canonical_listing_hash,
    metadata_schedule_bound,
    retained_publication_records,
    training_records,
    validate_retained_dataset_remediation_request,
    validate_training_request,
)


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-06T07:23:00Z"
DECISION_ID = "DEC-035"
TASK_ID = "T-E01-PRODUCTION-BC-PATH-REMEDIATION-PREPARATION-035"

MANIFEST = ROOT / CORPUS_MANIFEST_PATH
CORPUS_REVIEW = ROOT / "reports/artifacts/e01-approved-replay-corpus-review-v3.json"
OLD_TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v1.json"
REMEDIATION_REQUEST = ROOT / "configs/e01_production_bc_retained_dataset_remediation_request_v1.json"
TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"
REMEDIATION_REVIEW = ROOT / "reports/artifacts/e01-production-bc-retained-dataset-remediation-contract-review-v1.json"
TRAINING_REVIEW = ROOT / "reports/artifacts/e01-production-recurrent-bc-contract-review-v2.json"
DECISION = ROOT / "docs/decisions/DEC-035_E01_PRODUCTION_BC_ROOT_BASENAME_REMEDIATION_PREPARED.md"
IMPLEMENTATION = ROOT / "src/ptcg_rl/g3/bc_production_v2.py"
RUNNER = ROOT / "scripts/e01_production_recurrent_bc_v2.py"
TEST = ROOT / "tests/g3/test_bc_production.py"
CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
CARD_DATA = ROOT / "private/assets/official/EN_Card_Data.csv"
RAW_EVIDENCE = ROOT / "reports/artifacts/raw/e01-production-bc-retained-dataset-verification-20260805-v1.json"
EXECUTION_REVIEW = ROOT / "reports/artifacts/e01-production-bc-input-publication-execution-review-v1.json"
INCIDENT = ROOT / "reports/incidents/e01-production-bc-retained-dataset-path-flattening-v1.json"
DEC034 = ROOT / "docs/decisions/DEC-034_E01_PRODUCTION_BC_RETAINED_DATASET_PATH_FLATTENING.md"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

EXPECTED = {
    RAW_EVIDENCE: "1a08b64f1f492a09536fb4894797b1e3cd59fa34283532f83ec538280157c991",
    EXECUTION_REVIEW: "ad80752c394408153a4ea1db4790b100cc6a3444cc63e8a388e0431a76b53765",
    INCIDENT: "7d4f993cd5f2b85413590708f50e94d5a6cd7fc53b7abb97f58af86aec50f7c3",
    DEC034: "28c4b3ea1c256ce68507481729850c93bd4fc70c4d1dc63f1ab2f108387172c8",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    raw = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def replace_prefix(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return "\n".join(lines) + "\n"
    raise ValueError(f"missing line prefix: {prefix}")


def append_section(text: str, heading: str, section: str) -> str:
    if heading in text:
        start = text.index(heading)
        following = text.find("\n## ", start + len(heading))
        if following < 0:
            following = len(text)
        return text[:start] + section.rstrip() + "\n" + text[following:]
    return text.rstrip() + "\n\n" + section.rstrip() + "\n"


def upsert(records: list[dict[str, Any]], key: str, value: str, record: dict[str, Any]) -> None:
    matches = [index for index, item in enumerate(records) if item.get(key) == value]
    if len(matches) > 1:
        raise ValueError(f"duplicate ledger identity {key}={value}")
    if matches:
        records[matches[0]] = record
    else:
        records.append(record)


def evidence_binding(path: Path, self_field: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    if self_field is not None:
        value = load(path)
        result["self_hash"] = value[self_field]
        result["self_hash_field"] = self_field
    return result


def main() -> None:
    if sha(MANIFEST) != CORPUS_MANIFEST_FILE_SHA256:
        raise ValueError("corpus-v3 file hash differs")
    manifest = load(MANIFEST)
    if manifest.get("manifest_sha256") != CORPUS_MANIFEST_SELF_HASH:
        raise ValueError("corpus-v3 self-hash field differs")
    for path, expected in EXPECTED.items():
        if sha(path) != expected:
            raise ValueError(f"DEC-034 evidence hash differs: {path}")

    retained = list(retained_publication_records(manifest))
    production = list(training_records(manifest))
    if len(retained) != 58 or sum(item["bytes"] for item in retained) != 341559745:
        raise ValueError("retained corpus aggregate differs")
    if len(production) != 316:
        raise ValueError("production corpus aggregate differs")
    retained_training = [item for item in production if item["source"] == "retained_private"]
    if len(retained_training) != 58 or any(
        item["dataset_path"] != f"{item['episode_id']}.json" for item in retained_training
    ):
        raise ValueError("v2 retained root-basename mapping differs")
    schedule_bound = metadata_schedule_bound(production, 32)
    if schedule_bound != {
        "legacy_chunk_upper": 211,
        "primary_stratum_chunk_upper_max": 206,
        "balanced_steps_per_epoch_upper": 211,
    }:
        raise ValueError("metadata schedule bound differs")

    dataset = {
        "ref": "ashok205/kptcg-e01-production-bc-retained-inputs",
        "dataset_id": 11514316,
        "version": 1,
        "private": True,
        "status": "READY",
        "files": 58,
        "bytes": 341559745,
        "remote_inventory_sha256": "d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43",
        "path_contract": "root_basename",
    }
    remediation_records = [
        {
            "episode_id": int(item["episode_id"]),
            "split": str(item["split"]),
            "remote_name": f"{int(item['episode_id'])}.json",
            "bytes": int(item["bytes"]),
            "sha256": str(item["sha256"]),
        }
        for item in retained
    ]
    remediation_request = {
        "schema_version": 1,
        "record_id": "e01-production-bc-retained-dataset-remediation-request-v1",
        "source_path": REMEDIATION_REQUEST.relative_to(ROOT).as_posix(),
        "decision_id": DECISION_ID,
        "created_at_utc": CREATED_AT,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "purpose": "Adopt the already-created private retained dataset using its verified root-level replay basenames, without deleting, versioning, re-uploading, downloading, or rereading any replay body.",
        "corpus_manifest": {
            "path": CORPUS_MANIFEST_PATH,
            "sha256": CORPUS_MANIFEST_FILE_SHA256,
            "self_hash": CORPUS_MANIFEST_SELF_HASH,
        },
        "dataset": dataset,
        "records": remediation_records,
        "remediation_method": "contract_only_adopt_verified_root_basenames",
        "evidence": {
            "raw_verification": evidence_binding(RAW_EVIDENCE, "evidence_sha256"),
            "execution_review": evidence_binding(EXECUTION_REVIEW, "review_sha256"),
            "incident": evidence_binding(INCIDENT, "incident_sha256"),
            "decision": evidence_binding(DEC034),
        },
        "authorization": {
            "accept_existing_dataset_as_dependency": False,
            "renew_training_contract": False,
            "replay_body_read": False,
            "remote_replay_download": False,
            "dataset_delete": False,
            "dataset_create": False,
            "dataset_version_create": False,
            "dataset_upload": False,
            "agent_log_read": False,
            "source_bundle_update": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "evaluation": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "requested_authorization_for_later_exact_approval": {
            "accept_existing_dataset_as_dependency": True,
            "renew_training_contract": True,
            "dataset_id": 11514316,
            "dataset_version": 1,
            "remote_inventory_sha256": dataset["remote_inventory_sha256"],
            "path_contract": "root_basename",
            "replay_body_read": False,
            "remote_replay_download": False,
            "dataset_delete": False,
            "dataset_create": False,
            "dataset_version_create": False,
            "dataset_upload": False,
            "agent_log_read": False,
            "source_bundle_update": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "evaluation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "stop_conditions": [
            "Do not consume this remediation without a separate exact user approval bound to this request SHA-256 and dataset ID 11514316/version 1.",
            "Do not delete, replace, version, upload to, or download from the retained dataset under this request.",
            "Do not open or hash any local or remote replay body while consuming this metadata-only remediation.",
            "Fail closed if the dataset identity, privacy, Ready status, file count, byte total, remote inventory hash, corpus-v3 identity, or DEC-034 evidence differs.",
            "Stop after adopting the root-basename contract and renewing the production BC request; source-bundle publication and training remain separately gated.",
        ],
    }
    write_json(REMEDIATION_REQUEST, remediation_request)
    remediation_request_sha = sha(REMEDIATION_REQUEST)
    validate_retained_dataset_remediation_request(ROOT, REMEDIATION_REQUEST)

    implementation_sha = sha(IMPLEMENTATION)
    runner_sha = sha(RUNNER)
    test_sha = sha(TEST)
    old_training = load(OLD_TRAINING_REQUEST)
    training_request = copy.deepcopy(old_training)
    training_request["record_id"] = "e01-production-recurrent-bc-request-v2"
    training_request["source_path"] = TRAINING_REQUEST.relative_to(ROOT).as_posix()
    training_request["decision_id"] = DECISION_ID
    training_request["created_at_utc"] = CREATED_AT
    training_request["purpose"] = "Train the sealed recurrent semantic policy on corpus-v3 using the verified root-basename retained dataset contract, while keeping test records sealed and all candidates evaluation-only."
    training_request["corpus"]["record_listing_sha256"] = canonical_listing_hash(production)
    training_request["implementation"] = {
        "path": IMPLEMENTATION.relative_to(ROOT).as_posix(),
        "sha256": implementation_sha,
    }
    training_request["runner"] = {
        "path": RUNNER.relative_to(ROOT).as_posix(),
        "sha256": runner_sha,
    }
    training_request["focused_tests"] = {
        "path": TEST.relative_to(ROOT).as_posix(),
        "sha256": test_sha,
    }
    training_request["dataset_sources"]["retained_private"] = {
        "ref": dataset["ref"],
        "dataset_id": dataset["dataset_id"],
        "version": dataset["version"],
        "private": dataset["private"],
        "status": dataset["status"],
        "files": dataset["files"],
        "bytes": dataset["bytes"],
        "remote_inventory_sha256": dataset["remote_inventory_sha256"],
        "path_contract": dataset["path_contract"],
    }
    training_request.pop("publication_dependency", None)
    training_request["retained_dataset_dependency"] = {
        "status": "READY_REMEDIATION_UNAUTHORIZED",
        "dataset": dataset,
        "remediation_request_path": REMEDIATION_REQUEST.relative_to(ROOT).as_posix(),
        "remediation_request_sha256": remediation_request_sha,
        "exact_remediation_approval_required": True,
    }
    requested = training_request["requested_authorization_for_later_exact_approval"]
    requested.pop("retained_dataset_publication_must_already_pass", None)
    requested["retained_dataset_remediation_must_be_exactly_approved"] = True
    training_request["output_contract"]["private_kaggle_working_directory"] = "/kaggle/working/e01-production-recurrent-bc-v2"

    overlay_paths = [
        IMPLEMENTATION,
        RUNNER,
        MANIFEST,
        CORPUS_REVIEW,
        CHECKPOINT,
        REMEDIATION_REQUEST,
        RAW_EVIDENCE,
        EXECUTION_REVIEW,
        INCIDENT,
        DEC034,
    ]
    overlay_records = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha(path),
        }
        for path in overlay_paths
    ]
    source_bundle = training_request["source_bundle_dependency"]
    source_bundle["overlay_records"] = overlay_records
    source_bundle["overlay_files"] = len(overlay_records)
    source_bundle["overlay_bytes"] = sum(item["bytes"] for item in overlay_records)
    source_bundle["overlay_listing_sha256"] = canonical_listing_hash(overlay_records)
    source_bundle["status"] = "PLANNED_UNPUBLISHED_VERSION_UPDATE"
    training_request["stop_conditions"] = [
        "Do not execute without a separate approval receipt bound to this request SHA-256, the v2 runner SHA-256, the v2 implementation SHA-256, and an exact notebook-wrapper SHA-256.",
        "Do not execute until the retained dataset remediation request is exactly approved and the private source bundle version 2 is published, Ready, independently inventoried, and bound in the approval receipt.",
        "Fail before the first replay-body read if any request, remediation, runner, implementation, corpus, checkpoint, card-data, dataset, inventory, source-bundle, notebook, split, or authorization identity differs.",
        "Resolve retained records only by the exact verified root-level <episode_id>.json names; read only corpus-v3 train and validation records and never resolve a test record.",
        "Stop at four epochs, 844 optimizer steps, the wall cap, or any earlier contract failure.",
        "Do not materialize labels, promote a checkpoint, claim competence, run held-out/on-policy evaluation, submit, commit, or push.",
    ]
    write_json(TRAINING_REQUEST, training_request)
    training_request_sha = sha(TRAINING_REQUEST)
    validate_training_request(ROOT, TRAINING_REQUEST)

    remediation_review = {
        "schema_version": 1,
        "record_id": "e01-production-bc-retained-dataset-remediation-contract-review-v1",
        "source_path": REMEDIATION_REVIEW.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "decision_id": DECISION_ID,
        "status": "PASS_READY_UNAUTHORIZED",
        "request_path": REMEDIATION_REQUEST.relative_to(ROOT).as_posix(),
        "request_sha256": remediation_request_sha,
        "dataset": dataset,
        "records": 58,
        "bytes": 341559745,
        "train_records": 50,
        "validation_records": 8,
        "test_records": 0,
        "checks": {
            "corpus_v3_identity": "PASS",
            "dec034_evidence_hashes": "PASS",
            "remote_dataset_identity": "PASS",
            "root_basename_inventory": "PASS",
            "no_remote_mutation_authorized": "PASS",
            "no_replay_read_or_download_authorized": "PASS",
            "no_training_authorized": "PASS",
        },
        "replay_bodies_read": 0,
        "remote_replay_bodies_downloaded": 0,
        "dataset_mutations": 0,
        "optimizer_steps": 0,
        "training": False,
        "review_sha256": None,
    }
    remediation_review["review_sha256"] = self_hash(remediation_review, "review_sha256")
    write_json(REMEDIATION_REVIEW, remediation_review)

    training_review = {
        "schema_version": 2,
        "record_id": "e01-production-recurrent-bc-contract-review-v2",
        "source_path": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "decision_id": DECISION_ID,
        "status": "PASS_READY_UNAUTHORIZED_BLOCKED_REMEDIATION_AND_SOURCE_BUNDLE",
        "request_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
        "request_sha256": training_request_sha,
        "implementation_path": IMPLEMENTATION.relative_to(ROOT).as_posix(),
        "implementation_sha256": implementation_sha,
        "runner_path": RUNNER.relative_to(ROOT).as_posix(),
        "runner_sha256": runner_sha,
        "focused_tests_sha256": test_sha,
        "remediation_request_sha256": remediation_request_sha,
        "retained_dataset": dataset,
        "train_episodes": 284,
        "validation_episodes": 32,
        "test_episodes_sealed": 46,
        "train_policy_loss_targets": 19646,
        "validation_policy_loss_targets": 2318,
        "maximum_epochs": 4,
        "maximum_optimizer_steps": 844,
        "source_bundle_overlay_files": len(overlay_records),
        "source_bundle_overlay_bytes": sum(item["bytes"] for item in overlay_records),
        "source_bundle_overlay_listing_sha256": canonical_listing_hash(overlay_records),
        "checks": {
            "root_basename_retained_mapping": "PASS",
            "dataset_id_version_privacy_status_bound": "PASS",
            "remote_inventory_hash_bound": "PASS",
            "corpus_split_and_target_counts": "PASS",
            "balanced_80_20_schedule_bound": "PASS",
            "test_split_sealed": "PASS",
            "request_runner_implementation_hashes": "PASS",
            "source_bundle_overlay_exact": "PASS",
            "authorization_all_false": "PASS",
        },
        "replay_bodies_read": 0,
        "labels_materialized": 0,
        "optimizer_steps": 0,
        "training": False,
        "review_sha256": None,
    }
    training_review["review_sha256"] = self_hash(training_review, "review_sha256")
    write_json(TRAINING_REVIEW, training_review)

    remediation_review_sha = sha(REMEDIATION_REVIEW)
    training_review_sha = sha(TRAINING_REVIEW)
    decision_text = f"""# DEC-035 — Prepare root-basename retained-dataset remediation\n\n- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED\n- **Created:** {CREATED_AT}\n- **Dataset:** `ashok205/kptcg-e01-production-bc-retained-inputs` ID `11514316`, version `1`\n- **Remote inventory SHA-256:** `{dataset['remote_inventory_sha256']}`\n- **Remediation request SHA-256:** `{remediation_request_sha}`\n- **Renewed production BC request SHA-256:** `{training_request_sha}`\n\n## Decision\n\nPrepare, but do not consume, a contract-only remediation that adopts the already verified root-level `<episode_id>.json` names. Keep dataset version 1 unchanged. Renew production recurrent BC under versioned implementation and runner paths so historical DEC-033 hashes remain intact.\n\n## Boundaries\n\n- Replay bodies read or downloaded: `0`\n- Dataset deletions, creations, versions, or uploads: `0`\n- Agent logs read: `0`\n- Labels materialized: `0`\n- Optimizer steps or training: `0`\n- Model mutation, evaluation, promotion, submission, commit, or push: none\n\nThe remediation request requires a separate exact approval. Source-bundle version 2 and production training remain separately gated.\n\n## Evidence\n\n- `{REMEDIATION_REQUEST.relative_to(ROOT).as_posix()}`\n- `{REMEDIATION_REVIEW.relative_to(ROOT).as_posix()}`\n- `{TRAINING_REQUEST.relative_to(ROOT).as_posix()}`\n- `{TRAINING_REVIEW.relative_to(ROOT).as_posix()}`\n- `{DEC034.relative_to(ROOT).as_posix()}`\n"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")
    decision_sha = sha(DECISION)

    decisions = load(DECISIONS)
    decision_record = {
        "schema_version": 1,
        "record_id": "decision-dec-035",
        "decision_id": DECISION_ID,
        "title": "Prepare root-basename retained-dataset remediation",
        "created_at_utc": CREATED_AT,
        "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
        "decision": "Prepare a contract-only adoption of retained dataset ID 11514316/version 1 using verified root basenames, and renew production BC under versioned implementation and runner paths without executing either contract.",
        "rationale": "The private dataset is byte-count and basename exact, and accepting its actual root-level names avoids another 341559745-byte transfer while preserving fail-closed body verification at training execution.",
        "source_path": DECISION.relative_to(ROOT).as_posix(),
        "source_sha256": decision_sha,
        "remediation_request_path": REMEDIATION_REQUEST.relative_to(ROOT).as_posix(),
        "remediation_request_sha256": remediation_request_sha,
        "remediation_review_path": REMEDIATION_REVIEW.relative_to(ROOT).as_posix(),
        "remediation_review_sha256": remediation_review_sha,
        "remediation_review_self_hash": remediation_review["review_sha256"],
        "training_request_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
        "training_request_sha256": training_request_sha,
        "training_review_path": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
        "training_review_sha256": training_review_sha,
        "training_review_self_hash": training_review["review_sha256"],
        "dataset_id": 11514316,
        "dataset_version": 1,
        "remote_inventory_sha256": dataset["remote_inventory_sha256"],
        "implementation_sha256": implementation_sha,
        "runner_sha256": runner_sha,
        "revisit_trigger": "The exact remediation request is approved or rejected, source-bundle version 2 is published, or any dataset, corpus, code, checkpoint, schedule, compute, or authorization identity changes.",
        "producer": "decision-sidecar",
    }
    upsert(decisions, "decision_id", DECISION_ID, decision_record)
    write_json(DECISIONS, decisions)

    tasks = load(TASKS)
    task_record = {
        "schema_version": 1,
        "record_id": "task-e01-production-bc-path-remediation-preparation-035",
        "task_id": TASK_ID,
        "title": "Prepare retained dataset root-basename remediation",
        "phase": "E01-B",
        "priority": 19,
        "created_at_utc": CREATED_AT,
        "completed_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "status": "SUCCEEDED",
        "decision_id": DECISION_ID,
        "decision_path": DECISION.relative_to(ROOT).as_posix(),
        "decision_sha256": decision_sha,
        "done_when": "A metadata-only remediation request and renewed implementation-bound production BC request are frozen without replay access or remote mutation.",
        "blocker": "The remediation request, source-bundle version 2, notebook wrapper, and production training each require later exact approvals and live identity binding.",
        "dataset_id": 11514316,
        "dataset_version": 1,
        "dataset_private": True,
        "dataset_status": "READY",
        "dataset_files": 58,
        "dataset_bytes": 341559745,
        "remote_inventory_sha256": dataset["remote_inventory_sha256"],
        "remediation_request": REMEDIATION_REQUEST.relative_to(ROOT).as_posix(),
        "remediation_request_sha256": remediation_request_sha,
        "remediation_request_ready": True,
        "remediation_authorized": False,
        "training_request": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
        "training_request_sha256": training_request_sha,
        "training_request_ready": True,
        "training_authorized": False,
        "source_bundle_update_authorized": False,
        "replay_bodies_read": 0,
        "remote_replay_bodies_downloaded": 0,
        "dataset_mutations": 0,
        "optimizer_steps": 0,
        "training": False,
        "test_episodes_sealed": 46,
    }
    upsert(tasks, "task_id", TASK_ID, task_record)
    write_json(TASKS, tasks)

    gate = load(GATE)
    gate["updated_at_utc"] = CREATED_AT
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-035_ROOT_BASENAME_REMEDIATION_AND_PRODUCTION_BC_V2_READY_UNAUTHORIZED"
    gate["authorization"] = "CORPUS_V3_FROZEN_REMEDIATION_READY_NO_DATASET_MUTATION_REPLAY_ACCESS_SOURCE_BUNDLE_LABELS_OPTIMIZER_TRAINING_OR_SUBMISSION_AUTHORIZED"
    gate["approved_next_action"] = f"Obtain exact approval for {REMEDIATION_REQUEST.relative_to(ROOT).as_posix()} at SHA-256 {remediation_request_sha}; consume only the metadata-only root-basename adoption, then separately approve and publish source-bundle version 2 before any training."
    gate["blockers"] = [
        "Corpus v3 remains frozen at 362 episodes and 25056 policy-loss targets.",
        f"Root-basename remediation request {remediation_request_sha} is READY_UNAUTHORIZED for private dataset ID 11514316/version 1.",
        f"Renewed production recurrent BC request {training_request_sha} is READY_UNAUTHORIZED and blocked on exact remediation approval plus private source-bundle version 2.",
        "Production labels, replay loading, optimizer steps, training, evaluation, model promotion, and submission remain blocked.",
    ]
    checks = gate.setdefault("technical_checks", [])
    checks = [item for item in checks if item.get("name") not in {
        "DEC-035 retained dataset root-basename remediation request",
        "DEC-035 renewed implementation-bound production recurrent BC request",
    }]
    checks.extend([
        {
            "name": "DEC-035 retained dataset root-basename remediation request",
            "status": "PASS",
            "evidence": REMEDIATION_REVIEW.relative_to(ROOT).as_posix(),
        },
        {
            "name": "DEC-035 renewed implementation-bound production recurrent BC request",
            "status": "PASS",
            "evidence": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
        },
    ])
    gate["technical_checks"] = checks
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = replace_prefix(project, "Last updated UTC:", "Last updated UTC: 2026-08-06")
    project = replace_prefix(project, "Last completed milestone:", "Last completed milestone: DEC-035 prepared exact root-basename remediation and renewed production recurrent BC v2 contracts")
    project = replace_prefix(project, "Current gate:", f"Current gate: remediation request `{REMEDIATION_REQUEST.relative_to(ROOT).as_posix()}` at SHA-256 `{remediation_request_sha}` and renewed production BC request `{TRAINING_REQUEST.relative_to(ROOT).as_posix()}` at SHA-256 `{training_request_sha}` are READY_UNAUTHORIZED")
    project = replace_prefix(project, "Gold-path status:", "Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / RETAINED DATASET ID 11514316 V1 ROOT-BASENAME REMEDIATION READY UNAUTHORIZED / PRODUCTION BC V2 4 EPOCHS, 844-STEP CAP READY UNAUTHORIZED / TEST SEALED / TRAINING BLOCKED")
    project = replace_prefix(project, "Next review required before:", "Next review required before: consuming the root-basename remediation, source-bundle version-2 publication, any replay-body read, label materialization, optimizer step, training/evaluation, GPU/TPU use, model promotion, submission, commit, or push")
    section = f"""## DEC-035 Root-Basename Remediation Prepared\n\nPrivate dataset `ashok205/kptcg-e01-production-bc-retained-inputs`, ID `11514316`, version `1`, remains unchanged, private and Ready with 58 root-level replay basenames and 341,559,745 bytes. The contract-only remediation request is `{remediation_request_sha}`. It adopts those verified root basenames without deleting, versioning, uploading to, downloading from, or rereading the dataset.\n\nProduction recurrent BC v2 is frozen at `{training_request_sha}` under versioned implementation `{implementation_sha}` and runner `{runner_sha}`. It keeps the 284/32 train-validation split, 46 sealed test episodes, deterministic 80/20 recurrent sampling, four epochs and an 844-step cap. Remediation consumption, source-bundle version 2, notebook execution and training all remain separately unauthorized.\n\nEvidence: `{REMEDIATION_REVIEW.relative_to(ROOT).as_posix()}`, `{TRAINING_REVIEW.relative_to(ROOT).as_posix()}`, and `{DECISION.relative_to(ROOT).as_posix()}`.\n"""
    project = append_section(project, "## DEC-035 Root-Basename Remediation Prepared", section)
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress = replace_prefix(progress, "Current gate:", f"Current gate: **DEC-035 remediation request `{remediation_request_sha}` and renewed production BC v2 request `{training_request_sha}` are READY_UNAUTHORIZED**")
    progress = replace_prefix(progress, "Gold-path status:", "Gold-path status: **CORPUS V3 362 / 25,056; RETAINED DATASET 11514316 V1 ROOT-BASENAME REMEDIATION READY UNAUTHORIZED; PRODUCTION BC V2 4 EPOCHS / 844 STEPS READY UNAUTHORIZED; TEST SEALED; TRAINING BLOCKED**")
    progress = replace_prefix(progress, "Latest completed milestone:", "Latest completed milestone: **metadata-only root-basename remediation and production BC v2 contract preparation completed with zero replay access and zero remote mutation**")
    progress_section = f"""## DEC-035 Root-Basename Remediation Preparation\n\nDataset ID `11514316`, version `1`, was not changed. The exact 58-file, 341,559,745-byte root-level inventory remains bound by SHA-256 `{dataset['remote_inventory_sha256']}`. The new metadata-only remediation request is `{remediation_request_sha}` and requires separate exact approval.\n\nThe renewed production recurrent BC request is `{training_request_sha}`, implementation `{implementation_sha}`, runner `{runner_sha}`. No replay body or agent log was read, no dataset was mutated, no label was materialized, and no optimizer, training, evaluation, model, submission, commit or push operation occurred.\n"""
    progress = append_section(progress, "## DEC-035 Root-Basename Remediation Preparation", progress_section)
    PROGRESS.write_text(progress, encoding="utf-8")

    print(json.dumps({
        "status": "PASS_DEC035_REMEDIATION_PREPARED_METADATA_ONLY",
        "remediation_request_sha256": remediation_request_sha,
        "remediation_review_sha256": remediation_review_sha,
        "remediation_review_self_hash": remediation_review["review_sha256"],
        "training_request_sha256": training_request_sha,
        "training_review_sha256": training_review_sha,
        "training_review_self_hash": training_review["review_sha256"],
        "implementation_sha256": implementation_sha,
        "runner_sha256": runner_sha,
        "focused_tests_sha256": test_sha,
        "source_bundle_overlay_files": len(overlay_records),
        "source_bundle_overlay_bytes": sum(item["bytes"] for item in overlay_records),
        "source_bundle_overlay_listing_sha256": canonical_listing_hash(overlay_records),
        "decision_sha256": decision_sha,
        "dataset_mutations": 0,
        "replay_bodies_read": 0,
        "optimizer_steps": 0,
        "training": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
