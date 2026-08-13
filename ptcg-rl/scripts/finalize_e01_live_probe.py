from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from e01_select_balanced_probe import select_pair, selection_rule

ROOT = Path(__file__).resolve().parents[1]
INTERSECTION = (
    ROOT
    / ".chatgpt/scratch/live-gold-refresh-20260804/"
    "submission-55186239-intersection.json"
)
LIVE = ROOT / "reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json"
REQUEST = ROOT / "configs/e01_majkel_live_gold_teacher_probe_request_v1.json"
LATEST_SNAPSHOT_UTC = "2026-08-04T10:40:05Z"
LATEST_TOP_FIVE = [
    {
        "rank": 1,
        "team_name": "Majkel1337",
        "team_id": 16374395,
        "score": 1253.6,
        "active_submission_id": 55186239,
        "active_submission_created_at_utc": "2026-08-02T12:57:04.700Z",
    },
    {
        "rank": 2,
        "team_name": "M Sato",
        "team_id": 16385817,
        "score": 1198.4,
        "active_submission_id": 55198468,
        "active_submission_created_at_utc": "2026-08-03T04:09:37.453Z",
    },
    {
        "rank": 3,
        "team_name": "Raihan Ramadistra",
        "team_id": 16422241,
        "score": 1182.4,
        "active_submission_id": 55177269,
        "active_submission_created_at_utc": "2026-08-02T03:50:05.370Z",
    },
    {
        "rank": 4,
        "team_name": "ntumlnoob",
        "team_id": 16536318,
        "score": 1159.8,
        "active_submission_id": 55184021,
        "active_submission_created_at_utc": "2026-08-02T09:45:53.100Z",
    },
    {
        "rank": 5,
        "team_name": "AlphaStarmie",
        "team_id": 16381823,
        "score": 1146.6,
        "active_submission_id": 54773249,
        "active_submission_created_at_utc": "2026-07-10T10:30:30.083Z",
    },
]


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


def self_hash(value: dict, field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    return canonical_hash(payload)


def main() -> int:
    items = json.loads(INTERSECTION.read_text(encoding="utf-8"))
    selected = select_pair(items, "win")
    selected_ids = [int(item["episode_id"]) for item in selected]
    total_bytes = sum(int(item["manifest_size_bytes"]) for item in selected)
    if selected_ids != [89651832, 89802438]:
        raise ValueError(f"balanced winning probe identity differs: {selected_ids}")
    if total_bytes != 832_877:
        raise ValueError(f"balanced winning probe bytes differ: {total_bytes}")

    live = json.loads(LIVE.read_text(encoding="utf-8"))
    live["latest_leaderboard_snapshot"] = {
        "fetched_at_utc": LATEST_SNAPSHOT_UTC,
        "scores_are_dynamic_snapshot_only": True,
        "stable_authorization_basis": [
            "team_id",
            "active_submission_id",
            "dataset owner/slug/version",
            "exact episode IDs",
            "exact declared byte caps",
        ],
        "top_five": LATEST_TOP_FIVE,
        "notes": [
            "Simulation ratings changed during adjacent authenticated endpoint calls.",
            "The exact source inventory and intersections remain bound to the earlier immutable inventory snapshot and stable submission IDs.",
            "AlphaStarmie entered the displayed top five after the exact inventory snapshot; its active submission identity was refreshed, but no new replay body was retrieved and no exact Alpha intersection is asserted by this artifact.",
        ],
    }
    live["daily_dataset"]["manifest_rows_without_json_body"] = 4
    live["daily_dataset"]["source_ready_json_files"] = 4720
    live["daily_dataset"]["intersection_basis"] = (
        "Available JSON filenames only; four manifest metadata rows have no matching JSON file."
    )
    live["smallest_balanced_winning_probe"] = {
        "episode_ids": selected_ids,
        "episodes": selected,
        "teacher_rewards": [float(item["teacher_reward"]) for item in selected],
        "teacher_seats": [int(item["teacher_index"]) for item in selected],
        "total_bytes": total_bytes,
        "selection_rule": selection_rule("win"),
    }
    live["evidence_sha256"] = self_hash(live, "evidence_sha256")
    LIVE.write_text(
        json.dumps(live, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    request["created_at_utc"] = LATEST_SNAPSHOT_UTC
    request["purpose"] = (
        "Smallest exact opposite-seat, both-winning current-rank-1 source probe "
        "for identity, module, exact deck, current-card compatibility, and "
        "lag-aligned action-contract review only."
    )
    request["selection"] = {
        "method": selection_rule("win"),
        "selection_mode": "win",
        "selection_sha256": canonical_hash(selected),
        "episodes": [
            {
                "episode_id": int(item["episode_id"]),
                "file_name": f"{item['episode_id']}.json",
                "declared_bytes": int(item["manifest_size_bytes"]),
                "create_time_utc": item["create_time"],
                "end_time_utc": item["end_time"],
                "teacher_index": int(item["teacher_index"]),
                "teacher_reward": float(item["teacher_reward"]),
                "opponents": item["opponents"],
            }
            for item in selected
        ],
        "maximum_new_files": 2,
        "maximum_new_bytes": total_bytes,
    }
    request["source"].pop("live_rank", None)
    request["source"].pop("live_score", None)
    request["source"]["leaderboard_snapshot"] = {
        "fetched_at_utc": LATEST_SNAPSHOT_UTC,
        "rank": 1,
        "score": 1253.6,
        "score_is_snapshot_only": True,
        "score_is_authorization_basis": False,
    }
    request["source"]["available_json_file_count"] = 4720
    request["source"]["manifest_metadata_row_count"] = 4724
    request["source"]["manifest_rows_without_json_body"] = 4
    REQUEST.write_text(
        json.dumps(request, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "episode_ids": selected_ids,
                "total_bytes": total_bytes,
                "selection_sha256": request["selection"]["selection_sha256"],
                "live_evidence_sha256": live["evidence_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
