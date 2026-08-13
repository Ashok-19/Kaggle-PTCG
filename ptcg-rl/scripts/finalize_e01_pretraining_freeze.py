from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-04T14:45:26Z"

LIVE_PATH = ROOT / "reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json"
PROBE_REVIEW_PATH = ROOT / "reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json"
BASE_CORPUS_REVIEW_PATH = ROOT / "reports/artifacts/e01-approved-replay-corpus-review-v1.json"
MODEL_PATH = ROOT / "reports/artifacts/g2-policy-v1.json"
BC_CANARY_PATH = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-027_PRETRAINING_FREEZE_AND_MAJKEL_PRIMARY_SOURCE.md"
REQUEST_PATH = ROOT / "configs/e01_majkel_corpus_expansion_request_v1.json"
REQUEST_REVIEW_PATH = ROOT / "reports/artifacts/e01-majkel-corpus-expansion-contract-review-v1.json"
LAUNCH_PLAN_PATH = ROOT / "configs/e01_pretraining_launch_plan_v1.json"
FREEZE_REVIEW_PATH = ROOT / "reports/artifacts/e01-pretraining-freeze-review-v1.json"

PRIMARY_TEAM_ID = 16_374_395
PRIMARY_TEAM_NAME = "Majkel1337"
PRIMARY_SUBMISSION_ID = 55_186_239
PRIMARY_DECK_SHA256 = "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278"
MODEL_ARCHITECTURE_SHA256 = "aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf"
PROBE_IDS = {89_651_832, 89_802_438}
PROBE_BYTES = 832_877
EXPECTED_INTERSECTION_FILES = 271
EXPECTED_INTERSECTION_BYTES = 1_031_040_048
EXPECTED_NEW_FILES = 269
EXPECTED_NEW_BYTES = 1_030_207_171


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return sha256_bytes(canonical_bytes(payload))


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(pretty_bytes(value))
    temporary.replace(path)


def stratum(teacher_index: int, teacher_reward: int | float) -> str:
    return f"seat_{teacher_index}_{'win' if float(teacher_reward) > 0 else 'loss'}"


def episode_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    opponents = raw.get("opponents")
    if not isinstance(opponents, list) or len(opponents) != 1:
        raise ValueError("Majkel candidate must contain exactly one opponent")
    opponent = opponents[0]
    if not isinstance(opponent, Mapping):
        raise ValueError("opponent metadata differs")
    episode_id = int(raw["episode_id"])
    teacher_index = int(raw["teacher_index"])
    teacher_reward = int(raw["teacher_reward"])
    if teacher_index not in (0, 1) or teacher_reward not in (-1, 1):
        raise ValueError("teacher seat or reward differs")
    if int(raw["teacher_submission_id"]) != PRIMARY_SUBMISSION_ID:
        raise ValueError("teacher submission differs")
    if raw["teacher_team"] != PRIMARY_TEAM_NAME:
        raise ValueError("teacher team differs")
    return {
        "create_time": raw["create_time"],
        "declared_bytes": int(raw["manifest_size_bytes"]),
        "end_time": raw["end_time"],
        "episode_id": episode_id,
        "file_name": f"{episode_id}.json",
        "opponent_player_index": int(opponent["index"]),
        "opponent_reward": int(opponent["reward"]),
        "opponent_submission_id": int(opponent["submission_id"]),
        "opponent_team_id": int(opponent["team_id"]),
        "opponent_team_name": opponent["team_name"],
        "state": "COMPLETED",
        "stratum": stratum(teacher_index, teacher_reward),
        "teacher_player_index": teacher_index,
        "teacher_reward": teacher_reward,
        "teacher_submission_id": PRIMARY_SUBMISSION_ID,
        "teacher_team_id": PRIMARY_TEAM_ID,
        "teacher_team_name": PRIMARY_TEAM_NAME,
        "type": "EPISODE_TYPE_PUBLIC",
    }


def build_decision() -> str:
    return f"""# DEC-027 - Freeze the pretraining configuration and Majkel primary source

Status: Accepted

Date: 2026-08-04

## Decision

Freeze the initial learned-policy configuration so training can begin immediately after the remaining exact approvals and data review complete.

### Primary teacher and initial training deck

- Primary teacher: `{PRIMARY_TEAM_NAME}`
- Stable team ID: `{PRIMARY_TEAM_ID}`
- Stable active submission ID: `{PRIMARY_SUBMISSION_ID}`
- Initial behavior-cloning deck: Mega Lucario ex
- Exact teacher deck multiset SHA-256: `{PRIMARY_DECK_SHA256}`
- Accepted observed source modules for body review: `1.32.2` and `1.32.3`, tracked separately

The latest refreshed leaderboard still places Majkel1337 first. Volatile score values are monitoring signals only; team, submission, dataset version, episode ID, declared bytes, body hash, deck hash, module and contract results are the frozen identities.

This locks Majkel as the **primary training teacher** and the reviewed Mega Lucario deck as the **initial BC training deck**. It does not declare the final submitted deck. Final D1 selection remains contingent on held-out, cross-deck and important-matchup evaluation.

### Model architecture

Freeze the existing G2 compact recurrent semantic policy for initial BC and the first bounded PPO stage:

- 970,022 trainable parameters
- architecture SHA-256 `{MODEL_ARCHITECTURE_SHA256}`
- public-information actor and critic
- entity attention, public-event and recurrent GRUs
- ragged semantic option scoring
- STOP-aware autoregressive compound-action decoder

No architecture change is permitted before a qualified ablation or a demonstrated blocker. This prevents architecture churn from delaying training.

### Data policy

Retain the immutable qualified multi-teacher corpus v1 as a diversity and anti-overfitting set:

- 66 qualified episodes
- 7,140 policy-loss targets
- 50 / 8 / 8 train / validation / test split
- 402 forced singleton requests retained for recurrence and excluded from policy loss

Prepare one exact private-Kaggle-CPU request covering the remaining 269 files in the 271-file Majkel August 3 version-1 intersection. Reuse the two already reviewed probe files rather than reading or exporting them again. The newly read replay-body cap is exactly `{EXPECTED_NEW_BYTES:,}` bytes. No replay body is exported from the notebook.

A Majkel episode qualifies for corpus v2 only when all of the following pass:

- exact team and submission binding;
- schema 1, CABT `1.0.0`, and module `1.32.2` or `1.32.3`;
- exact Mega Lucario deck hash `{PRIMARY_DECK_SHA256}`;
- current-card construction compatibility;
- complete terminal records and lag-aligned legal compound actions;
- no duplicate episode or content hash;
- forced singleton calls advance recurrence but create no policy loss.

All four seat/result strata remain eligible. Training sampling is Majkel-dominant while retaining at least 20% legacy qualified-teacher sampling. Majkel examples are sampled equally across the four seat/result strata as far as available. New qualified episodes receive deterministic episode-level 80/10/10 train/validation/test assignments stratified by module and seat/result using the frozen split seed `20260804`.

The data is called final only after the exact request is approved, all candidate bodies are reviewed, corpus v2 is emitted, and the resulting episode and target counts are known. No unsupported target-count projection is treated as a guarantee.

### Training and gold sequence

Freeze the execution sequence:

1. Run the existing exact 64-step BC engineering canary after its separate approval.
2. In parallel, execute the exact 269-file Majkel corpus review after its separate approval.
3. Freeze corpus v2 and prepare a production recurrent BC request from its exact hashes and counts.
4. Run held-out and on-policy competence evaluation before production checkpoint promotion.
5. Only after BC competence, permit bounded KL/auxiliary-BC recurrent PPO, capped at 500,000 choices before another decision.
6. Run equal-budget deck/checkpoint tournament evaluation and freeze the final submission deck only after D1 thresholds pass.

Gold remains the objective, not a guarantee. The strategy is finalized; stage-specific execution budgets remain exact-approval gated.

## Authorization boundary

This decision authorizes only repository planning, deterministic metadata processing, request generation, contract review and tests. It does not authorize:

- the private Kaggle CPU read of the 269 named replay bodies;
- corpus promotion or training-label materialization;
- the 64 BC optimizer steps;
- production BC, PPO, self-play or any model mutation;
- GPU, TPU, Modal or paid compute;
- model or dataset publication;
- deck freeze for submission;
- competition submission, Git commit or Git push.

## Revisit trigger

Revisit if Majkel's active submission identity changes, the pinned daily source changes, the exact deck or module/action contract fails at scale, corpus v2 cannot meet training needs, the BC canary fails, a qualified ablation is proposed, or any production training, accelerator, model promotion, final deck freeze or submission scope is requested.
"""


def upsert_by(items: list[dict[str, Any]], key: str, value: str, item: dict[str, Any]) -> None:
    for index, existing in enumerate(items):
        if existing.get(key) == value:
            items[index] = item
            return
    items.append(item)


def replace_prefix(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"expected one line beginning {prefix!r}, found {len(matches)}")
    lines[matches[0]] = replacement
    return "\n".join(lines) + "\n"


def insert_before_heading(text: str, heading: str, block: str) -> str:
    if block.strip().splitlines()[0] in text:
        return text
    marker = f"\n{heading}\n"
    if marker not in text:
        raise ValueError(f"heading not found: {heading}")
    return text.replace(marker, f"\n{block.rstrip()}\n\n{heading}\n", 1)


def main() -> None:
    live = load(LIVE_PATH)
    probe_review = load(PROBE_REVIEW_PATH)
    base_corpus = load(BASE_CORPUS_REVIEW_PATH)
    model = load(MODEL_PATH)
    bc_canary = load(BC_CANARY_PATH)

    if live["current_rank_1_intersection"]["exact_count"] != EXPECTED_INTERSECTION_FILES:
        raise ValueError("Majkel intersection file count differs")
    if live["current_rank_1_intersection"]["total_bytes"] != EXPECTED_INTERSECTION_BYTES:
        raise ValueError("Majkel intersection bytes differ")
    if live["current_rank_1_intersection"]["submission_id"] != PRIMARY_SUBMISSION_ID:
        raise ValueError("Majkel submission differs")
    if live["current_rank_1_intersection"]["team_name"] != PRIMARY_TEAM_NAME:
        raise ValueError("Majkel team differs")
    if probe_review["status"] != "PASS":
        raise ValueError("Majkel probe review is not PASS")
    if probe_review["consistency"]["teacher_deck_multiset_sha256"] != PRIMARY_DECK_SHA256:
        raise ValueError("Majkel deck differs")
    if model["architecture_sha256"] != MODEL_ARCHITECTURE_SHA256:
        raise ValueError("model architecture differs")
    if model["trainable_parameters"] != 970_022:
        raise ValueError("model parameter count differs")
    if bc_canary["request_ready"] is not True or bc_canary["authorized"] is not False:
        raise ValueError("BC canary readiness differs")

    all_rows = [episode_row(item) for item in live["current_rank_1_intersection"]["episodes"]]
    if len(all_rows) != EXPECTED_INTERSECTION_FILES:
        raise ValueError("Majkel episode metadata count differs")
    if len({row["episode_id"] for row in all_rows}) != len(all_rows):
        raise ValueError("duplicate Majkel episode IDs")
    if sum(row["declared_bytes"] for row in all_rows) != EXPECTED_INTERSECTION_BYTES:
        raise ValueError("Majkel episode byte sum differs")

    existing = sorted(
        (row for row in all_rows if row["episode_id"] in PROBE_IDS),
        key=lambda row: row["episode_id"],
    )
    new_rows = sorted(
        (row for row in all_rows if row["episode_id"] not in PROBE_IDS),
        key=lambda row: row["episode_id"],
    )
    if len(existing) != 2 or sum(row["declared_bytes"] for row in existing) != PROBE_BYTES:
        raise ValueError("existing probe binding differs")
    if len(new_rows) != EXPECTED_NEW_FILES:
        raise ValueError("new Majkel file count differs")
    if sum(row["declared_bytes"] for row in new_rows) != EXPECTED_NEW_BYTES:
        raise ValueError("new Majkel byte cap differs")

    strata = Counter(row["stratum"] for row in all_rows)
    expected_strata = {
        "seat_0_loss": 34,
        "seat_0_win": 97,
        "seat_1_loss": 54,
        "seat_1_win": 86,
    }
    if dict(sorted(strata.items())) != expected_strata:
        raise ValueError("Majkel strata differ")

    decision_text = build_decision()
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(decision_text, encoding="utf-8")
    decision_sha = sha256_file(DECISION_PATH)

    request: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-corpus-expansion-request-v1",
        "source_path": "configs/e01_majkel_corpus_expansion_request_v1.json",
        "created_at_utc": NOW,
        "decision_id": "DEC-027",
        "decision_path": "docs/decisions/DEC-027_PRETRAINING_FREEZE_AND_MAJKEL_PRIMARY_SOURCE.md",
        "decision_sha256": decision_sha,
        "status": "READY_UNAUTHORIZED",
        "request_ready": True,
        "authorized": False,
        "authorization_consumed": False,
        "authorization_scope": "UNAUTHORIZED_EXACT_269_FILE_MAJKEL_PRIVATE_KAGGLE_CPU_BODY_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION_ONLY",
        "purpose": "Read exactly the remaining 269 files from the pinned Majkel daily dataset in a private Kaggle CPU notebook, reuse the two reviewed probe files without rereading them, perform deterministic body-level qualification, and finalize a hash-frozen corpus-v2 manifest and review containing only qualified episodes. Export metadata artifacts only and stop before labels or training.",
        "source": {
            "competition": "pokemon-tcg-ai-battle",
            "dataset_owner": "kaggle",
            "dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-08-03",
            "dataset_version": 1,
            "versioned_ref": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
            "live_refresh_path": str(LIVE_PATH.relative_to(ROOT)),
            "live_refresh_sha256": sha256_file(LIVE_PATH),
            "live_refresh_evidence_sha256": live["evidence_sha256"],
            "teacher_team_id": PRIMARY_TEAM_ID,
            "teacher_team_name": PRIMARY_TEAM_NAME,
            "teacher_submission_id": PRIMARY_SUBMISSION_ID,
            "latest_verified_rank": 1,
            "latest_verified_score_snapshot": 1251.0,
            "score_is_authorization_basis": False,
        },
        "selection": {
            "intersection_files": EXPECTED_INTERSECTION_FILES,
            "intersection_bytes": EXPECTED_INTERSECTION_BYTES,
            "existing_reviewed_files": 2,
            "existing_reviewed_bytes": PROBE_BYTES,
            "existing_reviewed_episode_ids": sorted(PROBE_IDS),
            "maximum_new_files": EXPECTED_NEW_FILES,
            "maximum_new_bytes": EXPECTED_NEW_BYTES,
            "balanced_source_strata": expected_strata,
            "persistent_replay_output_directory": None,
            "review_output_directory": "/kaggle/working/e01-majkel-corpus-review-v1",
            "overwrite_authorized": False,
            "replay_bodies_exported": False,
        },
        "execution": {
            "platform": "private_kaggle_cpu",
            "notebook_slug": "kptcg-e01-majkel-corpus-review-v1",
            "internet": False,
            "gpu": False,
            "tpu": False,
            "maximum_cpu_cores": 4,
            "maximum_wall_seconds": 10800,
            "competition_data_source": "pokemon-tcg-ai-battle",
            "dataset_data_source": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
            "verify_notebook_metadata_before_run": True,
            "inventory_actual_input_tree_before_body_reads": True,
            "derive_paths_from_observed_input_tree": True,
            "fail_closed_on_metadata_tree_mismatch": True,
            "output_files": [
                "e01-majkel-corpus-review-v1.json",
                "e01-approved-replay-corpus-manifest-v2.json",
                "e01-approved-replay-corpus-review-v2.json",
                "e01-majkel-corpus-review-v1-output-manifest.json",
            ],
            "replay_body_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
        },
        "episodes": new_rows,
        "requested_authorization": {
            "private_kaggle_cpu_execution": True,
            "named_replay_body_reads": True,
            "maximum_new_files": EXPECTED_NEW_FILES,
            "maximum_new_bytes": EXPECTED_NEW_BYTES,
            "qualified_only_corpus_v2_finalization": True,
            "replay_body_exports": False,
            "training_label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "model_promotion": False,
            "submission": False,
        },
        "review_boundary": {
            "count_only_schema_version": 1,
            "count_only_environment_name": "cabt",
            "count_only_environment_version": "1.0.0",
            "accepted_module_versions": ["1.32.2", "1.32.3"],
            "count_only_teacher_team_id": PRIMARY_TEAM_ID,
            "count_only_teacher_submission_id": PRIMARY_SUBMISSION_ID,
            "count_only_deck_multiset_sha256": PRIMARY_DECK_SHA256,
            "require_current_asset_construction_compatibility": "PASS",
            "require_action_alignment": "PASS",
            "require_terminal_statuses": ["DONE", "DONE"],
            "nonmatching_files_rejected_from_counts": True,
            "duplicate_episode_or_content_hash_rejected": True,
            "forced_calls_advance_recurrence": True,
            "forced_calls_create_policy_loss": False,
        },
        "corpus_v2_policy": {
            "retain_existing_qualified_corpus_v1": True,
            "base_qualified_episodes": 66,
            "base_policy_loss_targets": 7140,
            "primary_teacher_sampling_minimum_fraction": 0.8,
            "legacy_teacher_sampling_minimum_fraction": 0.2,
            "majkel_sampling_equal_across_available_seat_result_strata": True,
            "split_seed": 20260804,
            "split_algorithm": "SHA256(seed|module_version|stratum|episode_id), deterministic 80/10/10 within module-by-stratum groups",
            "episode_level_split_only": True,
            "corpus_final_only_after_body_review": True,
            "target_count_projection_is_guarantee": False,
        },
        "authorization": {
            "replay_transfer": False,
            "corpus_promotion": False,
            "training_label_materialization": False,
            "optimizer_steps": False,
            "training": False,
            "external_compute": False,
            "gpu": False,
            "tpu": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "stop_conditions": [
            "Any source dataset version, teacher team, submission, episode list, byte count, output path, deck hash, accepted module set, or authorization flag changes.",
            "Any named dataset file is missing, any unlisted body is read, notebook metadata and the observed input tree disagree, or any declared-byte check fails.",
            "Stop after body-level qualification, independent metadata verification, and qualified-only corpus-v2 manifest/review finalization; no label, optimizer, or training continuation is implied.",
        ],
    }
    write_json(REQUEST_PATH, request)
    request_sha = sha256_file(REQUEST_PATH)

    request_review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-corpus-expansion-contract-review-v1",
        "source_path": "reports/artifacts/e01-majkel-corpus-expansion-contract-review-v1.json",
        "created_at_utc": NOW,
        "producer": "scripts/finalize_e01_pretraining_freeze.py",
        "reviewed_decision": "DEC-027",
        "status": "PASS_READY_UNAUTHORIZED",
        "decision": "ACCEPT_EXACT_REMAINING_269_FILE_MAJKEL_BODY_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": decision_sha},
            "request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": request_sha},
            "live_refresh": {
                "path": str(LIVE_PATH.relative_to(ROOT)),
                "sha256": sha256_file(LIVE_PATH),
                "evidence_sha256": live["evidence_sha256"],
            },
            "probe_review": {
                "path": str(PROBE_REVIEW_PATH.relative_to(ROOT)),
                "sha256": sha256_file(PROBE_REVIEW_PATH),
                "review_sha256": probe_review["review_sha256"],
            },
        },
        "selection": {
            "intersection_files": EXPECTED_INTERSECTION_FILES,
            "intersection_bytes": EXPECTED_INTERSECTION_BYTES,
            "reused_reviewed_files": 2,
            "reused_reviewed_bytes": PROBE_BYTES,
            "new_files": EXPECTED_NEW_FILES,
            "new_bytes": EXPECTED_NEW_BYTES,
            "new_episode_ids_unique": len({row["episode_id"] for row in new_rows}) == EXPECTED_NEW_FILES,
            "new_declared_bytes_exact": sum(row["declared_bytes"] for row in new_rows) == EXPECTED_NEW_BYTES,
            "strata": expected_strata,
            "requested_platform": request["execution"]["platform"],
            "persistent_replay_output_directory": request["selection"]["persistent_replay_output_directory"],
            "replay_body_outputs": request["execution"]["replay_body_outputs"],
        },
        "freeze": {
            "primary_teacher_locked": True,
            "initial_bc_training_deck_locked": True,
            "final_submission_deck_locked": False,
            "model_architecture_locked": True,
            "macro_training_strategy_locked": True,
            "data_selection_universe_locked": True,
            "training_corpus_final": False,
        },
        "authorization": request["authorization"],
        "next_action": "REQUEST_SEPARATE_EXPLICIT_APPROVAL_FOR_THE_EXACT_PRIVATE_KAGGLE_CPU_269_FILE_BODY_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION;_THE_64_STEP_BC_CANARY_REMAINS_A_SEPARATE_EXACT_APPROVAL",
    }
    request_review["review_sha256"] = self_hash(request_review, "review_sha256")
    write_json(REQUEST_REVIEW_PATH, request_review)
    request_review_file_sha = sha256_file(REQUEST_REVIEW_PATH)

    launch_plan: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-pretraining-launch-plan-v1",
        "source_path": "configs/e01_pretraining_launch_plan_v1.json",
        "created_at_utc": NOW,
        "decision_id": "DEC-027",
        "status": "FROZEN_UNAUTHORIZED",
        "architecture": {
            "policy_artifact": str(MODEL_PATH.relative_to(ROOT)),
            "policy_artifact_sha256": sha256_file(MODEL_PATH),
            "architecture_sha256": MODEL_ARCHITECTURE_SHA256,
            "trainable_parameters": 970022,
            "architecture_change_authorized": False,
        },
        "primary_teacher": {
            "team_id": PRIMARY_TEAM_ID,
            "team_name": PRIMARY_TEAM_NAME,
            "submission_id": PRIMARY_SUBMISSION_ID,
            "deck_multiset_sha256": PRIMARY_DECK_SHA256,
            "initial_training_deck_frozen": True,
            "final_submission_deck_frozen": False,
        },
        "data": {
            "base_corpus_review": str(BASE_CORPUS_REVIEW_PATH.relative_to(ROOT)),
            "base_corpus_review_sha256": sha256_file(BASE_CORPUS_REVIEW_PATH),
            "base_episodes": base_corpus["qualified_corpus"]["episodes"],
            "base_policy_loss_targets": base_corpus["qualified_corpus"]["policy_loss_targets"],
            "majkel_expansion_request": str(REQUEST_PATH.relative_to(ROOT)),
            "majkel_expansion_request_sha256": request_sha,
            "majkel_expansion_contract_review": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
            "majkel_expansion_contract_review_sha256": request_review_file_sha,
            "corpus_v2_final": False,
        },
        "stages": [
            {
                "order": 1,
                "stage": "BC_ENGINEERING_CANARY",
                "request": str(BC_CANARY_PATH.relative_to(ROOT)),
                "request_sha256": sha256_file(BC_CANARY_PATH),
                "maximum_optimizer_steps": 64,
                "exact_approval_required": True,
                "authorized": False,
                "production_checkpoint_eligible": False,
                "may_run_in_parallel_with_stage_2": True,
            },
            {
                "order": 2,
                "stage": "MAJKEL_PRIVATE_KAGGLE_CPU_BODY_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION",
                "request": str(REQUEST_PATH.relative_to(ROOT)),
                "request_sha256": request_sha,
                "maximum_new_files": EXPECTED_NEW_FILES,
                "maximum_new_bytes": EXPECTED_NEW_BYTES,
                "platform": "private_kaggle_cpu",
                "replay_body_outputs": 0,
                "exact_approval_required": True,
                "authorized": False,
                "optimizer_steps": 0,
                "may_run_in_parallel_with_stage_1": True,
            },
            {
                "order": 3,
                "stage": "PRODUCTION_RECURRENT_BC",
                "request_status": "GENERATE_ONLY_AFTER_STAGES_1_AND_2_PASS_AND_CORPUS_V2_IS_HASH_FROZEN",
                "exact_approval_required": True,
                "authorized": False,
            },
            {
                "order": 4,
                "stage": "HELD_OUT_AND_ON_POLICY_COMPETENCE_EVALUATION",
                "exact_approval_required_for_external_execution": True,
                "authorized": False,
            },
            {
                "order": 5,
                "stage": "BOUNDED_KL_AUXILIARY_BC_RECURRENT_PPO",
                "maximum_choices_before_new_decision": 500000,
                "requires_bc_competence": True,
                "exact_approval_required": True,
                "authorized": False,
            },
            {
                "order": 6,
                "stage": "D1_DECK_AND_CHECKPOINT_TOURNAMENT_FREEZE",
                "final_submission_deck_frozen": False,
                "exact_approval_required": True,
                "authorized": False,
            },
        ],
        "authorization": {
            "replay_transfer": False,
            "optimizer_steps": False,
            "training": False,
            "external_compute": False,
            "model_promotion": False,
            "final_deck_freeze": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
    }
    write_json(LAUNCH_PLAN_PATH, launch_plan)
    launch_plan_sha = sha256_file(LAUNCH_PLAN_PATH)

    freeze_review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-pretraining-freeze-review-v1",
        "source_path": "reports/artifacts/e01-pretraining-freeze-review-v1.json",
        "created_at_utc": NOW,
        "producer": "scripts/finalize_e01_pretraining_freeze.py",
        "reviewed_decision": "DEC-027",
        "status": "PASS",
        "decision": "FREEZE_INITIAL_TRAINING_DECK_PRIMARY_TEACHER_MODEL_ARCHITECTURE_DATA_SELECTION_UNIVERSE_AND_GOLD_SEQUENCE",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": decision_sha},
            "model": {"path": str(MODEL_PATH.relative_to(ROOT)), "sha256": sha256_file(MODEL_PATH)},
            "base_corpus": {
                "path": str(BASE_CORPUS_REVIEW_PATH.relative_to(ROOT)),
                "sha256": sha256_file(BASE_CORPUS_REVIEW_PATH),
                "review_sha256": base_corpus["review_sha256"],
            },
            "majkel_probe": {
                "path": str(PROBE_REVIEW_PATH.relative_to(ROOT)),
                "sha256": sha256_file(PROBE_REVIEW_PATH),
                "review_sha256": probe_review["review_sha256"],
            },
            "expansion_request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": request_sha},
            "expansion_contract_review": {
                "path": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
                "sha256": request_review_file_sha,
                "review_sha256": request_review["review_sha256"],
            },
            "launch_plan": {"path": str(LAUNCH_PLAN_PATH.relative_to(ROOT)), "sha256": launch_plan_sha},
            "bc_canary": {"path": str(BC_CANARY_PATH.relative_to(ROOT)), "sha256": sha256_file(BC_CANARY_PATH)},
        },
        "freeze_status": {
            "primary_teacher": "FINAL_FOR_INITIAL_TRAINING",
            "initial_bc_training_deck": "FINAL",
            "final_submission_deck": "NOT_FINAL_PENDING_D1",
            "model_architecture": "FINAL_FOR_INITIAL_BC_AND_FIRST_BOUNDED_PPO",
            "data_selection_universe": "FINAL",
            "training_corpus": "NOT_FINAL_PENDING_EXACT_BODY_REVIEW",
            "gold_strategy_sequence": "FINAL",
            "bc_canary": "READY_UNAUTHORIZED",
            "production_training": "BLOCKED_EXACT_APPROVAL",
        },
        "remaining_gates": [
            "Exact 269-file Majkel transfer and corpus-v2 body review approval.",
            "Exact 64-step BC engineering canary optimizer approval.",
            "Corpus-v2 hash freeze and production BC request generation.",
            "Separate production BC approval.",
        ],
        "authorization": launch_plan["authorization"],
    }
    freeze_review["review_sha256"] = self_hash(freeze_review, "review_sha256")
    write_json(FREEZE_REVIEW_PATH, freeze_review)
    freeze_review_file_sha = sha256_file(FREEZE_REVIEW_PATH)

    decisions_path = ROOT / "reports/decisions/current.json"
    decisions = load(decisions_path)
    decision_entry = {
        "schema_version": 1,
        "record_id": "decision-dec-027",
        "source_path": str(DECISION_PATH.relative_to(ROOT)),
        "decision_id": "DEC-027",
        "title": "Freeze the pretraining configuration and Majkel primary source",
        "created_at_utc": NOW,
        "updated_at_utc": NOW,
        "producer": "decision-sidecar",
        "status": "ACCEPTED_PRETRAINING_FREEZE_REQUESTS_READY_UNAUTHORIZED",
        "decision": "Lock Majkel submission 55186239 as primary teacher, the reviewed Mega Lucario deck as the initial BC deck, the 970,022-parameter G2 architecture, the Majkel-dominant multi-teacher data policy, and the BC-to-evaluation-to-bounded-PPO sequence without authorizing transfer or training.",
        "rationale": "The top source identity is stable and body-qualified, architecture correctness and reliability are already closed, and further planning churn would delay training. Full corpus counts still require exact body review, so data selection is frozen while corpus finality remains pending.",
        "decision_sha256": decision_sha,
        "pretraining_freeze_review": str(FREEZE_REVIEW_PATH.relative_to(ROOT)),
        "pretraining_freeze_review_sha256": freeze_review_file_sha,
        "pretraining_freeze_review_self_hash": freeze_review["review_sha256"],
        "majkel_expansion_request": str(REQUEST_PATH.relative_to(ROOT)),
        "majkel_expansion_request_sha256": request_sha,
        "majkel_expansion_review": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
        "majkel_expansion_review_sha256": request_review_file_sha,
        "majkel_expansion_review_self_hash": request_review["review_sha256"],
        "launch_plan": str(LAUNCH_PLAN_PATH.relative_to(ROOT)),
        "launch_plan_sha256": launch_plan_sha,
        "primary_teacher_submission_id": PRIMARY_SUBMISSION_ID,
        "primary_deck_multiset_sha256": PRIMARY_DECK_SHA256,
        "model_architecture_sha256": MODEL_ARCHITECTURE_SHA256,
        "model_trainable_parameters": 970022,
        "new_replay_files": EXPECTED_NEW_FILES,
        "maximum_new_bytes": EXPECTED_NEW_BYTES,
        "data_selection_universe_frozen": True,
        "training_corpus_final": False,
        "initial_training_deck_frozen": True,
        "final_submission_deck_frozen": False,
        "model_architecture_frozen": True,
        "gold_strategy_sequence_frozen": True,
        "replay_transfer_authorized": False,
        "optimizer_steps_authorized": False,
        "training_authorized": False,
        "external_compute_authorized": False,
        "submission_authorized": False,
        "revisit_trigger": "The exact expansion or BC canary is approved or changes; corpus v2 is emitted; Majkel submission identity changes; a qualified architecture ablation is proposed; or production training, final deck freeze or submission is requested.",
    }
    upsert_by(decisions, "decision_id", "DEC-027", decision_entry)
    write_json(decisions_path, decisions)

    tasks_path = ROOT / "reports/tasks/current.json"
    tasks = load(tasks_path)
    freeze_task = {
        "schema_version": 1,
        "record_id": "task-e01-pretraining-freeze-027",
        "source_path": str(tasks_path.relative_to(ROOT)),
        "task_id": "T-E01-PRETRAINING-FREEZE-027",
        "title": "Freeze the initial training configuration",
        "phase": "E01-PRETRAIN",
        "priority": 15,
        "created_at_utc": NOW,
        "updated_at_utc": NOW,
        "completed_at_utc": NOW,
        "producer": "chatgpt-local-agent",
        "depends_on": ["DEC-025", "DEC-026", "DEC-027"],
        "status": "SUCCEEDED",
        "done_when": "Primary teacher, initial training deck, architecture, data-selection universe and gold sequence are hash-bound while all execution remains approval-gated.",
        "completion_evidence": [
            str(DECISION_PATH.relative_to(ROOT)),
            str(FREEZE_REVIEW_PATH.relative_to(ROOT)),
            str(LAUNCH_PLAN_PATH.relative_to(ROOT)),
        ],
        "primary_teacher_locked": True,
        "initial_training_deck_locked": True,
        "final_submission_deck_locked": False,
        "model_architecture_locked": True,
        "data_selection_universe_locked": True,
        "training_corpus_final": False,
        "gold_strategy_sequence_locked": True,
        "training_authorized": False,
    }
    expansion_task = {
        "schema_version": 1,
        "record_id": "task-e01-majkel-corpus-expansion-027",
        "source_path": str(tasks_path.relative_to(ROOT)),
        "task_id": "T-E01-MAJKEL-CORPUS-EXPANSION-027",
        "title": "Approve or reject the exact Majkel private CPU body review",
        "phase": "E01-DATA",
        "priority": 15,
        "created_at_utc": NOW,
        "updated_at_utc": NOW,
        "producer": "chatgpt-local-agent",
        "depends_on": ["DEC-027", "T-E01-MAJKEL-LIVE-GOLD-PROBE-025"],
        "status": "BLOCKED_APPROVAL",
        "done_when": "The exact private Kaggle CPU 269-file request is approved or rejected; if approved, only the named bodies are read, no replay body is exported, only qualified episodes enter a hash-frozen corpus v2, and execution stops before labels or training.",
        "request": str(REQUEST_PATH.relative_to(ROOT)),
        "request_sha256": request_sha,
        "contract_review": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
        "contract_review_sha256": request_review_file_sha,
        "contract_review_self_hash": request_review["review_sha256"],
        "request_ready": True,
        "explicit_exact_approval_required": True,
        "new_files": EXPECTED_NEW_FILES,
        "maximum_new_bytes": EXPECTED_NEW_BYTES,
        "reused_reviewed_files": 2,
        "candidate_files": EXPECTED_INTERSECTION_FILES,
        "replay_transfer_authorized": False,
        "qualified_only_corpus_v2_finalization_requested": True,
        "corpus_promotion_authorized": False,
        "training_authorized": False,
        "external_compute_authorized": False,
    }
    upsert_by(tasks, "task_id", freeze_task["task_id"], freeze_task)
    upsert_by(tasks, "task_id", expansion_task["task_id"], expansion_task)
    for task in tasks:
        if task.get("task_id") == "T-E01-BC-ENGINEERING-CANARY-025":
            task["priority"] = 15
            task["depends_on"] = list(dict.fromkeys(task.get("depends_on", []) + ["DEC-027"]))
            task["recommended_execution_order"] = 1
            task["may_run_in_parallel_with"] = "T-E01-MAJKEL-CORPUS-EXPANSION-027"
            task["explicit_exact_approval_required"] = True
            task["updated_at_utc"] = NOW
    write_json(tasks_path, tasks)

    gate_path = ROOT / "reports/gates/g3b.json"
    gate = load(gate_path)
    gate["approved_next_action"] = (
        "Obtain separate exact approvals for the existing 64-step BC engineering canary and the DEC-027 269-file Majkel corpus expansion. The two bounded stages may run in parallel. Production BC remains blocked until both pass and corpus v2 is hash-frozen."
    )
    gate["authorization"] = "DEC_027_PRETRAINING_CONFIGURATION_FROZEN_MAJKEL_EXPANSION_AND_BC_CANARY_READY_UNAUTHORIZED"
    gate["blockers"] = [
        "The initial training deck, primary teacher, model architecture, data-selection universe and gold sequence are frozen under DEC-027, but the exact 269-file Majkel body review remains unauthorized.",
        "The training corpus remains v1 at 66 episodes and 7140 policy-loss targets until corpus v2 body qualification completes; no projection is accepted as a guarantee.",
        "The exact eight-episode, 64-step BC engineering canary is preflight-qualified but optimizer steps remain unauthorized. Production BC, competence evaluation, PPO, final deck freeze and submission remain incomplete.",
    ]
    checks = gate.get("technical_checks", [])
    for entry in [
        {
            "evidence": str(FREEZE_REVIEW_PATH.relative_to(ROOT)),
            "name": "DEC-027 pretraining configuration and gold sequence frozen",
            "status": "PASS",
        },
        {
            "evidence": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
            "name": "DEC-027 exact remaining 269-file Majkel corpus expansion request",
            "status": "PASS",
        },
    ]:
        if not any(item.get("name") == entry["name"] for item in checks):
            checks.append(entry)
    gate["technical_checks"] = checks
    write_json(gate_path, gate)

    project_path = ROOT / "PROJECT_STATUS.md"
    project = project_path.read_text(encoding="utf-8")
    project = replace_prefix(
        project,
        "Last completed milestone:",
        "Last completed milestone: DEC-027 froze Majkel submission 55186239 as the primary teacher, its reviewed Mega Lucario deck as the initial BC deck, the 970,022-parameter architecture, the data-selection universe and the gold execution sequence",
    )
    project = replace_prefix(
        project,
        "Current gate:",
        "Current gate: exact approvals are required for the 64-step BC engineering canary and the 269-file Majkel corpus expansion; these bounded stages may run in parallel",
    )
    project = replace_prefix(
        project,
        "Gold-path status:",
        "Gold-path status: DEC-027 INITIAL TRAINING CONFIGURATION FROZEN / MAJKEL PRIMARY SOURCE LOCKED / 269-FILE DATA REVIEW READY UNAUTHORIZED / BC CANARY READY UNAUTHORIZED / PRODUCTION TRAINING BLOCKED / SUBMISSION BLOCKED",
    )
    project = replace_prefix(
        project,
        "Next review required before:",
        "Next review required before: the 269-file replay transfer and corpus-v2 review, the 64 BC optimizer steps, production BC, GPU/TPU use, model promotion, final D1 deck freeze, submission, commit or push",
    )
    dec_block = f"""### DEC-027 - Initial training configuration frozen

- Primary teacher: Majkel1337, team `{PRIMARY_TEAM_ID}`, active submission `{PRIMARY_SUBMISSION_ID}`.
- Initial BC deck: Mega Lucario ex, exact multiset SHA-256 `{PRIMARY_DECK_SHA256}`.
- Architecture: the sealed 970,022-parameter G2 recurrent semantic policy, architecture SHA-256 `{MODEL_ARCHITECTURE_SHA256}`.
- Data policy: retain the 66-episode multi-teacher corpus and prepare the exact remaining 269-file private Kaggle CPU review capped at `{EXPECTED_NEW_BYTES:,}` newly read bytes; the two reviewed files are reused and no replay body is exported.
- Execution sequence: the exact 64-step BC canary and exact data review may run in parallel after separate approvals; production BC follows only after both pass and corpus v2 is hash-frozen.
- Final submission deck remains unfrozen pending D1 cross-deck and important-matchup evaluation.
"""
    project = insert_before_heading(project, "## Immediate Next Actions", dec_block)
    old_actions = """1. Obtain separate explicit approval before promoting the two reviewed Majkel episodes into the corpus or retrieving any additional replay body.
2. Keep the exact 64-step BC engineering canary separately unauthorized; approval of replay or corpus work must not authorize optimizer steps or training.
3. Reuse the verified private Kaggle CPU attachment and `/kaggle/input/competitions/pokemon-tcg-ai-battle` path only for separately approved bounded workflows, and keep GPU/TPU, model promotion, final deck freeze, submission, commit and push blocked.
"""
    new_actions = f"""1. Obtain exact approval for `configs/e01_bc_engineering_canary_request_v1.json`, SHA-256 `{sha256_file(BC_CANARY_PATH)}`, to execute only the 64-step engineering canary.
2. Obtain separate exact approval for `configs/e01_majkel_corpus_expansion_request_v1.json`, SHA-256 `{request_sha}`, to run a private Kaggle CPU review of exactly 269 named bodies capped at `{EXPECTED_NEW_BYTES:,}` bytes, finalize only qualified episodes into hash-frozen corpus v2 metadata, export no replay bodies or labels, and stop before training.
3. After both bounded stages pass, freeze corpus v2 and prepare the exact production recurrent-BC request. GPU/TPU, model promotion, final D1 deck freeze, submission, commit and push remain separately blocked.
"""
    if old_actions in project:
        project = project.replace(old_actions, new_actions, 1)
    project_path.write_text(project, encoding="utf-8")

    progress_path = ROOT / "PROGRESS_REPORT.md"
    progress = progress_path.read_text(encoding="utf-8")
    progress = replace_prefix(
        progress,
        "Current gate:",
        "Current gate: **DEC-027 froze the initial training configuration; exact approvals are pending for the parallel 64-step BC canary and 269-file Majkel corpus review**",
    )
    progress = replace_prefix(
        progress,
        "Gold-path status:",
        "Gold-path status: **MAJKEL PRIMARY SOURCE LOCKED; INITIAL BC DECK AND MODEL ARCHITECTURE FROZEN; DATA SELECTION UNIVERSE FROZEN; CORPUS V2 AND TRAINING UNAUTHORIZED**",
    )
    progress = replace_prefix(
        progress,
        "Latest completed milestone:",
        "Latest completed milestone: **DEC-027 froze the pretraining configuration and generated the exact 269-file Majkel expansion request**",
    )
    progress_block = f"""## DEC-027 Pretraining Freeze

The initial learned-policy configuration is now frozen to remove planning delay. Majkel1337 team `{PRIMARY_TEAM_ID}` and active submission `{PRIMARY_SUBMISSION_ID}` are the primary teacher source. The reviewed Mega Lucario deck hash `{PRIMARY_DECK_SHA256}` is the initial BC training deck. The sealed 970,022-parameter G2 architecture remains unchanged for initial BC and the first bounded PPO stage.

The existing 66-episode, 7,140-target multi-teacher corpus remains the diversity set. The exact request reuses the two reviewed Majkel files and names all remaining 269 files in the August 3 version-1 intersection, with a hard newly read cap of `{EXPECTED_NEW_BYTES:,}` bytes. The review runs on private Kaggle CPU with internet, GPU and TPU off, exports metadata artifacts only, and finalizes only qualified episodes into a hash-frozen corpus v2. Corpus v2 becomes final only after body-level deck, module, action, terminal, duplicate and target-count review completes cleanly.

The execution sequence is frozen: run the separately approved 64-step BC engineering canary and the separately approved private Kaggle CPU Majkel body review plus qualified-only corpus-v2 finalization in parallel; then prepare production BC from the frozen corpus v2, evaluate held-out and on-policy competence, and only then permit bounded KL/auxiliary-BC recurrent PPO. The final submission deck remains pending D1 tournament evidence.

Evidence: `{DECISION_PATH.relative_to(ROOT)}`, `{FREEZE_REVIEW_PATH.relative_to(ROOT)}`, `{REQUEST_PATH.relative_to(ROOT)}`, `{REQUEST_REVIEW_PATH.relative_to(ROOT)}`, and `{LAUNCH_PLAN_PATH.relative_to(ROOT)}`.
"""
    progress = insert_before_heading(progress, "## DEC-026 Compute Placement and Kaggle CPU Infrastructure", progress_block)
    progress_path.write_text(progress, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": str(DECISION_PATH.relative_to(ROOT)),
                "decision_sha256": decision_sha,
                "request": str(REQUEST_PATH.relative_to(ROOT)),
                "request_sha256": request_sha,
                "request_review": str(REQUEST_REVIEW_PATH.relative_to(ROOT)),
                "request_review_sha256": request_review_file_sha,
                "request_review_self_hash": request_review["review_sha256"],
                "launch_plan": str(LAUNCH_PLAN_PATH.relative_to(ROOT)),
                "launch_plan_sha256": launch_plan_sha,
                "freeze_review": str(FREEZE_REVIEW_PATH.relative_to(ROOT)),
                "freeze_review_sha256": freeze_review_file_sha,
                "freeze_review_self_hash": freeze_review["review_sha256"],
                "new_files": EXPECTED_NEW_FILES,
                "new_bytes": EXPECTED_NEW_BYTES,
                "bc_canary_sha256": sha256_file(BC_CANARY_PATH),
                "training_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
