from __future__ import annotations

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
REQUEST_PATH = ROOT / "configs/e01_flg_gold_teacher_probe_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-019_E01_LIVE_GOLD_TEACHER_REFRESH.md"
SNAPSHOT_PATH = ROOT / "reports/artifacts/raw/e01-live-gold-refresh-v1.json"
CONTRACT_PATH = ROOT / "reports/artifacts/e01-flg-gold-teacher-contract-review-v1.json"
SUPERSEDED_REQUEST_PATH = ROOT / "configs/e01_luca_screening_expansion_request_v1.json"
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
FIRST_REPLAY_PATH = ROOT / "private/g3/e01/flg-gold-teacher-probe-v1/88302734.json"
SECOND_REPLAY_PATH = ROOT / "private/g3/e01/flg-gold-teacher-probe-v1/88333037.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json"

EXPECTED = {
    "request": "b1b0b81014fddeea8c5bb9d5be41a61ea538e1a3723eb64a246c87668c49b349",
    "authorized_request": "b1cb07cace93137c33dde150d6177d38bc7edce9de3c895f6268ee31b4bd1dea",
    "decision": "111fcc2e740d27aa718ead66be186c82f4f282103f2623441010e604b0a99b5c",
    "snapshot": "410b137a7ed4052111d6e16c373fbdc1b1ae484de4ad152a06420981c0870120",
    "contract": "bbe3368311d27abc11fe9c2e7264076ae4997ead9ff2f026fb1df9b78b79e045",
    "contract_self": "0e201c36c59fb8bc188a05f26e0748e95e9310262e94f51f250c814c38663775",
    "superseded_request": "c293268607ce0fc8762d543508bf2c798087ca9583cec05e3031a1906fc26962",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "first_replay": "30a97dfb6bbfe65b224011103b215c7e2ec946ad1cd977cc82a88b1232444452",
    "second_replay": "5b6b330d543037e561a889fe76baaf84d427019b0fc0523080045a6abc5214d6",
    "teacher_deck": "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    ace_spec = sum(
        cards[value]["Rule"] == "ACE SPEC" for value in deck if value in cards
    )
    ex_names = Counter(
        cards[value]["Card Name"]
        for value in deck
        if value in cards and cards[value]["Card Name"].lower().endswith(" ex")
    )
    archetype = (
        sorted(ex_names.items(), key=lambda item: (-item[1], item[0]))[0][0]
        if ex_names
        else "non-ex or unclassified archetype"
    )
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
        "archetype_context_label": archetype,
        "archetype_context_basis": "most frequent Pokemon ex card name",
        "raw_card_list_exported": False,
    }


def inspect_replay(
    path: Path,
    *,
    expected_episode_id: int,
    expected_bytes: int,
    expected_sha256: str,
    teacher_player_index: int,
    expected_reward: int,
) -> dict[str, Any]:
    require_hash(path, expected_sha256)
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"byte count differs for {path}")
    replay = load_json(path)
    if (
        replay.get("schema_version") != 1
        or replay.get("name") != "cabt"
        or replay.get("version") != "1.0.0"
    ):
        raise ValueError("replay schema or environment differs")
    info = replay.get("info")
    if not isinstance(info, Mapping) or info.get("EpisodeId") != expected_episode_id:
        raise ValueError("episode identity differs")
    if replay.get("statuses") != ["DONE", "DONE"]:
        raise ValueError("terminal statuses differ")
    rewards = replay.get("rewards")
    if not isinstance(rewards, list) or rewards[teacher_player_index] != expected_reward:
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
                _validate_record(
                    record, f"{path.name}.steps[{step_index}][{player_index}]"
                )
                for player_index, record in enumerate(step)
            ]
        )
    deck_actions: list[list[int]] = []
    for player_index, record in enumerate(parsed[1]):
        action = _validate_action(record.get("action"), f"deck[{player_index}]")
        if len(action) != 60:
            raise ValueError("initial deck action is not 60 cards")
        deck_actions.append(action)

    active_requests = 0
    nonempty = 0
    empty = 0
    maximum_options = 0
    maximum_selection = 0
    active_by_player: Counter[int] = Counter()
    for step_index in range(2, len(parsed)):
        for player_index, current in enumerate(parsed[step_index]):
            action = _validate_action(
                current.get("action"), f"action[{step_index}][{player_index}]"
            )
            previous = parsed[step_index - 1][player_index]
            if previous.get("status") != "ACTIVE":
                if action:
                    raise ValueError("action occurs after inactive record")
                continue
            request = _selection_request(
                previous, f"previous[{step_index - 1}][{player_index}]"
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
            active_requests += 1
            active_by_player[player_index] += 1
            nonempty += int(bool(action))
            empty += int(not action)
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
        agent_names[teacher_player_index] != "flg"
        or team_names[teacher_player_index] != "flg"
    ):
        raise ValueError("flg player binding differs")

    cards = card_table()
    decks = [deck_construction(action, cards) for action in deck_actions]
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
            "teacher_active_selection_requests": active_by_player[
                teacher_player_index
            ],
            "nonempty_lagged_selections": nonempty,
            "empty_lagged_selections": empty,
            "maximum_option_count": maximum_options,
            "maximum_selection_count": maximum_selection,
        },
    }


def build_report() -> dict[str, Any]:
    for path, expected in (
        (REQUEST_PATH, EXPECTED["request"]),
        (DECISION_PATH, EXPECTED["decision"]),
        (SNAPSHOT_PATH, EXPECTED["snapshot"]),
        (CONTRACT_PATH, EXPECTED["contract"]),
        (SUPERSEDED_REQUEST_PATH, EXPECTED["superseded_request"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    snapshot = load_json(SNAPSHOT_PATH)
    contract = load_json(CONTRACT_PATH)
    superseded = load_json(SUPERSEDED_REQUEST_PATH)
    if contract.get("review_sha256") != EXPECTED["contract_self"]:
        raise ValueError("contract review self hash differs")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
    ):
        raise ValueError("request is not consumed")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution is missing")
    if approval.get("authorized_request_sha256") != EXPECTED["authorized_request"]:
        raise ValueError("authorized request hash differs")
    expected_execution = {
        "files_downloaded": 2,
        "bytes_downloaded": 3_996_398,
        "downloaded_files": [
            {
                "path": "private/g3/e01/flg-gold-teacher-probe-v1/88302734.json",
                "bytes": 624_407,
                "sha256": EXPECTED["first_replay"],
            },
            {
                "path": "private/g3/e01/flg-gold-teacher-probe-v1/88333037.json",
                "bytes": 3_371_991,
                "sha256": EXPECTED["second_replay"],
            },
        ],
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
    }
    if execution != expected_execution:
        raise ValueError("execution boundary differs")
    if (
        superseded.get("status") != "READY_UNAUTHORIZED"
        or superseded.get("authorized") is not False
        or (ROOT / str(superseded.get("output_directory"))).exists()
    ):
        raise ValueError("superseded Luca request was changed or executed")
    quarantine = FIRST_REPLAY_PATH.parent
    expected_names = ["88302734.json", "88333037.json"]
    if sorted(path.name for path in quarantine.iterdir() if path.is_file()) != expected_names:
        raise ValueError("flg quarantine contains unexpected files")

    first = inspect_replay(
        FIRST_REPLAY_PATH,
        expected_episode_id=88_302_734,
        expected_bytes=624_407,
        expected_sha256=EXPECTED["first_replay"],
        teacher_player_index=1,
        expected_reward=-1,
    )
    second = inspect_replay(
        SECOND_REPLAY_PATH,
        expected_episode_id=88_333_037,
        expected_bytes=3_371_991,
        expected_sha256=EXPECTED["second_replay"],
        teacher_player_index=0,
        expected_reward=1,
    )
    selection = snapshot.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("live selection is missing")
    if (
        selection.get("teacher_live_rank") != 1
        or selection.get("teacher_team_id") != 16_380_946
        or selection.get("teacher_submission_id") != 55_004_495
        or selection.get("teacher_submission_public_score") != 1244.2
        or selection.get("selected_total_bytes") != 3_996_398
    ):
        raise ValueError("live teacher binding differs")

    module_versions = sorted({first["module_version"], second["module_version"]})
    deck_hashes = sorted(
        {
            first["teacher_deck"]["multiset_sha256"],
            second["teacher_deck"]["multiset_sha256"],
        }
    )
    archetypes = sorted(
        {
            first["teacher_deck"]["archetype_context_label"],
            second["teacher_deck"]["archetype_context_label"],
        }
    )
    teacher_decisions = (
        first["action_alignment"]["teacher_active_selection_requests"]
        + second["action_alignment"]["teacher_active_selection_requests"]
    )
    combined_requests = (
        first["action_alignment"]["active_selection_requests"]
        + second["action_alignment"]["active_selection_requests"]
    )
    if module_versions != ["1.32.2"]:
        raise ValueError("current rank-1 module versions differ")
    if deck_hashes != [EXPECTED["teacher_deck"]]:
        raise ValueError("current rank-1 exact deck differs")
    if archetypes != ["Dragapult ex"]:
        raise ValueError("current rank-1 archetype context differs")
    if teacher_decisions != 94 or combined_requests != 165:
        raise ValueError("current rank-1 aggregate decisions differ")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-flg-gold-teacher-probe-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json",
        "producer": "scripts/e01_flg_teacher_probe_review.py",
        "reviewed_decision": "DEC-019",
        "status": "PASS",
        "decision": "ACCEPT_CURRENT_RANK_1_DRAGAPULT_TEACHER_DECK_AND_ACTION_CONSISTENCY_SCREENING_FLOOR_BLOCKED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": EXPECTED["decision"]},
            "live_refresh": {"path": str(SNAPSHOT_PATH.relative_to(ROOT)), "sha256": EXPECTED["snapshot"]},
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
                "authorized_request_sha256": EXPECTED["authorized_request"],
                "authorization_consumed": True,
            },
            "contract_review": {
                "path": str(CONTRACT_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["contract"],
                "review_sha256": EXPECTED["contract_self"],
            },
            "card_data": {"path": str(CARD_DATA_PATH.relative_to(ROOT)), "sha256": EXPECTED["card_data"]},
            "superseded_request": {
                "path": str(SUPERSEDED_REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["superseded_request"],
                "executed": False,
            },
        },
        "transfer": {
            "new_files_downloaded": 2,
            "new_bytes_downloaded": 3_996_398,
            "new_replay_sha256": [EXPECTED["first_replay"], EXPECTED["second_replay"]],
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
        },
        "teacher": {
            "team_id": 16_380_946,
            "team_name": "flg",
            "submission_id": 55_004_495,
            "live_rank_at_refresh": 1,
            "live_team_score_at_refresh": selection.get("teacher_live_team_score"),
            "submission_public_score": 1244.2,
            "dataset_episode_count": 131,
            "strength_basis": "CURRENT_LIVE_RANK_1_AND_ACTIVE_SUBMISSION_PUBLIC_SCORE",
            "same_exact_public_submission_across_episodes": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_ids_bound_by_public_metadata": True,
            "opposite_player_slots": True,
            "opposite_terminal_results": True,
        },
        "episodes": [first, second],
        "consistency": {
            "same_schema_version": True,
            "same_environment_identity": True,
            "same_module_version": True,
            "module_versions": module_versions,
            "exact_teacher_deck_match": True,
            "teacher_deck_multiset_sha256": EXPECTED["teacher_deck"],
            "teacher_archetype_context_label": "Dragapult ex",
            "community_grimmsnarl_claim_matches_recovered_leader_deck": False,
            "current_asset_deck_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "both_replay_action_alignment": "PASS",
            "combined_all_player_active_selection_requests": combined_requests,
            "combined_teacher_active_selection_requests": teacher_decisions,
            "screening_minimum_teacher_decisions": 5000,
            "screening_teacher_decision_shortfall": 5000 - teacher_decisions,
        },
        "qualification": {
            "current_rank_1_strength_metadata_qualified": True,
            "teacher_strength_qualified": True,
            "same_submission_identity_qualified": True,
            "exact_deck_consistency_qualified": True,
            "current_asset_deck_construction_compatibility_qualified": True,
            "action_aligned_supervision_available": True,
            "same_module_version_qualified": True,
            "policy_behavior_contract_consistency_qualified": True,
            "exact_historical_deck_legality_qualified": False,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "PREPARE_BOUNDED_BALANCED_FLG_DRAGAPULT_CALIBRATION_REQUEST_WITH_NEW_APPROVAL",
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
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
