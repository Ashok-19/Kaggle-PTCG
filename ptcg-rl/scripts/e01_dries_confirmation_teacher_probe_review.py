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
REQUEST_PATH = ROOT / "configs/e01_dries_confirmation_teacher_probe_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-022_E01_DRIES_CONFIRMATION_TEACHER_PROBE.md"
SNAPSHOT_PATH = ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v1.json"
CONTRACT_PATH = ROOT / "reports/artifacts/e01-dries-confirmation-teacher-contract-review-v1.json"
FLG_SCREENING_PATH = ROOT / "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json"
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
FIRST_REPLAY_PATH = ROOT / "private/g3/e01/dries-confirmation-teacher-probe-v1/88281294.json"
SECOND_REPLAY_PATH = ROOT / "private/g3/e01/dries-confirmation-teacher-probe-v1/88332011.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json"

EXPECTED = {
    "request": "9e558be620bcf9722ba69ae7189ebec79145b351c20e4370eb1bb37d2427d2bc",
    "authorized_request": "5a5696077ae04b3701881cb619d76e381472049bf7d342b85dc8b92373ecb906",
    "decision": "a6802416e9d2cb03ca267c82a11a482014c22832f575cb310802cb111c93b027",
    "snapshot": "7642598704cca4899235089c57e6429805ebb8ea496e4c5b47befc677e4b80dc",
    "contract": "655c022cdf5f3baddbb6f70968c4cc4bf4165c4ecdc7a6dd52ff5f9330432815",
    "contract_self": "5238d31a608e56978a9753c1e81f4d9a0d02038c0499c18ebdb50fea4ac44bdd",
    "flg_screening": "38f1e6f4f0d68b52677e6e578ac7f69ca0730f819bc895b5205d42387f7c8fc2",
    "flg_screening_self": "0346535b89f0f14e153df0afeda90609f51e2a0d75b4b959df38be71dfb7df80",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "first_replay": "46929a43e1c84f79a8738be5258058206d5f730f57b706b3a0998675bf49364a",
    "second_replay": "07f7662d1c7cbd98195400f33f3dcff4cf4b188ba51a6ecd58159cc2875e64ee",
    "teacher_deck": "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd",
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
        agent_names[teacher_player_index] != "Dries @ Tufa Labs"
        or team_names[teacher_player_index] != "Dries @ Tufa Labs"
    ):
        raise ValueError("Dries player binding differs")

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
        (FLG_SCREENING_PATH, EXPECTED["flg_screening"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    snapshot = load_json(SNAPSHOT_PATH)
    contract = load_json(CONTRACT_PATH)
    flg_screening = load_json(FLG_SCREENING_PATH)
    if contract.get("review_sha256") != EXPECTED["contract_self"]:
        raise ValueError("contract review self hash differs")
    if flg_screening.get("review_sha256") != EXPECTED["flg_screening_self"]:
        raise ValueError("flg screening self hash differs")
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
    if authorization_payload_hash(request) == EXPECTED["authorized_request"]:
        raise ValueError("consumed request unexpectedly equals authorized payload")
    expected_downloads = [
        {
            "episode_id": 88_281_294,
            "file_name": "88281294.json",
            "path": "private/g3/e01/dries-confirmation-teacher-probe-v1/88281294.json",
            "bytes": 625_479,
            "sha256": EXPECTED["first_replay"],
        },
        {
            "episode_id": 88_332_011,
            "file_name": "88332011.json",
            "path": "private/g3/e01/dries-confirmation-teacher-probe-v1/88332011.json",
            "bytes": 509_759,
            "sha256": EXPECTED["second_replay"],
        },
    ]
    if (
        execution.get("files_downloaded") != 2
        or execution.get("bytes_downloaded") != 1_135_238
        or execution.get("downloaded_files") != expected_downloads
    ):
        raise ValueError("execution transfer record differs")
    for key in (
        "agent_logs_downloaded",
        "additional_replays_downloaded_after_named_files",
        "raw_replay_body_exports",
        "raw_step_exports",
        "request_exports",
        "option_exports",
        "observation_exports",
        "action_sequence_exports",
        "card_list_exports",
        "training_label_exports",
        "optimizer_steps",
    ):
        if execution.get(key) != 0:
            raise ValueError(f"execution boundary differs: {key}")
    for key in ("training", "external_compute", "submission"):
        if execution.get(key) is not False:
            raise ValueError(f"execution boundary differs: {key}")

    quarantine = FIRST_REPLAY_PATH.parent
    expected_names = ["88281294.json", "88332011.json"]
    if sorted(path.name for path in quarantine.iterdir() if path.is_file()) != expected_names:
        raise ValueError("Dries quarantine contains unexpected files")

    first = inspect_replay(
        FIRST_REPLAY_PATH,
        expected_episode_id=88_281_294,
        expected_bytes=625_479,
        expected_sha256=EXPECTED["first_replay"],
        teacher_player_index=1,
        expected_reward=1,
    )
    second = inspect_replay(
        SECOND_REPLAY_PATH,
        expected_episode_id=88_332_011,
        expected_bytes=509_759,
        expected_sha256=EXPECTED["second_replay"],
        teacher_player_index=0,
        expected_reward=-1,
    )

    teacher = snapshot.get("teacher")
    selection = snapshot.get("selection")
    if not isinstance(teacher, Mapping) or not isinstance(selection, Mapping):
        raise ValueError("live confirmation metadata is missing")
    if (
        teacher.get("live_rank_at_refresh") != 1
        or teacher.get("team_id") != 16_531_269
        or teacher.get("submission_id") != 55_002_825
        or teacher.get("submission_public_score") != 1205.2
        or teacher.get("dataset_episode_count") != 128
        or selection.get("selected_total_bytes") != 1_135_238
    ):
        raise ValueError("live Dries teacher binding differs")

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
    teacher_decisions = sum(
        episode["action_alignment"]["teacher_active_selection_requests"]
        for episode in (first, second)
    )
    combined_requests = sum(
        episode["action_alignment"]["active_selection_requests"]
        for episode in (first, second)
    )
    if module_versions != ["1.32.2"]:
        raise ValueError("Dries module versions differ")
    if deck_hashes != [EXPECTED["teacher_deck"]]:
        raise ValueError("Dries exact deck differs")
    if archetypes != ["Marnie's Grimmsnarl ex"]:
        raise ValueError("Dries archetype context differs")
    if teacher_decisions != 27 or combined_requests != 57:
        raise ValueError("Dries aggregate decisions differ")
    if any(
        episode["teacher_deck"]["current_asset_construction_checks"] != "PASS"
        or episode["action_alignment"]["status"] != "PASS"
        for episode in (first, second)
    ):
        raise ValueError("Dries construction or action alignment differs")

    flg_screening_data = flg_screening.get("screening")
    if not isinstance(flg_screening_data, Mapping):
        raise ValueError("flg screening data is missing")
    if (
        flg_screening_data.get("combined_observed_teacher_decisions") != 6_340
        or flg_screening_data.get("qualified_files") != 38
        or flg_screening_data.get("rejected_files") != 0
        or flg_screening_data.get("minimum_5000_teacher_decisions_met") is not True
    ):
        raise ValueError("completed flg screening differs")

    combined_recent_teacher_episodes = 52 + 2
    combined_recent_teacher_decisions = 6_340 + teacher_decisions
    confirmation_episode_shortfall = 200 - combined_recent_teacher_episodes
    confirmation_decision_shortfall = 25_000 - combined_recent_teacher_decisions

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-dries-confirmation-teacher-probe-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json",
        "producer": "scripts/e01_dries_confirmation_teacher_probe_review.py",
        "reviewed_decision": "DEC-022",
        "status": "PASS",
        "decision": "ACCEPT_CURRENT_RANK_1_DRIES_GRIMMSNARL_TEACHER_CONSISTENCY_SECOND_TEACHER_MET_CONFIRMATION_FLOORS_BLOCKED",
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "live_confirmation_refresh": {
                "path": str(SNAPSHOT_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["snapshot"],
            },
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
            "completed_flg_screening": {
                "path": str(FLG_SCREENING_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["flg_screening"],
                "review_sha256": EXPECTED["flg_screening_self"],
            },
            "card_data": {
                "path": str(CARD_DATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["card_data"],
            },
        },
        "transfer": {
            "new_files_downloaded": 2,
            "new_bytes_downloaded": 1_135_238,
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
            "team_id": 16_531_269,
            "team_name": "Dries @ Tufa Labs",
            "submission_id": 55_002_825,
            "live_rank_at_refresh": 1,
            "live_team_score_at_refresh": 1205.2,
            "submission_public_score": 1205.2,
            "dataset_episode_count": 128,
            "strength_basis": "CURRENT_LIVE_RANK_1_AND_ACTIVE_SUBMISSION_PUBLIC_SCORE",
            "same_exact_public_submission_across_episodes": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_ids_bound_by_public_metadata": True,
            "opposite_player_slots": True,
            "opposite_terminal_results": True,
            "independent_from_flg_teacher": True,
        },
        "episodes": [first, second],
        "consistency": {
            "same_schema_version": True,
            "same_environment_identity": True,
            "same_module_version": True,
            "module_versions": module_versions,
            "exact_teacher_deck_match": True,
            "teacher_deck_multiset_sha256": EXPECTED["teacher_deck"],
            "teacher_archetype_context_label": "Marnie's Grimmsnarl ex",
            "matches_prior_luca_deck_multiset_sha256": True,
            "current_asset_deck_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "both_replay_action_alignment": "PASS",
            "combined_all_player_active_selection_requests": combined_requests,
            "combined_teacher_active_selection_requests": teacher_decisions,
        },
        "confirmation": {
            "required_independent_recent_teachers": 2,
            "observed_independent_recent_teachers": 2,
            "independent_recent_teacher_requirement_met": True,
            "required_episodes": 200,
            "observed_recent_teacher_episodes": combined_recent_teacher_episodes,
            "episode_shortfall": confirmation_episode_shortfall,
            "required_meaningful_teacher_decisions": 25_000,
            "observed_recent_teacher_decisions": combined_recent_teacher_decisions,
            "decision_shortfall": confirmation_decision_shortfall,
            "confirmation_gate_passed": False,
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
            "second_independent_recent_teacher_qualified": True,
            "exact_historical_deck_legality_qualified": False,
            "minimum_200_recent_teacher_episodes_met": False,
            "minimum_25000_meaningful_teacher_decisions_met": False,
            "confirmation_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "PREPARE_BOUNDED_BALANCED_DRIES_GRIMMSNARL_CALIBRATION_REQUEST_WITH_NEW_APPROVAL",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def write_review(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    report = build_report()
    write_review(report, OUTPUT_PATH)
    print(
        json.dumps(
            {
                "status": report["status"],
                "decision": report["decision"],
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "review_sha256": report["review_sha256"],
                "teacher": report["teacher"],
                "consistency": report["consistency"],
                "confirmation": report["confirmation"],
                "qualification": report["qualification"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
