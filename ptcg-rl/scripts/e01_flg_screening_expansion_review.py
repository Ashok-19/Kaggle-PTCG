from __future__ import annotations

import copy
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.replay.acquisition import (
    _integer,
    _resolves_against_options,
    _selection_request,
    _validate_action,
    _validate_record,
)

ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / "configs/e01_flg_dragapult_screening_expansion_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-021_E01_FLG_DRAGAPULT_SCREENING_EXPANSION.md"
CANDIDATE_PATH = (
    ROOT
    / "reports/artifacts/raw/e01-flg-dragapult-screening-expansion-candidates-v1.json"
)
CALIBRATION_REVIEW_PATH = (
    ROOT / "reports/artifacts/e01-flg-dragapult-calibration-review-v1.json"
)
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
OUTPUT_PATH = (
    ROOT / "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json"
)
QUARANTINE = ROOT / "private/g3/e01/flg-dragapult-screening-expansion-v1"

EXPECTED = {
    "request": "f16d155948db791e355f561901daf2e4f2ef886d68d638a6fdce4c2d31939583",
    "authorized_payload": "72cc26257d28af61649d664103931effccbc9dfe65de0fcc66cf92fdfb6f6735",
    "authorized_file": "c29b740483d28f34701416ee13f3da5d05c134504c0b9895089bc33aa9dc40f5",
    "prior_request": "1c9a5b893af29f19dad214b3377919f996b48b62145e5401f189a6dc231ac559",
    "decision": "3533c0c1b099193ab8f02eee54e60cd89dedab1399eb2e33668041e4c103d23c",
    "candidate": "06afd9c1aaafe5fbf207ad4fd07bf9852fa1097c29ab8aaa9a862124731f1e37",
    "calibration_review": "719c08aac0bfc9d8c66c163cd85cea45cd8af8107a946c006e356ed9df248038",
    "calibration_review_self": "be2704b2f09126a1b77340e25971c4231c2f515e52ca4e41e3c9d32b8daa7282",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "deck": "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_value_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def authorization_payload_hash(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value))
    approval = payload.get("approval")
    if isinstance(approval, dict):
        approval.pop("authorized_request_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain an object")
    return value


def require_hash(path: Path, expected: str) -> None:
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(f"hash differs for {path}: {observed}")


def card_table() -> dict[int, dict[str, str]]:
    require_hash(CARD_DATA_PATH, EXPECTED["card_data"])
    rows: dict[int, dict[str, str]] = {}
    with CARD_DATA_PATH.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows[int(row["Card ID"])] = dict(row)
    return rows


def deck_construction(
    deck: list[int], cards: Mapping[int, Mapping[str, str]]
) -> dict[str, Any]:
    if len(deck) != 60 or any(
        isinstance(value, bool) or not isinstance(value, int) for value in deck
    ):
        raise ValueError("deck action is not exactly 60 integer card ids")
    missing = sorted({value for value in deck if value not in cards})
    names = Counter(cards[value]["Card Name"] for value in deck if value in cards)
    violations = 0
    for name, count in names.items():
        if count <= 4:
            continue
        matching = [
            cards[value]
            for value in deck
            if value in cards and cards[value]["Card Name"] == name
        ]
        if not matching or any(
            row["Stage (Pokémon)/Type (Energy and Trainer)"] != "Basic Energy"
            for row in matching
        ):
            violations += 1
    basic_pokemon = sum(
        cards[value]["Stage (Pokémon)/Type (Energy and Trainer)"] == "Basic Pokémon"
        for value in deck
        if value in cards
    )
    ace_spec = sum(cards[value]["Rule"] == "ACE SPEC" for value in deck if value in cards)
    passed = not missing and violations == 0 and basic_pokemon > 0 and ace_spec <= 1
    return {
        "cards": 60,
        "distinct_card_ids": len(set(deck)),
        "multiset_sha256": canonical_value_hash(sorted(deck)),
        "missing_card_ids": len(missing),
        "non_basic_energy_name_limit_violations": violations,
        "basic_pokemon_cards": basic_pokemon,
        "ace_spec_cards": ace_spec,
        "current_asset_construction_checks": "PASS" if passed else "FAIL",
    }


def inspect_replay(
    path: Path,
    *,
    item: Mapping[str, Any],
    expected_sha256: str,
    cards: Mapping[int, Mapping[str, str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "episode_id": int(item["episode_id"]),
        "stratum": str(item["stratum"]),
        "teacher_player_index": int(item["teacher_player_index"]),
        "teacher_reward": int(item["teacher_reward"]),
        "file": {
            "path": str(path.relative_to(ROOT)),
            "bytes": int(item["declared_bytes"]),
            "sha256": expected_sha256,
        },
        "qualification_status": "REJECTED",
        "rejection_reasons": [],
        "counted_teacher_active_selection_requests": 0,
        "counted_all_player_active_selection_requests": 0,
    }
    reasons: list[str] = result["rejection_reasons"]
    try:
        require_hash(path, expected_sha256)
        if path.stat().st_size != int(item["declared_bytes"]):
            raise ValueError("byte count differs")
        replay = load_json(path)
        if replay.get("schema_version") != 1:
            reasons.append("SCHEMA_VERSION_MISMATCH")
        if replay.get("module_version") != "1.32.2":
            reasons.append("MODULE_VERSION_MISMATCH")
        if replay.get("name") != "cabt":
            reasons.append("ENVIRONMENT_NAME_MISMATCH")
        if replay.get("version") != "1.0.0":
            reasons.append("ENVIRONMENT_VERSION_MISMATCH")
        info = replay.get("info")
        if not isinstance(info, Mapping) or info.get("EpisodeId") != int(
            item["episode_id"]
        ):
            reasons.append("EPISODE_IDENTITY_MISMATCH")
            info = {} if not isinstance(info, Mapping) else info
        teacher_index = int(item["teacher_player_index"])
        teacher_reward = int(item["teacher_reward"])
        rewards = replay.get("rewards")
        if (
            replay.get("statuses") != ["DONE", "DONE"]
            or not isinstance(rewards, list)
            or len(rewards) != 2
            or rewards[teacher_index] != teacher_reward
            or rewards[1 - teacher_index] != -teacher_reward
        ):
            reasons.append("TERMINAL_BINDING_MISMATCH")
        agents = info.get("Agents") if isinstance(info, Mapping) else None
        team_names = info.get("TeamNames") if isinstance(info, Mapping) else None
        agent_names = (
            [agent.get("Name") if isinstance(agent, Mapping) else None for agent in agents]
            if isinstance(agents, list)
            else []
        )
        if (
            len(agent_names) != 2
            or not isinstance(team_names, list)
            or len(team_names) != 2
            or agent_names[teacher_index] != "flg"
            or team_names[teacher_index] != "flg"
        ):
            reasons.append("TEACHER_TEAM_BINDING_MISMATCH")

        steps = replay.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            raise ValueError("steps are missing")
        parsed: list[list[Mapping[str, Any]]] = []
        for step_index, step in enumerate(steps):
            if not isinstance(step, list) or len(step) != 2:
                raise ValueError(f"step {step_index} does not contain two players")
            parsed.append(
                [
                    _validate_record(
                        record, f"{path.name}.steps[{step_index}][{player_index}]"
                    )
                    for player_index, record in enumerate(step)
                ]
            )
        decks: list[list[int]] = []
        for player_index, record in enumerate(parsed[1]):
            action = _validate_action(
                record.get("action"), f"{path.name}.deck[{player_index}]"
            )
            if len(action) != 60:
                raise ValueError("initial deck action is not 60 cards")
            decks.append(action)

        all_requests = 0
        teacher_requests = 0
        nonempty = 0
        empty = 0
        maximum_options = 0
        maximum_selection = 0
        for step_index in range(2, len(parsed)):
            for player_index, current in enumerate(parsed[step_index]):
                action = _validate_action(
                    current.get("action"),
                    f"{path.name}.action[{step_index}][{player_index}]",
                )
                previous = parsed[step_index - 1][player_index]
                if previous.get("status") != "ACTIVE":
                    if action:
                        raise ValueError("action occurs after inactive record")
                    continue
                request = _selection_request(
                    previous,
                    f"{path.name}.previous[{step_index - 1}][{player_index}]",
                )
                if request is None:
                    if action:
                        raise ValueError("action occurs after missing request")
                    continue
                minimum = _integer(request.get("minCount"), "minimum")
                maximum = _integer(request.get("maxCount"), "maximum")
                options = request.get("option")
                if not isinstance(options, list) or any(
                    not isinstance(option, Mapping) for option in options
                ):
                    raise ValueError("request options differ")
                if not minimum <= len(action) <= maximum:
                    raise ValueError("selection count is outside request bounds")
                if not _resolves_against_options(action, options):
                    raise ValueError("action does not resolve against request options")
                all_requests += 1
                teacher_requests += int(player_index == teacher_index)
                nonempty += int(bool(action))
                empty += int(not action)
                maximum_options = max(maximum_options, len(options))
                maximum_selection = max(maximum_selection, len(action))

        deck = deck_construction(decks[teacher_index], cards)
        if deck["multiset_sha256"] != EXPECTED["deck"]:
            reasons.append("EXACT_DECK_HASH_MISMATCH")
        if deck["current_asset_construction_checks"] != "PASS":
            reasons.append("CURRENT_ASSET_CONSTRUCTION_FAILURE")
        result.update(
            {
                "schema_version": replay.get("schema_version"),
                "module_version": replay.get("module_version"),
                "environment_name": replay.get("name"),
                "environment_version": replay.get("version"),
                "steps": len(steps),
                "teacher_deck": deck,
                "action_alignment": {
                    "status": "PASS",
                    "active_selection_requests": all_requests,
                    "teacher_active_selection_requests": teacher_requests,
                    "nonempty_lagged_selections": nonempty,
                    "empty_lagged_selections": empty,
                    "maximum_option_count": maximum_options,
                    "maximum_selection_count": maximum_selection,
                },
            }
        )
        if not reasons:
            result["qualification_status"] = "QUALIFIED"
            result["counted_teacher_active_selection_requests"] = teacher_requests
            result["counted_all_player_active_selection_requests"] = all_requests
    except Exception as exc:  # fail closed and preserve the file-level reason
        reasons.append(f"REVIEW_EXCEPTION:{type(exc).__name__}:{exc}")
    return result


def build_report() -> dict[str, Any]:
    for path, expected in (
        (REQUEST_PATH, EXPECTED["request"]),
        (DECISION_PATH, EXPECTED["decision"]),
        (CANDIDATE_PATH, EXPECTED["candidate"]),
        (CALIBRATION_REVIEW_PATH, EXPECTED["calibration_review"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    candidate = load_json(CANDIDATE_PATH)
    calibration = load_json(CALIBRATION_REVIEW_PATH)
    if calibration.get("review_sha256") != EXPECTED["calibration_review_self"]:
        raise ValueError("calibration review self hash differs")
    if (
        calibration.get("status") != "PASS"
        or calibration.get("density", {}).get("combined_observed_teacher_decisions")
        != 1386
        or calibration.get("consistency", {}).get("teacher_deck_multiset_sha256")
        != EXPECTED["deck"]
    ):
        raise ValueError("completed calibration evidence differs")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("maximum_new_files") != 38
        or request.get("maximum_new_bytes") != 254_237_550
        or request.get("authorization_scope")
        != "CONSUMED_EXACT_38_FILE_FLG_DRAGAPULT_SCREENING_EXPANSION_ONLY"
    ):
        raise ValueError("screening expansion request lifecycle differs")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution record is missing")
    if (
        approval.get("approved_prior_request_sha256") != EXPECTED["prior_request"]
        or approval.get("authorized_request_sha256") != EXPECTED["authorized_payload"]
        or approval.get("authorization_scope")
        != "AUTHORIZED_EXACT_38_FILE_FLG_DRAGAPULT_SCREENING_EXPANSION_ONLY"
        or approval.get("maximum_new_files") != 38
        or approval.get("maximum_new_bytes") != 254_237_550
    ):
        raise ValueError("authorization binding differs")
    if (
        execution.get("files_downloaded") != 38
        or execution.get("bytes_downloaded") != 254_237_550
        or execution.get("agent_logs_downloaded") != 0
        or execution.get("additional_replays_downloaded_after_named_files") != 0
        or execution.get("raw_replay_body_exports") != 0
        or execution.get("raw_step_exports") != 0
        or execution.get("request_exports") != 0
        or execution.get("option_exports") != 0
        or execution.get("observation_exports") != 0
        or execution.get("action_sequence_exports") != 0
        or execution.get("card_list_exports") != 0
        or execution.get("training_label_exports") != 0
        or execution.get("optimizer_steps") != 0
        or execution.get("training") is not False
        or execution.get("external_compute") is not False
        or execution.get("submission") is not False
    ):
        raise ValueError("execution boundary differs")

    episodes = request.get("episodes")
    selected = candidate.get("selection", {}).get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 38 or episodes != selected:
        raise ValueError("request episodes differ from frozen metadata selection")
    if candidate.get("selection", {}).get("selected_bytes") != 254_237_550:
        raise ValueError("candidate selection byte total differs")
    expected_names = sorted(str(item["file_name"]) for item in episodes)
    observed_names = sorted(path.name for path in QUARANTINE.iterdir() if path.is_file())
    if observed_names != expected_names:
        raise ValueError("screening quarantine contains unexpected files")
    execution_files = execution.get("downloaded_files")
    if not isinstance(execution_files, list) or len(execution_files) != 38:
        raise ValueError("downloaded file evidence differs")
    execution_by_name = {Path(str(item["path"])).name: item for item in execution_files}
    if sorted(execution_by_name) != expected_names:
        raise ValueError("downloaded file list differs")

    cards = card_table()
    reviewed: list[dict[str, Any]] = []
    qualified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    selected_strata: Counter[str] = Counter()
    qualified_strata: Counter[str] = Counter()
    all_requests = 0
    teacher_requests = 0
    nonempty = 0
    empty = 0
    maximum_options = 0
    maximum_selection = 0
    for item in episodes:
        file_name = str(item["file_name"])
        selected_strata[str(item["stratum"])] += 1
        execution_item = execution_by_name[file_name]
        if (
            execution_item.get("episode_id") != int(item["episode_id"])
            or execution_item.get("bytes") != int(item["declared_bytes"])
            or execution_item.get("path")
            != f"private/g3/e01/flg-dragapult-screening-expansion-v1/{file_name}"
        ):
            raise ValueError(f"execution file binding differs for {file_name}")
        result = inspect_replay(
            QUARANTINE / file_name,
            item=item,
            expected_sha256=str(execution_item["sha256"]),
            cards=cards,
        )
        reviewed.append(result)
        if result["qualification_status"] == "QUALIFIED":
            qualified.append(result)
            qualified_strata[result["stratum"]] += 1
            alignment = result["action_alignment"]
            all_requests += int(result["counted_all_player_active_selection_requests"])
            teacher_requests += int(result["counted_teacher_active_selection_requests"])
            nonempty += int(alignment["nonempty_lagged_selections"])
            empty += int(alignment["empty_lagged_selections"])
            maximum_options = max(maximum_options, int(alignment["maximum_option_count"]))
            maximum_selection = max(
                maximum_selection, int(alignment["maximum_selection_count"])
            )
        else:
            rejected.append(result)

    prior_decisions = int(
        calibration.get("density", {}).get("combined_observed_teacher_decisions")
    )
    combined_decisions = prior_decisions + teacher_requests
    minimum = 5000
    shortfall = max(0, minimum - combined_decisions)
    minimum_met = combined_decisions >= minimum
    all_files_qualified = len(qualified) == 38
    screening_passed = minimum_met and len(qualified) > 0
    status = "PASS" if screening_passed else "BLOCKED"
    decision = (
        "ACCEPT_CURRENT_RANK_1_DRAGAPULT_SCREENING_FLOOR_MET"
        if screening_passed
        else "ACCEPT_CURRENT_RANK_1_DRAGAPULT_SCREENING_EXPANSION_FLOOR_BLOCKED"
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-flg-dragapult-screening-expansion-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json",
        "producer": "scripts/e01_flg_screening_expansion_review.py",
        "reviewed_decision": "DEC-021",
        "status": status,
        "decision": decision,
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
                "approved_prior_request_sha256": EXPECTED["prior_request"],
                "authorized_payload_sha256": EXPECTED["authorized_payload"],
                "authorized_file_sha256": EXPECTED["authorized_file"],
                "authorization_consumed": True,
            },
            "candidate_metadata": {
                "path": str(CANDIDATE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["candidate"],
            },
            "completed_calibration_review": {
                "path": str(CALIBRATION_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_review"],
                "review_sha256": EXPECTED["calibration_review_self"],
            },
            "card_data": {
                "path": str(CARD_DATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["card_data"],
            },
        },
        "transfer": {
            "new_files_downloaded": 38,
            "new_bytes_downloaded": 254_237_550,
            "downloaded_files": execution_files,
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded_after_named_files": 0,
            "overwrite_used": False,
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
        },
        "teacher": {
            "submission_id": 55_004_495,
            "team_id": 16_380_946,
            "team_name": "flg",
            "live_rank_at_refresh": 1,
            "submission_public_score": 1244.2,
            "archetype_context_label": "Dragapult ex",
            "same_exact_public_submission_across_selected_metadata": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_ids_bound_by_public_metadata": True,
        },
        "episodes": reviewed,
        "screening": {
            "selected_files": 38,
            "selected_bytes": 254_237_550,
            "selected_strata": dict(sorted(selected_strata.items())),
            "qualified_files": len(qualified),
            "qualified_bytes": sum(int(item["file"]["bytes"]) for item in qualified),
            "qualified_strata": dict(sorted(qualified_strata.items())),
            "rejected_files": len(rejected),
            "rejected_episode_ids": [int(item["episode_id"]) for item in rejected],
            "rejection_reasons": dict(
                sorted(
                    Counter(
                        reason
                        for item in rejected
                        for reason in item["rejection_reasons"]
                    ).items()
                )
            ),
            "all_selected_files_qualified": all_files_qualified,
            "required_schema_version": 1,
            "required_module_version": "1.32.2",
            "required_environment_name": "cabt",
            "required_environment_version": "1.0.0",
            "required_deck_multiset_sha256": EXPECTED["deck"],
            "current_asset_deck_construction_compatibility": (
                "PASS" if qualified else "UNAVAILABLE"
            ),
            "qualified_all_player_active_selection_requests": all_requests,
            "qualified_teacher_active_selection_requests": teacher_requests,
            "prior_probe_and_calibration_teacher_decisions": prior_decisions,
            "combined_observed_teacher_decisions": combined_decisions,
            "screening_minimum_teacher_decisions": minimum,
            "screening_teacher_decision_shortfall": shortfall,
            "minimum_5000_teacher_decisions_met": minimum_met,
            "nonempty_lagged_selections": nonempty,
            "empty_lagged_selections": empty,
            "maximum_option_count": maximum_options,
            "maximum_selection_count": maximum_selection,
        },
        "qualification": {
            "current_rank_1_strength_metadata_qualified": True,
            "teacher_strength_qualified": True,
            "same_submission_identity_qualified": True,
            "at_least_one_matching_replay_qualified": len(qualified) > 0,
            "all_selected_replays_qualified": all_files_qualified,
            "exact_deck_consistency_qualified": len(qualified) > 0,
            "current_asset_deck_construction_compatibility_qualified": len(qualified)
            > 0,
            "action_aligned_supervision_available": len(qualified) > 0,
            "same_module_version_qualified": len(qualified) > 0,
            "same_version_replay_contract_consistency_qualified": len(qualified) > 0,
            "policy_behavior_consistency_qualified": len(qualified) > 0,
            "exact_historical_deck_legality_qualified": False,
            "minimum_5000_teacher_decisions_met": minimum_met,
            "e01_screening_gate_passed": screening_passed,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "policy_behavior_consistency_definition": "SAME_PUBLIC_SUBMISSION_ID_MODULE_DECK_AND_VALID_ACTION_ALIGNED_REPLAY_CONTRACT_NOT_IDENTICAL_STATE_ACTION_REPRODUCIBILITY",
        "next_action": (
            "PREPARE_E01_CONFIRMATION_AND_BEHAVIOR_CLONING_AUTHORIZATION_DECISION"
            if screening_passed
            else "REASSESS_MATCHING_REPLAY_COVERAGE_WITH_NEW_APPROVAL"
        ),
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def main() -> None:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)
    print(
        json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "review_sha256": report["review_sha256"],
                "screening": report["screening"],
                "qualification": report["qualification"],
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
