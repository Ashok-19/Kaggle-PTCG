from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.replay.acquisition import (  # noqa: E402
    _integer,
    _resolves_against_options,
    _selection_request,
    _validate_action,
    _validate_record,
)


REQUEST_PATH = ROOT / "configs/e01_provenance_probe_request_v2.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-014_E01_SOURCE_SCHEMA_RECONCILED.md"
DRY_RUN_PATH = ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json"
RECONCILIATION_PATH = ROOT / "reports/artifacts/e01-source-schema-reconciliation-v1.json"
RAW_RECONCILIATION_PATH = (
    ROOT / "reports/artifacts/raw/e01-public-source-schema-reconciliation-raw-v1.json"
)
CARD_DATA_PATH = ROOT / "private/assets/official/EN_Card_Data.csv"
REPLAY_PATH = ROOT / "private/g3/e01/provenance-probe-v1/87703034.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-provenance-probe-review-v1.json"

EXPECTED = {
    "request_sha256": "b9e27cd30f4ebd8f3db767c3da5708b3330a5052f651b5f666420e02815ce34b",
    "authorized_request_sha256": "5fdfb4c3fc11defbc2f3ea271816cc37413d23cb7115acd8c52a064b11f14fc1",
    "decision_sha256": "eb53541af1520384cbefa581af2a1dfadc06da29f716e7f18e412b04380ece67",
    "dry_run_sha256": "ecec3f97e62d177fbb111b528a3f70ad9b0059991af50935861b937ab87ea599",
    "reconciliation_sha256": "0c428b9703efa86875b2d98f8077cae1baea99f438b953e7ab8d76e7449a7cb1",
    "raw_reconciliation_sha256": "d14c6666999d6013147f394cb236c45dd2c9429e88b64be461fd3c639b874859",
    "card_data_sha256": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
    "replay_sha256": "58089ab3824ac703dddb5d1364718684d4770d3ebf853ea198ca00efdc6a43db",
    "replay_bytes": 3_641_302,
    "episode_id": 87_703_034,
    "file_name": "87703034.json",
    "team_names": ["Benarg", "junlee789"],
    "deck_hashes": [
        "606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283",
        "eff68cb08be178b9c7f06c409b61e88ae9200ab6dc26e05f4bf29eed86040455",
    ],
}


class ProbeReviewError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_object(path: Path, label: str) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ProbeReviewError(f"{label} must be a JSON object")
    return value


def validate_inputs() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    observed = {
        "request_sha256": sha256_file(REQUEST_PATH),
        "decision_sha256": sha256_file(DECISION_PATH),
        "dry_run_sha256": sha256_file(DRY_RUN_PATH),
        "reconciliation_sha256": sha256_file(RECONCILIATION_PATH),
        "raw_reconciliation_sha256": sha256_file(RAW_RECONCILIATION_PATH),
        "card_data_sha256": sha256_file(CARD_DATA_PATH),
        "replay_sha256": sha256_file(REPLAY_PATH),
        "replay_bytes": REPLAY_PATH.stat().st_size,
    }
    for key, expected in EXPECTED.items():
        if key in observed and observed[key] != expected:
            raise ProbeReviewError(
                f"input differs for {key}: observed={observed[key]!r}, expected={expected!r}"
            )

    request = load_object(REQUEST_PATH, "request")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("authorization_scope")
        != "CONSUMED_EXACT_ONE_FILE_PROVENANCE_PROBE_87703034_JSON_ONLY"
    ):
        raise ProbeReviewError("request is not consumed and fail-closed")
    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ProbeReviewError("request approval/execution record is missing")
    if approval.get("authorized_request_sha256") != EXPECTED["authorized_request_sha256"]:
        raise ProbeReviewError("authorized request hash differs")
    expected_execution = {
        "files_downloaded": 1,
        "bytes_downloaded": EXPECTED["replay_bytes"],
        "downloaded_file": "private/g3/e01/provenance-probe-v1/87703034.json",
        "downloaded_file_sha256": EXPECTED["replay_sha256"],
        "agent_logs_downloaded": 0,
        "additional_replays_downloaded": 0,
        "raw_step_exports": 0,
        "action_sequence_exports": 0,
        "observation_exports": 0,
        "training_label_exports": 0,
        "optimizer_steps": 0,
        "external_compute": False,
        "training": False,
        "submission": False,
    }
    if dict(execution) != expected_execution:
        raise ProbeReviewError("request execution record differs")

    output_files = sorted(
        path.name for path in REPLAY_PATH.parent.iterdir() if path.is_file()
    )
    if output_files != [EXPECTED["file_name"]]:
        raise ProbeReviewError(f"quarantine files differ: {output_files}")

    replay = load_object(REPLAY_PATH, "replay")
    return request, replay


def review_decks(replay: Mapping[str, Any]) -> list[dict[str, Any]]:
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ProbeReviewError("replay lacks initialization/deck steps")
    deck_step = steps[1]
    if not isinstance(deck_step, list) or len(deck_step) != 2:
        raise ProbeReviewError("deck step must contain two players")

    with CARD_DATA_PATH.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {int(row["Card ID"]): row for row in rows}

    reports: list[dict[str, Any]] = []
    for player, record in enumerate(deck_step):
        validated = _validate_record(record, f"steps[1][{player}]")
        deck = _validate_action(validated.get("action"), f"steps[1][{player}]")
        if len(deck) != 60:
            raise ProbeReviewError(f"player {player} deck is not 60 cards")
        deck_hash = canonical_sha256(deck)
        if deck_hash != EXPECTED["deck_hashes"][player]:
            raise ProbeReviewError(f"player {player} deck hash differs")
        missing = [card_id for card_id in deck if card_id not in by_id]
        selected = [by_id[card_id] for card_id in deck if card_id in by_id]
        by_name: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        for row in selected:
            by_name[row["Card Name"]].append(row)
        name_limit_violations = 0
        for cards in by_name.values():
            basic_energy = all(
                card["Stage (Pokémon)/Type (Energy and Trainer)"] == "Basic Energy"
                for card in cards
            )
            if len(cards) > 4 and not basic_energy:
                name_limit_violations += 1
        basic_pokemon_cards = sum(
            row["Stage (Pokémon)/Type (Energy and Trainer)"] == "Basic Pokémon"
            for row in selected
        )
        ace_spec_cards = sum(row["Rule"] == "ACE SPEC" for row in selected)
        construction_pass = (
            not missing
            and basic_pokemon_cards > 0
            and ace_spec_cards <= 1
            and name_limit_violations == 0
        )
        if not construction_pass:
            raise ProbeReviewError(f"player {player} current-asset deck checks fail")
        reports.append(
            {
                "player": player,
                "team_name": EXPECTED["team_names"][player],
                "cards": len(deck),
                "distinct_card_ids": len(set(deck)),
                "distinct_card_names": len(by_name),
                "maximum_same_id_count": max(Counter(deck).values()),
                "basic_pokemon_cards": basic_pokemon_cards,
                "ace_spec_cards": ace_spec_cards,
                "missing_card_ids": len(missing),
                "non_basic_energy_name_limit_violations": name_limit_violations,
                "ordered_sha256": deck_hash,
                "multiset_sha256": canonical_sha256(sorted(deck)),
                "current_asset_construction_checks": "PASS",
            }
        )
    return reports


def review_action_alignment(replay: Mapping[str, Any]) -> dict[str, Any]:
    steps = replay.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ProbeReviewError("steps must be a nonempty list")
    parsed: list[list[Mapping[str, Any]]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            raise ProbeReviewError(f"steps[{step_index}] must contain two players")
        parsed.append(
            [
                _validate_record(record, f"steps[{step_index}][{player}]")
                for player, record in enumerate(step)
            ]
        )

    for player, record in enumerate(parsed[0]):
        action = _validate_action(record.get("action"), f"steps[0][{player}]")
        if (
            action
            or record.get("status") != "ACTIVE"
            or _selection_request(record, f"steps[0][{player}]") is not None
        ):
            raise ProbeReviewError("initialization record differs")

    initial_deck_actions = 0
    for player, record in enumerate(parsed[1]):
        action = _validate_action(record.get("action"), f"steps[1][{player}]")
        if len(action) != 60:
            raise ProbeReviewError("initial deck action differs")
        initial_deck_actions += 1

    active_requests = 0
    nonempty = 0
    empty = 0
    maximum_option_count = 0
    maximum_selection_count = 0
    for step_index in range(2, len(parsed)):
        for player, current in enumerate(parsed[step_index]):
            action = _validate_action(
                current.get("action"), f"steps[{step_index}][{player}]"
            )
            previous = parsed[step_index - 1][player]
            if previous.get("status") != "ACTIVE":
                if action:
                    raise ProbeReviewError("action follows a non-active record")
                continue
            request = _selection_request(
                previous, f"steps[{step_index - 1}][{player}]"
            )
            if request is None:
                if action:
                    raise ProbeReviewError("action follows a missing request")
                continue
            minimum = _integer(request.get("minCount"), "minCount")
            maximum = _integer(request.get("maxCount"), "maxCount")
            options = request.get("option")
            if not isinstance(options, list) or not all(
                isinstance(option, Mapping) for option in options
            ):
                raise ProbeReviewError("request options differ")
            if not minimum <= len(action) <= maximum:
                raise ProbeReviewError("selection count is outside request bounds")
            if not _resolves_against_options(action, options):
                raise ProbeReviewError("selection cannot be resolved against options")
            active_requests += 1
            maximum_option_count = max(maximum_option_count, len(options))
            maximum_selection_count = max(maximum_selection_count, len(action))
            if action:
                nonempty += 1
            else:
                empty += 1

    if [record.get("status") for record in parsed[-1]] != ["DONE", "DONE"]:
        raise ProbeReviewError("terminal statuses differ")
    if [record.get("reward") for record in parsed[-1]] != replay.get("rewards"):
        raise ProbeReviewError("terminal rewards differ")
    return {
        "status": "PASS",
        "steps": len(parsed),
        "initial_60_card_actions": initial_deck_actions,
        "active_selection_requests": active_requests,
        "nonempty_lagged_selections": nonempty,
        "empty_lagged_selections": empty,
        "maximum_option_count": maximum_option_count,
        "maximum_selection_count": maximum_selection_count,
    }


def build_report() -> dict[str, Any]:
    request, replay = validate_inputs()
    info = replay.get("info")
    if not isinstance(info, Mapping):
        raise ProbeReviewError("replay info must be an object")
    agents = info.get("Agents")
    team_names = info.get("TeamNames")
    if info.get("EpisodeId") != EXPECTED["episode_id"]:
        raise ProbeReviewError("replay episode ID differs")
    if team_names != EXPECTED["team_names"]:
        raise ProbeReviewError("replay team names differ")
    if not isinstance(agents, list) or [agent.get("Name") for agent in agents] != team_names:
        raise ProbeReviewError("replay agent metadata differs")

    top_level_keys = sorted(replay)
    expected_top_level_keys = sorted(
        {
            "configuration",
            "description",
            "id",
            "info",
            "module_version",
            "name",
            "rewards",
            "schema_version",
            "specification",
            "statuses",
            "steps",
            "title",
            "version",
        }
    )
    if top_level_keys != expected_top_level_keys:
        raise ProbeReviewError("top-level schema differs")

    deck_reports = review_decks(replay)
    alignment = review_action_alignment(replay)
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-provenance-probe-review-v1",
        "created_at_utc": "2026-07-24T16:23:54.663065Z",
        "source_path": "reports/artifacts/e01-provenance-probe-review-v1.json",
        "producer": "scripts/e01_provenance_probe_review.py",
        "reviewed_decision": "DEC-014",
        "status": "PASS",
        "decision": "ACCEPT_PROVENANCE_ONLY_E01_SCREENING_BLOCKED",
        "inputs": {
            "request": {
                "path": "configs/e01_provenance_probe_request_v2.json",
                "sha256": EXPECTED["request_sha256"],
                "authorized_request_sha256": EXPECTED["authorized_request_sha256"],
                "authorization_consumed": True,
            },
            "decision": {
                "path": "docs/decisions/DEC-014_E01_SOURCE_SCHEMA_RECONCILED.md",
                "sha256": EXPECTED["decision_sha256"],
            },
            "dry_run": {
                "path": "reports/artifacts/e01a-public-replay-dry-run-v1.json",
                "sha256": EXPECTED["dry_run_sha256"],
            },
            "reconciliation": {
                "path": "reports/artifacts/e01-source-schema-reconciliation-v1.json",
                "sha256": EXPECTED["reconciliation_sha256"],
            },
            "raw_reconciliation": {
                "path": "reports/artifacts/raw/e01-public-source-schema-reconciliation-raw-v1.json",
                "sha256": EXPECTED["raw_reconciliation_sha256"],
            },
            "card_data": {
                "path": "private/assets/official/EN_Card_Data.csv",
                "sha256": EXPECTED["card_data_sha256"],
            },
            "replay": {
                "path": "private/g3/e01/provenance-probe-v1/87703034.json",
                "bytes": EXPECTED["replay_bytes"],
                "sha256": EXPECTED["replay_sha256"],
            },
        },
        "transfer": {
            "dataset_owner": request["dataset"]["owner_slug"],
            "dataset_slug": request["dataset"]["dataset_slug"],
            "dataset_version": request["dataset"]["version"],
            "files_downloaded": 1,
            "bytes_downloaded": EXPECTED["replay_bytes"],
            "agent_logs_downloaded": 0,
            "additional_replays_downloaded": 0,
            "overwrite_used": False,
        },
        "replay_contract": {
            "episode_id": info["EpisodeId"],
            "internal_id": replay["id"],
            "schema_version": replay["schema_version"],
            "module_version": replay["module_version"],
            "environment_name": replay["name"],
            "environment_version": replay["version"],
            "top_level_keys": top_level_keys,
            "team_names": team_names,
            "terminal_statuses": replay["statuses"],
            "terminal_rewards": replay["rewards"],
        },
        "submission_binding": {
            "episode_and_team_names_match_public_metadata": True,
            "submission_ids_present_in_replay_body": False,
            "submission_ids_available_from_reconciled_public_metadata": True,
            "player_0_submission_id": 54_933_084,
            "player_1_submission_id": 54_775_633,
        },
        "policy_identity": {
            "policy_id_present": False,
            "agent_version_present": False,
            "only_environment_module_version_present": True,
        },
        "decks": deck_reports,
        "legality": {
            "current_asset_construction_compatibility": "PASS",
            "exact_historical_engine_card_mapping_available": False,
            "exact_historical_legality": "UNPROVEN",
            "reason": "Replay module version 1.32.2 has no accepted exact engine/card-asset mapping.",
        },
        "action_aligned_supervision": {
            "availability": "PASS",
            **alignment,
            "raw_step_exported": False,
            "raw_action_sequence_exported": False,
            "raw_observation_exported": False,
            "training_labels_created": False,
        },
        "qualification": {
            "provenance_probe_passed": True,
            "exact_deck_hashes_recovered": True,
            "action_aligned_supervision_available": True,
            "teacher_strength_qualified": False,
            "policy_consistency_qualified": False,
            "exact_historical_deck_legality_qualified": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": (
            "PREPARE_A_SEPARATELY_APPROVED_SAME_SUBMISSION_MULTI_EPISODE_SCREENING_REQUEST"
        ),
        "cost_usd": 0.0,
    }
    report["review_sha256"] = canonical_sha256(
        {key: value for key, value in report.items() if key != "review_sha256"}
    )
    return report


def main() -> int:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
