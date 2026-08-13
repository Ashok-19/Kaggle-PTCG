from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERSECTION = (
    ROOT
    / ".chatgpt/scratch/live-gold-refresh-20260804/"
    "submission-55186239-intersection.json"
)
SelectionMode = Literal["win", "loss", "opposite", "any"]


def _result_matches(first: dict, second: dict, result: SelectionMode) -> bool:
    first_reward = float(first["teacher_reward"])
    second_reward = float(second["teacher_reward"])
    if result == "win":
        return first_reward == 1.0 and second_reward == 1.0
    if result == "loss":
        return first_reward == -1.0 and second_reward == -1.0
    if result == "opposite":
        return first_reward != second_reward
    return True


def selection_rule(result: SelectionMode) -> str:
    suffix = {
        "win": "both teacher terminal rewards +1",
        "loss": "both teacher terminal rewards -1",
        "opposite": "opposite teacher terminal results",
        "any": "any teacher terminal results",
    }[result]
    return (
        "Minimum total manifest bytes among exact-intersection pairs with "
        f"opposite teacher seats and {suffix}."
    )


def select_pair(items: list[dict], result: SelectionMode) -> list[dict]:
    pairs: list[tuple[int, int, int, dict, dict]] = []
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            if int(first["teacher_index"]) == int(second["teacher_index"]):
                continue
            if not _result_matches(first, second, result):
                continue
            ordered = sorted((first, second), key=lambda item: int(item["episode_id"]))
            pairs.append(
                (
                    int(ordered[0]["manifest_size_bytes"])
                    + int(ordered[1]["manifest_size_bytes"]),
                    int(ordered[0]["episode_id"]),
                    int(ordered[1]["episode_id"]),
                    ordered[0],
                    ordered[1],
                )
            )
    if not pairs:
        raise ValueError(
            f"no opposite-seat pair satisfies selection result mode {result!r}"
        )
    pairs.sort(key=lambda value: value[:3])
    return [pairs[0][3], pairs[0][4]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select the smallest exact opposite-seat replay probe."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INTERSECTION,
        help="Metadata-only exact-intersection JSON file.",
    )
    parser.add_argument(
        "--result",
        choices=("win", "loss", "opposite", "any"),
        default="opposite",
        help="Required teacher terminal-result relation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    items = json.loads(args.input.read_text(encoding="utf-8"))
    selected = select_pair(items, args.result)
    total_bytes = sum(int(item["manifest_size_bytes"]) for item in selected)
    print(
        json.dumps(
            {
                "selection_mode": args.result,
                "selection_rule": selection_rule(args.result),
                "total_bytes": total_bytes,
                "episodes": selected,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
