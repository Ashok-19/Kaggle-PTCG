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
REQUEST_PATH = ROOT / "configs/e01_same_submission_consistency_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-015_E01_SAME_SUBMISSION_CONSISTENCY_PROBE.md"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-benarg-consistency-candidate-metadata-v1.json"
PRIOR_REVIEW_PATH = ROOT / "reports/artifacts/e01-provenance-probe-review-v1.json"
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
FIRST_REPLAY_PATH = ROOT / "private/g3/e01/provenance-probe-v1/87703034.json"
SECOND_REPLAY_PATH = ROOT / "private/g3/e01/consistency-probe-v1/87741212.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-same-submission-consistency-review-v1.json"

EXPECTED = {
    "request": "e98cbbaae8bdd2a8b09b9ff43f6298c59f45e821206cd7bc860d140f60927ae2",
    "authorized_request": "03924ab3996a5147fb43f3b7a65ac15180d7092b857ef04821be96219bd9bfe7",
    "decision": "884ef8dd592d4296042b474f4900cbb18c89e3bf2ec9e6aebee4e35dde5dda1e",
    "metadata": "971e4f2b9323aa17bfa98e6b6a16f17a99d4e4b17af2acbae1b7dd02d69ff577",
    "prior_review": "94c8d1e90400f9fb950f1950e1a3ef37b66fca3a81767c0ab502affa5e58d92c",
    "prior_review_self": "f09117848e457b836c020c7c8112519d24daf392a74f14ba4c26a81b1618fec7",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "first_replay": "58089ab3824ac703dddb5d1364718684d4770d3ebf853ea198ca00efdc6a43db",
    "second_replay": "be962b8ca9146320f7d8976460c20244cf5e8bf6b026816816bc4b4ec91a87d2",
    "benarg_deck": "606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_value_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


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
            card_id = int(row["Card ID"])
            rows[card_id] = dict(row)
    return rows


def deck_construction(deck: list[int], cards: Mapping[int, Mapping[str, str]]) -> dict[str, Any]:
    if len(deck) != 60 or any(isinstance(value, bool) or not isinstance(value, int) for value in deck):
        raise ValueError("deck action is not exactly 60 integer card ids")
    missing = sorted({value for value in deck if value not in cards})
    names = Counter(cards[value]["Card Name"] for value in deck if value in cards)
    violations = 0
    for name, count in names.items():
        if count <= 4:
            continue
        matching = [cards[value] for value in deck if value in cards and cards[value]["Card Name"] == name]
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
    expected_episode_id: int,
    expected_bytes: int,
    expected_sha256: str,
    benarg_player_index: int,
) -> dict[str, Any]:
    require_hash(path, expected_sha256)
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"byte count differs for {path}")
    replay = load_json(path)
    if replay.get("schema_version") != 1 or replay.get("module_version") != "1.32.2":
        raise ValueError("replay schema or module version differs")
    if replay.get("name") != "cabt" or replay.get("version") != "1.0.0":
        raise ValueError("environment identity differs")
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
                _validate_record(record, f"{path.name}.steps[{step_index}][{player_index}]")
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
            if not isinstance(options, list) or any(not isinstance(option, Mapping) for option in options):
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
    agent_names = [agent.get("Name") if isinstance(agent, Mapping) else None for agent in agents]
    if agent_names[benarg_player_index] != "Benarg" or team_names[benarg_player_index] != "Benarg":
        raise ValueError("Benarg player binding differs")

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
        "benarg_player_index": benarg_player_index,
        "benarg_reward": replay["rewards"][benarg_player_index],
        "benarg_deck": decks[benarg_player_index],
        "opponent_deck_multiset_sha256": decks[1 - benarg_player_index]["multiset_sha256"],
        "action_alignment": {
            "status": "PASS",
            "active_selection_requests": active_requests,
            "active_requests_by_player": {
                str(key): value for key, value in sorted(active_by_player.items())
            },
            "benarg_active_selection_requests": active_by_player[benarg_player_index],
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
        (METADATA_PATH, EXPECTED["metadata"]),
        (PRIOR_REVIEW_PATH, EXPECTED["prior_review"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    metadata = load_json(METADATA_PATH)
    prior_review = load_json(PRIOR_REVIEW_PATH)
    if prior_review.get("review_sha256") != EXPECTED["prior_review_self"]:
        raise ValueError("prior review self hash differs")
    if request.get("status") != "CONSUMED" or request.get("request_ready") is not False:
        raise ValueError("request is not consumed")
    if request.get("authorized") is not False:
        raise ValueError("request remains authorized")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution record is missing")
    if approval.get("authorized_request_sha256") != EXPECTED["authorized_request"]:
        raise ValueError("authorized request hash differs")
    if execution != {
        "files_downloaded": 1,
        "bytes_downloaded": 559779,
        "downloaded_file": "private/g3/e01/consistency-probe-v1/87741212.json",
        "downloaded_file_sha256": EXPECTED["second_replay"],
        "agent_logs_downloaded": 0,
        "additional_replays_downloaded_after_named_file": 0,
        "raw_replay_body_exports": 0,
        "raw_step_exports": 0,
        "action_sequence_exports": 0,
        "observation_exports": 0,
        "training_label_exports": 0,
        "optimizer_steps": 0,
        "external_compute": False,
        "training": False,
        "submission": False,
    }:
        raise ValueError("execution boundary differs")
    second_directory = SECOND_REPLAY_PATH.parent
    if sorted(path.name for path in second_directory.iterdir() if path.is_file()) != [
        SECOND_REPLAY_PATH.name
    ]:
        raise ValueError("consistency quarantine contains unexpected files")

    first = inspect_replay(
        FIRST_REPLAY_PATH,
        expected_episode_id=87703034,
        expected_bytes=3641302,
        expected_sha256=EXPECTED["first_replay"],
        benarg_player_index=0,
    )
    second = inspect_replay(
        SECOND_REPLAY_PATH,
        expected_episode_id=87741212,
        expected_bytes=559779,
        expected_sha256=EXPECTED["second_replay"],
        benarg_player_index=1,
    )
    metadata_submission = metadata.get("submission")
    selected = metadata.get("selected_additional_candidate")
    if not isinstance(metadata_submission, Mapping) or not isinstance(selected, Mapping):
        raise ValueError("candidate metadata differs")
    if metadata_submission.get("submission_id") != 54933084:
        raise ValueError("submission id differs")
    agents = selected.get("agents")
    if not isinstance(agents, list) or agents[1].get("submission_id") != 54933084:
        raise ValueError("selected episode submission binding differs")

    first_hash = first["benarg_deck"]["multiset_sha256"]
    second_hash = second["benarg_deck"]["multiset_sha256"]
    if first_hash != EXPECTED["benarg_deck"] or second_hash != EXPECTED["benarg_deck"]:
        raise ValueError("Benarg exact deck differs across episodes")
    teacher_decisions = (
        first["action_alignment"]["benarg_active_selection_requests"]
        + second["action_alignment"]["benarg_active_selection_requests"]
    )
    combined_requests = (
        first["action_alignment"]["active_selection_requests"]
        + second["action_alignment"]["active_selection_requests"]
    )
    if teacher_decisions != 65 or combined_requests != 157:
        raise ValueError("aggregate decision counts differ")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-same-submission-consistency-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-same-submission-consistency-review-v1.json",
        "producer": "scripts/e01_consistency_probe_review.py",
        "reviewed_decision": "DEC-015",
        "status": "PASS",
        "decision": "ACCEPT_SAME_SUBMISSION_DECK_CONSISTENCY_SCREENING_FLOOR_BLOCKED",
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
            "candidate_metadata": {
                "path": str(METADATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["metadata"],
            },
            "prior_probe_review": {
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
            "new_files_downloaded": 1,
            "new_bytes_downloaded": 559779,
            "new_replay_sha256": EXPECTED["second_replay"],
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded_after_named_file": 0,
            "overwrite_used": False,
            "raw_replay_body_exports": 0,
            "raw_step_exports": 0,
            "action_sequence_exports": 0,
            "observation_exports": 0,
            "training_label_exports": 0,
            "optimizer_steps": 0,
        },
        "submission_binding": {
            "submission_id": 54933084,
            "team_id": 16401597,
            "team_name": "Benarg",
            "same_exact_public_submission_across_episodes": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_ids_bound_by_public_metadata": True,
            "opposite_player_slots": True,
            "opposite_terminal_results": True,
        },
        "episodes": [first, second],
        "consistency": {
            "same_schema_version": True,
            "same_module_version": True,
            "same_environment_identity": True,
            "exact_benarg_deck_match": True,
            "benarg_deck_multiset_sha256": EXPECTED["benarg_deck"],
            "current_asset_deck_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "both_replay_action_alignment": "PASS",
            "combined_all_player_active_selection_requests": combined_requests,
            "combined_benarg_active_selection_requests": teacher_decisions,
            "screening_minimum_teacher_decisions": 5000,
            "screening_teacher_decision_shortfall": 5000 - teacher_decisions,
        },
        "qualification": {
            "same_submission_identity_qualified": True,
            "exact_deck_consistency_qualified": True,
            "current_asset_deck_construction_compatibility_qualified": True,
            "action_aligned_supervision_available": True,
            "policy_artifact_identity_inferred_from_same_submission_id": True,
            "policy_behavior_consistency_qualified": False,
            "exact_historical_deck_legality_qualified": False,
            "teacher_strength_qualified": False,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "PREPARE_STRONGER_TEACHER_AND_BOUNDED_MULTI_EPISODE_SCREENING_PLAN_WITH_NEW_APPROVAL",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def main() -> None:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(canonical_bytes(report))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
