from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


WORK_ORDER_SCHEMA_VERSION = 1
REVIEW_SCHEMA_VERSION = 1
EXPECTED_STRATEGY = (
    "mega_lucario_provisional_specialist",
    "exact_deck_teacher_replay_qualification",
    "full_compound_action_recurrent_behavior_cloning",
    "on_policy_and_held_out_competence_evaluation",
    "bounded_kl_auxiliary_bc_recurrent_ppo",
    "maximum_500000_choices_before_redecision",
    "frozen_tournament_and_submission_selection",
)
EXPECTED_WORK_ORDERS = {"E01-A", "E01-B", "E04", "E08"}
EXPECTED_LUCARIO = {
    "receipt_sha256": "dc94ec50448e7a0dd40423d62cd33c480d6021870d2726c9849ba0429045713e",
    "deck_sha256": "406e2e9bd6ae82b8008b16ee64ffcbb58e4a50cd6bc36e33ae655456c6b9afee",
    "module_sha256": "ab8563b67b88b3666c2ff9c308505085a84fdac676c194c5b484d8544478c3b2",
}


class GoldPathContractError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise GoldPathContractError(f"value is not canonical-JSON safe: {error}") from error
    return text.encode("utf-8") + b"\n"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as error:
        raise GoldPathContractError(f"cannot read evidence file {path}: {error}") from error


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldPathContractError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise GoldPathContractError(f"JSON root must be an object: {path}")
    return value


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GoldPathContractError(f"{name} must be an object")
    return value


def _require_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GoldPathContractError(f"{name} must be an integer >= {minimum}")
    return value


def _require_false(value: Any, name: str) -> None:
    if value is not False:
        raise GoldPathContractError(f"{name} must remain false")


def validate_work_orders(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != WORK_ORDER_SCHEMA_VERSION:
        raise GoldPathContractError("unsupported gold-path work-order schema")
    if value.get("decision_id") != "DEC-024":
        raise GoldPathContractError("work orders are not bound to DEC-024")
    if tuple(value.get("strategy", ())) != EXPECTED_STRATEGY:
        raise GoldPathContractError("gold-path strategy sequence differs")

    architecture = _require_mapping(value.get("architecture"), "architecture")
    if _require_int(architecture.get("trainable_parameters"), "trainable parameters", 1) != 970_022:
        raise GoldPathContractError("architecture parameter count differs from the frozen model")
    _require_false(architecture.get("change_authorized"), "architecture.change_authorized")
    if architecture.get("compound_action") != "ordered_without_replacement_with_stop":
        raise GoldPathContractError("compound-action contract differs")
    if architecture.get("maximum_policy_version_lag") != 0:
        raise GoldPathContractError("policy-version lag must remain zero")
    for key in (
        "public_information_actor",
        "public_information_critic",
        "forced_calls_advance_recurrence",
    ):
        if architecture.get(key) is not True:
            raise GoldPathContractError(f"architecture.{key} must remain true")
    for key in (
        "forced_calls_create_policy_loss",
        "search_default",
        "reward_shaping",
        "broad_offline_q_learning",
    ):
        _require_false(architecture.get(key), f"architecture.{key}")
    if architecture.get("reward") != "terminal_win_draw_loss":
        raise GoldPathContractError("reward contract differs")

    authorization = _require_mapping(value.get("authorization"), "authorization")
    for key in (
        "named_replay_body_transfer",
        "behavior_cloning_optimizer_steps",
        "ppo_optimizer_steps",
        "meaningful_self_play",
        "kaggle_notebook_launch",
        "tpu_run",
        "modal_job",
        "paid_compute",
        "competition_submission",
        "audit_report_integration",
    ):
        _require_false(authorization.get(key), f"authorization.{key}")

    engine = _require_mapping(value.get("engine_binding"), "engine_binding")
    if engine.get("official_downloadable_asset_parity") != "PASS":
        raise GoldPathContractError("official downloadable asset parity must pass")
    if engine.get("hosted_runtime_behavior_parity") != "UNRESOLVED_AFTER_2026-07-23_ENGINE_UPDATE":
        raise GoldPathContractError("hosted runtime behavior parity must remain unresolved")
    if engine.get("execution_requires_exact_asset_hash_verification") is not True:
        raise GoldPathContractError("E04 execution must reverify exact asset hashes")
    if engine.get("official_asset_parity_artifact") != "reports/artifacts/e04-official-downloadable-asset-parity-v1.json":
        raise GoldPathContractError("official asset parity artifact path differs")
    artifact_hash = engine.get("official_asset_parity_artifact_sha256")
    if not isinstance(artifact_hash, str) or len(artifact_hash) != 64:
        raise GoldPathContractError("official asset parity artifact hash differs")

    work_orders = _require_mapping(value.get("work_orders"), "work_orders")
    if set(work_orders) != EXPECTED_WORK_ORDERS:
        raise GoldPathContractError("work-order set differs")

    e01a = _require_mapping(work_orders["E01-A"], "E01-A")
    caps = _require_mapping(e01a.get("dry_run_caps"), "E01-A dry-run caps")
    if caps != {
        "max_files": 8,
        "max_total_bytes": 67_108_864,
        "max_file_bytes": 16_777_216,
        "episode_json_transferred": 0,
    }:
        raise GoldPathContractError("E01-A dry-run caps differ")
    _require_false(e01a.get("transfer_authorized"), "E01-A.transfer_authorized")
    if e01a.get("state") != (
        "FLG_DRAGAPULT_SCREENING_PASS_DRIES_GRIMMSNARL_CALIBRATION_PASS_"
        "CURRENT_RANK_1_SOURCE_WAIT"
    ):
        raise GoldPathContractError("E01-A current rank-1 source-wait state differs")
    if e01a.get("source_provenance_status") != (
        "PASS_TWO_RECENT_TEACHERS_CONFIRMATION_BLOCKED_CURRENT_RANK_1_SOURCE_WAIT"
    ):
        raise GoldPathContractError("E01-A source-provenance status differs")
    for field in (
        "selected_episode_ids_match",
        "episode_identity_reproduced",
        "timestamp_reproduced",
        "file_byte_count_reproduced",
        "team_identity_reproduced",
        "submission_identity_reproduced",
        "provenance_probe_authorization_consumed",
        "provenance_probe_passed",
        "exact_deck_hashes_recovered",
        "action_aligned_supervision_available",
        "consistency_authorization_consumed",
        "same_submission_identity_qualified",
        "exact_deck_consistency_qualified",
        "policy_artifact_identity_inferred_from_same_submission_id",
        "gold_region_strength_metadata_available",
        "teacher_strength_qualified",
        "gold_teacher_authorization_consumed",
        "gold_teacher_exact_deck_consistency_qualified",
        "gold_teacher_action_alignment_qualified",
        "gold_teacher_same_module_version_qualified",
        "policy_behavior_consistency_qualified",
        "policy_consistency_qualified",
        "calibration_authorization_consumed",
        "calibration_all_module_version_qualified",
        "calibration_exact_deck_consistency_qualified",
        "calibration_action_alignment_qualified",
        "screening_expansion_request_ready",
        "current_gold_teacher_authorization_consumed",
        "current_gold_teacher_same_module_version_qualified",
        "current_gold_teacher_exact_deck_consistency_qualified",
        "current_gold_teacher_action_alignment_qualified",
        "current_teacher_calibration_authorization_consumed",
        "current_teacher_calibration_all_module_version_qualified",
        "current_teacher_calibration_exact_deck_consistency_qualified",
        "current_teacher_calibration_action_alignment_qualified",
        "current_teacher_screening_expansion_authorization_consumed",
        "current_teacher_screening_expansion_all_selected_files_qualified",
        "current_teacher_screening_expansion_exact_deck_consistency_qualified",
        "current_teacher_screening_expansion_action_alignment_qualified",
        "current_teacher_screening_expansion_same_module_version_qualified",
        "current_teacher_screening_expansion_current_asset_compatibility_qualified",
        "minimum_5000_teacher_decisions_met",
        "e01_screening_gate_passed",
        "confirmation_teacher_probe_authorization_consumed",
        "confirmation_teacher_probe_exact_deck_consistency_qualified",
        "confirmation_teacher_probe_action_alignment_qualified",
        "confirmation_teacher_probe_current_asset_compatibility_qualified",
        "confirmation_independent_recent_teachers_met",
        "confirmation_teacher_calibration_authorization_consumed",
        "confirmation_teacher_calibration_all_module_version_qualified",
        "confirmation_teacher_calibration_exact_deck_consistency_qualified",
        "confirmation_teacher_calibration_action_alignment_qualified",
        "confirmation_teacher_calibration_current_asset_compatibility_qualified",
        "current_rank_1_source_wait_active",
    ):
        if e01a.get(field) is not True:
            raise GoldPathContractError(f"E01-A required field differs: {field}")
    for field in (
        "rating_field_reproduced",
        "rating_field_used_for_probe",
        "candidate_set_reranked",
        "provenance_probe_request_ready",
        "provenance_probe_authorized",
        "consistency_request_ready",
        "consistency_request_authorized",
        "gold_teacher_request_ready",
        "gold_teacher_request_authorized",
        "calibration_request_ready",
        "calibration_request_authorized",
        "screening_expansion_request_authorized",
        "screening_expansion_projection_is_guarantee",
        "screening_expansion_active",
        "screening_expansion_executed",
        "current_teacher_calibration_request_ready",
        "current_teacher_calibration_request_authorized",
        "current_teacher_screening_expansion_request_ready",
        "current_teacher_screening_expansion_request_authorized",
        "current_teacher_screening_expansion_projection_is_guarantee",
        "current_teacher_screening_expansion_active",
        "confirmation_teacher_probe_request_ready",
        "confirmation_teacher_probe_request_authorized",
        "confirmation_teacher_probe_completes_confirmation",
        "confirmation_teacher_calibration_request_ready",
        "confirmation_teacher_calibration_request_authorized",
        "confirmation_teacher_calibration_active",
        "confirmation_teacher_calibration_projection_is_guarantee",
        "current_rank_1_source_ready",
        "current_rank_1_probe_request_ready",
        "current_rank_1_probe_request_exists",
        "current_rank_1_output_exists",
        "confirmation_gate_passed",
    ):
        _require_false(e01a.get(field), f"E01-A.{field}")
    if e01a.get("selected_rows_with_byte_or_timestamp_mismatch") != 8:
        raise GoldPathContractError("E01-A raw-manifest mismatch count differs")
    if (
        e01a.get("provenance_probe_episode_id") != 87_703_034
        or e01a.get("provenance_probe_file_name") != "87703034.json"
        or e01a.get("provenance_probe_declared_bytes") != 3_641_302
        or e01a.get("provenance_probe_files_transferred") != 1
        or e01a.get("provenance_probe_bytes_transferred") != 3_641_302
    ):
        raise GoldPathContractError("E01-A completed provenance probe differs")
    if e01a.get("current_asset_deck_construction_compatibility") != "PASS":
        raise GoldPathContractError("E01-A current-asset deck compatibility differs")
    if e01a.get("exact_historical_deck_legality") != "UNPROVEN":
        raise GoldPathContractError("E01-A historical deck-legality state differs")
    if e01a.get("provenance_probe_deck_hashes") != [
        "606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283",
        "eff68cb08be178b9c7f06c409b61e88ae9200ab6dc26e05f4bf29eed86040455",
    ]:
        raise GoldPathContractError("E01-A recovered deck hashes differ")
    if e01a.get("provenance_probe_action_alignment") != {
        "active_selection_requests": 128,
        "nonempty_lagged_selections": 125,
        "empty_lagged_selections": 3,
        "maximum_option_count": 25,
        "maximum_selection_count": 4,
    }:
        raise GoldPathContractError("E01-A action-alignment summary differs")
    if (
        e01a.get("consistency_request_episode_id") != 87_741_212
        or e01a.get("consistency_request_file_name") != "87741212.json"
        or e01a.get("consistency_request_declared_bytes") != 559_779
        or e01a.get("consistency_files_transferred") != 1
        or e01a.get("consistency_bytes_transferred") != 559_779
        or e01a.get("consistency_replay_sha256")
        != "be962b8ca9146320f7d8976460c20244cf5e8bf6b026816816bc4b4ec91a87d2"
        or e01a.get("combined_benarg_teacher_active_selection_requests") != 65
        or e01a.get("combined_all_player_active_selection_requests") != 157
    ):
        raise GoldPathContractError("E01-A completed consistency probe differs")
    if (
        e01a.get("gold_teacher_team_name") != "Luca"
        or e01a.get("gold_teacher_submission_id") != 54_863_653
        or e01a.get("gold_teacher_leaderboard_rank") != 2
        or e01a.get("gold_teacher_submission_public_score") != 1180.9
        or e01a.get("gold_teacher_dataset_episode_count") != 357
        or e01a.get("gold_teacher_probe_files") != 2
        or e01a.get("gold_teacher_probe_bytes") != 1_313_221
        or e01a.get("gold_teacher_probe_files_transferred") != 2
        or e01a.get("gold_teacher_probe_bytes_transferred") != 1_313_221
        or e01a.get("gold_teacher_deck_multiset_sha256")
        != "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
        or e01a.get("gold_teacher_module_versions") != ["1.32.2", "1.32.1"]
        or e01a.get("gold_teacher_active_selection_requests") != 37
        or e01a.get("gold_teacher_screening_decision_shortfall") != 4_963
    ):
        raise GoldPathContractError("E01-A completed Luca teacher probe differs")
    if e01a.get("gold_teacher_replay_sha256") != [
        "523c74d0e21d8ca7a687a835c178e947844614a95ee00479c0efe6f5dc31125c",
        "b10f5b2824c7db1b6a3f9c9f1e782da9a0e366595cd06ddc5e86e78d6ce23876",
    ]:
        raise GoldPathContractError("E01-A Luca replay hashes differ")
    if (
        e01a.get("calibration_candidate_pool_episodes") != 39
        or e01a.get("calibration_request_files") != 12
        or e01a.get("calibration_request_bytes") != 63_828_057
        or e01a.get("calibration_request_required_module_version") != "1.32.2"
        or e01a.get("calibration_request_balanced_strata")
        != {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
        or e01a.get("calibration_files_transferred") != 12
        or e01a.get("calibration_bytes_transferred") != 63_828_057
        or e01a.get("calibration_luca_active_selection_requests") != 1_170
        or e01a.get("calibration_all_player_active_selection_requests") != 2_258
        or e01a.get("combined_observed_luca_active_selection_requests") != 1_207
        or e01a.get("luca_calibration_screening_decision_shortfall") != 3_793
        or e01a.get("calibration_decisions_per_episode") != 97.5
        or e01a.get("calibration_conservative_decisions_per_mib")
        != 16.264384083698396
    ):
        raise GoldPathContractError("E01-A completed Luca calibration differs")
    if (
        e01a.get("screening_expansion_request_files") != 51
        or e01a.get("screening_expansion_request_bytes") != 270_807_738
        or e01a.get("screening_expansion_at_or_after_anchor_files") != 27
        or e01a.get("screening_expansion_pre_anchor_boundary_files") != 24
        or e01a.get("screening_expansion_projected_luca_decisions")
        != 4200.478614492002
        or e01a.get("screening_expansion_superseded_by") != "DEC-019"
        or e01a.get("screening_expansion_superseded_reason")
        != "LIVE_LEADERBOARD_AND_ACTIVE_SUBMISSION_REFRESH"
    ):
        raise GoldPathContractError("E01-A superseded Luca screening expansion differs")
    if (
        e01a.get("current_gold_teacher_team_name") != "flg"
        or e01a.get("current_gold_teacher_team_id") != 16_380_946
        or e01a.get("current_gold_teacher_submission_id") != 55_004_495
        or e01a.get("current_gold_teacher_live_rank_at_refresh") != 1
        or e01a.get("current_gold_teacher_live_team_score_at_refresh") != 1234.2
        or e01a.get("current_gold_teacher_submission_public_score") != 1244.2
        or e01a.get("current_gold_teacher_dataset_episode_count") != 131
        or e01a.get("current_gold_teacher_archetype_context_label") != "Dragapult ex"
        or e01a.get("current_gold_teacher_deck_multiset_sha256")
        != "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e"
        or e01a.get("current_gold_teacher_probe_files_transferred") != 2
        or e01a.get("current_gold_teacher_probe_bytes_transferred") != 3_996_398
        or e01a.get("current_gold_teacher_module_versions") != ["1.32.2"]
        or e01a.get("current_gold_teacher_active_selection_requests") != 94
        or e01a.get("current_gold_teacher_screening_decision_shortfall") != 4_906
    ):
        raise GoldPathContractError("E01-A current rank-1 teacher probe differs")
    if e01a.get("current_gold_teacher_probe_replay_sha256") != [
        "30a97dfb6bbfe65b224011103b215c7e2ec946ad1cd977cc82a88b1232444452",
        "5b6b330d543037e561a889fe76baaf84d427019b0fc0523080045a6abc5214d6",
    ]:
        raise GoldPathContractError("E01-A current rank-1 replay hashes differ")
    if (
        e01a.get("current_teacher_calibration_request_files") != 12
        or e01a.get("current_teacher_calibration_request_bytes") != 63_562_985
        or e01a.get("current_teacher_calibration_required_module_version") != "1.32.2"
        or e01a.get("current_teacher_calibration_required_deck_multiset_sha256")
        != "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e"
        or e01a.get("current_teacher_calibration_balanced_strata")
        != {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
        or e01a.get("current_teacher_calibration_files_transferred") != 12
        or e01a.get("current_teacher_calibration_bytes_transferred") != 63_562_985
        or e01a.get("current_teacher_calibration_teacher_active_selection_requests")
        != 1_292
        or e01a.get("current_teacher_calibration_all_player_active_selection_requests")
        != 2_247
        or e01a.get(
            "current_teacher_calibration_combined_observed_teacher_active_selection_requests"
        )
        != 1_386
        or e01a.get("current_teacher_calibration_screening_decision_shortfall")
        != 3_614
        or e01a.get("current_teacher_calibration_minimum_decisions_per_mib")
        != 16.446242027673883
    ):
        raise GoldPathContractError("E01-A completed current rank-1 calibration differs")
    if (
        e01a.get("current_teacher_screening_expansion_request_files") != 38
        or e01a.get("current_teacher_screening_expansion_request_bytes")
        != 254_237_550
        or e01a.get("current_teacher_screening_expansion_minimum_target_bytes")
        != 253_462_708
        or e01a.get("current_teacher_screening_expansion_balanced_strata")
        != {"seat_0_loss": 10, "seat_0_win": 10, "seat_1_loss": 9, "seat_1_win": 9}
        or e01a.get("current_teacher_screening_expansion_files_transferred") != 38
        or e01a.get("current_teacher_screening_expansion_bytes_transferred")
        != 254_237_550
        or e01a.get("current_teacher_screening_expansion_qualified_files") != 38
        or e01a.get("current_teacher_screening_expansion_rejected_files") != 0
        or e01a.get(
            "current_teacher_screening_expansion_qualified_teacher_active_selection_requests"
        )
        != 4_954
        or e01a.get(
            "current_teacher_screening_expansion_qualified_all_player_active_selection_requests"
        )
        != 8_609
        or e01a.get("current_teacher_combined_observed_teacher_active_selection_requests")
        != 6_340
        or e01a.get("current_teacher_screening_decision_shortfall") != 0
        or e01a.get("screening_teacher_decision_shortfall") != 0
    ):
        raise GoldPathContractError("E01-A completed current rank-1 screening expansion differs")
    if (
        e01a.get("completed_screening_teacher_current_rank_after_refresh") != 4
        or e01a.get("completed_screening_teacher_active_submission_changed") is not True
        or e01a.get("confirmation_teacher_team_id") != 16_531_269
        or e01a.get("confirmation_teacher_team_name") != "Dries @ Tufa Labs"
        or e01a.get("confirmation_teacher_live_rank_at_refresh") != 1
        or e01a.get("confirmation_teacher_live_team_score_at_refresh") != 1205.2
        or e01a.get("confirmation_teacher_submission_id") != 55_002_825
        or e01a.get("confirmation_teacher_submission_public_score") != 1205.2
        or e01a.get("confirmation_teacher_dataset_episode_count") != 128
        or e01a.get("confirmation_teacher_probe_request_files") != 2
        or e01a.get("confirmation_teacher_probe_request_bytes") != 1_135_238
        or e01a.get("confirmation_teacher_probe_files_transferred") != 2
        or e01a.get("confirmation_teacher_probe_bytes_transferred") != 1_135_238
        or e01a.get("confirmation_teacher_probe_required_module_version") != "1.32.2"
        or e01a.get("confirmation_teacher_probe_module_versions") != ["1.32.2"]
        or e01a.get("confirmation_teacher_probe_teacher_deck_multiset_sha256")
        != "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
        or e01a.get("confirmation_teacher_probe_archetype_context_label")
        != "Marnie's Grimmsnarl ex"
        or e01a.get("confirmation_teacher_probe_teacher_active_selection_requests") != 27
        or e01a.get("confirmation_teacher_probe_all_player_active_selection_requests") != 57
        or e01a.get("confirmation_minimum_teachers") != 2
        or e01a.get("confirmation_minimum_episodes") != 200
        or e01a.get("confirmation_minimum_meaningful_teacher_decisions") != 25_000
        or e01a.get("confirmation_independent_recent_teachers_observed") != 2
        or e01a.get("confirmation_observed_recent_teacher_episodes") != 66
        or e01a.get("confirmation_episode_shortfall") != 134
        or e01a.get("confirmation_observed_recent_teacher_decisions") != 7_542
        or e01a.get("confirmation_decision_shortfall") != 17_458
        or e01a.get("confirmation_teacher_calibration_request_files") != 12
        or e01a.get("confirmation_teacher_calibration_request_bytes") != 60_869_451
        or e01a.get("confirmation_teacher_calibration_files_transferred") != 12
        or e01a.get("confirmation_teacher_calibration_bytes_transferred") != 60_869_451
        or e01a.get("confirmation_teacher_calibration_required_module_version") != "1.32.2"
        or e01a.get("confirmation_teacher_calibration_required_deck_multiset_sha256")
        != "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
        or e01a.get("confirmation_teacher_calibration_balanced_strata")
        != {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
        or e01a.get("confirmation_teacher_calibration_teacher_active_selection_requests")
        != 1_175
        or e01a.get("confirmation_teacher_calibration_all_player_active_selection_requests")
        != 2_171
        or e01a.get("confirmation_teacher_calibration_projected_additional_episodes")
        != 179
        or e01a.get("confirmation_teacher_calibration_projected_additional_bytes")
        != 904_390_533
        or e01a.get("confirmation_teacher_current_top20_rank") is not None
        or e01a.get("confirmation_teacher_active_submission_changed") is not True
        or e01a.get("current_rank_1_team_id") != 16_441_077
        or e01a.get("current_rank_1_team_name") != "haggle"
        or e01a.get("current_rank_1_rank") != 1
        or e01a.get("current_rank_1_score") != 1169.5
        or e01a.get("current_rank_1_submission_id") != 55_104_355
        or e01a.get("current_rank_1_public_episode_count") != 76
        or e01a.get("current_rank_1_public_episode_strata")
        != {"seat_0_loss": 10, "seat_0_win": 26, "seat_1_loss": 14, "seat_1_win": 26}
        or e01a.get("current_rank_1_latest_complete_daily_dataset")
        != "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1"
        or e01a.get("current_rank_1_latest_dataset_json_files") != 4_387
        or e01a.get("current_rank_1_latest_dataset_declared_json_bytes")
        != 21_474_480_425
        or e01a.get("current_rank_1_dataset_intersection_files") != 0
        or e01a.get("current_rank_1_dataset_intersection_bytes") != 0
    ):
        raise GoldPathContractError("E01-A completed calibration or source-wait state differs")
    if e01a.get("next_stage") != "current_rank_1_daily_dataset_wait":
        raise GoldPathContractError("E01-A next stage differs")
    for key in (
        "source_provenance_decision_sha256",
        "current_manifest_snapshot_sha256",
        "source_provenance_review_script_sha256",
        "source_provenance_review_sha256",
        "source_provenance_review_self_hash",
        "provenance_probe_placeholder_sha256",
        "source_schema_decision_sha256",
        "raw_source_schema_reconciliation_sha256",
        "source_schema_review_script_sha256",
        "source_schema_review_sha256",
        "source_schema_review_self_hash",
        "provenance_probe_request_sha256",
        "provenance_probe_authorized_request_sha256",
        "provenance_probe_review_script_sha256",
        "provenance_probe_review_sha256",
        "provenance_probe_review_self_hash",
        "provenance_probe_replay_sha256",
        "consistency_decision_sha256",
        "consistency_candidate_metadata_sha256",
        "consistency_request_sha256",
        "consistency_contract_review_script_sha256",
        "consistency_contract_review_sha256",
        "consistency_contract_review_self_hash",
        "consistency_authorized_request_sha256",
        "consistency_probe_review_script_sha256",
        "consistency_probe_review_sha256",
        "consistency_probe_review_self_hash",
        "consistency_replay_sha256",
        "gold_teacher_decision_sha256",
        "gold_teacher_coverage_sha256",
        "gold_teacher_request_sha256",
        "gold_teacher_authorized_request_sha256",
        "gold_teacher_contract_review_script_sha256",
        "gold_teacher_contract_review_sha256",
        "gold_teacher_contract_review_self_hash",
        "gold_teacher_probe_review_script_sha256",
        "gold_teacher_probe_review_sha256",
        "gold_teacher_probe_review_self_hash",
        "calibration_decision_sha256",
        "calibration_candidate_metadata_sha256",
        "calibration_request_sha256",
        "calibration_contract_review_script_sha256",
        "calibration_contract_review_sha256",
        "calibration_contract_review_self_hash",
        "calibration_authorized_request_sha256",
        "calibration_review_script_sha256",
        "calibration_review_sha256",
        "calibration_review_self_hash",
        "screening_expansion_decision_sha256",
        "screening_expansion_candidate_metadata_sha256",
        "screening_expansion_request_sha256",
        "screening_expansion_contract_review_script_sha256",
        "screening_expansion_contract_review_sha256",
        "screening_expansion_contract_review_self_hash",
        "live_gold_refresh_sha256",
        "live_gold_refresh_decision_sha256",
        "current_gold_teacher_probe_request_sha256",
        "current_gold_teacher_authorized_request_sha256",
        "current_gold_teacher_contract_review_script_sha256",
        "current_gold_teacher_contract_review_sha256",
        "current_gold_teacher_contract_review_self_hash",
        "current_gold_teacher_probe_review_script_sha256",
        "current_gold_teacher_probe_review_sha256",
        "current_gold_teacher_probe_review_self_hash",
        "current_teacher_calibration_decision_sha256",
        "current_teacher_calibration_candidate_metadata_sha256",
        "current_teacher_calibration_request_sha256",
        "current_teacher_calibration_contract_review_script_sha256",
        "current_teacher_calibration_contract_review_sha256",
        "current_teacher_calibration_contract_review_self_hash",
        "current_teacher_calibration_authorized_request_sha256",
        "current_teacher_calibration_review_script_sha256",
        "current_teacher_calibration_review_sha256",
        "current_teacher_calibration_review_self_hash",
        "current_teacher_screening_expansion_decision_sha256",
        "current_teacher_screening_expansion_candidate_metadata_sha256",
        "current_teacher_screening_expansion_request_sha256",
        "current_teacher_screening_expansion_contract_review_script_sha256",
        "current_teacher_screening_expansion_contract_review_sha256",
        "current_teacher_screening_expansion_contract_review_self_hash",
        "current_teacher_screening_expansion_authorized_payload_sha256",
        "current_teacher_screening_expansion_authorized_file_sha256",
        "current_teacher_screening_expansion_review_script_sha256",
        "current_teacher_screening_expansion_review_sha256",
        "current_teacher_screening_expansion_review_self_hash",
        "current_confirmation_refresh_sha256",
        "confirmation_teacher_probe_decision_sha256",
        "confirmation_teacher_probe_request_sha256",
        "confirmation_teacher_probe_contract_review_script_sha256",
        "confirmation_teacher_probe_contract_review_sha256",
        "confirmation_teacher_probe_contract_review_self_hash",
        "confirmation_teacher_probe_authorized_request_sha256",
        "confirmation_teacher_probe_review_script_sha256",
        "confirmation_teacher_probe_review_sha256",
        "confirmation_teacher_probe_review_self_hash",
        "confirmation_teacher_calibration_decision_sha256",
        "confirmation_teacher_calibration_candidate_metadata_sha256",
        "confirmation_teacher_calibration_request_sha256",
        "confirmation_teacher_calibration_contract_review_script_sha256",
        "confirmation_teacher_calibration_contract_review_sha256",
        "confirmation_teacher_calibration_contract_review_self_hash",
        "confirmation_teacher_calibration_authorized_request_sha256",
        "confirmation_teacher_calibration_review_script_sha256",
        "confirmation_teacher_calibration_review_sha256",
        "confirmation_teacher_calibration_review_self_hash",
        "prior_confirmation_refresh_sha256",
        "current_rank_1_source_wait_decision_sha256",
        "current_rank_1_source_wait_review_script_sha256",
        "current_rank_1_source_wait_review_sha256",
        "current_rank_1_source_wait_review_self_hash",
        "current_rank_1_latest_dataset_inventory_sha256",
        "accepted_daily_manifest_sha256",
        "current_daily_manifest_sha256",
    ):
        value_hash = e01a.get(key)
        if not isinstance(value_hash, str) or len(value_hash) != 64:
            raise GoldPathContractError(f"E01-A hash differs: {key}")

    e01b = _require_mapping(work_orders["E01-B"], "E01-B")
    _require_false(e01b.get("execution_authorized"), "E01-B.execution_authorized")
    _require_false(e01b.get("training_authorized"), "E01-B.training_authorized")

    e04 = _require_mapping(work_orders["E04"], "E04")
    if e04.get("optimizer_steps") != 0 or e04.get("policy_version_lag") != 0:
        raise GoldPathContractError("E04 is not a zero-update, zero-lag contract")
    stages = e04.get("stages")
    if not isinstance(stages, list) or [stage.get("games") for stage in stages] != [1, 10, 180]:
        raise GoldPathContractError("E04 game stages differ")
    if stages[-1].get("minimum_meaningful_decisions") != 10_000:
        raise GoldPathContractError("E04 qualification decision floor differs")
    if e04.get("maximum_compound_log_probability_absolute_error") != 0.00001:
        raise GoldPathContractError("E04 replay tolerance differs")
    source_contract = _require_mapping(e04.get("source_contract"), "E04 source contract")
    expected_source_keys = {
        "bridge_path",
        "bridge_sha256",
        "native_adapter_path",
        "native_adapter_sha256",
        "authorization_validator_path",
        "authorization_validator_sha256",
        "runner_path",
        "runner_sha256",
        "single_process_request_path",
        "single_process_request_sha256",
        "bridge_tests_path",
        "bridge_tests_sha256",
        "native_tests_path",
        "native_tests_sha256",
        "single_trace_review_path",
        "single_trace_review_sha256",
        "single_trace_evidence_path",
        "single_trace_evidence_sha256",
        "ten_game_request_path",
        "ten_game_request_sha256",
        "smoke_review_path",
        "smoke_review_sha256",
        "smoke_evidence_path",
        "smoke_evidence_sha256",
        "qualification_decision_path",
        "qualification_decision_sha256",
        "qualification_review_path",
        "qualification_review_sha256",
        "qualification_review_script_path",
        "qualification_review_script_sha256",
        "qualification_request_path",
        "qualification_request_sha256",
        "qualification_execution_review_path",
        "qualification_execution_review_sha256",
        "qualification_evidence_path",
        "qualification_evidence_sha256",
    }
    if set(source_contract) != expected_source_keys:
        raise GoldPathContractError("E04 source contract keys differ")
    if e04.get("single_process_runner_ready") is not True:
        raise GoldPathContractError("E04 single-process runner is not ready")
    _require_false(
        e04.get("single_process_request_authorized"),
        "E04.single_process_request_authorized",
    )
    if e04.get("downloadable_asset_parity") != "PASS":
        raise GoldPathContractError("E04 downloadable asset parity differs")
    if e04.get("hosted_runtime_behavior_parity") != "UNRESOLVED_AFTER_2026-07-23_ENGINE_UPDATE":
        raise GoldPathContractError("E04 hosted runtime behavior parity differs")
    if e04.get("single_process_authorization_consumed") is not True:
        raise GoldPathContractError("E04 single-process authorization is not consumed")
    if e04.get("single_process_trace_status") != "PASS":
        raise GoldPathContractError("E04 single-process trace is not a PASS")
    if e04.get("single_process_trace_evidence") != (
        "reports/evaluations/e04-single-process-trace-v1.json"
    ):
        raise GoldPathContractError("E04 single-process evidence path differs")
    if e04.get("smoke_authorization_consumed") is not True:
        raise GoldPathContractError("E04 smoke authorization is not consumed")
    if e04.get("smoke_status") != "PASS":
        raise GoldPathContractError("E04 ten-game smoke is not a PASS")
    if e04.get("smoke_evidence") != "reports/evaluations/e04-ten-game-smoke-v1.json":
        raise GoldPathContractError("E04 smoke evidence path differs")
    if (
        e04.get("native_games_completed") != 191
        or e04.get("native_engine_decisions") != 12_972
        or e04.get("native_meaningful_decisions") != 11_961
        or e04.get("native_forced_decisions") != 1_011
        or e04.get("smoke_games_completed") != 10
        or e04.get("smoke_engine_decisions") != 711
        or e04.get("smoke_meaningful_decisions") != 648
        or e04.get("smoke_forced_decisions") != 63
        or e04.get("qualification_games_completed") != 180
        or e04.get("qualification_engine_decisions") != 12_194
        or e04.get("qualification_meaningful_decisions") != 11_250
        or e04.get("qualification_forced_decisions") != 944
        or e04.get("qualification_terminal_boundaries_for_both_players") != 180
        or e04.get("qualification_zero_tolerance_failures") != 0
    ):
        raise GoldPathContractError("E04 completed native execution counts differ")
    for field in (
        "maximum_observed_compound_log_probability_absolute_error",
        "smoke_maximum_compound_log_probability_absolute_error",
        "qualification_maximum_compound_log_probability_absolute_error",
    ):
        observed_replay_error = e04.get(field)
        if (
            isinstance(observed_replay_error, bool)
            or not isinstance(observed_replay_error, (int, float))
            or observed_replay_error < 0
            or observed_replay_error
            > e04["maximum_compound_log_probability_absolute_error"]
        ):
            raise GoldPathContractError(f"E04 observed replay error differs: {field}")
    if e04.get("qualification_contract_status") != "PASS_RESIZED_180_GAMES":
        raise GoldPathContractError("E04 qualification contract status differs")
    qualification_projection = {
        "qualification_required_meaningful_decisions": 10_000,
        "qualification_selected_games": 180,
        "qualification_bridge_checkpoint_interval_games": 10,
        "qualification_observed_mean_meaningful_decisions_per_game": 64.8,
        "qualification_observed_min_meaningful_decisions_per_game": 56,
        "qualification_observed_max_meaningful_decisions_per_game": 70,
        "qualification_games_required_at_observed_minimum": 179,
        "qualification_games_required_at_99_percent_lower_bound": 168,
        "qualification_projected_meaningful_decisions_at_180_games_mean": 11_664.0,
        "qualification_projected_meaningful_decisions_at_180_games_observed_minimum": 10_080,
        "qualification_projected_meaningful_decisions_at_180_games_99_percent_lower_bound": 10_725.109562871574,
    }
    if any(e04.get(key) != expected for key, expected in qualification_projection.items()):
        raise GoldPathContractError("E04 qualification projection differs")
    if e04.get("qualification_contract_review_status") != "PASS":
        raise GoldPathContractError("E04 qualification contract review differs")
    if e04.get("qualification_contract_review") != (
        "reports/artifacts/e04-qualification-contract-review-v1.json"
    ):
        raise GoldPathContractError("E04 qualification review path differs")
    if e04.get("qualification_authorization_consumed") is not True:
        raise GoldPathContractError("E04 qualification authorization is not consumed")
    if e04.get("qualification_status") != "PASS":
        raise GoldPathContractError("E04 qualification is not a PASS")
    if e04.get("qualification_evidence") != (
        "reports/evaluations/e04-qualification-v1.json"
    ):
        raise GoldPathContractError("E04 qualification evidence path differs")
    if e04.get("qualification_bridge_state_sha256") != (
        "ac2f63202898ea22455d53774a56762b128728f9002726a2ca20e703a4d52362"
    ):
        raise GoldPathContractError("E04 qualification bridge state differs")
    _require_false(
        e04.get("qualification_request_ready"),
        "E04.qualification_request_ready",
    )
    _require_false(
        e04.get("qualification_request_authorized"),
        "E04.qualification_request_authorized",
    )
    if e04.get("next_stage") is not None:
        raise GoldPathContractError("E04 next stage must be absent after qualification")
    if e04.get("next_stage_request") is not None:
        raise GoldPathContractError("E04 next-stage request must be absent")
    if e04.get("next_stage_request_sha256") is not None:
        raise GoldPathContractError("E04 next-stage request hash must be absent")
    _require_false(e04.get("next_stage_authorized"), "E04.next_stage_authorized")
    _require_false(e04.get("native_execution_authorized"), "E04.native_execution_authorized")
    _require_false(
        e04.get("accelerator_execution_authorized"),
        "E04.accelerator_execution_authorized",
    )

    e08 = _require_mapping(work_orders["E08"], "E08")
    for key, expected in EXPECTED_LUCARIO.items():
        if e08.get(key) != expected:
            raise GoldPathContractError(f"E08 {key} differs")
    if e08.get("unchanged_baseline_required") is not True:
        raise GoldPathContractError("E08 unchanged baseline is not required")
    _require_false(e08.get("final_submitted_deck_frozen"), "E08.final_submitted_deck_frozen")
    _require_false(e08.get("evaluation_execution_authorized"), "E08.evaluation_execution_authorized")
    return dict(value)


def validate_e01a_dry_run(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != 1 or value.get("record_id") != "e01a-public-replay-dry-run-v1":
        raise GoldPathContractError("E01-A dry-run identity differs")
    if value.get("status") != "DRY_RUN_PASS_TRANSFER_BLOCKED":
        raise GoldPathContractError("E01-A dry run must remain transfer-blocked")
    if value.get("episode_json_transferred") != 0 or value.get("transfer_authorized") is not False:
        raise GoldPathContractError("E01-A dry run transferred or authorized replay bodies")
    selection = _require_mapping(value.get("selection"), "E01-A selection")
    caps = _require_mapping(value.get("caps"), "E01-A caps")
    items = value.get("selected_items")
    if not isinstance(items, list) or len(items) != 8:
        raise GoldPathContractError("E01-A selected file count differs")
    sizes = [_require_int(item.get("declared_bytes"), "selected declared bytes", 1) for item in items]
    if selection.get("selected_files") != len(items) or selection.get("selected_bytes") != sum(sizes):
        raise GoldPathContractError("E01-A selected summary differs")
    if len(items) > caps.get("max_files", -1):
        raise GoldPathContractError("E01-A file cap exceeded")
    if sum(sizes) > caps.get("max_total_bytes", -1):
        raise GoldPathContractError("E01-A total-byte cap exceeded")
    if max(sizes) > caps.get("max_file_bytes", -1):
        raise GoldPathContractError("E01-A per-file cap exceeded")
    if len({item.get("episode_id") for item in items}) != len(items):
        raise GoldPathContractError("E01-A selected episode IDs are duplicated")
    blocking = set(value.get("blocking_requirements", ()))
    required = {
        "exact_teacher_identity",
        "exact_60_card_deck_hash",
        "teacher_policy_consistency",
        "named_file_transfer_approval",
    }
    if blocking != required:
        raise GoldPathContractError("E01-A transfer blockers differ")
    return dict(value)


def _self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return sha256_bytes(canonical_json_bytes(payload))


def review_gold_path(
    repository_root: Path,
    *,
    work_orders_path: Path,
    dry_run_path: Path,
    decision_path: Path,
) -> dict[str, Any]:
    work_orders = validate_work_orders(load_json(work_orders_path))
    dry_run = validate_e01a_dry_run(load_json(dry_run_path))
    checks: list[dict[str, Any]] = []
    e01a = _require_mapping(work_orders["work_orders"]["E01-A"], "E01-A")
    e01_paths = (
        ("source_provenance_decision", "source_provenance_decision_sha256"),
        ("current_manifest_snapshot", "current_manifest_snapshot_sha256"),
        ("source_provenance_review_script", "source_provenance_review_script_sha256"),
        ("source_provenance_review", "source_provenance_review_sha256"),
        ("provenance_probe_placeholder", "provenance_probe_placeholder_sha256"),
        ("source_schema_decision", "source_schema_decision_sha256"),
        (
            "raw_source_schema_reconciliation",
            "raw_source_schema_reconciliation_sha256",
        ),
        ("source_schema_review_script", "source_schema_review_script_sha256"),
        ("source_schema_review", "source_schema_review_sha256"),
        ("provenance_probe_request", "provenance_probe_request_sha256"),
        ("provenance_probe_review_script", "provenance_probe_review_script_sha256"),
        ("provenance_probe_review", "provenance_probe_review_sha256"),
        ("consistency_decision", "consistency_decision_sha256"),
        ("consistency_candidate_metadata", "consistency_candidate_metadata_sha256"),
        ("consistency_request", "consistency_request_sha256"),
        (
            "consistency_contract_review_script",
            "consistency_contract_review_script_sha256",
        ),
        ("consistency_contract_review", "consistency_contract_review_sha256"),
        ("consistency_probe_review_script", "consistency_probe_review_script_sha256"),
        ("consistency_probe_review", "consistency_probe_review_sha256"),
        ("gold_teacher_decision", "gold_teacher_decision_sha256"),
        ("gold_teacher_coverage", "gold_teacher_coverage_sha256"),
        ("gold_teacher_request", "gold_teacher_request_sha256"),
        (
            "gold_teacher_contract_review_script",
            "gold_teacher_contract_review_script_sha256",
        ),
        ("gold_teacher_contract_review", "gold_teacher_contract_review_sha256"),
        ("gold_teacher_probe_review_script", "gold_teacher_probe_review_script_sha256"),
        ("gold_teacher_probe_review", "gold_teacher_probe_review_sha256"),
        ("calibration_decision", "calibration_decision_sha256"),
        ("calibration_candidate_metadata", "calibration_candidate_metadata_sha256"),
        ("calibration_request", "calibration_request_sha256"),
        ("calibration_contract_review_script", "calibration_contract_review_script_sha256"),
        ("calibration_contract_review", "calibration_contract_review_sha256"),
        ("calibration_review_script", "calibration_review_script_sha256"),
        ("calibration_review", "calibration_review_sha256"),
        ("screening_expansion_decision", "screening_expansion_decision_sha256"),
        (
            "screening_expansion_candidate_metadata",
            "screening_expansion_candidate_metadata_sha256",
        ),
        ("screening_expansion_request", "screening_expansion_request_sha256"),
        (
            "screening_expansion_contract_review_script",
            "screening_expansion_contract_review_script_sha256",
        ),
        (
            "screening_expansion_contract_review",
            "screening_expansion_contract_review_sha256",
        ),
        ("live_gold_refresh_decision", "live_gold_refresh_decision_sha256"),
        ("live_gold_refresh", "live_gold_refresh_sha256"),
        ("current_gold_teacher_probe_request", "current_gold_teacher_probe_request_sha256"),
        (
            "current_gold_teacher_contract_review_script",
            "current_gold_teacher_contract_review_script_sha256",
        ),
        (
            "current_gold_teacher_contract_review",
            "current_gold_teacher_contract_review_sha256",
        ),
        (
            "current_gold_teacher_probe_review_script",
            "current_gold_teacher_probe_review_script_sha256",
        ),
        ("current_gold_teacher_probe_review", "current_gold_teacher_probe_review_sha256"),
        ("current_teacher_calibration_decision", "current_teacher_calibration_decision_sha256"),
        (
            "current_teacher_calibration_candidate_metadata",
            "current_teacher_calibration_candidate_metadata_sha256",
        ),
        ("current_teacher_calibration_request", "current_teacher_calibration_request_sha256"),
        (
            "current_teacher_calibration_contract_review_script",
            "current_teacher_calibration_contract_review_script_sha256",
        ),
        (
            "current_teacher_calibration_contract_review",
            "current_teacher_calibration_contract_review_sha256",
        ),
        (
            "current_teacher_calibration_review_script",
            "current_teacher_calibration_review_script_sha256",
        ),
        (
            "current_teacher_calibration_review",
            "current_teacher_calibration_review_sha256",
        ),
        (
            "current_teacher_screening_expansion_decision",
            "current_teacher_screening_expansion_decision_sha256",
        ),
        (
            "current_teacher_screening_expansion_candidate_metadata",
            "current_teacher_screening_expansion_candidate_metadata_sha256",
        ),
        (
            "current_teacher_screening_expansion_request",
            "current_teacher_screening_expansion_request_sha256",
        ),
        (
            "current_teacher_screening_expansion_contract_review_script",
            "current_teacher_screening_expansion_contract_review_script_sha256",
        ),
        (
            "current_teacher_screening_expansion_contract_review",
            "current_teacher_screening_expansion_contract_review_sha256",
        ),
        (
            "current_teacher_screening_expansion_review_script",
            "current_teacher_screening_expansion_review_script_sha256",
        ),
        (
            "current_teacher_screening_expansion_review",
            "current_teacher_screening_expansion_review_sha256",
        ),
        ("prior_confirmation_refresh", "prior_confirmation_refresh_sha256"),
        ("current_confirmation_refresh", "current_confirmation_refresh_sha256"),
        (
            "confirmation_teacher_probe_decision",
            "confirmation_teacher_probe_decision_sha256",
        ),
        (
            "confirmation_teacher_probe_request",
            "confirmation_teacher_probe_request_sha256",
        ),
        (
            "confirmation_teacher_probe_contract_review_script",
            "confirmation_teacher_probe_contract_review_script_sha256",
        ),
        (
            "confirmation_teacher_probe_contract_review",
            "confirmation_teacher_probe_contract_review_sha256",
        ),
        (
            "confirmation_teacher_probe_review_script",
            "confirmation_teacher_probe_review_script_sha256",
        ),
        (
            "confirmation_teacher_probe_review",
            "confirmation_teacher_probe_review_sha256",
        ),
        (
            "confirmation_teacher_calibration_decision",
            "confirmation_teacher_calibration_decision_sha256",
        ),
        (
            "confirmation_teacher_calibration_candidate_metadata",
            "confirmation_teacher_calibration_candidate_metadata_sha256",
        ),
        (
            "confirmation_teacher_calibration_request",
            "confirmation_teacher_calibration_request_sha256",
        ),
        (
            "confirmation_teacher_calibration_contract_review_script",
            "confirmation_teacher_calibration_contract_review_script_sha256",
        ),
        (
            "confirmation_teacher_calibration_contract_review",
            "confirmation_teacher_calibration_contract_review_sha256",
        ),
        (
            "confirmation_teacher_calibration_review_script",
            "confirmation_teacher_calibration_review_script_sha256",
        ),
        (
            "confirmation_teacher_calibration_review",
            "confirmation_teacher_calibration_review_sha256",
        ),
        (
            "current_rank_1_source_wait_decision",
            "current_rank_1_source_wait_decision_sha256",
        ),
        (
            "current_rank_1_source_wait_review_script",
            "current_rank_1_source_wait_review_script_sha256",
        ),
        (
            "current_rank_1_source_wait_review",
            "current_rank_1_source_wait_review_sha256",
        ),
    )
    for path_key, hash_key in e01_paths:
        relative = str(e01a[path_key])
        observed = sha256_file(repository_root / "ptcg-rl" / relative)
        if observed != e01a[hash_key]:
            raise GoldPathContractError(f"E01-A evidence hash differs: {relative}")
    e01_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["source_provenance_review"])
    )
    e01_qualification = _require_mapping(
        e01_review.get("qualification"), "E01-A source qualification"
    )
    e01_probe = _require_mapping(e01_review.get("probe"), "E01-A probe boundary")
    comparison = _require_mapping(
        e01_review.get("manifest_comparison"), "E01-A manifest comparison"
    )
    if (
        e01_review.get("status") != "PASS"
        or e01_review.get("decision")
        != "BLOCK_E01_SOURCE_MANIFEST_CONTRACT_UNRESOLVED"
        or e01_review.get("reviewed_decision") != "DEC-013"
        or comparison.get("manifest_object_matches") is not False
        or comparison.get("schema_matches") is not False
        or comparison.get("selected_episode_ids_match") is not True
        or len(comparison.get("selected_row_mismatches", ())) != 8
        or any(e01_qualification.values())
        or e01_probe.get("request_ready") is not False
        or e01_probe.get("request_authorized") is not False
        or e01_probe.get("files_authorized") != 0
        or e01_probe.get("bytes_authorized") != 0
        or e01_probe.get("agent_logs_authorized") is not False
        or e01_probe.get("training_authorized") is not False
        or e01_probe.get("external_compute_authorized") is not False
        or e01_review.get("review_sha256")
        != e01a["source_provenance_review_self_hash"]
    ):
        raise GoldPathContractError("E01-A source-provenance review differs")
    checks.append(
        {
            "check": "e01_source_provenance",
            "status": "BLOCKED",
            "decision": "DEC-013",
            "accepted_manifest_sha256": comparison["accepted_manifest_sha256"],
            "current_manifest_sha256": comparison["current_manifest_sha256"],
            "selected_episode_ids_match": True,
            "selected_row_mismatches": 8,
            "replay_bodies_transferred": 0,
            "probe_request_ready": False,
            "probe_authorized": False,
        }
    )

    e01_schema_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["source_schema_review"])
    )
    adapter = _require_mapping(
        e01_schema_review.get("adapter"), "E01-A source-schema adapter"
    )
    schema_probe = _require_mapping(
        e01_schema_review.get("probe"), "E01-A reconciled probe"
    )
    schema_qualification = _require_mapping(
        e01_schema_review.get("qualification"),
        "E01-A reconciled qualification",
    )
    if (
        e01_schema_review.get("status") != "PASS"
        or e01_schema_review.get("decision")
        != "ACCEPT_PROVENANCE_ADAPTER_AND_ONE_FILE_REQUEST"
        or e01_schema_review.get("reviewed_decision") != "DEC-014"
        or adapter.get("episode_identity_reproduced") is not True
        or adapter.get("timestamp_reproduced") is not True
        or adapter.get("file_byte_count_reproduced") is not True
        or adapter.get("team_identity_reproduced") is not True
        or adapter.get("submission_identity_reproduced") is not True
        or adapter.get("rating_field_reproduced") is not False
        or adapter.get("rating_field_used_for_probe") is not False
        or adapter.get("candidate_set_reranked") is not False
        or schema_probe.get("episode_id") != 87_703_034
        or schema_probe.get("file_name") != "87703034.json"
        or schema_probe.get("declared_bytes") != 3_641_302
        or schema_probe.get("request_ready") is not True
        or schema_probe.get("request_authorized") is not False
        or schema_probe.get("output_directory_exists") is not False
        or schema_probe.get("files_authorized") != 1
        or schema_probe.get("agent_logs_authorized") is not False
        or schema_probe.get("additional_replays_authorized") is not False
        or schema_probe.get("training_authorized") is not False
        or schema_probe.get("external_compute_authorized") is not False
        or schema_qualification.get("source_schema_reconciled_for_probe") is not True
        or any(
            schema_qualification.get(key) is not False
            for key in (
                "teacher_strength_qualified",
                "deck_qualified",
                "policy_consistency_qualified",
                "e01_screening_gate_passed",
                "replay_transfer_authorized",
            )
        )
        or e01_schema_review.get("review_sha256")
        != e01a["source_schema_review_self_hash"]
    ):
        raise GoldPathContractError("E01-A source-schema review differs")
    checks.append(
        {
            "check": "e01_source_schema_reconciliation",
            "status": "PASS",
            "decision": "DEC-014",
            "evidence_sha256": sha256_file(
                repository_root / "ptcg-rl" / str(e01a["source_schema_review"])
            ),
            "candidate_set_reranked": False,
            "rating_field_reproduced": False,
            "probe_episode_id": 87_703_034,
            "probe_file_name": "87703034.json",
            "probe_declared_bytes": 3_641_302,
            "probe_request_ready": True,
            "probe_authorized": False,
            "replay_bodies_transferred": 0,
            "agent_logs_transferred": 0,
        }
    )

    probe_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["provenance_probe_request"])
    )
    probe_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["provenance_probe_review"])
    )
    probe_qualification = _require_mapping(
        probe_review.get("qualification"), "E01-A provenance-probe qualification"
    )
    probe_alignment = _require_mapping(
        probe_review.get("action_aligned_supervision"),
        "E01-A provenance-probe action alignment",
    )
    probe_decks = probe_review.get("decks")
    if (
        probe_request.get("status") != "CONSUMED"
        or probe_request.get("request_ready") is not False
        or probe_request.get("authorized") is not False
        or probe_request.get("approval", {}).get("authorized_request_sha256")
        != e01a["provenance_probe_authorized_request_sha256"]
        or probe_review.get("status") != "PASS"
        or probe_review.get("decision")
        != "ACCEPT_PROVENANCE_ONLY_E01_SCREENING_BLOCKED"
        or probe_review.get("reviewed_decision") != "DEC-014"
        or probe_review.get("review_sha256")
        != e01a["provenance_probe_review_self_hash"]
        or not isinstance(probe_decks, list)
        or [deck.get("multiset_sha256") for deck in probe_decks]
        != e01a["provenance_probe_deck_hashes"]
        or any(deck.get("current_asset_construction_checks") != "PASS" for deck in probe_decks)
        or probe_alignment.get("availability") != "PASS"
        or probe_alignment.get("active_selection_requests") != 128
        or probe_alignment.get("nonempty_lagged_selections") != 125
        or probe_alignment.get("empty_lagged_selections") != 3
        or probe_alignment.get("maximum_option_count") != 25
        or probe_alignment.get("maximum_selection_count") != 4
        or probe_alignment.get("training_labels_created") is not False
        or probe_qualification.get("provenance_probe_passed") is not True
        or probe_qualification.get("exact_deck_hashes_recovered") is not True
        or probe_qualification.get("action_aligned_supervision_available") is not True
        or any(
            probe_qualification.get(key) is not False
            for key in (
                "teacher_strength_qualified",
                "policy_consistency_qualified",
                "exact_historical_deck_legality_qualified",
                "e01_screening_gate_passed",
                "replay_transfer_authorized",
                "training_authorized",
            )
        )
    ):
        raise GoldPathContractError("E01-A completed provenance probe differs")
    probe_replay_path = repository_root / "ptcg-rl/private/g3/e01/provenance-probe-v1/87703034.json"
    if (
        not probe_replay_path.is_file()
        or probe_replay_path.stat().st_size != 3_641_302
        or sha256_file(probe_replay_path) != e01a["provenance_probe_replay_sha256"]
    ):
        raise GoldPathContractError("E01-A quarantined provenance replay differs")
    checks.append(
        {
            "check": "e01_provenance_probe",
            "status": "PASS",
            "decision": "DEC-014",
            "request_sha256": e01a["provenance_probe_request_sha256"],
            "authorization_consumed": True,
            "episode_id": 87_703_034,
            "file_name": "87703034.json",
            "bytes": 3_641_302,
            "replay_sha256": e01a["provenance_probe_replay_sha256"],
            "deck_hashes": e01a["provenance_probe_deck_hashes"],
            "active_selection_requests": 128,
            "training_labels_created": 0,
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded": 0,
            "screening_gate_passed": False,
        }
    )

    consistency_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["consistency_request"])
    )
    consistency_contract_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["consistency_contract_review"])
    )
    consistency_probe_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["consistency_probe_review"])
    )
    consistency_result = _require_mapping(
        consistency_probe_review.get("consistency"),
        "E01-A completed consistency result",
    )
    consistency_qualification = _require_mapping(
        consistency_probe_review.get("qualification"),
        "E01-A completed consistency qualification",
    )
    consistency_execution = _require_mapping(
        consistency_request.get("execution"), "E01-A consistency execution"
    )
    if (
        consistency_request.get("status") != "CONSUMED"
        or consistency_request.get("request_ready") is not False
        or consistency_request.get("authorized") is not False
        or consistency_request.get("maximum_new_files") != 1
        or consistency_request.get("maximum_new_bytes") != 559_779
        or consistency_request.get("approval", {}).get("authorized_request_sha256")
        != e01a["consistency_authorized_request_sha256"]
        or consistency_request.get("additional_episode", {}).get("episode_id")
        != 87_741_212
        or consistency_request.get("additional_episode", {}).get("file_name")
        != "87741212.json"
        or consistency_request.get("additional_episode", {}).get("submission_id")
        != 54_933_084
        or consistency_execution.get("files_downloaded") != 1
        or consistency_execution.get("bytes_downloaded") != 559_779
        or consistency_execution.get("downloaded_file_sha256")
        != e01a["consistency_replay_sha256"]
        or consistency_execution.get("agent_logs_downloaded") != 0
        or consistency_execution.get("additional_replays_downloaded_after_named_file") != 0
        or consistency_execution.get("training_label_exports") != 0
        or consistency_execution.get("optimizer_steps") != 0
        or consistency_contract_review.get("status") != "PASS"
        or consistency_contract_review.get("decision")
        != "ACCEPT_ONE_FILE_CONSISTENCY_REQUEST_UNAUTHORIZED"
        or consistency_contract_review.get("reviewed_decision") != "DEC-015"
        or consistency_contract_review.get("review_sha256")
        != e01a["consistency_contract_review_self_hash"]
        or consistency_probe_review.get("status") != "PASS"
        or consistency_probe_review.get("decision")
        != "ACCEPT_SAME_SUBMISSION_DECK_CONSISTENCY_SCREENING_FLOOR_BLOCKED"
        or consistency_probe_review.get("reviewed_decision") != "DEC-015"
        or consistency_probe_review.get("review_sha256")
        != e01a["consistency_probe_review_self_hash"]
        or consistency_result.get("exact_benarg_deck_match") is not True
        or consistency_result.get("benarg_deck_multiset_sha256")
        != "606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283"
        or consistency_result.get("combined_benarg_active_selection_requests") != 65
        or consistency_result.get("combined_all_player_active_selection_requests") != 157
        or consistency_result.get("screening_teacher_decision_shortfall") != 4_935
        or consistency_qualification.get("same_submission_identity_qualified") is not True
        or consistency_qualification.get("exact_deck_consistency_qualified") is not True
        or consistency_qualification.get("action_aligned_supervision_available") is not True
        or consistency_qualification.get("policy_artifact_identity_inferred_from_same_submission_id")
        is not True
        or any(
            consistency_qualification.get(key) is not False
            for key in (
                "policy_behavior_consistency_qualified",
                "exact_historical_deck_legality_qualified",
                "teacher_strength_qualified",
                "minimum_5000_teacher_decisions_met",
                "e01_screening_gate_passed",
                "replay_transfer_authorized",
                "training_authorized",
            )
        )
    ):
        raise GoldPathContractError("E01-A completed consistency probe differs")
    consistency_replay_path = (
        repository_root / "ptcg-rl/private/g3/e01/consistency-probe-v1/87741212.json"
    )
    if (
        not consistency_replay_path.is_file()
        or consistency_replay_path.stat().st_size != 559_779
        or sha256_file(consistency_replay_path) != e01a["consistency_replay_sha256"]
    ):
        raise GoldPathContractError("E01-A quarantined consistency replay differs")
    checks.append(
        {
            "check": "e01_same_submission_consistency_probe",
            "status": "PASS",
            "decision": "DEC-015",
            "request_sha256": e01a["consistency_request_sha256"],
            "authorization_consumed": True,
            "episode_id": 87_741_212,
            "file_name": "87741212.json",
            "bytes": 559_779,
            "replay_sha256": e01a["consistency_replay_sha256"],
            "same_submission_id": 54_933_084,
            "exact_deck_match": True,
            "teacher_active_selection_requests": 65,
            "all_player_active_selection_requests": 157,
            "screening_decision_shortfall": 4_935,
            "screening_gate_passed": False,
        }
    )

    gold_teacher_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["gold_teacher_request"])
    )
    gold_teacher_contract = load_json(
        repository_root / "ptcg-rl" / str(e01a["gold_teacher_contract_review"])
    )
    gold_teacher_probe_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["gold_teacher_probe_review"])
    )
    gold_teacher_execution = _require_mapping(
        gold_teacher_request.get("execution"), "E01-A Luca execution"
    )
    gold_teacher_result = _require_mapping(
        gold_teacher_probe_review.get("consistency"), "E01-A Luca probe result"
    )
    gold_teacher_qualification = _require_mapping(
        gold_teacher_probe_review.get("qualification"),
        "E01-A Luca probe qualification",
    )
    if (
        gold_teacher_request.get("status") != "CONSUMED"
        or gold_teacher_request.get("request_ready") is not False
        or gold_teacher_request.get("authorized") is not False
        or gold_teacher_request.get("maximum_new_files") != 2
        or gold_teacher_request.get("maximum_new_bytes") != 1_313_221
        or gold_teacher_request.get("approval", {}).get("authorized_request_sha256")
        != e01a["gold_teacher_authorized_request_sha256"]
        or gold_teacher_execution.get("files_downloaded") != 2
        or gold_teacher_execution.get("bytes_downloaded") != 1_313_221
        or [item.get("sha256") for item in gold_teacher_execution.get("downloaded_files", [])]
        != e01a["gold_teacher_replay_sha256"]
        or gold_teacher_execution.get("agent_logs_downloaded") != 0
        or gold_teacher_execution.get("additional_replays_downloaded_after_named_files") != 0
        or gold_teacher_execution.get("training_label_exports") != 0
        or gold_teacher_execution.get("optimizer_steps") != 0
        or gold_teacher_contract.get("status") != "PASS"
        or gold_teacher_contract.get("decision")
        != "ACCEPT_EXACT_TWO_FILE_LUCA_GOLD_TEACHER_REQUEST_UNAUTHORIZED"
        or gold_teacher_contract.get("reviewed_decision") != "DEC-016"
        or gold_teacher_contract.get("review_sha256")
        != e01a["gold_teacher_contract_review_self_hash"]
        or gold_teacher_probe_review.get("status") != "PASS"
        or gold_teacher_probe_review.get("decision")
        != "ACCEPT_GOLD_REGION_TEACHER_DECK_CONSISTENCY_MODULE_BOUNDARY_SCREENING_FLOOR_BLOCKED"
        or gold_teacher_probe_review.get("reviewed_decision") != "DEC-016"
        or gold_teacher_probe_review.get("review_sha256")
        != e01a["gold_teacher_probe_review_self_hash"]
        or gold_teacher_result.get("exact_luca_deck_match") is not True
        or gold_teacher_result.get("luca_deck_multiset_sha256")
        != e01a["gold_teacher_deck_multiset_sha256"]
        or gold_teacher_result.get("same_module_version") is not False
        or gold_teacher_result.get("module_versions") != ["1.32.2", "1.32.1"]
        or gold_teacher_result.get("combined_luca_active_selection_requests") != 37
        or gold_teacher_result.get("combined_all_player_active_selection_requests") != 61
        or gold_teacher_result.get("screening_teacher_decision_shortfall") != 4_963
        or gold_teacher_qualification.get("teacher_strength_qualified") is not True
        or gold_teacher_qualification.get("same_submission_identity_qualified") is not True
        or gold_teacher_qualification.get("exact_deck_consistency_qualified") is not True
        or gold_teacher_qualification.get("action_aligned_supervision_available") is not True
        or gold_teacher_qualification.get("same_module_version_qualified") is not False
        or gold_teacher_qualification.get("policy_behavior_consistency_qualified") is not False
        or gold_teacher_qualification.get("minimum_5000_teacher_decisions_met") is not False
        or gold_teacher_qualification.get("e01_screening_gate_passed") is not False
        or gold_teacher_qualification.get("replay_transfer_authorized") is not False
        or gold_teacher_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError("E01-A completed Luca teacher probe differs")
    luca_root = repository_root / "ptcg-rl/private/g3/e01/luca-gold-teacher-probe-v1"
    luca_files = [
        ("87731214.json", 574_428, e01a["gold_teacher_replay_sha256"][0]),
        ("87615736.json", 738_793, e01a["gold_teacher_replay_sha256"][1]),
    ]
    for file_name, expected_bytes, expected_sha256 in luca_files:
        path = luca_root / file_name
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or sha256_file(path) != expected_sha256
        ):
            raise GoldPathContractError("E01-A quarantined Luca replay differs")
    checks.append(
        {
            "check": "e01_luca_gold_teacher_probe",
            "status": "PASS",
            "decision": "DEC-016",
            "request_sha256": e01a["gold_teacher_request_sha256"],
            "authorization_consumed": True,
            "teacher_submission_id": 54_863_653,
            "teacher_submission_public_score": 1180.9,
            "leaderboard_rank": 2,
            "episode_ids": [87_731_214, 87_615_736],
            "files": 2,
            "bytes": 1_313_221,
            "exact_deck_match": True,
            "deck_multiset_sha256": e01a["gold_teacher_deck_multiset_sha256"],
            "module_versions": ["1.32.2", "1.32.1"],
            "same_module_version": False,
            "teacher_active_selection_requests": 37,
            "screening_decision_shortfall": 4_963,
            "screening_gate_passed": False,
        }
    )

    calibration_metadata = load_json(
        repository_root / "ptcg-rl" / str(e01a["calibration_candidate_metadata"])
    )
    calibration_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["calibration_request"])
    )
    calibration_contract = load_json(
        repository_root / "ptcg-rl" / str(e01a["calibration_contract_review"])
    )
    calibration_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["calibration_review"])
    )
    calibration_selection = _require_mapping(
        calibration_metadata.get("selection"), "E01-A calibration metadata selection"
    )
    calibration_execution = _require_mapping(
        calibration_request.get("execution"), "E01-A calibration execution"
    )
    calibration_result = _require_mapping(
        calibration_review.get("consistency"), "E01-A calibration result"
    )
    calibration_density = _require_mapping(
        calibration_review.get("density"), "E01-A calibration density"
    )
    calibration_qualification = _require_mapping(
        calibration_review.get("qualification"), "E01-A calibration qualification"
    )
    if (
        calibration_selection.get("files") != 12
        or calibration_selection.get("total_bytes") != 63_828_057
        or calibration_request.get("status") != "CONSUMED"
        or calibration_request.get("request_ready") is not False
        or calibration_request.get("authorized") is not False
        or calibration_request.get("approval", {}).get("authorized_request_sha256")
        != e01a["calibration_authorized_request_sha256"]
        or calibration_execution.get("files_downloaded") != 12
        or calibration_execution.get("bytes_downloaded") != 63_828_057
        or calibration_execution.get("agent_logs_downloaded") != 0
        or calibration_execution.get("additional_replays_downloaded_after_named_files") != 0
        or calibration_execution.get("training_label_exports") != 0
        or calibration_execution.get("optimizer_steps") != 0
        or calibration_contract.get("status") != "PASS"
        or calibration_contract.get("decision")
        != "ACCEPT_EXACT_12_FILE_LUCA_CALIBRATION_REQUEST_UNAUTHORIZED"
        or calibration_contract.get("reviewed_decision") != "DEC-017"
        or calibration_contract.get("review_sha256")
        != e01a["calibration_contract_review_self_hash"]
        or calibration_review.get("status") != "PASS"
        or calibration_review.get("decision")
        != "ACCEPT_LUCA_SAME_VERSION_CALIBRATION_SCREENING_FLOOR_BLOCKED"
        or calibration_review.get("reviewed_decision") != "DEC-017"
        or calibration_review.get("review_sha256") != e01a["calibration_review_self_hash"]
        or calibration_result.get("module_versions") != ["1.32.2"]
        or calibration_result.get("all_same_module_version") is not True
        or calibration_result.get("exact_luca_deck_match") is not True
        or calibration_result.get("luca_deck_multiset_sha256")
        != e01a["gold_teacher_deck_multiset_sha256"]
        or calibration_result.get("all_replay_action_alignment") != "PASS"
        or calibration_result.get("calibration_luca_active_selection_requests") != 1_170
        or calibration_result.get("combined_all_player_active_selection_requests") != 2_258
        or calibration_density.get("combined_observed_luca_decisions") != 1_207
        or calibration_density.get("screening_teacher_decision_shortfall") != 3_793
        or calibration_qualification.get("same_module_version_qualified") is not True
        or calibration_qualification.get("policy_behavior_consistency_qualified") is not True
        or calibration_qualification.get("minimum_5000_teacher_decisions_met") is not False
        or calibration_qualification.get("e01_screening_gate_passed") is not False
        or calibration_qualification.get("replay_transfer_authorized") is not False
        or calibration_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError("E01-A completed Luca calibration differs")
    calibration_root = repository_root / "ptcg-rl/private/g3/e01/luca-same-version-calibration-v1"
    downloaded_files = calibration_execution.get("downloaded_files")
    if not isinstance(downloaded_files, list) or len(downloaded_files) != 12:
        raise GoldPathContractError("E01-A calibration file list differs")
    expected_names = sorted(Path(str(item["path"])).name for item in downloaded_files)
    observed_names = sorted(path.name for path in calibration_root.iterdir() if path.is_file())
    if observed_names != expected_names:
        raise GoldPathContractError("E01-A calibration quarantine file set differs")
    for item in downloaded_files:
        path = repository_root / "ptcg-rl" / str(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or sha256_file(path) != item.get("sha256")
        ):
            raise GoldPathContractError("E01-A quarantined calibration replay differs")
    checks.append(
        {
            "check": "e01_luca_same_version_calibration",
            "status": "PASS",
            "decision": "DEC-017",
            "request_sha256": e01a["calibration_request_sha256"],
            "authorization_consumed": True,
            "files": 12,
            "bytes": 63_828_057,
            "module_versions": ["1.32.2"],
            "exact_deck_match": True,
            "calibration_luca_decisions": 1_170,
            "combined_observed_luca_decisions": 1_207,
            "screening_decision_shortfall": 3_793,
            "screening_gate_passed": False,
        }
    )

    expansion_metadata = load_json(
        repository_root / "ptcg-rl" / str(e01a["screening_expansion_candidate_metadata"])
    )
    expansion_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["screening_expansion_request"])
    )
    expansion_contract = load_json(
        repository_root / "ptcg-rl" / str(e01a["screening_expansion_contract_review"])
    )
    expansion_selection = _require_mapping(
        expansion_metadata.get("selection"), "E01-A screening expansion selection"
    )
    expansion_boundary = _require_mapping(
        expansion_contract.get("request"), "E01-A screening expansion boundary"
    )
    expansion_qualification = _require_mapping(
        expansion_contract.get("qualification"), "E01-A expansion qualification"
    )
    if (
        expansion_selection.get("selected_files") != 51
        or expansion_selection.get("selected_bytes") != 270_807_738
        or expansion_selection.get("at_or_after_anchor_files") != 27
        or expansion_selection.get("pre_anchor_boundary_files") != 24
        or expansion_request.get("status") != "READY_UNAUTHORIZED"
        or expansion_request.get("request_ready") is not True
        or expansion_request.get("authorized") is not False
        or expansion_request.get("maximum_new_files") != 51
        or expansion_request.get("maximum_new_bytes") != 270_807_738
        or expansion_contract.get("status") != "PASS"
        or expansion_contract.get("decision")
        != "ACCEPT_EXACT_51_FILE_LUCA_SCREENING_EXPANSION_REQUEST_UNAUTHORIZED"
        or expansion_contract.get("reviewed_decision") != "DEC-018"
        or expansion_contract.get("review_sha256")
        != e01a["screening_expansion_contract_review_self_hash"]
        or expansion_boundary.get("request_ready") is not True
        or expansion_boundary.get("authorized") is not False
        or expansion_boundary.get("maximum_new_files") != 51
        or expansion_boundary.get("maximum_new_bytes") != 270_807_738
        or expansion_boundary.get("output_directory_exists") is not False
        or expansion_boundary.get("count_only_module_version") != "1.32.2"
        or expansion_boundary.get("nonmatching_files_rejected_from_counts") is not True
        or expansion_boundary.get("agent_logs_authorized") is not False
        or expansion_boundary.get("additional_replays_authorized") is not False
        or expansion_boundary.get("raw_exports_authorized") is not False
        or expansion_boundary.get("training_authorized") is not False
        or expansion_boundary.get("external_compute_authorized") is not False
        or expansion_qualification.get("same_version_source_consistency_qualified") is not True
        or expansion_qualification.get("minimum_5000_teacher_decisions_met") is not False
        or expansion_qualification.get("e01_screening_gate_passed") is not False
        or expansion_qualification.get("screening_expansion_request_ready") is not True
        or expansion_qualification.get("replay_transfer_authorized") is not False
        or expansion_qualification.get("training_authorized") is not False
        or (repository_root / "ptcg-rl/private/g3/e01/luca-screening-expansion-v1").exists()
    ):
        raise GoldPathContractError("E01-A Luca screening expansion contract differs")
    checks.append(
        {
            "check": "e01_luca_screening_expansion_contract",
            "status": "PASS",
            "decision": "DEC-018",
            "request_sha256": e01a["screening_expansion_request_sha256"],
            "teacher_submission_id": 54_863_653,
            "maximum_new_files": 51,
            "maximum_new_bytes": 270_807_738,
            "at_or_after_anchor_files": 27,
            "pre_anchor_boundary_files": 24,
            "count_only_module_version": "1.32.2",
            "request_ready": True,
            "authorized": False,
        }
    )

    live_refresh = load_json(
        repository_root / "ptcg-rl" / str(e01a["live_gold_refresh"])
    )
    current_teacher_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_gold_teacher_probe_request"])
    )
    current_teacher_contract = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_gold_teacher_contract_review"])
    )
    current_teacher_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_gold_teacher_probe_review"])
    )
    live_selection = _require_mapping(
        live_refresh.get("selection"), "E01-A live gold selection"
    )
    current_teacher_execution = _require_mapping(
        current_teacher_request.get("execution"), "E01-A current teacher execution"
    )
    current_teacher_result = _require_mapping(
        current_teacher_review.get("consistency"), "E01-A current teacher result"
    )
    current_teacher_qualification = _require_mapping(
        current_teacher_review.get("qualification"),
        "E01-A current teacher qualification",
    )
    if (
        live_refresh.get("record_id") != "e01-live-gold-refresh-v1"
        or live_selection.get("teacher_live_rank") != 1
        or live_selection.get("teacher_team_id") != 16_380_946
        or live_selection.get("teacher_team_name") != "flg"
        or live_selection.get("teacher_submission_id") != 55_004_495
        or live_selection.get("teacher_submission_public_score") != 1244.2
        or live_selection.get("selected_total_bytes") != 3_996_398
        or current_teacher_request.get("status") != "CONSUMED"
        or current_teacher_request.get("request_ready") is not False
        or current_teacher_request.get("authorized") is not False
        or current_teacher_request.get("approval", {}).get(
            "authorized_request_sha256"
        )
        != e01a["current_gold_teacher_authorized_request_sha256"]
        or current_teacher_execution.get("files_downloaded") != 2
        or current_teacher_execution.get("bytes_downloaded") != 3_996_398
        or current_teacher_execution.get("agent_logs_downloaded") != 0
        or current_teacher_execution.get(
            "additional_replays_downloaded_after_named_files"
        )
        != 0
        or current_teacher_execution.get("training_label_exports") != 0
        or current_teacher_execution.get("optimizer_steps") != 0
        or current_teacher_contract.get("status") != "PASS"
        or current_teacher_contract.get("decision")
        != "ACCEPT_EXACT_TWO_FILE_CURRENT_RANK_1_TEACHER_REQUEST_UNAUTHORIZED"
        or current_teacher_contract.get("reviewed_decision") != "DEC-019"
        or current_teacher_contract.get("review_sha256")
        != e01a["current_gold_teacher_contract_review_self_hash"]
        or current_teacher_review.get("status") != "PASS"
        or current_teacher_review.get("decision")
        != "ACCEPT_CURRENT_RANK_1_DRAGAPULT_TEACHER_DECK_AND_ACTION_CONSISTENCY_SCREENING_FLOOR_BLOCKED"
        or current_teacher_review.get("reviewed_decision") != "DEC-019"
        or current_teacher_review.get("review_sha256")
        != e01a["current_gold_teacher_probe_review_self_hash"]
        or current_teacher_result.get("module_versions") != ["1.32.2"]
        or current_teacher_result.get("same_module_version") is not True
        or current_teacher_result.get("exact_teacher_deck_match") is not True
        or current_teacher_result.get("teacher_deck_multiset_sha256")
        != e01a["current_gold_teacher_deck_multiset_sha256"]
        or current_teacher_result.get("teacher_archetype_context_label")
        != "Dragapult ex"
        or current_teacher_result.get("both_replay_action_alignment") != "PASS"
        or current_teacher_result.get("combined_all_player_active_selection_requests")
        != 165
        or current_teacher_result.get("combined_teacher_active_selection_requests")
        != 94
        or current_teacher_result.get("screening_teacher_decision_shortfall")
        != 4_906
        or current_teacher_qualification.get("current_rank_1_strength_metadata_qualified")
        is not True
        or current_teacher_qualification.get("teacher_strength_qualified") is not True
        or current_teacher_qualification.get("same_module_version_qualified") is not True
        or current_teacher_qualification.get("exact_deck_consistency_qualified") is not True
        or current_teacher_qualification.get("action_aligned_supervision_available")
        is not True
        or current_teacher_qualification.get("minimum_5000_teacher_decisions_met")
        is not False
        or current_teacher_qualification.get("e01_screening_gate_passed") is not False
        or current_teacher_qualification.get("replay_transfer_authorized") is not False
        or current_teacher_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError("E01-A current rank-1 Dragapult probe differs")
    current_teacher_root = (
        repository_root / "ptcg-rl/private/g3/e01/flg-gold-teacher-probe-v1"
    )
    current_teacher_files = [
        (
            "88302734.json",
            624_407,
            "30a97dfb6bbfe65b224011103b215c7e2ec946ad1cd977cc82a88b1232444452",
        ),
        (
            "88333037.json",
            3_371_991,
            "5b6b330d543037e561a889fe76baaf84d427019b0fc0523080045a6abc5214d6",
        ),
    ]
    if sorted(path.name for path in current_teacher_root.iterdir() if path.is_file()) != [
        item[0] for item in current_teacher_files
    ]:
        raise GoldPathContractError("E01-A current rank-1 quarantine file set differs")
    for file_name, expected_bytes, expected_sha256 in current_teacher_files:
        path = current_teacher_root / file_name
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or sha256_file(path) != expected_sha256
        ):
            raise GoldPathContractError("E01-A quarantined current rank-1 replay differs")
    checks.append(
        {
            "check": "e01_current_rank_1_dragapult_probe",
            "status": "PASS",
            "decision": "DEC-019",
            "request_sha256": e01a["current_gold_teacher_probe_request_sha256"],
            "authorization_consumed": True,
            "teacher_submission_id": 55_004_495,
            "teacher_live_rank_at_refresh": 1,
            "teacher_submission_public_score": 1244.2,
            "files": 2,
            "bytes": 3_996_398,
            "module_versions": ["1.32.2"],
            "deck_multiset_sha256": e01a[
                "current_gold_teacher_deck_multiset_sha256"
            ],
            "archetype_context_label": "Dragapult ex",
            "teacher_active_selection_requests": 94,
            "screening_decision_shortfall": 4_906,
            "screening_gate_passed": False,
        }
    )

    current_calibration_metadata = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_calibration_candidate_metadata"])
    )
    current_calibration_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_teacher_calibration_request"])
    )
    current_calibration_contract = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_calibration_contract_review"])
    )
    current_calibration_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_teacher_calibration_review"])
    )
    current_calibration_selection = _require_mapping(
        current_calibration_metadata.get("selection"),
        "E01-A current teacher calibration selection",
    )
    current_calibration_execution = _require_mapping(
        current_calibration_request.get("execution"),
        "E01-A current teacher calibration execution",
    )
    current_calibration_result = _require_mapping(
        current_calibration_review.get("consistency"),
        "E01-A current teacher calibration consistency",
    )
    current_calibration_density = _require_mapping(
        current_calibration_review.get("density"),
        "E01-A current teacher calibration density",
    )
    current_calibration_qualification = _require_mapping(
        current_calibration_review.get("qualification"),
        "E01-A current teacher calibration qualification",
    )
    if (
        current_calibration_metadata.get("record_id")
        != "e01-flg-dragapult-calibration-candidates-v1"
        or current_calibration_selection.get("files") != 12
        or current_calibration_selection.get("total_bytes") != 63_562_985
        or current_calibration_selection.get("balanced_strata")
        != {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
        or current_calibration_request.get("status") != "CONSUMED"
        or current_calibration_request.get("request_ready") is not False
        or current_calibration_request.get("authorized") is not False
        or current_calibration_request.get("approval", {}).get(
            "authorized_request_sha256"
        )
        != e01a["current_teacher_calibration_authorized_request_sha256"]
        or current_calibration_execution.get("files_downloaded") != 12
        or current_calibration_execution.get("bytes_downloaded") != 63_562_985
        or current_calibration_execution.get("agent_logs_downloaded") != 0
        or current_calibration_execution.get(
            "additional_replays_downloaded_after_named_files"
        )
        != 0
        or current_calibration_execution.get("training_label_exports") != 0
        or current_calibration_execution.get("optimizer_steps") != 0
        or current_calibration_execution.get("external_compute") is not False
        or current_calibration_execution.get("training") is not False
        or current_calibration_execution.get("submission") is not False
        or current_calibration_contract.get("status") != "PASS"
        or current_calibration_contract.get("decision")
        != "ACCEPT_EXACT_12_FILE_CURRENT_RANK_1_DRAGAPULT_CALIBRATION_REQUEST_UNAUTHORIZED"
        or current_calibration_contract.get("reviewed_decision") != "DEC-020"
        or current_calibration_contract.get("review_sha256")
        != e01a["current_teacher_calibration_contract_review_self_hash"]
        or current_calibration_review.get("status") != "PASS"
        or current_calibration_review.get("decision")
        != "ACCEPT_CURRENT_RANK_1_DRAGAPULT_CALIBRATION_SCREENING_FLOOR_BLOCKED"
        or current_calibration_review.get("reviewed_decision") != "DEC-020"
        or current_calibration_review.get("review_sha256")
        != e01a["current_teacher_calibration_review_self_hash"]
        or current_calibration_result.get("module_versions") != ["1.32.2"]
        or current_calibration_result.get("all_same_module_version") is not True
        or current_calibration_result.get("exact_teacher_deck_match") is not True
        or current_calibration_result.get("teacher_deck_multiset_sha256")
        != e01a["current_gold_teacher_deck_multiset_sha256"]
        or current_calibration_result.get("all_replay_action_alignment") != "PASS"
        or current_calibration_result.get(
            "calibration_teacher_active_selection_requests"
        )
        != 1_292
        or current_calibration_result.get(
            "combined_all_player_active_selection_requests"
        )
        != 2_247
        or current_calibration_density.get("combined_observed_teacher_decisions")
        != 1_386
        or current_calibration_density.get("screening_teacher_decision_shortfall")
        != 3_614
        or current_calibration_qualification.get("same_module_version_qualified")
        is not True
        or current_calibration_qualification.get(
            "policy_behavior_consistency_qualified"
        )
        is not True
        or current_calibration_qualification.get(
            "minimum_5000_teacher_decisions_met"
        )
        is not False
        or current_calibration_qualification.get("e01_screening_gate_passed")
        is not False
        or current_calibration_qualification.get("replay_transfer_authorized")
        is not False
        or current_calibration_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError(
            "E01-A completed current rank-1 Dragapult calibration differs"
        )
    current_calibration_root = (
        repository_root / "ptcg-rl/private/g3/e01/flg-dragapult-calibration-v1"
    )
    current_downloaded_files = current_calibration_execution.get("downloaded_files")
    if not isinstance(current_downloaded_files, list) or len(current_downloaded_files) != 12:
        raise GoldPathContractError("E01-A current calibration file list differs")
    expected_current_names = sorted(
        Path(str(item["path"])).name for item in current_downloaded_files
    )
    observed_current_names = sorted(
        path.name for path in current_calibration_root.iterdir() if path.is_file()
    )
    if observed_current_names != expected_current_names:
        raise GoldPathContractError("E01-A current calibration quarantine differs")
    for item in current_downloaded_files:
        path = repository_root / "ptcg-rl" / str(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or sha256_file(path) != item.get("sha256")
        ):
            raise GoldPathContractError(
                "E01-A quarantined current calibration replay differs"
            )
    checks.append(
        {
            "check": "e01_current_rank_1_dragapult_calibration",
            "status": "PASS",
            "decision": "DEC-020",
            "request_sha256": e01a["current_teacher_calibration_request_sha256"],
            "authorization_consumed": True,
            "teacher_submission_id": 55_004_495,
            "files": 12,
            "bytes": 63_562_985,
            "module_versions": ["1.32.2"],
            "exact_deck_match": True,
            "calibration_teacher_decisions": 1_292,
            "combined_observed_teacher_decisions": 1_386,
            "screening_decision_shortfall": 3_614,
            "screening_gate_passed": False,
        }
    )

    current_expansion_metadata = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_screening_expansion_candidate_metadata"])
    )
    current_expansion_request = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_screening_expansion_request"])
    )
    current_expansion_contract = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_screening_expansion_contract_review"])
    )
    current_expansion_review = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["current_teacher_screening_expansion_review"])
    )
    current_expansion_selection = _require_mapping(
        current_expansion_metadata.get("selection"),
        "E01-A current teacher screening expansion selection",
    )
    current_expansion_boundary = _require_mapping(
        current_expansion_contract.get("request"),
        "E01-A current teacher screening expansion boundary",
    )
    current_expansion_contract_qualification = _require_mapping(
        current_expansion_contract.get("qualification"),
        "E01-A current teacher screening expansion contract qualification",
    )
    current_expansion_screening = _require_mapping(
        current_expansion_review.get("screening"),
        "E01-A current teacher screening expansion results",
    )
    current_expansion_qualification = _require_mapping(
        current_expansion_review.get("qualification"),
        "E01-A current teacher screening expansion qualification",
    )
    current_expansion_execution = _require_mapping(
        current_expansion_request.get("execution"),
        "E01-A current teacher screening expansion execution",
    )
    current_expansion_approval = _require_mapping(
        current_expansion_request.get("approval"),
        "E01-A current teacher screening expansion approval",
    )
    if (
        current_expansion_metadata.get("record_id")
        != "e01-flg-dragapult-screening-expansion-candidates-v1"
        or current_expansion_selection.get("selected_files") != 38
        or current_expansion_selection.get("selected_bytes") != 254_237_550
        or current_expansion_selection.get("balanced_strata")
        != {"seat_0_loss": 10, "seat_0_win": 10, "seat_1_loss": 9, "seat_1_win": 9}
        or current_expansion_request.get("status") != "CONSUMED"
        or current_expansion_request.get("request_ready") is not False
        or current_expansion_request.get("authorized") is not False
        or current_expansion_request.get("maximum_new_files") != 38
        or current_expansion_request.get("maximum_new_bytes") != 254_237_550
        or current_expansion_request.get("projection_is_guarantee") is not False
        or current_expansion_approval.get("authorized_request_sha256")
        != e01a["current_teacher_screening_expansion_authorized_payload_sha256"]
        or current_expansion_execution.get("files_downloaded") != 38
        or current_expansion_execution.get("bytes_downloaded") != 254_237_550
        or current_expansion_execution.get("agent_logs_downloaded") != 0
        or current_expansion_execution.get("additional_replays_downloaded_after_named_files")
        != 0
        or current_expansion_execution.get("training_label_exports") != 0
        or current_expansion_execution.get("optimizer_steps") != 0
        or current_expansion_execution.get("training") is not False
        or current_expansion_execution.get("external_compute") is not False
        or current_expansion_execution.get("submission") is not False
        or current_expansion_contract.get("status") != "PASS"
        or current_expansion_contract.get("decision")
        != "ACCEPT_EXACT_38_FILE_CURRENT_RANK_1_DRAGAPULT_SCREENING_EXPANSION_REQUEST_UNAUTHORIZED"
        or current_expansion_contract.get("reviewed_decision") != "DEC-021"
        or current_expansion_contract.get("review_sha256")
        != e01a["current_teacher_screening_expansion_contract_review_self_hash"]
        or current_expansion_boundary.get("request_ready") is not True
        or current_expansion_boundary.get("authorized") is not False
        or current_expansion_boundary.get("maximum_new_files") != 38
        or current_expansion_boundary.get("maximum_new_bytes") != 254_237_550
        or current_expansion_boundary.get("minimum_target_bytes") != 253_462_708
        or current_expansion_boundary.get("output_directory_exists") is not False
        or current_expansion_boundary.get("required_module_version") != "1.32.2"
        or current_expansion_boundary.get("required_deck_multiset_sha256")
        != e01a["current_gold_teacher_deck_multiset_sha256"]
        or current_expansion_contract_qualification.get(
            "screening_expansion_request_ready"
        )
        is not True
        or current_expansion_contract_qualification.get("replay_transfer_authorized")
        is not False
        or current_expansion_review.get("status") != "PASS"
        or current_expansion_review.get("decision")
        != "ACCEPT_CURRENT_RANK_1_DRAGAPULT_SCREENING_FLOOR_MET"
        or current_expansion_review.get("reviewed_decision") != "DEC-021"
        or current_expansion_review.get("review_sha256")
        != e01a["current_teacher_screening_expansion_review_self_hash"]
        or current_expansion_screening.get("qualified_files") != 38
        or current_expansion_screening.get("rejected_files") != 0
        or current_expansion_screening.get("qualified_bytes") != 254_237_550
        or current_expansion_screening.get("qualified_teacher_active_selection_requests")
        != 4_954
        or current_expansion_screening.get(
            "qualified_all_player_active_selection_requests"
        )
        != 8_609
        or current_expansion_screening.get("combined_observed_teacher_decisions")
        != 6_340
        or current_expansion_screening.get("screening_teacher_decision_shortfall")
        != 0
        or current_expansion_screening.get("minimum_5000_teacher_decisions_met")
        is not True
        or current_expansion_qualification.get("all_selected_replays_qualified")
        is not True
        or current_expansion_qualification.get("minimum_5000_teacher_decisions_met")
        is not True
        or current_expansion_qualification.get("e01_screening_gate_passed")
        is not True
        or current_expansion_qualification.get("replay_transfer_authorized")
        is not False
        or current_expansion_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError(
            "E01-A completed current rank-1 Dragapult screening expansion differs"
        )
    current_expansion_root = (
        repository_root
        / "ptcg-rl/private/g3/e01/flg-dragapult-screening-expansion-v1"
    )
    current_expansion_files = current_expansion_execution.get("downloaded_files")
    if not isinstance(current_expansion_files, list) or len(current_expansion_files) != 38:
        raise GoldPathContractError("E01-A screening expansion file list differs")
    expected_expansion_names = sorted(
        Path(str(item["path"])).name for item in current_expansion_files
    )
    observed_expansion_names = sorted(
        path.name for path in current_expansion_root.iterdir() if path.is_file()
    )
    if observed_expansion_names != expected_expansion_names:
        raise GoldPathContractError("E01-A screening expansion quarantine differs")
    for item in current_expansion_files:
        path = repository_root / "ptcg-rl" / str(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or sha256_file(path) != item.get("sha256")
        ):
            raise GoldPathContractError(
                "E01-A quarantined screening expansion replay differs"
            )
    checks.append(
        {
            "check": "e01_current_rank_1_dragapult_screening_expansion",
            "status": "PASS",
            "decision": "DEC-021",
            "request_sha256": e01a[
                "current_teacher_screening_expansion_request_sha256"
            ],
            "authorization_consumed": True,
            "teacher_submission_id": 55_004_495,
            "files": 38,
            "bytes": 254_237_550,
            "qualified_files": 38,
            "rejected_files": 0,
            "qualified_teacher_decisions": 4_954,
            "combined_observed_teacher_decisions": 6_340,
            "screening_decision_shortfall": 0,
            "screening_gate_passed": True,
        }
    )

    prior_confirmation_refresh = load_json(
        repository_root / "ptcg-rl" / str(e01a["prior_confirmation_refresh"])
    )
    confirmation_request = load_json(
        repository_root / "ptcg-rl" / str(e01a["confirmation_teacher_probe_request"])
    )
    confirmation_contract = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["confirmation_teacher_probe_contract_review"])
    )
    confirmation_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["confirmation_teacher_probe_review"])
    )
    calibration_metadata = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["confirmation_teacher_calibration_candidate_metadata"])
    )
    calibration_request = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["confirmation_teacher_calibration_request"])
    )
    calibration_contract = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["confirmation_teacher_calibration_contract_review"])
    )
    calibration_review = load_json(
        repository_root
        / "ptcg-rl"
        / str(e01a["confirmation_teacher_calibration_review"])
    )
    current_refresh = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_confirmation_refresh"])
    )
    source_wait_review = load_json(
        repository_root / "ptcg-rl" / str(e01a["current_rank_1_source_wait_review"])
    )

    confirmation_selection = _require_mapping(
        prior_confirmation_refresh.get("selection"), "E01-A Dries confirmation selection"
    )
    confirmation_teacher = _require_mapping(
        prior_confirmation_refresh.get("teacher"), "E01-A Dries confirmation teacher"
    )
    confirmation_execution = _require_mapping(
        confirmation_request.get("execution"), "E01-A Dries confirmation execution"
    )
    confirmation_consistency = _require_mapping(
        confirmation_review.get("consistency"), "E01-A Dries consistency"
    )
    confirmation_result = _require_mapping(
        confirmation_review.get("confirmation"), "E01-A Dries confirmation result"
    )
    confirmation_qualification = _require_mapping(
        confirmation_review.get("qualification"), "E01-A Dries qualification"
    )
    if (
        prior_confirmation_refresh.get("record_id") != "e01-live-confirmation-refresh-v1"
        or confirmation_teacher.get("team_id") != 16_531_269
        or confirmation_teacher.get("team_name") != "Dries @ Tufa Labs"
        or confirmation_teacher.get("live_rank_at_refresh") != 1
        or confirmation_teacher.get("submission_id") != 55_002_825
        or confirmation_teacher.get("dataset_episode_count") != 128
        or confirmation_selection.get("selected_total_bytes") != 1_135_238
        or len(confirmation_selection.get("selected_files", [])) != 2
        or confirmation_request.get("status") != "CONSUMED"
        or confirmation_request.get("request_ready") is not False
        or confirmation_request.get("authorized") is not False
        or confirmation_execution.get("files_downloaded") != 2
        or confirmation_execution.get("bytes_downloaded") != 1_135_238
        or confirmation_contract.get("status") != "PASS"
        or confirmation_contract.get("reviewed_decision") != "DEC-022"
        or confirmation_review.get("status") != "PASS"
        or confirmation_review.get("reviewed_decision") != "DEC-022"
        or confirmation_review.get("review_sha256")
        != e01a["confirmation_teacher_probe_review_self_hash"]
        or confirmation_consistency.get("module_versions") != ["1.32.2"]
        or confirmation_consistency.get("teacher_deck_multiset_sha256")
        != "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
        or confirmation_consistency.get("combined_teacher_active_selection_requests") != 27
        or confirmation_result.get("observed_recent_teacher_episodes") != 54
        or confirmation_result.get("observed_recent_teacher_decisions") != 6_367
        or confirmation_result.get("confirmation_gate_passed") is not False
        or confirmation_qualification.get("second_independent_recent_teacher_qualified")
        is not True
        or confirmation_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError("E01-A completed Dries teacher probe differs")
    downloaded = confirmation_execution.get("downloaded_files")
    if not isinstance(downloaded, list) or len(downloaded) != 2:
        raise GoldPathContractError("E01-A Dries replay list differs")
    quarantine = repository_root / "ptcg-rl/private/g3/e01/dries-confirmation-teacher-probe-v1"
    if sorted(path.name for path in quarantine.iterdir() if path.is_file()) != [
        "88281294.json",
        "88332011.json",
    ]:
        raise GoldPathContractError("E01-A Dries quarantine differs")
    for item in downloaded:
        replay_path = repository_root / "ptcg-rl" / str(item["path"])
        if (
            not replay_path.is_file()
            or replay_path.stat().st_size != item.get("bytes")
            or sha256_file(replay_path) != item.get("sha256")
        ):
            raise GoldPathContractError("E01-A quarantined Dries replay differs")
    checks.append(
        {
            "check": "e01_current_rank_1_dries_confirmation_teacher_probe",
            "status": "PASS",
            "decision": "DEC-022",
            "request_sha256": e01a["confirmation_teacher_probe_request_sha256"],
            "authorization_consumed": True,
            "teacher_submission_id": 55_002_825,
            "files": 2,
            "bytes": 1_135_238,
            "teacher_decisions": 27,
            "independent_recent_teachers": 2,
            "confirmation_gate_passed": False,
        }
    )

    calibration_selection = _require_mapping(
        calibration_metadata.get("selection"), "E01-A Dries calibration selection"
    )
    calibration_execution = _require_mapping(
        calibration_request.get("execution"), "E01-A Dries calibration execution"
    )
    calibration_approval = _require_mapping(
        calibration_request.get("approval"), "E01-A Dries calibration approval"
    )
    calibration_boundary = _require_mapping(
        calibration_contract.get("request"), "E01-A Dries calibration boundary"
    )
    calibration_consistency = _require_mapping(
        calibration_review.get("consistency"), "E01-A Dries calibration consistency"
    )
    calibration_confirmation = _require_mapping(
        calibration_review.get("confirmation"), "E01-A Dries calibration confirmation"
    )
    calibration_qualification = _require_mapping(
        calibration_review.get("qualification"), "E01-A Dries calibration qualification"
    )
    if (
        calibration_metadata.get("record_id")
        != "e01-dries-grimmsnarl-calibration-candidates-v1"
        or calibration_selection.get("files") != 12
        or calibration_selection.get("total_bytes") != 60_869_451
        or calibration_selection.get("balanced_strata")
        != {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
        or calibration_request.get("status") != "CONSUMED"
        or calibration_request.get("request_ready") is not False
        or calibration_request.get("authorized") is not False
        or calibration_request.get("authorization_scope")
        != "CONSUMED_EXACT_12_FILE_DRIES_GRIMMSNARL_CALIBRATION_ONLY"
        or calibration_approval.get("authorized_request_sha256")
        != e01a["confirmation_teacher_calibration_authorized_request_sha256"]
        or calibration_execution.get("files_downloaded") != 12
        or calibration_execution.get("bytes_downloaded") != 60_869_451
        or calibration_contract.get("status") != "PASS"
        or calibration_contract.get("reviewed_decision") != "DEC-023"
        or calibration_contract.get("review_sha256")
        != e01a["confirmation_teacher_calibration_contract_review_self_hash"]
        or calibration_boundary.get("maximum_new_files") != 12
        or calibration_boundary.get("maximum_new_bytes") != 60_869_451
        or calibration_review.get("status") != "PASS"
        or calibration_review.get("reviewed_decision") != "DEC-023"
        or calibration_review.get("review_sha256")
        != e01a["confirmation_teacher_calibration_review_self_hash"]
        or calibration_consistency.get("module_versions") != ["1.32.2"]
        or calibration_consistency.get("exact_teacher_deck_match") is not True
        or calibration_consistency.get("all_replay_action_alignment") != "PASS"
        or calibration_consistency.get("calibration_teacher_active_selection_requests")
        != 1_175
        or calibration_consistency.get("combined_all_player_active_selection_requests")
        != 2_171
        or calibration_confirmation.get("observed_recent_teacher_episodes") != 66
        or calibration_confirmation.get("observed_recent_teacher_decisions") != 7_542
        or calibration_confirmation.get("episode_shortfall") != 134
        or calibration_confirmation.get("decision_shortfall") != 17_458
        or calibration_confirmation.get("confirmation_gate_passed") is not False
        or calibration_qualification.get("training_authorized") is not False
    ):
        raise GoldPathContractError("E01-A completed Dries calibration differs")
    calibration_files = calibration_execution.get("downloaded_files")
    if not isinstance(calibration_files, list) or len(calibration_files) != 12:
        raise GoldPathContractError("E01-A Dries calibration replay list differs")
    calibration_root = (
        repository_root / "ptcg-rl/private/g3/e01/dries-grimmsnarl-calibration-v1"
    )
    expected_calibration_names = sorted(
        Path(str(item["path"])).name for item in calibration_files
    )
    if sorted(path.name for path in calibration_root.iterdir() if path.is_file()) != (
        expected_calibration_names
    ):
        raise GoldPathContractError("E01-A Dries calibration quarantine differs")
    for item in calibration_files:
        replay_path = repository_root / "ptcg-rl" / str(item["path"])
        if (
            not replay_path.is_file()
            or replay_path.stat().st_size != item.get("bytes")
            or sha256_file(replay_path) != item.get("sha256")
        ):
            raise GoldPathContractError("E01-A quarantined Dries calibration replay differs")
    checks.append(
        {
            "check": "e01_current_rank_1_dries_grimmsnarl_calibration",
            "status": "PASS",
            "decision": "DEC-023",
            "request_sha256": e01a["confirmation_teacher_calibration_request_sha256"],
            "authorization_consumed": True,
            "teacher_submission_id": 55_002_825,
            "files": 12,
            "bytes": 60_869_451,
            "teacher_decisions": 1_175,
            "combined_recent_teacher_episodes": 66,
            "combined_recent_teacher_decisions": 7_542,
            "confirmation_gate_passed": False,
        }
    )

    rank_1 = _require_mapping(current_refresh.get("current_rank_1"), "E01-A current rank 1")
    active_submission = _require_mapping(
        rank_1.get("active_submission"), "E01-A current rank-1 submission"
    )
    dataset = _require_mapping(
        current_refresh.get("latest_complete_daily_dataset"),
        "E01-A latest daily dataset",
    )
    intersection = _require_mapping(
        current_refresh.get("current_rank_1_dataset_intersection"),
        "E01-A current rank-1 dataset intersection",
    )
    source_wait = _require_mapping(
        source_wait_review.get("source_wait"), "E01-A source-wait boundary"
    )
    if (
        current_refresh.get("record_id") != "e01-live-confirmation-refresh-v2"
        or rank_1.get("team_id") != 16_441_077
        or rank_1.get("team_name") != "haggle"
        or rank_1.get("rank") != 1
        or rank_1.get("score") != 1169.5
        or active_submission.get("submission_id") != 55_104_355
        or rank_1.get("public_episode_count") != 76
        or dataset.get("versioned_ref")
        != "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1"
        or intersection.get("episodes") != 0
        or intersection.get("total_bytes") != 0
        or intersection.get("files") != []
        or source_wait_review.get("status") != "PASS"
        or source_wait_review.get("reviewed_decision") != "DEC-024"
        or source_wait_review.get("review_sha256")
        != e01a["current_rank_1_source_wait_review_self_hash"]
        or source_wait.get("current_rank_1_probe_request_ready") is not False
        or source_wait.get("current_rank_1_probe_request_exists") is not False
        or source_wait.get("current_rank_1_output_exists") is not False
        or source_wait.get("replay_transfer_authorized") is not False
        or source_wait.get("training_authorized") is not False
        or (
            repository_root
            / "ptcg-rl/configs/e01_haggle_confirmation_teacher_probe_request_v1.json"
        ).exists()
        or (
            repository_root
            / "ptcg-rl/private/g3/e01/haggle-confirmation-teacher-probe-v1"
        ).exists()
    ):
        raise GoldPathContractError("E01-A current rank-1 source-wait evidence differs")
    checks.append(
        {
            "check": "e01_current_rank_1_source_wait",
            "status": "PASS",
            "decision": "DEC-024",
            "team_name": "haggle",
            "submission_id": 55_104_355,
            "public_episode_count": 76,
            "latest_daily_dataset": (
                "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1"
            ),
            "dataset_intersection_files": 0,
            "request_ready": False,
            "replay_transfer_authorized": False,
        }
    )

    for relative, expected in sorted(work_orders["source_evidence"].items()):
        observed = sha256_file(repository_root / relative)
        if observed != expected:
            raise GoldPathContractError(f"source evidence hash differs: {relative}")
        checks.append({"check": "source_evidence_hash", "path": relative, "sha256": observed})

    engine = work_orders["engine_binding"]
    parity_path = repository_root / "ptcg-rl" / engine["official_asset_parity_artifact"]
    parity_sha256 = sha256_file(parity_path)
    if parity_sha256 != engine["official_asset_parity_artifact_sha256"]:
        raise GoldPathContractError("official asset parity artifact hash differs")
    parity = load_json(parity_path)
    if (
        parity.get("status") != "PASS"
        or parity.get("downloadable_asset_parity") != "PASS"
        or parity.get("hosted_runtime_behavior_parity")
        != "UNRESOLVED_AFTER_2026-07-23_ENGINE_UPDATE"
        or parity.get("native_games_run") != 0
        or parity.get("optimizer_steps") != 0
        or parity.get("authorization_granted") is not False
    ):
        raise GoldPathContractError("official asset parity artifact contract differs")
    expected_assets = {
        "engine_library": engine["engine_library_sha256"],
        "wrapper_api": engine["wrapper_api_sha256"],
        "card_data": engine["card_data_sha256"],
    }
    parity_assets = _require_mapping(parity.get("assets"), "official parity assets")
    for name, expected_sha256 in expected_assets.items():
        asset = _require_mapping(parity_assets.get(name), f"official parity asset {name}")
        if (
            asset.get("parity") != "PASS"
            or asset.get("official_sha256") != expected_sha256
            or asset.get("local_sha256") != expected_sha256
        ):
            raise GoldPathContractError(f"official parity asset differs: {name}")
        local_path = repository_root / "ptcg-rl" / str(asset.get("local_path"))
        if sha256_file(local_path) != expected_sha256:
            raise GoldPathContractError(f"local official asset hash differs: {name}")
    checks.append(
        {
            "check": "official_downloadable_asset_parity",
            "status": "PASS",
            "artifact_sha256": parity_sha256,
            "hosted_runtime_behavior_parity": parity["hosted_runtime_behavior_parity"],
        }
    )

    source_contract = work_orders["work_orders"]["E04"]["source_contract"]
    source_pairs = (
        ("bridge_path", "bridge_sha256"),
        ("native_adapter_path", "native_adapter_sha256"),
        ("authorization_validator_path", "authorization_validator_sha256"),
        ("runner_path", "runner_sha256"),
        ("single_process_request_path", "single_process_request_sha256"),
        ("bridge_tests_path", "bridge_tests_sha256"),
        ("native_tests_path", "native_tests_sha256"),
        ("single_trace_review_path", "single_trace_review_sha256"),
        ("single_trace_evidence_path", "single_trace_evidence_sha256"),
        ("ten_game_request_path", "ten_game_request_sha256"),
        ("smoke_review_path", "smoke_review_sha256"),
        ("smoke_evidence_path", "smoke_evidence_sha256"),
        ("qualification_decision_path", "qualification_decision_sha256"),
        ("qualification_review_path", "qualification_review_sha256"),
        ("qualification_review_script_path", "qualification_review_script_sha256"),
        ("qualification_request_path", "qualification_request_sha256"),
        (
            "qualification_execution_review_path",
            "qualification_execution_review_sha256",
        ),
        ("qualification_evidence_path", "qualification_evidence_sha256"),
    )
    for path_key, hash_key in source_pairs:
        relative = source_contract[path_key]
        observed = sha256_file(repository_root / "ptcg-rl" / relative)
        if observed != source_contract[hash_key]:
            raise GoldPathContractError(f"E04 source contract hash differs: {relative}")
        checks.append(
            {"check": "e04_source_hash", "path": relative, "sha256": observed}
        )
    request = load_json(
        repository_root / "ptcg-rl" / source_contract["single_process_request_path"]
    )
    if (
        request.get("stage") != "single_process_trace"
        or request.get("games") != 1
        or request.get("minimum_meaningful_decisions") != 1
        or request.get("authorized") is not False
        or request.get("authorization_scope")
        != "CONSUMED_AFTER_SINGLE_APPROVED_EXECUTION"
        or request.get("optimizer_steps_authorized") != 0
        or request.get("external_compute_authorized") is not False
        or request.get("consumed_authorization_sha256")
        != "8b801f8432e821c3a43be10645f3fc89d1422ab329c2acd2df26ce1aac7a72ad"
        or request.get("bridge_checkpoint_sha256")
        != "bb71dcbee278478af9f1c37c206a99da2a47471b08905c11a7b7ddbb05f0f59f"
    ):
        raise GoldPathContractError("E04 consumed single-process request differs")
    checks.append(
        {
            "check": "e04_single_process_authorization_consumed",
            "status": "PASS",
            "authorized": False,
            "games": 1,
            "optimizer_steps_authorized": 0,
        }
    )

    trace_path = (
        repository_root
        / "ptcg-rl"
        / source_contract["single_trace_evidence_path"]
    )
    trace = load_json(trace_path)
    trace_results = _require_mapping(trace.get("results"), "E04 trace results")
    trace_authorization = _require_mapping(
        trace.get("authorization"), "E04 trace authorization"
    )
    trace_execution = _require_mapping(trace.get("execution"), "E04 trace execution")
    if (
        trace.get("status") != "SUCCEEDED"
        or trace.get("decision") != "PASS"
        or trace.get("stage") != "single_process_trace"
        or trace_authorization.get("authorization_consumed") is not True
        or trace_authorization.get("current_request_authorized") is not False
        or trace_authorization.get("rerun_authorized") is not False
        or trace_authorization.get("later_stage_authorized") is not False
        or trace_execution.get("cabt_episode_count") != 1
        or trace_execution.get("cabt_rerun_count_during_recovery") != 0
        or trace_execution.get("optimizer_steps") != 0
        or trace_execution.get("training_loop_ran") is not False
        or trace_results.get("games") != 1
        or trace_results.get("engine_decisions") != 67
        or trace_results.get("meaningful_decisions") != 63
        or trace_results.get("forced_decisions") != 4
        or trace_results.get("terminal_boundaries_for_both_players") != 1
        or set(_require_mapping(trace_results.get("zero_tolerance"), "E04 zero tolerance").values())
        != {0}
    ):
        raise GoldPathContractError("E04 single-process trace evidence differs")
    replay_error = trace_results.get(
        "maximum_compound_log_probability_absolute_error"
    )
    if (
        isinstance(replay_error, bool)
        or not isinstance(replay_error, (int, float))
        or replay_error > 0.00001
    ):
        raise GoldPathContractError("E04 trace probability replay differs")
    checks.append(
        {
            "check": "e04_single_process_trace",
            "status": "PASS",
            "evidence_sha256": sha256_file(trace_path),
            "games": 1,
            "engine_decisions": 67,
            "meaningful_decisions": 63,
            "forced_decisions": 4,
            "maximum_replay_error": replay_error,
            "additional_cabt_execution_for_recovery": False,
        }
    )

    smoke_request_path = (
        repository_root / "ptcg-rl" / source_contract["ten_game_request_path"]
    )
    smoke_request = load_json(smoke_request_path)
    if (
        smoke_request.get("stage") != "smoke"
        or smoke_request.get("games") != 10
        or smoke_request.get("minimum_meaningful_decisions") != 1
        or smoke_request.get("authorized") is not False
        or smoke_request.get("authorization_scope")
        != "CONSUMED_AFTER_TEN_GAME_APPROVED_EXECUTION"
        or smoke_request.get("authorization_snapshot_sha256")
        != "f8019962c4914fa1cfac754b1af7616db69fdb4e0503e89cb46f6282cd2f4922"
        or smoke_request.get("optimizer_steps_authorized") != 0
        or smoke_request.get("external_compute_authorized") is not False
        or smoke_request.get("runner_sha256")
        != "e30ce8d0b468058a95473ee7a0f5fc67dafe797d21c3f40c1c6baa81bd8a8bd3"
        or smoke_request.get("prerequisite_evidence_sha256")
        != source_contract["single_trace_evidence_sha256"]
    ):
        raise GoldPathContractError("E04 consumed ten-game smoke request differs")
    checks.append(
        {
            "check": "e04_ten_game_smoke_authorization_consumed",
            "status": "PASS",
            "authorized": False,
            "games": 10,
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
            "request_sha256": sha256_file(smoke_request_path),
        }
    )

    smoke_evidence_path = (
        repository_root / "ptcg-rl" / source_contract["smoke_evidence_path"]
    )
    smoke = load_json(smoke_evidence_path)
    smoke_results = _require_mapping(smoke.get("results"), "E04 smoke results")
    smoke_authorization = _require_mapping(
        smoke.get("authorization"), "E04 smoke authorization"
    )
    smoke_execution = _require_mapping(smoke.get("execution"), "E04 smoke execution")
    if (
        smoke.get("status") != "SUCCEEDED"
        or smoke.get("decision") != "PASS"
        or smoke.get("stage") != "smoke"
        or smoke_authorization.get("authorization_consumed") is not True
        or smoke_authorization.get("current_request_authorized") is not False
        or smoke_authorization.get("rerun_authorized") is not False
        or smoke_authorization.get("hundred_game_stage_authorized") is not False
        or smoke_execution.get("device") != "cpu"
        or smoke_execution.get("single_process") is not True
        or smoke_execution.get("optimizer_steps") != 0
        or smoke_execution.get("training_loop_ran") is not False
        or smoke_results.get("games") != 10
        or smoke_results.get("engine_decisions") != 711
        or smoke_results.get("meaningful_decisions") != 648
        or smoke_results.get("forced_decisions") != 63
        or smoke_results.get("terminal_boundaries_for_both_players") != 10
        or set(
            _require_mapping(
                smoke_results.get("zero_tolerance"), "E04 smoke zero tolerance"
            ).values()
        )
        != {0}
    ):
        raise GoldPathContractError("E04 ten-game smoke evidence differs")
    smoke_replay_error = smoke_results.get(
        "maximum_compound_log_probability_absolute_error"
    )
    if (
        isinstance(smoke_replay_error, bool)
        or not isinstance(smoke_replay_error, (int, float))
        or smoke_replay_error > 0.00001
    ):
        raise GoldPathContractError("E04 smoke probability replay differs")
    projected_at_mean = smoke_results["meaningful_decisions"] * 10
    per_game = smoke_results.get("per_game")
    if not isinstance(per_game, list) or len(per_game) != 10:
        raise GoldPathContractError("E04 smoke per-game evidence differs")
    projected_at_observed_max = max(
        item["meaningful_decisions"] for item in per_game
    ) * 100
    if projected_at_mean != 6_480 or projected_at_observed_max != 7_000:
        raise GoldPathContractError("E04 smoke qualification projection differs")
    checks.append(
        {
            "check": "e04_ten_game_smoke",
            "status": "PASS",
            "evidence_sha256": sha256_file(smoke_evidence_path),
            "games": 10,
            "engine_decisions": 711,
            "meaningful_decisions": 648,
            "forced_decisions": 63,
            "maximum_replay_error": smoke_replay_error,
            "projected_meaningful_decisions_at_100_games": projected_at_mean,
            "projected_at_observed_max_for_100_games": projected_at_observed_max,
            "qualification_floor": 10_000,
            "qualification_request_ready": True,
        }
    )

    qualification_review_path = (
        repository_root / "ptcg-rl" / source_contract["qualification_review_path"]
    )
    qualification_review = load_json(qualification_review_path)
    qualification_request_path = (
        repository_root / "ptcg-rl" / source_contract["qualification_request_path"]
    )
    qualification_request = load_json(qualification_request_path)
    qualification_evidence_path = (
        repository_root / "ptcg-rl" / source_contract["qualification_evidence_path"]
    )
    qualification_evidence = load_json(qualification_evidence_path)
    review_sizing = _require_mapping(
        qualification_review.get("sizing"), "E04 qualification sizing"
    )
    review_authorization = _require_mapping(
        qualification_review.get("authorization"),
        "E04 qualification review authorization",
    )
    if (
        qualification_review.get("status") != "PASS"
        or qualification_review.get("decision")
        != "ACCEPT_180_GAME_QUALIFICATION_CONTRACT"
        or review_sizing.get("selected_games") != 180
        or review_sizing.get("games_required_at_observed_minimum") != 179
        or review_sizing.get("games_required_at_99_percent_lower_bound") != 168
        or review_sizing.get("selected_projection_at_observed_minimum") != 10_080
        or review_authorization.get("qualification_execution") is not False
        or review_authorization.get("optimizer_steps") is not False
        or review_authorization.get("external_compute") is not False
    ):
        raise GoldPathContractError("E04 qualification contract evidence differs")
    if (
        qualification_request.get("decision_id") != "DEC-012"
        or qualification_request.get("stage") != "qualification"
        or qualification_request.get("games") != 180
        or qualification_request.get("minimum_meaningful_decisions") != 10_000
        or qualification_request.get("bridge_checkpoint_interval_games") != 10
        or qualification_request.get("authorized") is not False
        or qualification_request.get("authorization_scope")
        != "CONSUMED_AFTER_180_GAME_APPROVED_EXECUTION"
        or qualification_request.get("authorization_snapshot_sha256")
        != "cab752414df29ad9d7ceb78baf46c44cb2fbba7384c02e6aad3e72b55ad1a947"
        or qualification_request.get("native_report_sha256")
        != "e7c85dfeeb14d8bdc23c5ed11bf4fe86bdcbf4f64348fe9a313f11b999e3a56e"
        or qualification_request.get("game_ledger_sha256")
        != "b45be2af9f8011fa99e040a5b4069aa59a3e59d78450ca0b08a4a019e02e0672"
        or qualification_request.get("bridge_checkpoint_sha256")
        != "9a9e89d737ef640ab14eb64d4756c89d37dc75b4049bc5a7a3c0598114bc9c22"
        or qualification_request.get("optimizer_steps_authorized") != 0
        or qualification_request.get("external_compute_authorized") is not False
        or qualification_request.get("runner_sha256")
        != source_contract["runner_sha256"]
        or qualification_request.get("authorization_validator_sha256")
        != source_contract["authorization_validator_sha256"]
        or qualification_request.get("prerequisite_evidence_sha256")
        != source_contract["smoke_evidence_sha256"]
        or qualification_request.get("decision_sha256")
        != source_contract["qualification_decision_sha256"]
    ):
        raise GoldPathContractError("E04 consumed qualification request differs")
    qualification_authorization = _require_mapping(
        qualification_evidence.get("authorization"),
        "E04 qualification authorization",
    )
    qualification_execution = _require_mapping(
        qualification_evidence.get("execution"),
        "E04 qualification execution",
    )
    qualification_results = _require_mapping(
        qualification_evidence.get("results"),
        "E04 qualification results",
    )
    if (
        qualification_evidence.get("status") != "SUCCEEDED"
        or qualification_evidence.get("decision") != "PASS"
        or qualification_evidence.get("stage") != "qualification"
        or qualification_authorization.get("authorization_consumed") is not True
        or qualification_authorization.get("current_request_authorized") is not False
        or qualification_authorization.get("rerun_authorized") is not False
        or qualification_authorization.get("later_native_stage_authorized") is not False
        or qualification_execution.get("device") != "cpu"
        or qualification_execution.get("single_process") is not True
        or qualification_execution.get("bridge_checkpoint_interval_games") != 10
        or qualification_execution.get("optimizer_steps") != 0
        or qualification_execution.get("training_loop_ran") is not False
        or qualification_results.get("games") != 180
        or qualification_results.get("engine_decisions") != 12_194
        or qualification_results.get("meaningful_decisions") != 11_250
        or qualification_results.get("forced_decisions") != 944
        or qualification_results.get("terminal_boundaries_for_both_players") != 180
        or qualification_results.get("bridge_state_sha256")
        != "ac2f63202898ea22455d53774a56762b128728f9002726a2ca20e703a4d52362"
        or set(
            _require_mapping(
                qualification_results.get("zero_tolerance"),
                "E04 qualification zero tolerance",
            ).values()
        )
        != {0}
    ):
        raise GoldPathContractError("E04 qualification evidence differs")
    qualification_replay_error = qualification_results.get(
        "maximum_compound_log_probability_absolute_error"
    )
    if (
        isinstance(qualification_replay_error, bool)
        or not isinstance(qualification_replay_error, (int, float))
        or qualification_replay_error > 0.00001
    ):
        raise GoldPathContractError("E04 qualification probability replay differs")
    checks.append(
        {
            "check": "e04_qualification_contract",
            "status": "PASS",
            "decision": "DEC-012",
            "review_sha256": sha256_file(qualification_review_path),
            "games": 180,
            "minimum_meaningful_decisions": 10_000,
            "bridge_checkpoint_interval_games": 10,
        }
    )
    checks.append(
        {
            "check": "e04_qualification",
            "status": "PASS",
            "evidence_sha256": sha256_file(qualification_evidence_path),
            "request_sha256": sha256_file(qualification_request_path),
            "authorization_consumed": True,
            "games": 180,
            "engine_decisions": 12_194,
            "meaningful_decisions": 11_250,
            "forced_decisions": 944,
            "terminal_boundaries_for_both_players": 180,
            "maximum_replay_error": qualification_replay_error,
            "zero_tolerance_total": 0,
            "optimizer_steps": 0,
            "rerun_authorized": False,
        }
    )

    decision_raw = decision_path.read_text(encoding="utf-8")
    for required in (
        "Status: Accepted",
        "Do not prepare, authorize or execute a current-rank-1 replay request",
        "exact current-rank-1 intersection with that dataset: `0` files and `0` bytes",
        "This decision authorizes no replay transfer",
        "requires a new exact request and separate explicit user approval",
    ):
        if required not in decision_raw:
            raise GoldPathContractError(f"DEC-024 is missing required text: {required}")
    checks.append({"check": "decision_scope", "status": "PASS"})

    private_root = repository_root / "ptcg-rl/private/baselines/mega-lucario-ex"
    observed_lucario = {
        "receipt_sha256": sha256_file(private_root / "receipt.json"),
        "deck_sha256": sha256_file(private_root / "deck.csv"),
        "module_sha256": sha256_file(private_root / "main.py"),
    }
    if observed_lucario != EXPECTED_LUCARIO:
        raise GoldPathContractError("Mega Lucario hedge differs from the frozen baseline")
    checks.append({"check": "mega_lucario_byte_freeze", "status": "PASS", **observed_lucario})

    if dry_run.get("planner_plan_sha256") != "4123d318c3cfc898858233c1aff3f987580fdbdf64e8204227294ae1117584c2":
        raise GoldPathContractError("E01-A planner plan hash differs")
    checks.append(
        {
            "check": "e01a_zero_transfer_caps",
            "status": "PASS",
            "selected_files": dry_run["selection"]["selected_files"],
            "selected_bytes": dry_run["selection"]["selected_bytes"],
            "episode_json_transferred": 0,
        }
    )

    report: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "record_id": "gold-path-work-orders-review-v1",
        "created_at_utc": "2026-07-24T11:20:00Z",
        "source_path": "reports/artifacts/gold-path-work-orders-review-v1.json",
        "reviewed_decision": "DEC-024",
        "status": "PASS",
        "decision": "ACCEPT",
        "work_orders_sha256": sha256_file(work_orders_path),
        "dry_run_sha256": sha256_file(dry_run_path),
        "decision_sha256": sha256_file(decision_path),
        "official_asset_parity_sha256": parity_sha256,
        "checks": checks,
        "authorization": {
            "replay_transfer": False,
            "e01_source_schema_reconciled_for_probe": True,
            "e01_provenance_probe_completed": True,
            "e01_provenance_probe_authorization_consumed": True,
            "e01_provenance_probe_request_ready": False,
            "e01_same_submission_consistency_completed": True,
            "e01_same_submission_consistency_authorization_consumed": True,
            "e01_same_submission_consistency_request_ready": False,
            "e01_luca_gold_teacher_completed": True,
            "e01_luca_gold_teacher_authorization_consumed": True,
            "e01_luca_gold_teacher_request_ready": False,
            "e01_luca_same_version_calibration_completed": True,
            "e01_luca_same_version_calibration_authorization_consumed": True,
            "e01_luca_same_version_calibration_request_ready": False,
            "e01_luca_screening_expansion_request_ready": True,
            "e01_luca_screening_expansion_execution": False,
            "e01_luca_screening_expansion_superseded": True,
            "e01_live_gold_refresh_completed": True,
            "e01_current_rank_1_teacher_completed": True,
            "e01_current_rank_1_teacher_authorization_consumed": True,
            "e01_current_rank_1_teacher_request_ready": False,
            "e01_current_rank_1_dragapult_calibration_completed": True,
            "e01_current_rank_1_dragapult_calibration_authorization_consumed": True,
            "e01_current_rank_1_dragapult_calibration_request_ready": False,
            "e01_current_rank_1_dragapult_screening_expansion_completed": True,
            "e01_current_rank_1_dragapult_screening_expansion_authorization_consumed": True,
            "e01_current_rank_1_dragapult_screening_expansion_request_ready": False,
            "e01_live_confirmation_refresh_completed": True,
            "e01_current_rank_1_dries_confirmation_teacher_completed": True,
            "e01_current_rank_1_dries_confirmation_teacher_authorization_consumed": True,
            "e01_current_rank_1_dries_confirmation_teacher_request_ready": False,
            "e01_current_rank_1_dries_grimmsnarl_calibration_completed": True,
            "e01_current_rank_1_dries_grimmsnarl_calibration_authorization_consumed": True,
            "e01_current_rank_1_dries_grimmsnarl_calibration_request_ready": False,
            "e01_current_rank_1_source_wait_completed": True,
            "e01_current_rank_1_source_ready": False,
            "e01_current_rank_1_probe_request_ready": False,
            "training": False,
            "native_e04_single_trace_completed": True,
            "native_e04_ten_game_smoke_completed": True,
            "native_e04_qualification_completed": True,
            "zero_update_bridge_qualified": True,
            "qualification_contract_review_required": False,
            "qualification_request_ready": False,
            "qualification_execution_completed": True,
            "further_native_e04_execution": False,
            "native_e04_execution": False,
            "external_compute": False,
            "submission": False,
        },
        "revisit_trigger": "Any source or evidence hash changes, any consumed E01 replay changes, a pinned daily dataset begins containing current rank-1 submission 55104355, the active rank-1 team or submission changes, runtime asset parity is resolved differently, or any replay transfer, optimizer step, external compute, submission, rerun or later native E04 execution becomes authorized."
    }
    report["review_sha256"] = _self_hash(report, "review_sha256")
    return report


def write_review(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
