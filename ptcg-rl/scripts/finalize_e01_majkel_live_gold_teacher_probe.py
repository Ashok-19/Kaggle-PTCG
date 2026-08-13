from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import e01_dries_confirmation_teacher_probe_review as base

ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / "configs/e01_majkel_live_gold_teacher_probe_request_v1.json"
READINESS_PATH = ROOT / "reports/artifacts/e01-majkel-next-step-readiness-v1.json"
CONTRACT_PATH = ROOT / "reports/artifacts/e01-majkel-live-gold-teacher-contract-review-v1.json"
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
FIRST_REPLAY_PATH = ROOT / "private/g3/e01/majkel-live-gold-teacher-probe-v1/89651832.json"
SECOND_REPLAY_PATH = ROOT / "private/g3/e01/majkel-live-gold-teacher-probe-v1/89802438.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json"

PRIOR_REQUEST_SHA256 = "e0b43f2a507728f5b2048a9ac7d8e30b6f444448e74885503267058477029886"
READINESS_SHA256 = "b4bf06e417f24e533c63627c14800c04d1fcbfac46c25777cd306edcc4c93520"
CONTRACT_SHA256 = "5d3e2682554690990ba1bc301bf9a0a075ed56bf4707df5ff473c4e8761fffc0"
CONTRACT_SELF_SHA256 = "12e82afaf04b50c245d4cfaecf0a06cced488ef6abec45fa015db3bcbbe79384"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
FIRST_REPLAY_SHA256 = "6e03791819464b8376423a7e2d0cda171cf4abfc1541ac84cd2b90069aeec288"
SECOND_REPLAY_SHA256 = "ec5ab4bce6e29c8062f504ae24aac754d83c32689103ec3e997d4ab44cfe97e2"
APPROVED_AT_UTC = "2026-08-04T12:56:00Z"
CONSUMED_AT_UTC = "2026-08-04T13:08:38Z"


def file_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def value_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(base.canonical_bytes(value)).hexdigest()


def require_hash(path: Path, expected: str) -> None:
    observed = base.sha256_file(path)
    if observed != expected:
        raise ValueError(f"hash differs for {path}: {observed}")


def require_bound_request(request: Mapping[str, Any]) -> None:
    selection = request.get("selection")
    source = request.get("source")
    if not isinstance(selection, Mapping) or not isinstance(source, Mapping):
        raise ValueError("request selection or source is missing")
    episodes = selection.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 2:
        raise ValueError("request does not contain exactly two episodes")
    expected = [
        (89_651_832, "89651832.json", 376_976, 1, 1.0),
        (89_802_438, "89802438.json", 455_901, 0, 1.0),
    ]
    observed = [
        (
            item.get("episode_id"),
            item.get("file_name"),
            item.get("declared_bytes"),
            item.get("teacher_index"),
            item.get("teacher_reward"),
        )
        for item in episodes
        if isinstance(item, Mapping)
    ]
    if observed != expected:
        raise ValueError("request episode identities or bounds differ")
    if (
        selection.get("maximum_new_files") != 2
        or selection.get("maximum_new_bytes") != 832_877
        or request.get("output_directory")
        != "private/g3/e01/majkel-live-gold-teacher-probe-v1"
        or source.get("dataset_owner") != "kaggle"
        or source.get("dataset_slug")
        != "pokemon-tcg-ai-battle-episodes-2026-08-03"
        or source.get("dataset_version") != 1
        or source.get("teacher_team_id") != 16_374_395
        or source.get("teacher_team_name") != "Majkel1337"
        or source.get("teacher_submission_id") != 55_186_239
    ):
        raise ValueError("request source, output, or cap differs")


def inspect_replay(
    path: Path,
    *,
    expected_episode_id: int,
    expected_bytes: int,
    expected_sha256: str,
    teacher_player_index: int,
    cards: Mapping[int, Mapping[str, str]],
) -> dict[str, Any]:
    require_hash(path, expected_sha256)
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"byte count differs for {path}")
    replay = base.load_json(path)
    if (
        replay.get("schema_version") != 1
        or replay.get("name") != "cabt"
        or replay.get("version") != "1.0.0"
        or replay.get("module_version") not in {"1.32.2", "1.32.3"}
    ):
        raise ValueError("replay schema, environment, or reviewed module differs")
    info = replay.get("info")
    if not isinstance(info, Mapping) or info.get("EpisodeId") != expected_episode_id:
        raise ValueError("episode identity differs")
    if replay.get("statuses") != ["DONE", "DONE"]:
        raise ValueError("terminal statuses differ")
    rewards = replay.get("rewards")
    if not isinstance(rewards, list) or rewards[teacher_player_index] != 1:
        raise ValueError("teacher reward differs")
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError("steps are missing")

    parsed: list[list[Mapping[str, Any]]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            raise ValueError(f"step {step_index} does not contain two players")
        parsed.append(
            [
                base._validate_record(
                    record, f"{path.name}.steps[{step_index}][{player_index}]"
                )
                for player_index, record in enumerate(step)
            ]
        )

    deck_actions: list[list[int]] = []
    for player_index, record in enumerate(parsed[1]):
        action = base._validate_action(record.get("action"), f"deck[{player_index}]")
        if len(action) != 60:
            raise ValueError("initial deck action is not exactly 60 cards")
        deck_actions.append(action)

    active_requests = 0
    active_by_player: Counter[int] = Counter()
    forced_by_player: Counter[int] = Counter()
    empty_by_player: Counter[int] = Counter()
    nonempty_by_player: Counter[int] = Counter()
    maximum_options = 0
    maximum_selection = 0
    for step_index in range(2, len(parsed)):
        for player_index, current in enumerate(parsed[step_index]):
            action = base._validate_action(
                current.get("action"), f"action[{step_index}][{player_index}]"
            )
            previous = parsed[step_index - 1][player_index]
            if previous.get("status") != "ACTIVE":
                if action:
                    raise ValueError("action occurs after inactive record")
                continue
            request = base._selection_request(
                previous, f"previous[{step_index - 1}][{player_index}]"
            )
            if request is None:
                if action:
                    raise ValueError("action occurs after missing request")
                continue
            minimum = base._integer(request.get("minCount"), "minimum")
            maximum = base._integer(request.get("maxCount"), "maximum")
            options = request.get("option")
            if not isinstance(options, list) or any(
                not isinstance(option, Mapping) for option in options
            ):
                raise ValueError("request options differ")
            if not minimum <= len(action) <= maximum:
                raise ValueError("selection count is outside request bounds")
            if not base._resolves_against_options(action, options):
                raise ValueError("action does not resolve against request options")
            active_requests += 1
            active_by_player[player_index] += 1
            forced_by_player[player_index] += int(
                minimum == 1 and maximum == 1 and len(options) == 1
            )
            empty_by_player[player_index] += int(not action)
            nonempty_by_player[player_index] += int(bool(action))
            maximum_options = max(maximum_options, len(options))
            maximum_selection = max(maximum_selection, len(action))

    agents = info.get("Agents")
    team_names = info.get("TeamNames")
    if not isinstance(agents, list) or not isinstance(team_names, list):
        raise ValueError("agent metadata differs")
    agent_names = [
        agent.get("Name") if isinstance(agent, Mapping) else None for agent in agents
    ]
    if (
        agent_names[teacher_player_index] != "Majkel1337"
        or team_names[teacher_player_index] != "Majkel1337"
    ):
        raise ValueError("Majkel player binding differs")

    decks = [base.deck_construction(action, cards) for action in deck_actions]
    teacher_active = active_by_player[teacher_player_index]
    teacher_forced = forced_by_player[teacher_player_index]
    return {
        "episode_id": expected_episode_id,
        "file": {
            "path": str(path.relative_to(ROOT)),
            "bytes": expected_bytes,
            "sha256": expected_sha256,
        },
        "schema_version": replay.get("schema_version"),
        "module_version": replay.get("module_version"),
        "environment_name": replay.get("name"),
        "environment_version": replay.get("version"),
        "steps": len(steps),
        "team_names": team_names,
        "agent_names": agent_names,
        "statuses": replay.get("statuses"),
        "rewards": rewards,
        "teacher_player_index": teacher_player_index,
        "teacher_reward": rewards[teacher_player_index],
        "teacher_deck": decks[teacher_player_index],
        "opponent_deck_multiset_sha256": decks[1 - teacher_player_index][
            "multiset_sha256"
        ],
        "action_alignment": {
            "status": "PASS",
            "active_selection_requests": active_requests,
            "active_requests_by_player": {
                str(key): value for key, value in sorted(active_by_player.items())
            },
            "teacher_active_selection_requests": teacher_active,
            "teacher_forced_singleton_requests": teacher_forced,
            "teacher_policy_loss_targets_if_later_authorized": teacher_active
            - teacher_forced,
            "empty_lagged_selections_by_player": {
                str(key): value for key, value in sorted(empty_by_player.items())
            },
            "nonempty_lagged_selections_by_player": {
                str(key): value for key, value in sorted(nonempty_by_player.items())
            },
            "maximum_option_count": maximum_options,
            "maximum_selection_count": maximum_selection,
        },
    }


def build_consumed_request(original: Mapping[str, Any]) -> dict[str, Any]:
    require_bound_request(original)
    if (
        original.get("status") != "READY_UNAUTHORIZED"
        or original.get("request_ready") is not True
        or original.get("authorized") is not False
        or original.get("authorization_consumed") is not False
    ):
        raise ValueError("prior request is not ready and unconsumed")
    consumed = copy.deepcopy(dict(original))
    approval = {
        "approved_by": "user",
        "approval_received_at_utc": APPROVED_AT_UTC,
        "approval_time_precision": "minute_from_conversation_metadata",
        "approval_scope": "AUTHORIZED_EXACT_TWO_FILE_MAJKEL_LIVE_GOLD_TEACHER_PROBE_ONLY",
        "approved_prior_request_sha256": PRIOR_REQUEST_SHA256,
        "one_time": True,
        "maximum_new_files": 2,
        "maximum_new_bytes": 832_877,
        "replay_transfer_authorized": True,
        "agent_logs_authorized": False,
        "raw_exports_authorized": False,
        "label_generation_authorized": False,
        "optimizer_steps_authorized": False,
        "training_authorized": False,
        "external_compute_authorized": False,
        "submission_authorized": False,
        "git_commit_authorized": False,
        "git_push_authorized": False,
        "consumed_at_utc": CONSUMED_AT_UTC,
    }
    approval["approval_receipt_sha256"] = value_sha256(approval)
    execution = {
        "dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
        "retrieval_method": "authenticated_kaggle_cli_filename_scoped_download",
        "output_directory": "private/g3/e01/majkel-live-gold-teacher-probe-v1",
        "files_downloaded": 2,
        "bytes_downloaded": 832_877,
        "downloaded_files": [
            {
                "episode_id": 89_651_832,
                "file_name": "89651832.json",
                "path": "private/g3/e01/majkel-live-gold-teacher-probe-v1/89651832.json",
                "bytes": 376_976,
                "sha256": FIRST_REPLAY_SHA256,
            },
            {
                "episode_id": 89_802_438,
                "file_name": "89802438.json",
                "path": "private/g3/e01/majkel-live-gold-teacher-probe-v1/89802438.json",
                "bytes": 455_901,
                "sha256": SECOND_REPLAY_SHA256,
            },
        ],
        "unexpected_files": 0,
        "overwrite_used": False,
        "agent_logs_downloaded": 0,
        "additional_replays_downloaded_after_named_files": 0,
        "raw_replay_body_exports": 0,
        "raw_step_exports": 0,
        "request_exports": 0,
        "option_exports": 0,
        "observation_exports": 0,
        "action_sequence_exports": 0,
        "card_list_exports": 0,
        "training_label_exports": 0,
        "optimizer_steps": 0,
        "training": False,
        "external_compute": False,
        "submission": False,
        "git_commit": False,
        "git_push": False,
        "completed_at_utc": CONSUMED_AT_UTC,
    }
    execution["execution_receipt_sha256"] = value_sha256(execution)
    consumed["approval"] = approval
    consumed["execution"] = execution
    consumed["authorization_scope"] = (
        "CONSUMED_EXACT_TWO_FILE_MAJKEL_LIVE_GOLD_TEACHER_PROBE_ONLY"
    )
    consumed["authorization_consumed"] = True
    consumed["authorized"] = False
    consumed["request_ready"] = False
    consumed["status"] = "CONSUMED"
    consumed["completed_at_utc"] = CONSUMED_AT_UTC
    return consumed


def validate_consumed_request(request: Mapping[str, Any]) -> None:
    require_bound_request(request)
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("authorization_consumed") is not True
    ):
        raise ValueError("request consumption state differs")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution receipt is missing")
    if (
        approval.get("approved_prior_request_sha256") != PRIOR_REQUEST_SHA256
        or approval.get("replay_transfer_authorized") is not True
        or approval.get("one_time") is not True
        or approval.get("maximum_new_files") != 2
        or approval.get("maximum_new_bytes") != 832_877
        or approval.get("optimizer_steps_authorized") is not False
        or approval.get("training_authorized") is not False
        or approval.get("external_compute_authorized") is not False
        or approval.get("submission_authorized") is not False
        or approval.get("git_commit_authorized") is not False
        or approval.get("git_push_authorized") is not False
    ):
        raise ValueError("approval scope differs")
    approval_copy = dict(approval)
    approval_hash = approval_copy.pop("approval_receipt_sha256", None)
    if approval_hash != value_sha256(approval_copy):
        raise ValueError("approval receipt self hash differs")
    execution_copy = dict(execution)
    execution_hash = execution_copy.pop("execution_receipt_sha256", None)
    if execution_hash != value_sha256(execution_copy):
        raise ValueError("execution receipt self hash differs")
    if (
        execution.get("files_downloaded") != 2
        or execution.get("bytes_downloaded") != 832_877
        or execution.get("unexpected_files") != 0
        or execution.get("optimizer_steps") != 0
        or execution.get("training") is not False
        or execution.get("external_compute") is not False
        or execution.get("submission") is not False
    ):
        raise ValueError("execution boundary differs")


def build_report(
    consumed_request: Mapping[str, Any], consumed_request_sha256: str
) -> dict[str, Any]:
    require_hash(READINESS_PATH, READINESS_SHA256)
    require_hash(CONTRACT_PATH, CONTRACT_SHA256)
    require_hash(CARD_DATA_PATH, CARD_DATA_SHA256)
    validate_consumed_request(consumed_request)

    readiness = base.load_json(READINESS_PATH)
    contract = base.load_json(CONTRACT_PATH)
    if contract.get("review_sha256") != CONTRACT_SELF_SHA256:
        raise ValueError("contract review self hash differs")
    rank_1 = readiness.get("live_leaderboard", {}).get("rank_1", {})
    source = readiness.get("daily_source", {})
    exact_request = readiness.get("exact_request", {})
    if (
        rank_1.get("team_id") != 16_374_395
        or rank_1.get("team_name") != "Majkel1337"
        or exact_request.get("teacher_submission_id") != 55_186_239
        or exact_request.get("sha256") != PRIOR_REQUEST_SHA256
        or source.get("request_source_version") != 1
        or source.get("request_source_unchanged") is not True
    ):
        raise ValueError("readiness source binding differs")

    expected_names = ["89651832.json", "89802438.json"]
    observed_names = sorted(
        path.name for path in FIRST_REPLAY_PATH.parent.iterdir() if path.is_file()
    )
    if observed_names != expected_names:
        raise ValueError("Majkel quarantine contains unexpected files")

    cards = base.card_table()
    first = inspect_replay(
        FIRST_REPLAY_PATH,
        expected_episode_id=89_651_832,
        expected_bytes=376_976,
        expected_sha256=FIRST_REPLAY_SHA256,
        teacher_player_index=1,
        cards=cards,
    )
    second = inspect_replay(
        SECOND_REPLAY_PATH,
        expected_episode_id=89_802_438,
        expected_bytes=455_901,
        expected_sha256=SECOND_REPLAY_SHA256,
        teacher_player_index=0,
        cards=cards,
    )
    episodes = [first, second]
    module_versions = sorted({episode["module_version"] for episode in episodes})
    if module_versions != ["1.32.2", "1.32.3"]:
        raise ValueError("Majkel module transition differs")
    deck_hashes = sorted(
        {episode["teacher_deck"]["multiset_sha256"] for episode in episodes}
    )
    archetypes = sorted(
        {episode["teacher_deck"]["archetype_context_label"] for episode in episodes}
    )
    if len(deck_hashes) != 1 or len(archetypes) != 1:
        raise ValueError("Majkel exact deck or archetype differs across episodes")
    if any(
        episode["teacher_deck"]["current_asset_construction_checks"] != "PASS"
        or episode["action_alignment"]["status"] != "PASS"
        for episode in episodes
    ):
        raise ValueError("deck construction or action alignment differs")

    teacher_active = sum(
        episode["action_alignment"]["teacher_active_selection_requests"]
        for episode in episodes
    )
    teacher_forced = sum(
        episode["action_alignment"]["teacher_forced_singleton_requests"]
        for episode in episodes
    )
    teacher_policy_targets = teacher_active - teacher_forced
    all_player_active = sum(
        episode["action_alignment"]["active_selection_requests"]
        for episode in episodes
    )
    if teacher_active <= 0 or teacher_policy_targets <= 0:
        raise ValueError("Majkel probe contains no meaningful teacher supervision")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-live-gold-teacher-probe-review-v1",
        "source_path": "reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json",
        "created_at_utc": CONSUMED_AT_UTC,
        "producer": "scripts/finalize_e01_majkel_live_gold_teacher_probe.py",
        "reviewed_decision": "DEC-025",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_MAJKEL_CURRENT_RANK_1_TWO_FILE_MIXED_MODULE_CONTRACT_COMPATIBILITY_AND_STOP",
        "inputs": {
            "approved_prior_request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": PRIOR_REQUEST_SHA256,
            },
            "consumed_request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": consumed_request_sha256,
            },
            "readiness_review": {
                "path": str(READINESS_PATH.relative_to(ROOT)),
                "sha256": READINESS_SHA256,
            },
            "contract_review": {
                "path": str(CONTRACT_PATH.relative_to(ROOT)),
                "sha256": CONTRACT_SHA256,
                "review_sha256": CONTRACT_SELF_SHA256,
            },
            "card_data": {
                "path": str(CARD_DATA_PATH.relative_to(ROOT)),
                "sha256": CARD_DATA_SHA256,
            },
        },
        "transfer": {
            "new_files_downloaded": 2,
            "new_bytes_downloaded": 832_877,
            "new_replay_sha256": [FIRST_REPLAY_SHA256, SECOND_REPLAY_SHA256],
            "exact_byte_cap_met": True,
            "unexpected_files": 0,
            "overwrite_used": False,
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded_after_named_files": 0,
            "raw_replay_body_exports": 0,
            "training_label_exports": 0,
            "optimizer_steps": 0,
            "training": False,
            "external_compute": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "teacher": {
            "team_id": 16_374_395,
            "team_name": "Majkel1337",
            "submission_id": 55_186_239,
            "live_rank_at_readiness_refresh": 1,
            "live_score_at_readiness_refresh": rank_1.get("score"),
            "score_is_snapshot_only": True,
            "same_exact_public_submission_across_episodes": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_identity_bound_by_public_metadata": True,
            "opposite_player_slots": True,
            "both_terminal_results_are_teacher_wins": True,
        },
        "episodes": episodes,
        "consistency": {
            "same_schema_version": True,
            "same_environment_identity": True,
            "same_module_version": False,
            "module_versions": module_versions,
            "module_transition_observed": "1.32.2_TO_1.32.3",
            "exact_teacher_deck_match": True,
            "teacher_deck_multiset_sha256": deck_hashes[0],
            "teacher_archetype_context_label": archetypes[0],
            "current_asset_deck_construction_compatibility": "PASS",
            "both_replay_action_alignment": "PASS",
            "combined_all_player_active_selection_requests": all_player_active,
            "combined_teacher_active_selection_requests": teacher_active,
            "combined_teacher_forced_singleton_requests": teacher_forced,
            "combined_teacher_policy_loss_targets_if_later_authorized": teacher_policy_targets,
        },
        "qualification": {
            "current_rank_1_source_identity_qualified": True,
            "same_submission_identity_qualified": True,
            "exact_deck_consistency_qualified": True,
            "current_asset_deck_construction_compatibility_qualified": True,
            "action_aligned_supervision_available": True,
            "same_module_version_qualified": False,
            "mixed_module_transition_reviewed": True,
            "both_modules_action_contract_compatible": True,
            "opposite_teacher_seats_qualified": True,
            "both_teacher_wins_qualified": True,
            "contract_review_passed": True,
            "corpus_promotion_authorized": False,
            "label_generation_authorized": False,
            "optimizer_steps_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "authorization": {
            "exact_replay_transfer_authorization_consumed": True,
            "further_replay_transfer_authorized": False,
            "agent_logs_authorized": False,
            "raw_exports_authorized": False,
            "label_generation_authorized": False,
            "optimizer_steps_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
            "git_commit_authorized": False,
            "git_push_authorized": False,
        },
        "next_action": "STOP_AFTER_CONTRACT_REVIEW_CORPUS_PROMOTION_BC_CANARY_AND_TRAINING_REQUIRE_NEW_EXPLICIT_APPROVAL",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = base.self_hash(report, "review_sha256")
    return report


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main() -> None:
    current_sha = base.sha256_file(REQUEST_PATH)
    current_request = base.load_json(REQUEST_PATH)
    if current_sha == PRIOR_REQUEST_SHA256:
        consumed_request = build_consumed_request(current_request)
        consumed_bytes = file_bytes(consumed_request)
        consumed_sha = hashlib.sha256(consumed_bytes).hexdigest()
        report = build_report(consumed_request, consumed_sha)
        report_bytes = file_bytes(report)
        write_atomic(REQUEST_PATH, consumed_bytes)
        write_atomic(OUTPUT_PATH, report_bytes)
        mode = "FINALIZED"
    else:
        validate_consumed_request(current_request)
        consumed_sha = current_sha
        report = build_report(current_request, consumed_sha)
        report_bytes = file_bytes(report)
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_bytes() != report_bytes:
            raise ValueError("existing Majkel review differs from deterministic rebuild")
        mode = "VERIFIED_IDEMPOTENT"

    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": mode,
                "decision": report["decision"],
                "consumed_request_sha256": consumed_sha,
                "review_sha256": report["review_sha256"],
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "transfer": report["transfer"],
                "consistency": report["consistency"],
                "qualification": report["qualification"],
                "next_action": report["next_action"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
