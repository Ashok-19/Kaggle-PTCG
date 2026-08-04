from __future__ import annotations

import csv
import hashlib
import json
import math
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
REQUEST_PATH = ROOT / "configs/e01_dries_grimmsnarl_calibration_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-023_E01_DRIES_GRIMMSNARL_CALIBRATION.md"
CANDIDATE_PATH = (
    ROOT / "reports/artifacts/raw/e01-dries-grimmsnarl-calibration-candidates-v1.json"
)
PRIOR_PROBE_REVIEW_PATH = (
    ROOT / "reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json"
)
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json"
QUARANTINE = ROOT / "private/g3/e01/dries-grimmsnarl-calibration-v1"

EXPECTED = {
    "request": "f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380",
    "authorized_request": "75bc96fe9f5ab595f1443716a96f47c67843687b32f6d55616b05f9a59c8945d",
    "decision": "9ea27e6e2f5f41953a2ef2eb68af0840a0297a7640832480b232674826403460",
    "candidate": "18e84036a294c57e6d805114270815c84cddea903cad5599a5cb5bab83603bcd",
    "prior_probe_review": "42d65b6f40fd2a2767ed3b7ed56852c2a7efb096c159f97f294c8fe6183008e0",
    "prior_probe_self": "85845efb12c00b4fc489daa65be9291d1ff0db2d18e55261c66d107c8c64422c",
    "card_data": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "deck": "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd",
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
    item: Mapping[str, Any],
    expected_sha256: str,
    cards: Mapping[int, Mapping[str, str]],
) -> dict[str, Any]:
    require_hash(path, expected_sha256)
    expected_bytes = int(item["declared_bytes"])
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"byte count differs for {path}")
    replay = load_json(path)
    if (
        replay.get("schema_version") != 1
        or replay.get("module_version") != "1.32.2"
        or replay.get("name") != "cabt"
        or replay.get("version") != "1.0.0"
    ):
        raise ValueError(f"replay schema, module, or environment differs for {path.name}")
    info = replay.get("info")
    if not isinstance(info, Mapping) or info.get("EpisodeId") != int(item["episode_id"]):
        raise ValueError(f"episode identity differs for {path.name}")
    teacher_player_index = int(item["teacher_player_index"])
    expected_teacher_reward = int(item["teacher_reward"])
    rewards = replay.get("rewards")
    if (
        replay.get("statuses") != ["DONE", "DONE"]
        or not isinstance(rewards, list)
        or len(rewards) != 2
        or rewards[teacher_player_index] != expected_teacher_reward
        or rewards[1 - teacher_player_index] != -expected_teacher_reward
    ):
        raise ValueError(f"terminal binding differs for {path.name}")
    agents = info.get("Agents")
    team_names = info.get("TeamNames")
    if not isinstance(agents, list) or not isinstance(team_names, list):
        raise ValueError(f"agent metadata differs for {path.name}")
    agent_names = [
        agent.get("Name") if isinstance(agent, Mapping) else None for agent in agents
    ]
    if (
        agent_names[teacher_player_index] != "Dries @ Tufa Labs"
        or team_names[teacher_player_index] != "Dries @ Tufa Labs"
    ):
        raise ValueError(f"Dries replay binding differs for {path.name}")

    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError(f"steps are missing for {path.name}")
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
        action = _validate_action(record.get("action"), f"{path.name}.deck[{player_index}]")
        if len(action) != 60:
            raise ValueError(f"initial deck action is not 60 cards for {path.name}")
        decks.append(action)

    active_requests = 0
    nonempty = 0
    empty = 0
    maximum_options = 0
    maximum_selection = 0
    active_by_player: Counter[int] = Counter()
    for step_index in range(2, len(parsed)):
        for player_index, current in enumerate(parsed[step_index]):
            action = _validate_action(
                current.get("action"), f"{path.name}.action[{step_index}][{player_index}]"
            )
            previous = parsed[step_index - 1][player_index]
            if previous.get("status") != "ACTIVE":
                if action:
                    raise ValueError(f"action occurs after inactive record in {path.name}")
                continue
            request = _selection_request(
                previous, f"{path.name}.previous[{step_index - 1}][{player_index}]"
            )
            if request is None:
                if action:
                    raise ValueError(f"action occurs after missing request in {path.name}")
                continue
            minimum = _integer(request.get("minCount"), "minimum")
            maximum = _integer(request.get("maxCount"), "maximum")
            options = request.get("option")
            if not isinstance(options, list) or any(
                not isinstance(option, Mapping) for option in options
            ):
                raise ValueError(f"request options differ in {path.name}")
            if not minimum <= len(action) <= maximum:
                raise ValueError(f"selection count is outside request bounds in {path.name}")
            if not _resolves_against_options(action, options):
                raise ValueError(f"action does not resolve against request options in {path.name}")
            active_requests += 1
            active_by_player[player_index] += 1
            nonempty += int(bool(action))
            empty += int(not action)
            maximum_options = max(maximum_options, len(options))
            maximum_selection = max(maximum_selection, len(action))

    deck = deck_construction(decks[teacher_player_index], cards)
    if deck["multiset_sha256"] != EXPECTED["deck"]:
        raise ValueError(f"Dries exact deck differs for {path.name}")
    if deck["current_asset_construction_checks"] != "PASS":
        raise ValueError(f"current-card construction fails for {path.name}")
    if deck["archetype_context_label"] != "Marnie's Grimmsnarl ex":
        raise ValueError(f"Dries archetype context differs for {path.name}")
    stratum = (
        f"seat_{teacher_player_index}_"
        f"{'win' if expected_teacher_reward == 1 else 'loss'}"
    )
    return {
        "episode_id": int(item["episode_id"]),
        "file": {
            "path": str(path.relative_to(ROOT)),
            "bytes": expected_bytes,
            "sha256": expected_sha256,
        },
        "schema_version": 1,
        "module_version": "1.32.2",
        "environment_name": "cabt",
        "environment_version": "1.0.0",
        "steps": len(steps),
        "teacher_player_index": teacher_player_index,
        "teacher_reward": expected_teacher_reward,
        "stratum": stratum,
        "teacher_deck": deck,
        "action_alignment": {
            "status": "PASS",
            "active_selection_requests": active_requests,
            "teacher_active_selection_requests": active_by_player[teacher_player_index],
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
        (CANDIDATE_PATH, EXPECTED["candidate"]),
        (PRIOR_PROBE_REVIEW_PATH, EXPECTED["prior_probe_review"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    candidates = load_json(CANDIDATE_PATH)
    prior_review = load_json(PRIOR_PROBE_REVIEW_PATH)
    if prior_review.get("review_sha256") != EXPECTED["prior_probe_self"]:
        raise ValueError("prior Dries probe self hash differs")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("maximum_new_files") != 12
        or request.get("maximum_new_bytes") != 60_869_451
        or request.get("authorization_scope")
        != "CONSUMED_EXACT_12_FILE_DRIES_GRIMMSNARL_CALIBRATION_ONLY"
    ):
        raise ValueError("calibration request lifecycle differs")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("approval or execution record is missing")
    if (
        approval.get("authorized_request_sha256") != EXPECTED["authorized_request"]
        or approval.get("authorization_scope")
        != "AUTHORIZED_EXACT_12_FILE_DRIES_GRIMMSNARL_CALIBRATION_ONLY"
        or approval.get("maximum_new_files") != 12
        or approval.get("maximum_new_bytes") != 60_869_451
        or approval.get("one_time") is not True
    ):
        raise ValueError("authorized request binding differs")
    if (
        execution.get("files_downloaded") != 12
        or execution.get("bytes_downloaded") != 60_869_451
        or execution.get("agent_logs_downloaded") != 0
        or execution.get("additional_replays_downloaded_after_named_files") != 0
        or execution.get("raw_replay_body_exports") != 0
        or execution.get("raw_step_exports") != 0
        or execution.get("action_sequence_exports") != 0
        or execution.get("observation_exports") != 0
        or execution.get("option_exports") != 0
        or execution.get("card_list_exports") != 0
        or execution.get("request_exports") != 0
        or execution.get("training_label_exports") != 0
        or execution.get("optimizer_steps") != 0
        or execution.get("external_compute") is not False
        or execution.get("training") is not False
        or execution.get("submission") is not False
    ):
        raise ValueError("execution boundary differs")

    episodes = request.get("episodes")
    selected = candidates.get("selection", {}).get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 12 or episodes != selected:
        raise ValueError("request episodes differ from frozen metadata selection")
    if candidates.get("selection", {}).get("total_bytes") != 60_869_451:
        raise ValueError("candidate selection byte total differs")
    expected_names = sorted(item["file_name"] for item in episodes)
    observed_entries = list(QUARANTINE.iterdir())
    if any(not path.is_file() for path in observed_entries):
        raise ValueError("calibration quarantine contains a non-file entry")
    observed_names = sorted(path.name for path in observed_entries)
    if observed_names != expected_names:
        raise ValueError("calibration quarantine contains unexpected files")

    execution_files = execution.get("downloaded_files")
    if not isinstance(execution_files, list) or len(execution_files) != 12:
        raise ValueError("downloaded file evidence differs")
    execution_by_name = {Path(str(item["path"])).name: item for item in execution_files}
    if sorted(execution_by_name) != expected_names:
        raise ValueError("downloaded file list differs")

    cards = card_table()
    reviewed: list[dict[str, Any]] = []
    strata: Counter[str] = Counter()
    all_requests = 0
    teacher_requests = 0
    nonempty = 0
    empty = 0
    maximum_options = 0
    maximum_selection = 0
    for item in episodes:
        file_name = str(item["file_name"])
        execution_item = execution_by_name[file_name]
        expected_sha = str(execution_item["sha256"])
        if (
            execution_item.get("bytes") != int(item["declared_bytes"])
            or execution_item.get("episode_id") != int(item["episode_id"])
            or execution_item.get("file_name") != file_name
            or execution_item.get("path")
            != f"private/g3/e01/dries-grimmsnarl-calibration-v1/{file_name}"
        ):
            raise ValueError(f"execution file binding differs for {file_name}")
        result = inspect_replay(
            QUARANTINE / file_name,
            item=item,
            expected_sha256=expected_sha,
            cards=cards,
        )
        reviewed.append(result)
        strata[result["stratum"]] += 1
        alignment = result["action_alignment"]
        all_requests += int(alignment["active_selection_requests"])
        teacher_requests += int(alignment["teacher_active_selection_requests"])
        nonempty += int(alignment["nonempty_lagged_selections"])
        empty += int(alignment["empty_lagged_selections"])
        maximum_options = max(maximum_options, int(alignment["maximum_option_count"]))
        maximum_selection = max(
            maximum_selection, int(alignment["maximum_selection_count"])
        )
    expected_strata = Counter(
        {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
    )
    if strata != expected_strata:
        raise ValueError("calibration stratum balance differs")

    prior_confirmation = prior_review.get("confirmation")
    if not isinstance(prior_confirmation, Mapping):
        raise ValueError("prior confirmation aggregate is missing")
    if (
        prior_confirmation.get("observed_independent_recent_teachers") != 2
        or prior_confirmation.get("observed_recent_teacher_episodes") != 54
        or prior_confirmation.get("observed_recent_teacher_decisions") != 6_367
        or prior_confirmation.get("required_episodes") != 200
        or prior_confirmation.get("required_meaningful_teacher_decisions") != 25_000
        or prior_confirmation.get("required_independent_recent_teachers") != 2
    ):
        raise ValueError("prior confirmation aggregate differs")

    observed_teachers = 2
    combined_episodes = 54 + 12
    combined_decisions = 6_367 + teacher_requests
    episode_shortfall = max(0, 200 - combined_episodes)
    decision_shortfall = max(0, 25_000 - combined_decisions)
    decisions_per_episode = teacher_requests / 12
    decisions_per_mib = teacher_requests / (60_869_451 / (1024 * 1024))
    projected_episodes_for_decisions = (
        math.ceil(decision_shortfall / decisions_per_episode)
        if decision_shortfall
        else 0
    )
    projected_additional_episodes = max(
        episode_shortfall, projected_episodes_for_decisions
    )
    projected_additional_bytes = (
        math.ceil(decision_shortfall / decisions_per_mib * 1024 * 1024)
        if decision_shortfall
        else 0
    )
    confirmation_passed = (
        observed_teachers >= 2
        and combined_episodes >= 200
        and combined_decisions >= 25_000
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-dries-grimmsnarl-calibration-review-v1",
        "created_at_utc": approval.get("consumed_at_utc"),
        "source_path": "reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json",
        "producer": "scripts/e01_dries_grimmsnarl_calibration_review.py",
        "reviewed_decision": "DEC-023",
        "status": "PASS",
        "decision": (
            "ACCEPT_DRIES_GRIMMSNARL_CALIBRATION_CONFIRMATION_FLOOR_PASS"
            if confirmation_passed
            else "ACCEPT_DRIES_GRIMMSNARL_CALIBRATION_CONFIRMATION_FLOOR_BLOCKED"
        ),
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
                "path": str(CANDIDATE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["candidate"],
            },
            "prior_dries_probe_review": {
                "path": str(PRIOR_PROBE_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["prior_probe_review"],
                "review_sha256": EXPECTED["prior_probe_self"],
            },
            "card_data": {
                "path": str(CARD_DATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["card_data"],
            },
        },
        "transfer": {
            "new_files_downloaded": 12,
            "new_bytes_downloaded": 60_869_451,
            "downloaded_files": execution_files,
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded_after_named_files": 0,
            "overwrite_used": False,
            "raw_replay_body_exports": 0,
            "raw_step_exports": 0,
            "action_sequence_exports": 0,
            "observation_exports": 0,
            "option_exports": 0,
            "card_list_exports": 0,
            "request_exports": 0,
            "training_label_exports": 0,
            "optimizer_steps": 0,
        },
        "teacher": {
            "submission_id": 55_002_825,
            "team_id": 16_531_269,
            "team_name": "Dries @ Tufa Labs",
            "archetype_context_label": "Marnie's Grimmsnarl ex",
            "live_rank_at_refresh": 1,
            "submission_public_score": 1205.2,
            "dataset_episode_count": 128,
            "same_exact_public_submission_across_episodes": True,
            "submission_ids_present_in_replay_bodies": False,
            "submission_ids_bound_by_public_metadata": True,
        },
        "episodes": reviewed,
        "consistency": {
            "schema_version": 1,
            "environment_name": "cabt",
            "environment_version": "1.0.0",
            "module_versions": ["1.32.2"],
            "all_same_module_version": True,
            "exact_teacher_deck_match": True,
            "teacher_deck_multiset_sha256": EXPECTED["deck"],
            "teacher_archetype_context_label": "Marnie's Grimmsnarl ex",
            "current_asset_deck_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "all_replay_action_alignment": "PASS",
            "balanced_strata": dict(sorted(strata.items())),
            "combined_all_player_active_selection_requests": all_requests,
            "calibration_teacher_active_selection_requests": teacher_requests,
            "nonempty_lagged_selections": nonempty,
            "empty_lagged_selections": empty,
            "maximum_option_count": maximum_options,
            "maximum_selection_count": maximum_selection,
        },
        "confirmation": {
            "prior_observed_independent_recent_teachers": 2,
            "prior_observed_recent_teacher_episodes": 54,
            "prior_observed_recent_teacher_decisions": 6_367,
            "calibration_teacher_episodes": 12,
            "calibration_teacher_decisions": teacher_requests,
            "observed_independent_recent_teachers": observed_teachers,
            "observed_recent_teacher_episodes": combined_episodes,
            "observed_recent_teacher_decisions": combined_decisions,
            "required_independent_recent_teachers": 2,
            "required_episodes": 200,
            "required_meaningful_teacher_decisions": 25_000,
            "episode_shortfall": episode_shortfall,
            "decision_shortfall": decision_shortfall,
            "independent_recent_teacher_requirement_met": observed_teachers >= 2,
            "confirmation_gate_passed": confirmation_passed,
        },
        "density": {
            "calibration_decisions_per_episode": decisions_per_episode,
            "calibration_decisions_per_mib": decisions_per_mib,
            "projected_additional_episodes_for_decision_floor": projected_episodes_for_decisions,
            "projected_additional_episodes_for_all_confirmation_floors": projected_additional_episodes,
            "projected_additional_bytes_for_decision_floor": projected_additional_bytes,
            "projection_is_guarantee": False,
        },
        "qualification": {
            "current_rank_1_strength_metadata_qualified": True,
            "teacher_strength_qualified": True,
            "same_submission_identity_qualified": True,
            "exact_deck_consistency_qualified": True,
            "current_asset_deck_construction_compatibility_qualified": True,
            "action_aligned_supervision_available": True,
            "same_module_version_qualified": True,
            "same_version_replay_contract_consistency_qualified": True,
            "policy_behavior_contract_consistency_qualified": True,
            "exact_historical_deck_legality_qualified": False,
            "second_independent_recent_teacher_qualified": True,
            "minimum_200_recent_teacher_episodes_met": combined_episodes >= 200,
            "minimum_25000_meaningful_teacher_decisions_met": combined_decisions >= 25_000,
            "confirmation_gate_passed": confirmation_passed,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "policy_behavior_consistency_definition": (
            "SAME_PUBLIC_SUBMISSION_ID_MODULE_DECK_AND_VALID_ACTION_ALIGNED_"
            "REPLAY_CONTRACT_NOT_IDENTICAL_STATE_ACTION_REPRODUCIBILITY"
        ),
        "next_action": (
            "PREPARE_BEHAVIOR_CLONING_REQUEST_UNAUTHORIZED"
            if confirmation_passed
            else "PREPARE_BOUNDED_DRIES_GRIMMSNARL_CONFIRMATION_EXPANSION_"
            "REQUEST_FROM_CALIBRATED_DENSITY_WITH_NEW_APPROVAL"
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
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
