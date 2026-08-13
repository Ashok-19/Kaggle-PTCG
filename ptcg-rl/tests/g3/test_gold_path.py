from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg_rl.g3.gold_path import (
    GoldPathContractError,
    review_gold_path,
    validate_e01a_dry_run,
    validate_work_orders,
)


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent


def test_frozen_work_orders_validate() -> None:
    value = json.loads((ROOT / "configs/gold_path_work_orders_v1.json").read_text())
    validated = validate_work_orders(value)
    assert validated["decision_id"] == "DEC-028"
    assert validated["work_orders"]["E04"]["optimizer_steps"] == 0
    assert validated["work_orders"]["E04"]["native_games_completed"] == 191
    assert validated["work_orders"]["E04"]["native_meaningful_decisions"] == 11_961
    assert validated["work_orders"]["E04"]["single_process_trace_status"] == "PASS"
    assert validated["work_orders"]["E04"]["qualification_selected_games"] == 180
    assert validated["work_orders"]["E04"]["qualification_request_ready"] is False
    assert validated["work_orders"]["E04"]["qualification_request_authorized"] is False
    assert validated["work_orders"]["E04"]["qualification_authorization_consumed"] is True
    assert validated["work_orders"]["E04"]["qualification_status"] == "PASS"
    assert validated["work_orders"]["E04"]["smoke_status"] == "PASS"
    assert validated["work_orders"]["E04"]["next_stage"] is None
    e01a = validated["work_orders"]["E01-A"]
    assert e01a["state"] == (
        "CORPUS_V2_337_EPISODES_23460_TARGETS_BC_CANARY_PASS_"
        "PRODUCTION_TRAINING_BLOCKED"
    )
    assert e01a["source_provenance_status"] == (
        "PASS_MAJKEL_271_EPISODES_CORPUS_V2_FROZEN_"
        "BC_CANARY_PASS_TARGET_FLOOR_BLOCKED"
    )
    assert e01a["selected_episode_ids_match"] is True
    assert e01a["selected_rows_with_byte_or_timestamp_mismatch"] == 8
    assert e01a["episode_identity_reproduced"] is True
    assert e01a["timestamp_reproduced"] is True
    assert e01a["file_byte_count_reproduced"] is True
    assert e01a["team_identity_reproduced"] is True
    assert e01a["submission_identity_reproduced"] is True
    assert e01a["rating_field_reproduced"] is False
    assert e01a["rating_field_used_for_probe"] is False
    assert e01a["candidate_set_reranked"] is False
    assert e01a["provenance_probe_request_ready"] is False
    assert e01a["provenance_probe_authorized"] is False
    assert e01a["provenance_probe_authorization_consumed"] is True
    assert e01a["provenance_probe_episode_id"] == 87_703_034
    assert e01a["provenance_probe_file_name"] == "87703034.json"
    assert e01a["provenance_probe_declared_bytes"] == 3_641_302
    assert e01a["provenance_probe_files_transferred"] == 1
    assert e01a["provenance_probe_passed"] is True
    assert e01a["exact_deck_hashes_recovered"] is True
    assert e01a["action_aligned_supervision_available"] is True
    assert e01a["consistency_request_ready"] is False
    assert e01a["consistency_request_authorized"] is False
    assert e01a["consistency_authorization_consumed"] is True
    assert e01a["consistency_request_episode_id"] == 87_741_212
    assert e01a["consistency_request_declared_bytes"] == 559_779
    assert e01a["consistency_files_transferred"] == 1
    assert e01a["same_submission_identity_qualified"] is True
    assert e01a["exact_deck_consistency_qualified"] is True
    assert e01a["combined_benarg_teacher_active_selection_requests"] == 65
    assert e01a["gold_teacher_team_name"] == "Luca"
    assert e01a["gold_teacher_submission_id"] == 54_863_653
    assert e01a["gold_teacher_submission_public_score"] == 1180.9
    assert e01a["gold_teacher_dataset_episode_count"] == 357
    assert e01a["gold_teacher_request_ready"] is False
    assert e01a["gold_teacher_request_authorized"] is False
    assert e01a["gold_teacher_authorization_consumed"] is True
    assert e01a["gold_teacher_probe_files_transferred"] == 2
    assert e01a["gold_teacher_active_selection_requests"] == 37
    assert e01a["gold_teacher_same_module_version_qualified"] is True
    assert e01a["teacher_strength_qualified"] is True
    assert e01a["gold_teacher_screening_decision_shortfall"] == 4_963
    assert e01a["luca_calibration_screening_decision_shortfall"] == 3_793
    assert e01a["calibration_request_ready"] is False
    assert e01a["calibration_request_authorized"] is False
    assert e01a["calibration_authorization_consumed"] is True
    assert e01a["calibration_request_files"] == 12
    assert e01a["calibration_request_bytes"] == 63_828_057
    assert e01a["calibration_luca_active_selection_requests"] == 1_170
    assert e01a["combined_observed_luca_active_selection_requests"] == 1_207
    assert e01a["policy_behavior_consistency_qualified"] is True
    assert e01a["screening_expansion_request_ready"] is True
    assert e01a["screening_expansion_request_authorized"] is False
    assert e01a["screening_expansion_request_files"] == 51
    assert e01a["screening_expansion_request_bytes"] == 270_807_738
    assert e01a["screening_expansion_active"] is False
    assert e01a["screening_expansion_executed"] is False
    assert e01a["screening_expansion_superseded_by"] == "DEC-019"
    assert e01a["current_gold_teacher_team_name"] == "flg"
    assert e01a["current_gold_teacher_submission_id"] == 55_004_495
    assert e01a["current_gold_teacher_live_rank_at_refresh"] == 1
    assert e01a["current_gold_teacher_archetype_context_label"] == "Dragapult ex"
    assert e01a["current_gold_teacher_authorization_consumed"] is True
    assert e01a["current_gold_teacher_probe_files_transferred"] == 2
    assert e01a["current_gold_teacher_probe_bytes_transferred"] == 3_996_398
    assert e01a["current_gold_teacher_active_selection_requests"] == 94
    assert e01a["current_gold_teacher_screening_decision_shortfall"] == 4_906
    assert e01a["screening_teacher_decision_shortfall"] == 0
    assert e01a["current_teacher_calibration_request_ready"] is False
    assert e01a["current_teacher_calibration_request_authorized"] is False
    assert e01a["current_teacher_calibration_authorization_consumed"] is True
    assert e01a["current_teacher_calibration_request_files"] == 12
    assert e01a["current_teacher_calibration_request_bytes"] == 63_562_985
    assert e01a["current_teacher_calibration_files_transferred"] == 12
    assert e01a["current_teacher_calibration_bytes_transferred"] == 63_562_985
    assert e01a["current_teacher_calibration_teacher_active_selection_requests"] == 1_292
    assert e01a["current_teacher_calibration_all_player_active_selection_requests"] == 2_247
    assert e01a[
        "current_teacher_calibration_combined_observed_teacher_active_selection_requests"
    ] == 1_386
    assert e01a["current_teacher_calibration_screening_decision_shortfall"] == 3_614
    assert e01a["current_teacher_screening_expansion_request_ready"] is False
    assert e01a["current_teacher_screening_expansion_request_authorized"] is False
    assert e01a["current_teacher_screening_expansion_active"] is False
    assert e01a["current_teacher_screening_expansion_authorization_consumed"] is True
    assert e01a["current_teacher_screening_expansion_request_files"] == 38
    assert e01a["current_teacher_screening_expansion_request_bytes"] == 254_237_550
    assert e01a["current_teacher_screening_expansion_files_transferred"] == 38
    assert e01a["current_teacher_screening_expansion_bytes_transferred"] == 254_237_550
    assert e01a["current_teacher_screening_expansion_qualified_files"] == 38
    assert e01a["current_teacher_screening_expansion_rejected_files"] == 0
    assert e01a[
        "current_teacher_screening_expansion_qualified_teacher_active_selection_requests"
    ] == 4_954
    assert e01a[
        "current_teacher_screening_expansion_qualified_all_player_active_selection_requests"
    ] == 8_609
    assert e01a["current_teacher_combined_observed_teacher_active_selection_requests"] == 6_340
    assert e01a["current_teacher_screening_decision_shortfall"] == 0
    assert e01a["minimum_5000_teacher_decisions_met"] is True
    assert e01a["e01_screening_gate_passed"] is True
    assert e01a["confirmation_teacher_team_name"] == "Dries @ Tufa Labs"
    assert e01a["confirmation_teacher_submission_id"] == 55_002_825
    assert e01a["confirmation_teacher_live_rank_at_refresh"] == 1
    assert e01a["confirmation_teacher_dataset_episode_count"] == 128
    assert e01a["confirmation_teacher_probe_request_ready"] is False
    assert e01a["confirmation_teacher_probe_request_authorized"] is False
    assert e01a["confirmation_teacher_probe_authorization_consumed"] is True
    assert e01a["confirmation_teacher_probe_request_files"] == 2
    assert e01a["confirmation_teacher_probe_request_bytes"] == 1_135_238
    assert e01a["confirmation_teacher_probe_files_transferred"] == 2
    assert e01a["confirmation_teacher_probe_bytes_transferred"] == 1_135_238
    assert e01a["confirmation_teacher_probe_module_versions"] == ["1.32.2"]
    assert e01a["confirmation_teacher_probe_teacher_active_selection_requests"] == 27
    assert e01a["confirmation_teacher_probe_teacher_deck_multiset_sha256"] == (
        "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
    )
    assert e01a["confirmation_teacher_probe_archetype_context_label"] == (
        "Marnie's Grimmsnarl ex"
    )
    assert e01a["confirmation_independent_recent_teachers_observed"] == 2
    assert e01a["confirmation_independent_recent_teachers_met"] is True
    assert e01a["confirmation_observed_recent_teacher_episodes"] == 66
    assert e01a["confirmation_episode_shortfall"] == 134
    assert e01a["confirmation_observed_recent_teacher_decisions"] == 7_140
    assert e01a["confirmation_observed_recent_teacher_active_requests"] == 7_542
    assert e01a["confirmation_observed_forced_teacher_requests"] == 402
    assert e01a["confirmation_decision_shortfall"] == 17_860
    assert e01a["confirmation_teacher_calibration_request_ready"] is False
    assert e01a["confirmation_teacher_calibration_request_authorized"] is False
    assert e01a["confirmation_teacher_calibration_authorization_consumed"] is True
    assert e01a["confirmation_teacher_calibration_request_files"] == 12
    assert e01a["confirmation_teacher_calibration_request_bytes"] == 60_869_451
    assert e01a["confirmation_teacher_calibration_files_transferred"] == 12
    assert e01a["confirmation_teacher_calibration_bytes_transferred"] == 60_869_451
    assert e01a["confirmation_teacher_calibration_teacher_active_selection_requests"] == 1_175
    assert e01a["confirmation_teacher_calibration_all_player_active_selection_requests"] == 2_171
    assert e01a["confirmation_teacher_calibration_balanced_strata"] == {
        "seat_0_loss": 3,
        "seat_0_win": 3,
        "seat_1_loss": 3,
        "seat_1_win": 3,
    }
    assert e01a["confirmation_teacher_calibration_all_module_version_qualified"] is True
    assert e01a["confirmation_teacher_calibration_exact_deck_consistency_qualified"] is True
    assert e01a["confirmation_teacher_calibration_action_alignment_qualified"] is True
    assert e01a["confirmation_teacher_probe_completes_confirmation"] is False
    assert e01a["confirmation_gate_passed"] is False
    assert e01a["current_rank_1_team_name"] == "Majkel1337"
    assert e01a["current_rank_1_submission_id"] == 55_186_239
    assert e01a["current_rank_1_public_episode_count"] == 573
    assert e01a["current_rank_1_completed_public_episode_count"] == 571
    assert e01a["current_rank_1_dataset_intersection_files"] == 271
    assert e01a["current_rank_1_dataset_intersection_bytes"] == 1_031_040_048
    assert e01a["current_rank_1_source_ready"] is True
    assert e01a["current_rank_1_probe_request_ready"] is False
    assert e01a["current_rank_1_probe_request_exists"] is True
    assert e01a["current_rank_1_output_exists"] is True
    assert e01a["live_current_rank_1_probe_authorization_consumed"] is True
    assert e01a["live_current_rank_1_probe_request_ready"] is False
    assert e01a["live_current_rank_1_probe_files_transferred"] == 2
    assert e01a["live_current_rank_1_probe_bytes_transferred"] == 832_877
    assert e01a["live_current_rank_1_probe_module_versions"] == ["1.32.2", "1.32.3"]
    assert e01a["live_current_rank_1_probe_teacher_active_requests"] == 35
    assert e01a["live_current_rank_1_probe_forced_teacher_requests"] == 3
    assert e01a["live_current_rank_1_probe_policy_loss_targets"] == 32
    assert e01a["live_current_rank_1_probe_corpus_promotion_authorized"] is False
    assert e01a["current_rank_1_source_wait_active"] is False
    assert e01a["approved_replay_qualified_episodes"] == 337
    assert e01a["approved_replay_policy_loss_targets"] == 23_460
    assert e01a["approved_replay_forced_teacher_requests"] == 1_598
    assert e01a["approved_replay_target_floor_shortfall"] == 1_540
    assert e01a["approved_replay_episode_floor_passed"] is True
    assert e01a["approved_replay_target_floor_passed"] is False
    assert e01a["majkel_corpus_expansion_authorization_consumed"] is True
    assert e01a["majkel_corpus_expansion_files_read"] == 269
    assert e01a["majkel_corpus_expansion_bytes_read"] == 1_030_207_171
    assert e01a["majkel_corpus_expansion_qualified_files"] == 269
    assert e01a["majkel_corpus_expansion_rejected_files"] == 0
    assert e01a["bc_engineering_canary_request_ready"] is False
    assert e01a["bc_engineering_canary_request_authorized"] is False
    assert e01a["bc_engineering_canary_authorization_consumed"] is True
    assert e01a["bc_engineering_canary_passed"] is True
    assert e01a["bc_engineering_canary_maximum_optimizer_steps"] == 64
    assert e01a["bc_engineering_canary_optimizer_steps_executed"] == 64
    assert e01a["bc_engineering_canary_production_checkpoint_eligible"] is False
    assert e01a["transfer_authorized"] is False
    assert e01a["next_stage"] in {
        "corpus_v2_target_shortfall_1540_awaiting_source_refresh_and_exact_approval",
        "resolve_1540_target_shortfall_then_request_production_bc_approval",
    }
    assert validated["work_orders"]["E08"]["final_submitted_deck_frozen"] is False


def test_work_orders_fail_closed_if_external_execution_is_authorized() -> None:
    value = json.loads((ROOT / "configs/gold_path_work_orders_v1.json").read_text())
    value["authorization"]["behavior_cloning_optimizer_steps"] = True
    with pytest.raises(GoldPathContractError, match="must remain false"):
        validate_work_orders(value)


def test_e01a_dry_run_is_exact_capped_and_zero_transfer() -> None:
    value = json.loads(
        (ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json").read_text()
    )
    validated = validate_e01a_dry_run(value)
    assert validated["selection"]["selected_files"] == 8
    assert validated["selection"]["selected_bytes"] == 42_620_009
    assert validated["episode_json_transferred"] == 0


def test_e01_source_provenance_review_blocks_transfer() -> None:
    report = json.loads(
        (ROOT / "reports/artifacts/e01-teacher-deck-metadata-review-v1.json").read_text()
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "BLOCK_E01_SOURCE_MANIFEST_CONTRACT_UNRESOLVED"
    assert report["reviewed_decision"] == "DEC-013"
    comparison = report["manifest_comparison"]
    assert comparison["manifest_object_matches"] is False
    assert comparison["schema_matches"] is False
    assert comparison["selected_episode_ids_match"] is True
    assert len(comparison["selected_row_mismatches"]) == 8
    assert all(not item["byte_count_matches"] for item in comparison["selected_row_mismatches"])
    assert all(not item["create_time_matches"] for item in comparison["selected_row_mismatches"])
    assert set(report["qualification"].values()) == {False}
    assert report["probe"] == {
        "agent_logs_authorized": False,
        "bytes_authorized": 0,
        "external_compute_authorized": False,
        "files_authorized": 0,
        "request_authorized": False,
        "request_ready": False,
        "training_authorized": False,
    }


def test_e01_source_schema_reconciliation_prepares_exact_probe_only() -> None:
    report = json.loads(
        (ROOT / "reports/artifacts/e01-source-schema-reconciliation-v1.json").read_text()
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "ACCEPT_PROVENANCE_ADAPTER_AND_ONE_FILE_REQUEST"
    assert report["reviewed_decision"] == "DEC-014"
    assert report["adapter"] == {
        "candidate_set_reranked": False,
        "episode_identity_reproduced": True,
        "file_byte_count_reproduced": True,
        "rating_field_reproduced": False,
        "rating_field_used_for_probe": False,
        "submission_identity_reproduced": True,
        "team_identity_reproduced": True,
        "timestamp_reproduced": True,
    }
    assert len(report["selected_candidates"]) == 8
    assert report["probe"] == {
        "additional_replays_authorized": False,
        "agent_logs_authorized": False,
        "declared_bytes": 3_641_302,
        "episode_id": 87_703_034,
        "external_compute_authorized": False,
        "file_name": "87703034.json",
        "files_authorized": 1,
        "output_directory_exists": False,
        "request_authorized": False,
        "request_ready": True,
        "smallest_accepted_candidate": True,
        "training_authorized": False,
    }
    assert report["qualification"]["source_schema_reconciled_for_probe"] is True
    assert report["qualification"]["teacher_strength_qualified"] is False
    assert report["qualification"]["deck_qualified"] is False
    assert report["qualification"]["policy_consistency_qualified"] is False
    assert report["qualification"]["e01_screening_gate_passed"] is False
    assert report["qualification"]["replay_transfer_authorized"] is False


def test_e01_completed_probes_and_current_calibration_request_are_fail_closed() -> None:
    consistency_request = json.loads(
        (ROOT / "configs/e01_same_submission_consistency_request_v1.json").read_text()
    )
    assert consistency_request["status"] == "CONSUMED"
    assert consistency_request["request_ready"] is False
    assert consistency_request["authorized"] is False
    assert consistency_request["execution"]["files_downloaded"] == 1
    assert consistency_request["execution"]["bytes_downloaded"] == 559_779

    luca_request = json.loads(
        (ROOT / "configs/e01_luca_gold_teacher_probe_request_v1.json").read_text()
    )
    assert luca_request["status"] == "CONSUMED"
    assert luca_request["request_ready"] is False
    assert luca_request["authorized"] is False
    assert luca_request["approval"]["authorized_request_sha256"] == (
        "8c1c6eac94cd0dc18ea29117c62255c8871df994e280033063c306f0a58aacf4"
    )
    assert luca_request["execution"]["files_downloaded"] == 2
    assert luca_request["execution"]["bytes_downloaded"] == 1_313_221
    assert luca_request["execution"]["agent_logs_downloaded"] == 0
    assert luca_request["execution"]["training_label_exports"] == 0

    luca_review = json.loads(
        (ROOT / "reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json").read_text()
    )
    assert luca_review["status"] == "PASS"
    assert luca_review["decision"] == (
        "ACCEPT_GOLD_REGION_TEACHER_DECK_CONSISTENCY_MODULE_BOUNDARY_SCREENING_FLOOR_BLOCKED"
    )
    assert luca_review["qualification"]["teacher_strength_qualified"] is True
    assert luca_review["qualification"]["exact_deck_consistency_qualified"] is True
    assert luca_review["qualification"]["same_module_version_qualified"] is False
    assert luca_review["qualification"]["minimum_5000_teacher_decisions_met"] is False
    assert luca_review["consistency"]["combined_luca_active_selection_requests"] == 37
    assert luca_review["consistency"]["screening_teacher_decision_shortfall"] == 4_963

    calibration_request = json.loads(
        (ROOT / "configs/e01_luca_same_version_calibration_request_v1.json").read_text()
    )
    assert calibration_request["status"] == "CONSUMED"
    assert calibration_request["request_ready"] is False
    assert calibration_request["authorized"] is False
    assert calibration_request["maximum_new_files"] == 12
    assert calibration_request["maximum_new_bytes"] == 63_828_057
    assert calibration_request["review_boundary"]["require_module_version"] == "1.32.2"
    assert calibration_request["execution"]["files_downloaded"] == 12
    assert calibration_request["execution"]["bytes_downloaded"] == 63_828_057
    assert calibration_request["execution"]["agent_logs_downloaded"] == 0
    assert calibration_request["execution"]["training_label_exports"] == 0

    contract = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-luca-same-version-calibration-contract-review-v1.json"
        ).read_text()
    )
    assert contract["status"] == "PASS"
    assert contract["decision"] == (
        "ACCEPT_EXACT_12_FILE_LUCA_CALIBRATION_REQUEST_UNAUTHORIZED"
    )
    assert contract["request"]["request_ready"] is True
    assert contract["request"]["authorized"] is False
    assert contract["request"]["maximum_new_files"] == 12
    assert contract["request"]["required_module_version"] == "1.32.2"

    calibration_review = json.loads(
        (ROOT / "reports/artifacts/e01-luca-same-version-calibration-review-v1.json").read_text()
    )
    assert calibration_review["status"] == "PASS"
    assert calibration_review["consistency"]["module_versions"] == ["1.32.2"]
    assert calibration_review["consistency"]["calibration_luca_active_selection_requests"] == 1_170
    assert calibration_review["density"]["combined_observed_luca_decisions"] == 1_207
    assert calibration_review["density"]["screening_teacher_decision_shortfall"] == 3_793
    assert calibration_review["qualification"]["policy_behavior_consistency_qualified"] is True
    assert calibration_review["qualification"]["minimum_5000_teacher_decisions_met"] is False

    expansion_request = json.loads(
        (ROOT / "configs/e01_luca_screening_expansion_request_v1.json").read_text()
    )
    assert expansion_request["status"] == "READY_UNAUTHORIZED"
    assert expansion_request["request_ready"] is True
    assert expansion_request["authorized"] is False
    assert expansion_request["maximum_new_files"] == 51
    assert expansion_request["maximum_new_bytes"] == 270_807_738
    assert len(expansion_request["episodes"]) == 51
    assert expansion_request["review_boundary"]["count_only_module_version"] == "1.32.2"

    expansion_contract = json.loads(
        (ROOT / "reports/artifacts/e01-luca-screening-expansion-contract-review-v1.json").read_text()
    )
    assert expansion_contract["status"] == "PASS"
    assert expansion_contract["decision"] == (
        "ACCEPT_EXACT_51_FILE_LUCA_SCREENING_EXPANSION_REQUEST_UNAUTHORIZED"
    )
    assert expansion_contract["request"]["request_ready"] is True
    assert expansion_contract["request"]["authorized"] is False
    assert expansion_contract["request"]["maximum_new_files"] == 51

    flg_request = json.loads(
        (ROOT / "configs/e01_flg_gold_teacher_probe_request_v1.json").read_text()
    )
    assert flg_request["status"] == "CONSUMED"
    assert flg_request["request_ready"] is False
    assert flg_request["authorized"] is False
    assert flg_request["approval"]["authorized_request_sha256"] == (
        "b1cb07cace93137c33dde150d6177d38bc7edce9de3c895f6268ee31b4bd1dea"
    )
    assert flg_request["execution"]["files_downloaded"] == 2
    assert flg_request["execution"]["bytes_downloaded"] == 3_996_398
    assert flg_request["execution"]["agent_logs_downloaded"] == 0
    assert flg_request["execution"]["training_label_exports"] == 0

    flg_review = json.loads(
        (ROOT / "reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json").read_text()
    )
    assert flg_review["status"] == "PASS"
    assert flg_review["reviewed_decision"] == "DEC-019"
    assert flg_review["teacher"]["live_rank_at_refresh"] == 1
    assert flg_review["consistency"]["module_versions"] == ["1.32.2"]
    assert flg_review["consistency"]["teacher_archetype_context_label"] == "Dragapult ex"
    assert flg_review["consistency"]["combined_teacher_active_selection_requests"] == 94
    assert flg_review["consistency"]["screening_teacher_decision_shortfall"] == 4_906
    assert flg_review["qualification"]["teacher_strength_qualified"] is True
    assert flg_review["qualification"]["minimum_5000_teacher_decisions_met"] is False

    flg_calibration_request = json.loads(
        (ROOT / "configs/e01_flg_dragapult_calibration_request_v1.json").read_text()
    )
    assert flg_calibration_request["status"] == "CONSUMED"
    assert flg_calibration_request["request_ready"] is False
    assert flg_calibration_request["authorized"] is False
    assert flg_calibration_request["maximum_new_files"] == 12
    assert flg_calibration_request["maximum_new_bytes"] == 63_562_985
    assert flg_calibration_request["approval"]["authorized_request_sha256"] == (
        "42b97e0fbb26e293a62747e5437315ae2018bdb7d5c07c0d28004dcc604adce7"
    )
    assert flg_calibration_request["execution"]["files_downloaded"] == 12
    assert flg_calibration_request["execution"]["bytes_downloaded"] == 63_562_985
    assert flg_calibration_request["execution"]["agent_logs_downloaded"] == 0
    assert flg_calibration_request["execution"]["training_label_exports"] == 0
    assert flg_calibration_request["review_boundary"]["require_module_version"] == "1.32.2"
    assert flg_calibration_request["teacher"]["archetype_context_label"] == "Dragapult ex"

    flg_calibration_contract = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-flg-dragapult-calibration-contract-review-v1.json"
        ).read_text()
    )
    assert flg_calibration_contract["status"] == "PASS"
    assert flg_calibration_contract["reviewed_decision"] == "DEC-020"
    assert flg_calibration_contract["request"]["request_ready"] is True
    assert flg_calibration_contract["request"]["authorized"] is False
    assert flg_calibration_contract["request"]["maximum_new_files"] == 12
    assert flg_calibration_contract["request"]["maximum_new_bytes"] == 63_562_985

    flg_calibration_review = json.loads(
        (ROOT / "reports/artifacts/e01-flg-dragapult-calibration-review-v1.json").read_text()
    )
    assert flg_calibration_review["status"] == "PASS"
    assert flg_calibration_review["reviewed_decision"] == "DEC-020"
    assert flg_calibration_review["consistency"]["module_versions"] == ["1.32.2"]
    assert flg_calibration_review["consistency"]["calibration_teacher_active_selection_requests"] == 1_292
    assert flg_calibration_review["density"]["combined_observed_teacher_decisions"] == 1_386
    assert flg_calibration_review["density"]["screening_teacher_decision_shortfall"] == 3_614
    assert flg_calibration_review["qualification"]["minimum_5000_teacher_decisions_met"] is False

    flg_expansion_request = json.loads(
        (ROOT / "configs/e01_flg_dragapult_screening_expansion_request_v1.json").read_text()
    )
    assert flg_expansion_request["status"] == "CONSUMED"
    assert flg_expansion_request["request_ready"] is False
    assert flg_expansion_request["authorized"] is False
    assert flg_expansion_request["maximum_new_files"] == 38
    assert flg_expansion_request["maximum_new_bytes"] == 254_237_550
    assert flg_expansion_request["approval"]["authorized_request_sha256"] == (
        "72cc26257d28af61649d664103931effccbc9dfe65de0fcc66cf92fdfb6f6735"
    )
    assert flg_expansion_request["execution"]["files_downloaded"] == 38
    assert flg_expansion_request["execution"]["bytes_downloaded"] == 254_237_550
    assert flg_expansion_request["execution"]["agent_logs_downloaded"] == 0
    assert flg_expansion_request["execution"]["training_label_exports"] == 0
    assert (ROOT / flg_expansion_request["output_directory"]).exists()

    flg_expansion_contract = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-flg-dragapult-screening-expansion-contract-review-v1.json"
        ).read_text()
    )
    assert flg_expansion_contract["status"] == "PASS"
    assert flg_expansion_contract["reviewed_decision"] == "DEC-021"
    assert flg_expansion_contract["decision"] == (
        "ACCEPT_EXACT_38_FILE_CURRENT_RANK_1_DRAGAPULT_"
        "SCREENING_EXPANSION_REQUEST_UNAUTHORIZED"
    )
    assert flg_expansion_contract["request"]["request_ready"] is True
    assert flg_expansion_contract["request"]["authorized"] is False

    flg_expansion_review = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json"
        ).read_text()
    )
    assert flg_expansion_review["status"] == "PASS"
    assert flg_expansion_review["reviewed_decision"] == "DEC-021"
    assert flg_expansion_review["screening"]["qualified_files"] == 38
    assert flg_expansion_review["screening"]["rejected_files"] == 0
    assert flg_expansion_review["screening"]["qualified_teacher_active_selection_requests"] == 4_954
    assert flg_expansion_review["screening"]["combined_observed_teacher_decisions"] == 6_340
    assert flg_expansion_review["qualification"]["minimum_5000_teacher_decisions_met"] is True
    assert flg_expansion_review["qualification"]["e01_screening_gate_passed"] is True

    confirmation_refresh = json.loads(
        (ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v1.json").read_text()
    )
    assert confirmation_refresh["teacher"]["team_name"] == "Dries @ Tufa Labs"
    assert confirmation_refresh["teacher"]["live_rank_at_refresh"] == 1
    assert confirmation_refresh["teacher"]["submission_id"] == 55_002_825
    assert confirmation_refresh["teacher"]["dataset_episode_count"] == 128
    assert confirmation_refresh["selection"]["selected_total_bytes"] == 1_135_238
    assert len(confirmation_refresh["selection"]["selected_files"]) == 2
    assert confirmation_refresh["supersession"]["completed_screening_teacher_current_rank"] == 4
    assert confirmation_refresh["supersession"]["completed_screening_teacher_active_submission_changed"] is True

    dries_request = json.loads(
        (ROOT / "configs/e01_dries_confirmation_teacher_probe_request_v1.json").read_text()
    )
    assert dries_request["status"] == "CONSUMED"
    assert dries_request["request_ready"] is False
    assert dries_request["authorized"] is False
    assert dries_request["maximum_new_files"] == 2
    assert dries_request["maximum_new_bytes"] == 1_135_238
    assert dries_request["execution"]["files_downloaded"] == 2
    assert dries_request["execution"]["bytes_downloaded"] == 1_135_238
    assert [item["episode_id"] for item in dries_request["episodes"]] == [
        88_281_294,
        88_332_011,
    ]
    assert (ROOT / dries_request["output_directory"]).is_dir()

    dries_contract = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-dries-confirmation-teacher-contract-review-v1.json"
        ).read_text()
    )
    assert dries_contract["status"] == "PASS"
    assert dries_contract["reviewed_decision"] == "DEC-022"
    assert dries_contract["request"]["request_ready"] is True
    assert dries_contract["request"]["authorized"] is False

    dries_review = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json"
        ).read_text()
    )
    assert dries_review["status"] == "PASS"
    assert dries_review["reviewed_decision"] == "DEC-022"
    assert dries_review["consistency"]["module_versions"] == ["1.32.2"]
    assert dries_review["consistency"]["teacher_deck_multiset_sha256"] == (
        "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd"
    )
    assert dries_review["consistency"]["teacher_archetype_context_label"] == (
        "Marnie's Grimmsnarl ex"
    )
    assert dries_review["consistency"]["combined_teacher_active_selection_requests"] == 27
    assert dries_review["confirmation"]["observed_recent_teacher_episodes"] == 54
    assert dries_review["confirmation"]["observed_recent_teacher_decisions"] == 6_367
    assert dries_review["confirmation"]["confirmation_gate_passed"] is False

    dries_calibration_request = json.loads(
        (ROOT / "configs/e01_dries_grimmsnarl_calibration_request_v1.json").read_text()
    )
    assert dries_calibration_request["status"] == "CONSUMED"
    assert dries_calibration_request["request_ready"] is False
    assert dries_calibration_request["authorized"] is False
    assert dries_calibration_request["maximum_new_files"] == 12
    assert dries_calibration_request["maximum_new_bytes"] == 60_869_451
    assert dries_calibration_request["selection_basis"]["balanced_strata"] == {
        "seat_0_loss": 3,
        "seat_0_win": 3,
        "seat_1_loss": 3,
        "seat_1_win": 3,
    }
    assert (ROOT / dries_calibration_request["output_directory"]).is_dir()
    assert dries_calibration_request["execution"]["files_downloaded"] == 12
    assert dries_calibration_request["execution"]["bytes_downloaded"] == 60_869_451

    dries_calibration_contract = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-dries-grimmsnarl-calibration-contract-review-v1.json"
        ).read_text()
    )
    assert dries_calibration_contract["status"] == "PASS"
    assert dries_calibration_contract["reviewed_decision"] == "DEC-023"
    assert dries_calibration_contract["request"]["request_ready"] is True
    assert dries_calibration_contract["request"]["authorized"] is False
    assert dries_calibration_contract["request"]["maximum_new_files"] == 12
    assert dries_calibration_contract["request"]["maximum_new_bytes"] == 60_869_451
    assert dries_calibration_contract["confirmation"]["confirmation_gate_passed"] is False

    dries_calibration_review = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json"
        ).read_text()
    )
    assert dries_calibration_review["status"] == "PASS"
    assert dries_calibration_review["reviewed_decision"] == "DEC-023"
    assert dries_calibration_review["consistency"]["calibration_teacher_active_selection_requests"] == 1_175
    assert dries_calibration_review["confirmation"]["observed_recent_teacher_episodes"] == 66
    assert dries_calibration_review["confirmation"]["observed_recent_teacher_decisions"] == 7_542
    assert dries_calibration_review["confirmation"]["episode_shortfall"] == 134
    assert dries_calibration_review["confirmation"]["decision_shortfall"] == 17_458
    assert dries_calibration_review["confirmation"]["confirmation_gate_passed"] is False

    source_refresh = json.loads(
        (ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v2.json").read_text()
    )
    assert source_refresh["current_rank_1"]["team_name"] == "haggle"
    assert source_refresh["current_rank_1"]["active_submission"]["submission_id"] == 55_104_355
    assert source_refresh["current_rank_1_dataset_intersection"]["episodes"] == 0
    assert source_refresh["source_boundary"]["current_rank_1_probe_request_ready"] is False

    source_wait_review = json.loads(
        (
            ROOT
            / "reports/artifacts/e01-live-confirmation-source-wait-review-v1.json"
        ).read_text()
    )
    assert source_wait_review["status"] == "PASS"
    assert source_wait_review["reviewed_decision"] == "DEC-024"
    assert source_wait_review["source_wait"]["current_rank_1_probe_request_exists"] is False
    assert source_wait_review["source_wait"]["replay_transfer_authorized"] is False


def test_independent_gold_path_review_passes() -> None:
    report = review_gold_path(
        REPOSITORY_ROOT,
        work_orders_path=ROOT / "configs/gold_path_work_orders_v1.json",
        dry_run_path=ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json",
        decision_path=(
            ROOT
            / "docs/decisions/DEC-028_E01_CORPUS_V2_AND_BC_CANARY_RESULTS.md"
        ),
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "ACCEPT"
    assert report["authorization"]["training"] is False
    assert report["authorization"]["e01_source_schema_reconciled_for_probe"] is True
    assert report["authorization"]["e01_provenance_probe_completed"] is True
    assert report["authorization"]["e01_provenance_probe_authorization_consumed"] is True
    assert report["authorization"]["e01_provenance_probe_request_ready"] is False
    assert report["authorization"]["e01_same_submission_consistency_completed"] is True
    assert report["authorization"]["e01_same_submission_consistency_authorization_consumed"] is True
    assert report["authorization"]["e01_same_submission_consistency_request_ready"] is False
    assert report["authorization"]["e01_luca_gold_teacher_completed"] is True
    assert report["authorization"]["e01_luca_gold_teacher_authorization_consumed"] is True
    assert report["authorization"]["e01_luca_gold_teacher_request_ready"] is False
    assert report["authorization"]["e01_luca_same_version_calibration_completed"] is True
    assert report["authorization"]["e01_luca_same_version_calibration_authorization_consumed"] is True
    assert report["authorization"]["e01_luca_same_version_calibration_request_ready"] is False
    assert report["authorization"]["e01_luca_screening_expansion_request_ready"] is True
    assert report["authorization"]["e01_luca_screening_expansion_execution"] is False
    assert report["authorization"]["e01_luca_screening_expansion_superseded"] is True
    assert report["authorization"]["e01_live_gold_refresh_completed"] is True
    assert report["authorization"]["e01_current_rank_1_teacher_completed"] is True
    assert report["authorization"]["e01_current_rank_1_teacher_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_teacher_request_ready"] is False
    assert report["authorization"]["e01_current_rank_1_dragapult_calibration_completed"] is True
    assert report["authorization"]["e01_current_rank_1_dragapult_calibration_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_dragapult_calibration_request_ready"] is False
    assert report["authorization"]["e01_current_rank_1_dragapult_screening_expansion_completed"] is True
    assert report["authorization"]["e01_current_rank_1_dragapult_screening_expansion_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_dragapult_screening_expansion_request_ready"] is False
    assert report["authorization"]["e01_live_confirmation_refresh_completed"] is True
    assert report["authorization"]["e01_current_rank_1_dries_confirmation_teacher_completed"] is True
    assert report["authorization"]["e01_current_rank_1_dries_confirmation_teacher_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_dries_confirmation_teacher_request_ready"] is False
    assert report["authorization"]["e01_current_rank_1_dries_grimmsnarl_calibration_completed"] is True
    assert report["authorization"]["e01_current_rank_1_dries_grimmsnarl_calibration_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_dries_grimmsnarl_calibration_request_ready"] is False
    assert report["authorization"]["e01_current_rank_1_source_wait_completed"] is True
    assert report["authorization"]["e01_current_rank_1_source_ready"] is True
    assert report["authorization"]["e01_current_rank_1_probe_authorization_consumed"] is True
    assert report["authorization"]["e01_current_rank_1_probe_request_ready"] is False
    assert report["authorization"]["e01_current_rank_1_probe_corpus_promotion_authorized"] is False
    assert report["authorization"]["e01_approved_replay_corpus_frozen"] is True
    assert report["authorization"]["e01_approved_replay_episode_floor_passed"] is True
    assert report["authorization"]["e01_approved_replay_target_floor_passed"] is False
    assert report["authorization"]["e01_approved_replay_target_floor_shortfall"] == 1_540
    assert report["authorization"]["e01_majkel_corpus_expansion_completed"] is True
    assert report["authorization"]["e01_majkel_corpus_expansion_authorization_consumed"] is True
    assert report["authorization"]["e01_bc_engineering_canary_completed"] is True
    assert report["authorization"]["e01_bc_engineering_canary_authorization_consumed"] is True
    assert report["authorization"]["e01_bc_engineering_canary_request_ready"] is False
    assert report["authorization"]["e01_bc_engineering_canary_optimizer_steps_authorized"] is False
    assert report["authorization"]["e01_bc_engineering_canary_production_checkpoint_eligible"] is False
    assert report["authorization"]["replay_transfer"] is False
    assert report["authorization"]["native_e04_single_trace_completed"] is True
    assert report["authorization"]["native_e04_ten_game_smoke_completed"] is True
    assert report["reviewed_decision"] == "DEC-028"
    assert report["authorization"]["qualification_contract_review_required"] is False
    assert report["authorization"]["qualification_request_ready"] is False
    assert report["authorization"]["qualification_execution_completed"] is True
    assert report["authorization"]["native_e04_qualification_completed"] is True
    assert report["authorization"]["zero_update_bridge_qualified"] is True
    assert report["authorization"]["further_native_e04_execution"] is False
