from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g3.bc_production import (
    CORPUS_MANIFEST_FILE_SHA256,
    CORPUS_MANIFEST_PATH,
    CORPUS_MANIFEST_SELF_HASH,
    canonical_listing_hash,
    metadata_schedule_bound,
    retained_publication_records,
    training_records,
)


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-05T10:20:00Z"
DECISION_ID = "DEC-033"
PUBLICATION_REQUEST = ROOT / "configs/e01_production_bc_input_publication_request_v1.json"
TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v1.json"
PUBLICATION_REVIEW = ROOT / "reports/artifacts/e01-production-bc-input-publication-contract-review-v1.json"
TRAINING_REVIEW = ROOT / "reports/artifacts/e01-production-recurrent-bc-contract-review-v1.json"
DECISION = ROOT / "docs/decisions/DEC-033_E01_PRODUCTION_BC_REQUESTS_PREPARED.md"
MANIFEST = ROOT / CORPUS_MANIFEST_PATH
CORPUS_REVIEW = ROOT / "reports/artifacts/e01-approved-replay-corpus-review-v3.json"
INCIDENT = ROOT / "reports/incidents/e01-production-bc-preparation-local-replay-read-v1.json"
PUBLICATION_RUNNER = ROOT / "scripts/e01_prepare_production_bc_input_dataset.py"
TRAINING_RUNNER = ROOT / "scripts/e01_production_recurrent_bc.py"
IMPLEMENTATION = ROOT / "src/ptcg_rl/g3/bc_production.py"
TEST = ROOT / "tests/g3/test_bc_production.py"
CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
CARD_DATA = ROOT / "private/assets/official/EN_Card_Data.csv"
CANARY_REVIEW = ROOT / "reports/artifacts/e01-bc-engineering-canary-execution-review-v1.json"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"


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
        following = text.find("\n### ", start + len(heading))
        if following < 0:
            following = len(text)
        return text[:start] + section.rstrip() + "\n" + text[following:]
    return text.rstrip() + "\n\n" + section.rstrip() + "\n"


def main() -> None:
    manifest = load(MANIFEST)
    if sha(MANIFEST) != CORPUS_MANIFEST_FILE_SHA256:
        raise ValueError("corpus-v3 file hash differs")
    if manifest.get("manifest_sha256") != CORPUS_MANIFEST_SELF_HASH:
        raise ValueError("corpus-v3 self hash differs")
    publication_records = list(retained_publication_records(manifest))
    production_records = list(training_records(manifest))
    schedule_bound = metadata_schedule_bound(production_records, 32)
    if schedule_bound != {
        "legacy_chunk_upper": 211,
        "primary_stratum_chunk_upper_max": 206,
        "balanced_steps_per_epoch_upper": 211,
    }:
        raise ValueError("metadata schedule bound differs")

    implementation_sha = sha(IMPLEMENTATION)
    publication_runner_sha = sha(PUBLICATION_RUNNER)
    training_runner_sha = sha(TRAINING_RUNNER)
    test_sha = sha(TEST)

    publication_request = {
        "schema_version": 1,
        "record_id": "e01-production-bc-input-publication-request-v1",
        "source_path": PUBLICATION_REQUEST.relative_to(ROOT).as_posix(),
        "decision_id": DECISION_ID,
        "created_at_utc": CREATED_AT,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "purpose": "Publish only the retained flg/Dries train and validation replay bodies required by production recurrent BC into one private versioned Kaggle dataset. Test replays remain sealed.",
        "corpus_manifest": {
            "path": CORPUS_MANIFEST_PATH,
            "sha256": CORPUS_MANIFEST_FILE_SHA256,
            "self_hash": CORPUS_MANIFEST_SELF_HASH,
        },
        "runner": {
            "path": PUBLICATION_RUNNER.relative_to(ROOT).as_posix(),
            "sha256": publication_runner_sha,
        },
        "implementation": {
            "path": IMPLEMENTATION.relative_to(ROOT).as_posix(),
            "sha256": implementation_sha,
        },
        "publication": {
            "dataset_ref": "ashok205/kptcg-e01-production-bc-retained-inputs",
            "dataset_version": 1,
            "private": True,
            "files": 58,
            "bytes": 341559745,
            "train_files": 50,
            "train_bytes": 303098913,
            "validation_files": 8,
            "validation_bytes": 38460832,
            "test_files": 0,
            "test_bytes": 0,
            "listing_sha256": canonical_listing_hash(publication_records),
            "staging_outputs": [
                "dataset/episodes/<episode_id>.json",
                "dataset/dataset-metadata.json",
                "publication-report.json",
            ],
        },
        "records": publication_records,
        "authorization": {
            "replay_body_read": False,
            "copy": False,
            "stage": False,
            "private_dataset_create": False,
            "private_dataset_upload": False,
            "dataset_update": False,
            "agent_log_read": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "requested_authorization_for_later_exact_approval": {
            "replay_body_read": True,
            "copy": True,
            "stage": True,
            "private_dataset_create": True,
            "private_dataset_upload": True,
            "maximum_replay_files": 58,
            "maximum_replay_bytes": 341559745,
            "test_replay_files": 0,
            "agent_log_read": False,
            "label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "stop_conditions": [
            "Do not execute without a separate user approval receipt bound to this request file SHA-256 and the publication runner SHA-256.",
            "Fail before staging if any selected source path, episode ID, split, byte count, SHA-256, listing order, total count or total bytes differs.",
            "Never select, read, copy, stage or upload a test-split replay.",
            "Never publish an agent log, label, checkpoint, code file or other non-replay payload under this request.",
            "Stop after the exact private dataset is uploaded and independently inventory-verified; do not train.",
        ],
    }
    write_json(PUBLICATION_REQUEST, publication_request)
    publication_request_sha = sha(PUBLICATION_REQUEST)

    overlay_records = [
        {
            "path": IMPLEMENTATION.relative_to(ROOT).as_posix(),
            "bytes": IMPLEMENTATION.stat().st_size,
            "sha256": implementation_sha,
        },
        {
            "path": TRAINING_RUNNER.relative_to(ROOT).as_posix(),
            "bytes": TRAINING_RUNNER.stat().st_size,
            "sha256": training_runner_sha,
        },
        {
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "bytes": MANIFEST.stat().st_size,
            "sha256": sha(MANIFEST),
        },
        {
            "path": CORPUS_REVIEW.relative_to(ROOT).as_posix(),
            "bytes": CORPUS_REVIEW.stat().st_size,
            "sha256": sha(CORPUS_REVIEW),
        },
        {
            "path": CHECKPOINT.relative_to(ROOT).as_posix(),
            "bytes": CHECKPOINT.stat().st_size,
            "sha256": sha(CHECKPOINT),
        },
    ]
    overlay_listing_sha = canonical_listing_hash(overlay_records)

    training_request = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-request-v1",
        "source_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
        "decision_id": DECISION_ID,
        "created_at_utc": CREATED_AT,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "purpose": "Train the sealed 970,022-parameter recurrent semantic policy with full-compound behavior cloning on corpus-v3 train records, select by validation NLL, keep test records sealed, and emit only evaluation-ineligible candidate checkpoints.",
        "corpus_manifest": {
            "path": CORPUS_MANIFEST_PATH,
            "sha256": CORPUS_MANIFEST_FILE_SHA256,
            "self_hash": CORPUS_MANIFEST_SELF_HASH,
        },
        "corpus_review": {
            "path": CORPUS_REVIEW.relative_to(ROOT).as_posix(),
            "sha256": sha(CORPUS_REVIEW),
            "self_hash": load(CORPUS_REVIEW)["review_sha256"],
        },
        "publication_dependency": {
            "request_path": PUBLICATION_REQUEST.relative_to(ROOT).as_posix(),
            "request_sha256": publication_request_sha,
            "dataset_ref": publication_request["publication"]["dataset_ref"],
            "dataset_version": 1,
            "dataset_id": None,
            "status": "PLANNED_UNPUBLISHED",
            "files": 58,
            "bytes": 341559745,
            "listing_sha256": publication_request["publication"]["listing_sha256"],
            "exact_live_dataset_id_and_inventory_must_be_bound_by_later_approval": True,
        },
        "source_bundle_dependency": {
            "base_dataset_ref": "ashok205/kptcg-e01-majkel-corpus-review-inputs",
            "base_dataset_id": 11501808,
            "base_dataset_version": 1,
            "base_dataset_total_bytes": 1637620,
            "base_source_bundle_sha256": "ceec17e0a76097af8f25de4ecddfa627f509f44a58bb67e2528a2c0696f3a97a",
            "required_dataset_version": 2,
            "status": "PLANNED_UNPUBLISHED_VERSION_UPDATE",
            "overlay_records": overlay_records,
            "overlay_files": len(overlay_records),
            "overlay_bytes": sum(item["bytes"] for item in overlay_records),
            "overlay_listing_sha256": overlay_listing_sha,
            "exact_version_2_inventory_must_be_bound_by_later_approval": True,
        },
        "runner": {
            "path": TRAINING_RUNNER.relative_to(ROOT).as_posix(),
            "sha256": training_runner_sha,
        },
        "implementation": {
            "path": IMPLEMENTATION.relative_to(ROOT).as_posix(),
            "sha256": implementation_sha,
        },
        "focused_tests": {
            "path": TEST.relative_to(ROOT).as_posix(),
            "sha256": test_sha,
        },
        "assets": {
            "initial_checkpoint": {
                "path": CHECKPOINT.relative_to(ROOT).as_posix(),
                "bytes": CHECKPOINT.stat().st_size,
                "sha256": sha(CHECKPOINT),
                "architecture_sha256": "aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf",
                "model_schema_sha256": "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68",
                "card_table_sha256": "7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0",
                "trainable_parameters": 970022,
            },
            "card_data": {
                "path": CARD_DATA.relative_to(ROOT).as_posix(),
                "bytes": CARD_DATA.stat().st_size,
                "sha256": sha(CARD_DATA),
            },
            "engineering_canary_review": {
                "path": CANARY_REVIEW.relative_to(ROOT).as_posix(),
                "sha256": sha(CANARY_REVIEW),
                "self_hash": load(CANARY_REVIEW)["review_sha256"],
                "cumulative_optimizer_steps": 64,
                "checkpoint_promotable": False,
            },
        },
        "dataset_sources": {
            "retained_private": {
                "ref": publication_request["publication"]["dataset_ref"],
                "version": 1,
                "dataset_id": None,
                "expected_files": 58,
                "expected_bytes": 341559745,
                "expected_listing_sha256": publication_request["publication"]["listing_sha256"],
            },
            "august_3_daily": {
                "ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03",
                "version": 1,
                "dataset_id": 11490894,
                "reported_total_bytes": 21451850075,
                "declared_json_bytes": 21451459378,
                "json_files": 4720,
                "inventory_sha256": "3f1d4c27d13eb3308d9efe3e32cb45a543439711e1dfd1f51dd30baa6ba0436d",
            },
            "august_4_daily": {
                "ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04",
                "version": 1,
                "dataset_id": 11506836,
                "reported_total_bytes": 21457813826,
                "inventory_files": 4812,
                "inventory_sha256": "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77",
                "manifest_sha256": "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1",
            },
        },
        "corpus": {
            "record_listing_sha256": canonical_listing_hash(production_records),
            "selected_episodes": 316,
            "selected_bytes": sum(item["bytes"] for item in production_records),
            "train_episodes": 284,
            "train_bytes": 1190672201,
            "train_teacher_active_requests": 20984,
            "train_forced_recurrent_calls": 1338,
            "train_policy_loss_targets": 19646,
            "validation_episodes": 32,
            "validation_bytes": 137322701,
            "validation_teacher_active_requests": 2471,
            "validation_forced_recurrent_calls": 153,
            "validation_policy_loss_targets": 2318,
            "test_episodes_sealed": 46,
            "test_bytes_sealed": 189787857,
            "test_policy_loss_targets_sealed": 3092,
            "records_embedded": False,
            "records_reconstructed_from_frozen_manifest_at_execution": True,
        },
        "sampling": {
            "policy": "deterministic balanced recurrent chunks",
            "primary_teacher": "majkel",
            "primary_chunks_per_step": 4,
            "one_primary_chunk_per_seat_result_stratum": True,
            "legacy_chunks_per_step": 1,
            "primary_fraction": 0.8,
            "legacy_fraction": 0.2,
            "legacy_teachers": ["flg", "dries"],
            "recurrent_sequence_length": 32,
            "forced_calls_advance_recurrence": True,
            "forced_calls_create_policy_loss": False,
            "ordering_seed": 20260805,
            "test_split_inaccessible": True,
        },
        "metadata_schedule_bound": schedule_bound,
        "execution": {
            "platform": "private_kaggle_cpu",
            "internet": False,
            "gpu": False,
            "tpu": False,
            "torch_num_threads": 4,
            "torch_num_interop_threads": 1,
            "data_workers": 0,
            "seed": 20260805,
            "optimizer": "AdamW",
            "learning_rate": 0.0001,
            "weight_decay": 0.0,
            "maximum_gradient_norm": 1.0,
            "recurrent_sequence_length": 32,
            "primary_chunks_per_step": 4,
            "legacy_chunks_per_step": 1,
            "maximum_epochs": 4,
            "maximum_optimizer_steps": 844,
            "maximum_wall_seconds": 14400,
            "validation_before_training": True,
            "validation_after_each_epoch": True,
            "checkpoint_after_each_epoch": True,
            "candidate_selection": "lowest validation mean compound-action NLL; ties choose earliest epoch",
            "candidate_requires_strict_improvement_over_initial_by": 0.000001,
            "initial_checkpoint_may_win": True,
            "test_evaluation": False,
        },
        "output_contract": {
            "private_kaggle_working_directory": "/kaggle/working/e01-production-recurrent-bc-v1",
            "metadata_outputs": ["execution-report.json"],
            "checkpoint_outputs": [
                "epoch-1.pt",
                "epoch-1.pt.manifest.json",
                "epoch-2.pt",
                "epoch-2.pt.manifest.json",
                "epoch-3.pt",
                "epoch-3.pt.manifest.json",
                "epoch-4.pt",
                "epoch-4.pt.manifest.json",
            ],
            "training_label_outputs": 0,
            "replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "production_model_promotion": False,
            "candidate_eligible_for_separate_evaluation_only": True,
        },
        "acceptance": {
            "all_losses_finite": True,
            "all_gradients_finite": True,
            "zero_invalid_targets": True,
            "zero_mask_violations": True,
            "zero_duplicate_ordered_selections": True,
            "zero_split_leakage": True,
            "zero_test_replay_reads": True,
            "optimizer_step_cap_respected": True,
            "candidate_not_promoted": True,
            "policy_competence_not_claimed": True,
            "separate_held_out_and_on_policy_evaluation_required": True,
        },
        "authorization": {
            "source_bundle_dataset_update": False,
            "retained_dataset_publication": False,
            "replay_body_read": False,
            "agent_log_read": False,
            "label_materialization": False,
            "external_compute": False,
            "private_kaggle_cpu": False,
            "optimizer_steps": False,
            "training": False,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "model_mutation": False,
            "model_promotion": False,
            "competence_evaluation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "requested_authorization_for_later_exact_approval": {
            "source_bundle_dataset_update": True,
            "retained_dataset_publication_must_already_pass": True,
            "replay_body_read": True,
            "private_kaggle_cpu": True,
            "external_compute": True,
            "optimizer_steps": True,
            "training": True,
            "maximum_optimizer_steps": 844,
            "maximum_epochs": 4,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "agent_log_read": False,
            "label_materialization": False,
            "model_promotion": False,
            "competence_evaluation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "stop_conditions": [
            "Do not execute without a separate approval receipt bound to this request file SHA-256 and the production runner SHA-256.",
            "Do not execute until the retained private dataset and source-bundle version 2 are published, READY, independently inventoried, and bound by live dataset IDs and hashes in the approval receipt.",
            "Fail before the first replay-body read if any request, runner, implementation, corpus, checkpoint, card-data, dataset, inventory, source-bundle or publication identity differs.",
            "Read only corpus-v3 train and validation records; never resolve or open a test record.",
            "Stop at four epochs, 844 optimizer steps, the wall cap, or any earlier contract failure.",
            "Do not materialize labels, promote a checkpoint, claim competence, run held-out/on-policy evaluation, submit, commit or push.",
        ],
    }
    write_json(TRAINING_REQUEST, training_request)
    training_request_sha = sha(TRAINING_REQUEST)

    publication_review = {
        "schema_version": 1,
        "record_id": "e01-production-bc-input-publication-contract-review-v1",
        "source_path": PUBLICATION_REVIEW.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "reviewed_decision": DECISION_ID,
        "status": "PASS",
        "decision": "ACCEPT_EXACT_58_FILE_RETAINED_TRAIN_VALIDATION_PRIVATE_PUBLICATION_REQUEST_READY_UNAUTHORIZED",
        "request": {
            "path": PUBLICATION_REQUEST.relative_to(ROOT).as_posix(),
            "sha256": publication_request_sha,
            "status": "READY_UNAUTHORIZED",
        },
        "runner": publication_request["runner"],
        "implementation": publication_request["implementation"],
        "selection": {
            "files": 58,
            "bytes": 341559745,
            "train_files": 50,
            "validation_files": 8,
            "test_files": 0,
            "listing_sha256": publication_request["publication"]["listing_sha256"],
            "source_values_derived_from_manifest_metadata_only": True,
        },
        "boundary": {
            "replay_bodies_read_during_preparation": 0,
            "agent_logs_read": 0,
            "files_copied_or_staged": 0,
            "kaggle_dataset_created_or_updated": False,
            "labels": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "review_sha256": None,
    }
    publication_review["review_sha256"] = self_hash(publication_review, "review_sha256")
    write_json(PUBLICATION_REVIEW, publication_review)

    training_review = {
        "schema_version": 1,
        "record_id": "e01-production-recurrent-bc-contract-review-v1",
        "source_path": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
        "created_at_utc": CREATED_AT,
        "reviewed_decision": DECISION_ID,
        "status": "PASS",
        "decision": "ACCEPT_IMPLEMENTATION_BOUND_PRODUCTION_RECURRENT_BC_REQUEST_READY_UNAUTHORIZED_BLOCKED_INPUT_PUBLICATION",
        "request": {
            "path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "sha256": training_request_sha,
            "status": "READY_UNAUTHORIZED",
        },
        "runner": training_request["runner"],
        "implementation": training_request["implementation"],
        "corpus": training_request["corpus"],
        "schedule": {
            "balanced_primary_legacy_fraction": "80/20",
            "one_majkel_chunk_per_stratum_per_step": True,
            "metadata_steps_per_epoch_upper": 211,
            "maximum_epochs": 4,
            "maximum_optimizer_steps": 844,
            "test_split_sealed": True,
        },
        "dependencies": {
            "retained_dataset": "PLANNED_UNPUBLISHED",
            "source_bundle_version_2": "PLANNED_UNPUBLISHED_VERSION_UPDATE",
            "august_3_daily": "PINNED_VERSION_1",
            "august_4_daily": "PINNED_VERSION_1",
        },
        "boundary": {
            "replay_bodies_read_during_preparation": 0,
            "agent_logs_read": 0,
            "data_loading_path_executed": False,
            "optimizer_constructed": False,
            "optimizer_steps": 0,
            "training": False,
            "evaluation": False,
            "kaggle_dataset_created_or_updated": False,
            "kaggle_notebook_created_or_run": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "review_sha256": None,
    }
    training_review["review_sha256"] = self_hash(training_review, "review_sha256")
    write_json(TRAINING_REVIEW, training_review)

    decision_text = f"""# DEC-033 - Prepare Production Recurrent BC Requests Without Replay Access

- Status: accepted request preparation; publication and training unauthorized
- Date: 2026-08-05

## Decision

Accept the exact manifest-only preparation of one private replay-input publication request and one implementation-bound production recurrent BC request. Preserve corpus v3 at 362 episodes and 25,056 policy-loss targets. The publication request contains only 58 retained flg/Dries train/validation replay records and excludes all test records. The training request uses 284 train episodes and 32 validation episodes, seals all 46 test episodes, and caps a deterministic four-epoch 80/20 primary/legacy schedule at 844 optimizer steps.

## Frozen requests

- Replay input publication: `{PUBLICATION_REQUEST.relative_to(ROOT)}`, SHA-256 `{publication_request_sha}`.
- Production recurrent BC: `{TRAINING_REQUEST.relative_to(ROOT)}`, SHA-256 `{training_request_sha}`.
- Publication runner: `{PUBLICATION_RUNNER.relative_to(ROOT)}`, SHA-256 `{publication_runner_sha}`.
- Training runner: `{TRAINING_RUNNER.relative_to(ROOT)}`, SHA-256 `{training_runner_sha}`.
- Shared implementation: `{IMPLEMENTATION.relative_to(ROOT)}`, SHA-256 `{implementation_sha}`.

## Dependencies

The retained replay dataset does not exist yet. The existing private corpus-review source bundle remains version 1 and lacks the sealed initial checkpoint and new production runner. The training request therefore binds an exact version-2 overlay plan and cannot execute until both private dataset operations are separately approved, completed, and independently inventoried.

## Authorization boundary

Preparation used corpus-manifest metadata only and performed zero replay-body reads, zero agent-log reads, zero copies, zero staging, zero uploads, zero label materialization, zero optimizer construction or steps, zero training/evaluation, zero model mutation/promotion, zero submission, and zero Git commit/push. Any publication or execution requires a separate exact approval.
"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")
    decision_sha = sha(DECISION)

    decisions = load(DECISIONS)
    decisions = [item for item in decisions if item.get("decision_id") != DECISION_ID]
    decisions.append(
        {
            "schema_version": 1,
            "record_id": "decision-dec-033",
            "decision_id": DECISION_ID,
            "title": "Prepare production recurrent BC requests without replay access",
            "status": "ACCEPTED_REQUESTS_READY_UNAUTHORIZED_BLOCKED_INPUT_PUBLICATION",
            "created_at_utc": CREATED_AT,
            "producer": "decision-sidecar",
            "decision": "Freeze the exact 58-file retained replay publication request and the exact implementation-bound production recurrent BC request without accessing replay bodies or starting training.",
            "rationale": "Corpus v3 passes the production data floors, the canary passed engineering checks, and manifest metadata is sufficient to define the next exact publication and training scopes while keeping test data sealed.",
            "source_path": DECISION.relative_to(ROOT).as_posix(),
            "source_sha256": decision_sha,
            "publication_request_path": PUBLICATION_REQUEST.relative_to(ROOT).as_posix(),
            "publication_request_sha256": publication_request_sha,
            "publication_review_path": PUBLICATION_REVIEW.relative_to(ROOT).as_posix(),
            "publication_review_sha256": sha(PUBLICATION_REVIEW),
            "publication_review_self_hash": publication_review["review_sha256"],
            "training_request_path": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "training_request_sha256": training_request_sha,
            "training_review_path": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
            "training_review_sha256": sha(TRAINING_REVIEW),
            "training_review_self_hash": training_review["review_sha256"],
            "publication_runner_sha256": publication_runner_sha,
            "training_runner_sha256": training_runner_sha,
            "implementation_sha256": implementation_sha,
            "revisit_trigger": "Either exact request is approved or rejected, a planned private dataset identity becomes available, or any corpus, code, checkpoint, data-source, schedule, compute or authorization identity changes.",
        }
    )
    write_json(DECISIONS, decisions)

    tasks = load(TASKS)
    for item in tasks:
        if item.get("task_id") == "T-E01-PRODUCTION-BC-REQUEST-032":
            item["status"] = "SUPERSEDED_BY_DEC_033"
            item["updated_at_utc"] = CREATED_AT
            item["blocker"] = "DEC-033 prepared exact manifest-only requests. Publication and training remain unauthorized."
    tasks = [item for item in tasks if item.get("task_id") != "T-E01-PRODUCTION-BC-PREPARATION-033"]
    tasks.append(
        {
            "schema_version": 1,
            "record_id": "task-e01-production-bc-preparation-033",
            "task_id": "T-E01-PRODUCTION-BC-PREPARATION-033",
            "title": "Prepare exact production BC publication and training requests",
            "phase": "E01-B",
            "priority": 18,
            "status": "SUCCEEDED",
            "created_at_utc": CREATED_AT,
            "updated_at_utc": CREATED_AT,
            "completed_at_utc": CREATED_AT,
            "decision_id": DECISION_ID,
            "decision_path": DECISION.relative_to(ROOT).as_posix(),
            "decision_sha256": decision_sha,
            "corpus_v3_manifest": CORPUS_MANIFEST_PATH,
            "corpus_v3_manifest_sha256": CORPUS_MANIFEST_FILE_SHA256,
            "publication_request": PUBLICATION_REQUEST.relative_to(ROOT).as_posix(),
            "publication_request_sha256": publication_request_sha,
            "publication_request_ready": True,
            "publication_authorized": False,
            "training_request": TRAINING_REQUEST.relative_to(ROOT).as_posix(),
            "training_request_sha256": training_request_sha,
            "training_request_ready": True,
            "training_authorized": False,
            "publication_files": 58,
            "publication_bytes": 341559745,
            "train_episodes": 284,
            "validation_episodes": 32,
            "test_episodes_sealed": 46,
            "maximum_optimizer_steps": 844,
            "optimizer_steps_executed": 0,
            "replay_bodies_read_during_preparation": 0,
            "done_when": "Both exact requests, runners, contract reviews and ledgers are frozen without replay access or execution.",
            "blocker": "Retained replay dataset version 1 and source-bundle version 2 are unpublished; all publication and training operations require separate exact approvals.",
        }
    )
    write_json(TASKS, tasks)

    gate = load(GATE)
    gate["status"] = "BLOCKED"
    gate["decision"] = "DEC-033_PRODUCTION_BC_PUBLICATION_AND_TRAINING_REQUESTS_READY_UNAUTHORIZED"
    gate["authorization"] = "CORPUS_V3_FROZEN_REQUESTS_READY_NO_DATASET_PUBLICATION_REPLAY_ACCESS_LABELS_OPTIMIZER_OR_TRAINING_AUTHORIZED"
    gate["approved_next_action"] = (
        f"Request separate exact approval for {PUBLICATION_REQUEST.relative_to(ROOT)} at SHA-256 {publication_request_sha}; "
        "publish and independently verify only the 58 retained train/validation replay bodies, update the private source bundle to the exact bound version-2 overlay, and stop before training."
    )
    gate["blockers"] = [
        "Corpus v3 passes the frozen data floors at 362 episodes and 25056 policy-loss targets.",
        "The exact 58-file / 341559745-byte retained private replay dataset is READY_UNAUTHORIZED and does not yet exist.",
        "The existing private source bundle is version 1; the exact version-2 code/metadata/checkpoint overlay is planned but unpublished.",
        "Production recurrent BC is READY_UNAUTHORIZED with a four-epoch / 844-step cap; labels, optimizer steps, training, evaluation, promotion and submission remain blocked.",
    ]
    checks = gate.setdefault("technical_checks", [])
    checks = [
        item
        for item in checks
        if item.get("name")
        not in {
            "DEC-033 exact retained replay input-publication request",
            "DEC-033 implementation-bound production recurrent BC request",
        }
    ]
    checks.extend(
        [
            {
                "name": "DEC-033 exact retained replay input-publication request",
                "status": "PASS",
                "evidence": PUBLICATION_REVIEW.relative_to(ROOT).as_posix(),
            },
            {
                "name": "DEC-033 implementation-bound production recurrent BC request",
                "status": "PASS",
                "evidence": TRAINING_REVIEW.relative_to(ROOT).as_posix(),
            },
        ]
    )
    gate["technical_checks"] = checks
    gate["updated_at_utc"] = CREATED_AT
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = replace_prefix(
        project,
        "Last completed milestone:",
        "Last completed milestone: DEC-033 froze exact manifest-only retained-input publication and implementation-bound production recurrent BC requests",
    )
    project = replace_prefix(
        project,
        "Current gate:",
        f"Current gate: retained publication request `{PUBLICATION_REQUEST.relative_to(ROOT)}` at SHA-256 `{publication_request_sha}` and production BC request `{TRAINING_REQUEST.relative_to(ROOT)}` at SHA-256 `{training_request_sha}` are READY_UNAUTHORIZED",
    )
    project = replace_prefix(
        project,
        "Gold-path status:",
        "Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / 58-FILE PRIVATE INPUT PUBLICATION READY UNAUTHORIZED / PRODUCTION BC 4 EPOCHS, 844-STEP CAP READY UNAUTHORIZED / TEST SEALED / TRAINING BLOCKED",
    )
    project = replace_prefix(
        project,
        "Next review required before:",
        "Next review required before: retained replay publication, source-bundle version update, any replay-body read/copy/upload, label materialization, production optimizer step, training/evaluation, GPU/TPU use, model promotion, final D1 deck freeze, submission, commit or push",
    )
    section = f"""### DEC-033 - Production BC requests prepared without replay access

- Retained replay publication request: `{PUBLICATION_REQUEST.relative_to(ROOT)}`, SHA-256 `{publication_request_sha}`; exactly 58 train/validation bodies / 341559745 bytes; zero test records.
- Production recurrent BC request: `{TRAINING_REQUEST.relative_to(ROOT)}`, SHA-256 `{training_request_sha}`; 284 train episodes / 19646 targets, 32 validation episodes / 2318 targets, and 46 sealed test episodes / 3092 targets.
- Deterministic sampling is four Majkel seat/result chunks plus one retained flg/Dries chunk per step, at most 211 steps per epoch, four epochs and 844 optimizer steps.
- The existing source bundle requires one exact version-2 overlay containing the new implementation, runner, corpus-v3 metadata and sealed checkpoint. It remains unpublished.
- Preparation read zero replay bodies and agent logs and performed zero copy, staging, upload, label, optimizer, training, evaluation, model, submission or Git operations.
"""
    project = append_section(project, "### DEC-033 - Production BC requests prepared without replay access", section)
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress = replace_prefix(
        progress,
        "Current gate:",
        f"Current gate: **DEC-033 exact retained publication request `{publication_request_sha}` and production BC request `{training_request_sha}` are READY_UNAUTHORIZED**",
    )
    progress = replace_prefix(
        progress,
        "Gold-path status:",
        "Gold-path status: **CORPUS V3 362 / 25,056; 58-FILE RETAINED INPUT PUBLICATION READY UNAUTHORIZED; PRODUCTION BC 4 EPOCHS / 844 STEPS READY UNAUTHORIZED; TEST SEALED; TRAINING BLOCKED**",
    )
    progress = replace_prefix(
        progress,
        "Latest completed milestone:",
        "Latest completed milestone: **manifest-only production BC request preparation completed with zero replay access and zero training**",
    )
    progress_section = f"""## 2026-08-05 — DEC-033 production BC requests prepared

- Exact retained replay publication: 58 train/validation files, 341559745 bytes, zero test files; request SHA-256 `{publication_request_sha}`.
- Exact production recurrent BC: 284 train episodes / 19646 targets, 32 validation episodes / 2318 targets, 46 test episodes sealed; request SHA-256 `{training_request_sha}`.
- Sampling: one Majkel chunk from each of four seat/result strata plus one retained legacy chunk per step; maximum 211 steps per epoch, four epochs, 844 optimizer steps.
- Publication runner SHA-256 `{publication_runner_sha}`; training runner SHA-256 `{training_runner_sha}`; implementation SHA-256 `{implementation_sha}`.
- No replay body or agent log was opened. No dataset, notebook or model was created or updated. Labels, optimizer steps, training, evaluation, promotion, submission, commit and push remain unauthorized.
"""
    progress = append_section(progress, "## 2026-08-05 — DEC-033 production BC requests prepared", progress_section)
    PROGRESS.write_text(progress, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "PASS_DEC033_REQUESTS_PREPARED_METADATA_ONLY",
                "publication_request_sha256": publication_request_sha,
                "training_request_sha256": training_request_sha,
                "publication_review_sha256": sha(PUBLICATION_REVIEW),
                "publication_review_self_hash": publication_review["review_sha256"],
                "training_review_sha256": sha(TRAINING_REVIEW),
                "training_review_self_hash": training_review["review_sha256"],
                "decision_sha256": decision_sha,
                "implementation_sha256": implementation_sha,
                "publication_runner_sha256": publication_runner_sha,
                "training_runner_sha256": training_runner_sha,
                "replay_bodies_read": 0,
                "agent_logs_read": 0,
                "optimizer_steps": 0,
                "training": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
