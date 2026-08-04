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
REQUEST_PATH = ROOT / "configs/e01_luca_gold_teacher_probe_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-016_E01_LUCA_GOLD_TEACHER_PROBE.md"
COVERAGE_PATH = ROOT / "reports/artifacts/raw/e01-gold-teacher-coverage-v1.json"
PRIOR_REVIEW_PATH = ROOT / "reports/artifacts/e01-same-submission-consistency-review-v1.json"
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
FIRST_REPLAY_PATH = ROOT / "private/g3/e01/luca-gold-teacher-probe-v1/87731214.json"
SECOND_REPLAY_PATH = ROOT / "private/g3/e01/luca-gold-teacher-probe-v1/87615736.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json"

EXPECTED = {
    "request": "b70efe6228d08f78c104e75c3007d4e1b99c747223d05d1d14e9808f975146a2",
    "authorized_request": "8c1c6eac94cd0dc18ea29117c62255c8871df994e280033063c306f0a58aacf4",
    "decision": "e52bf2d91a504db6e9828de3190aa652dde59c46aa93b0035912e675d17792f8",
    "coverage": "f73d67ea3aa8450f712ab046f35a97e887d1e287813c9968efbb33f8fd06acb7",
    "prior_review": "4ec60a2a4dffeb9ffae898fad8ae44a0e77c0c5e51a50e155df21b90ae665966",
    "prior_review_self": "dae9bd135831b745d7050b49872b7f1404bbea45ab49b7cd20195f74885862bb",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "first_replay": "523c74d0e21d8ca7a687a835c178e947844614a95ee00479c0efe6f5dc31125c",
    "second_replay": "b10f5b2824c7db1b6a3f9c9f1e782da9a0e366595cd06ddc5e86e78d6ce23876",
    "luca_deck": "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd",
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
    expected_episode_id: int,
    expected_bytes: int,
    expected_sha256: str,
    luca_player_index: int,
    expected_module_version: str,
) -> dict[str, Any]:
    require_hash(path, expected_sha256)
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"byte count differs for {path}")
    replay = load_json(path)
    if (
        replay.get("schema_version") != 1
        or replay.get("module_version") != expected_module_version
        or replay.get("name") != "cabt"
        or replay.get("version") != "1.0.0"
    ):
        raise ValueError("replay schema, module, or environment differs")
    info = replay.get("info")
    if not isinstance(info, Mapping) or info.get("EpisodeId") != expected_episode_id:
        raise ValueError("episode identity differs")
    if replay.get("statuses") != ["DONE", "DONE"] or replay.get("rewards") != [1, -1]:
        raise ValueError("terminal result differs")
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
        agent_names[luca_player_index] != "Luca"
        or team_names[luca_player_index] != "Luca"
    ):
        raise ValueError("Luca player binding differs")

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
        "rewards": replay.get("rewards"),
        "luca_player_index": luca_player_index,
        "luca_reward": replay["rewards"][luca_player_index],
        "luca_deck": decks[luca_player_index],
        "opponent_deck_multiset_sha256": decks[1 - luca_player_index][
            "multiset_sha256"
        ],
        "action_alignment": {
            "status": "PASS",
            "active_selection_requests": active_requests,
            "active_requests_by_player": {
                str(key): value for key, value in sorted(active_by_player.items())
            },
            "luca_active_selection_requests": active_by_player[luca_player_index],
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
        (COVERAGE_PATH, EXPECTED["coverage"]),
        (PRIOR_REVIEW_PATH, EXPECTED["prior_review"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    coverage = load_json(COVERAGE_PATH)
    prior_review = load_json(PRIOR_REVIEW_PATH)
    if prior_review.get("review_sha256") != EXPECTED["prior_review_self"]:
        raise ValueError("prior review self hash differs")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
    ):
        raise ValueError("request is not consumed")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution record is missing")
    if approval.get("authorized_request_sha256") != EXPECTED["authorized_request"]:
        raise ValueError("authorized request hash differs")
    expected_execution = {
        "files_downloaded": 2,
        "bytes_downloaded": 1313221,
        "downloaded_files": [
            {
                "path": "private/g3/e01/luca-gold-teacher-probe-v1/87731214.json",
                "bytes": 574428,
                "sha256": EXPECTED["first_replay"],
            },
            {
                "path": "private/g3/e01/luca-gold-teacher-probe-v1/87615736.json",
                "bytes": 738793,
                "sha256": EXPECTED["second_replay"],
            },
        ],
        "agent_logs_downloaded": 0,
        "additional_replays_downloaded_after_named_files": 0,
        "raw_replay_body_exports": 0,
        "raw_step_exports": 0,
        "action_sequence_exports": 0,
        "observation_exports": 0,
        "training_label_exports": 0,
        "optimizer_steps": 0,
        "external_compute": False,
        "training": False,
        "submission": False,
    }
    if execution != expected_execution:
        raise ValueError("execution boundary differs")
    quarantine = FIRST_REPLAY_PATH.parent
    expected_names = ["87615736.json", "87731214.json"]
    if sorted(path.name for path in quarantine.iterdir() if path.is_file()) != expected_names:
        raise ValueError("Luca quarantine contains unexpected files")

    first = inspect_replay(
        FIRST_REPLAY_PATH,
        expected_episode_id=87731214,
        expected_bytes=574428,
        expected_sha256=EXPECTED["first_replay"],
        luca_player_index=1,
        expected_module_version="1.32.2",
    )
    second = inspect_replay(
        SECOND_REPLAY_PATH,
        expected_episode_id=87615736,
        expected_bytes=738793,
        expected_sha256=EXPECTED["second_replay"],
        luca_player_index=0,
        expected_module_version="1.32.1",
    )
    teacher = request.get("teacher")
    if not isinstance(teacher, Mapping):
        raise ValueError("teacher binding is missing")
    if (
        teacher.get("submission_id") != 54863653
        or teacher.get("team_id") != 16448747
        or teacher.get("team_name") != "Luca"
        or teacher.get("leaderboard_rank") != 2
        or teacher.get("submission_public_score") != 1180.9
        or teacher.get("dataset_episode_count") != 357
    ):
        raise ValueError("teacher binding differs")
    coverage_candidates = coverage.get("covered_top_10")
    coverage_selection = coverage.get("selection")
    if (
        not isinstance(coverage_candidates, list)
        or not isinstance(coverage_selection, Mapping)
        or coverage_selection.get("teacher_submission_id") != 54863653
        or coverage_selection.get("teacher_dataset_episode_count") != 357
        or not any(
            isinstance(item, Mapping)
            and item.get("selected_active_submission_id") == 54863653
            and item.get("dataset_episode_count") == 357
            for item in coverage_candidates
        )
    ):
        raise ValueError("coverage evidence does not bind Luca")

    first_hash = first["luca_deck"]["multiset_sha256"]
    second_hash = second["luca_deck"]["multiset_sha256"]
    if first_hash != EXPECTED["luca_deck"] or second_hash != EXPECTED["luca_deck"]:
        raise ValueError("Luca exact deck differs across episodes")
    teacher_decisions = (
        first["action_alignment"]["luca_active_selection_requests"]
        + second["action_alignment"]["luca_active_selection_requests"]
    )
    combined_requests = (
        first["action_alignment"]["active_selection_requests"]
        + second["action_alignment"]["active_selection_requests"]
    )
    if teacher_decisions != 37 or combined_requests != 61:
        raise ValueError("aggregate decision counts differ")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-luca-gold-teacher-probe-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json",
        "producer": "scripts/e01_luca_teacher_probe_review.py",
        "reviewed_decision": "DEC-016",
        "status": "PASS",
        "decision": "ACCEPT_GOLD_REGION_TEACHER_DECK_CONSISTENCY_MODULE_BOUNDARY_SCREENING_FLOOR_BLOCKED",
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
                "authorized_request_sha256": EXPECTED["authorized_request"],
                "authorization_consumed": True,
            },
            "coverage": {
                "path": str(COVERAGE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["coverage"],
            },
            "prior_consistency_review": {
                "path": str(PRIOR_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["prior_review"],
                "review_sha256": EXPECTED["prior_review_self"],
            },
            "card_data": {
                "path": str(CARD_DATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["card_data"],
            },
        },
        "transfer": {
            "new_files_downloaded": 2,
            "new_bytes_downloaded": 1313221,
            "new_replay_sha256": [EXPECTED["first_replay"], EXPECTED["second_replay"]],
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded_after_named_files": 0,
            "overwrite_used": False,
            "raw_replay_body_exports": 0,
            "raw_step_exports": 0,
            "action_sequence_exports": 0,
            "observation_exports": 0,
            "training_label_exports": 0,
            "optimizer_steps": 0,
        },
        "teacher": {
            "submission_id": 54863653,
            "team_id": 16448747,
            "team_name": "Luca",
            "leaderboard_rank": 2,
            "leaderboard_team_score": 1190.4,
            "submission_public_score": 1180.9,
            "dataset_episode_count": 357,
            "dataset_seat_0_count": 181,
            "dataset_seat_1_count": 176,
            "strength_basis": "CURRENT_PUBLIC_GOLD_REGION_SCORE_AND_RANK",
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
            "same_module_version": False,
            "module_versions": ["1.32.2", "1.32.1"],
            "exact_luca_deck_match": True,
            "luca_deck_multiset_sha256": EXPECTED["luca_deck"],
            "current_asset_deck_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "both_replay_action_alignment": "PASS",
            "combined_all_player_active_selection_requests": combined_requests,
            "combined_luca_active_selection_requests": teacher_decisions,
            "screening_minimum_teacher_decisions": 5000,
            "screening_teacher_decision_shortfall": 5000 - teacher_decisions,
        },
        "qualification": {
            "gold_region_strength_metadata_qualified": True,
            "teacher_strength_qualified": True,
            "same_submission_identity_qualified": True,
            "exact_deck_consistency_qualified": True,
            "current_asset_deck_construction_compatibility_qualified": True,
            "action_aligned_supervision_available": True,
            "same_module_version_qualified": False,
            "policy_behavior_consistency_qualified": False,
            "exact_historical_deck_legality_qualified": False,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "PREPARE_BOUNDED_SAME_VERSION_LUCA_SCREENING_BATCH_REQUEST_WITH_NEW_APPROVAL",
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
