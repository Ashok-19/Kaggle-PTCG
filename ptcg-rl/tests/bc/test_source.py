from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import pytest

from ptcg_rl.bc.source import (
    BCSourceError,
    archive_inventory,
    build_source_catalog,
    extract_selected_episodes,
    load_daily_index,
    select_archive_entries,
)


def _write_index(path: Path, *, episode_count: int, total_bytes: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "daily_dataset_slug",
                "daily_dataset_url",
                "episode_count",
                "total_bytes",
                "top_avg_score",
                "median_avg_score",
            ]
        )
        writer.writerow(
            [
                "2026-08-13",
                "pokemon-tcg-ai-battle-episodes-2026-08-13",
                "https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-08-13",
                str(episode_count),
                str(total_bytes),
                "1262.3",
                "1038.2",
            ]
        )


def _replay(episode_id: int, winner: int) -> bytes:
    rewards = [1, -1] if winner == 0 else [-1, 1]
    rows = [
        [
            {
                "action": [],
                "observation": {"select": None},
                "reward": 0,
                "status": "ACTIVE",
            },
            {
                "action": [],
                "observation": {"select": None},
                "reward": 0,
                "status": "ACTIVE",
            },
        ],
        [
            {
                "action": list(range(1, 61)),
                "observation": {"select": {"type": 9}},
                "reward": 0,
                "status": "ACTIVE" if winner == 0 else "INACTIVE",
            },
            {
                "action": list(range(61, 121)),
                "observation": {"select": {"type": 9}},
                "reward": 0,
                "status": "ACTIVE" if winner == 1 else "INACTIVE",
            },
        ],
        [
            {
                "action": [0] if winner == 0 else [],
                "observation": {"select": None},
                "reward": rewards[0],
                "status": "DONE",
            },
            {
                "action": [0] if winner == 1 else [],
                "observation": {"select": None},
                "reward": rewards[1],
                "status": "DONE",
            },
        ],
    ]
    return json.dumps(
        {
            "id": f"internal-{episode_id}",
            "info": {"EpisodeId": episode_id, "TeamNames": ["alpha", "beta"]},
            "module_version": "1.32.4",
            "rewards": rewards,
            "statuses": ["DONE", "DONE"],
            "steps": rows,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def test_archive_catalog_selection_and_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "daily.zip"
    bodies = {101: _replay(101, 0), 102: _replay(102, 1), 103: _replay(103, 0)}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("manifest.csv", "episode_id\n101\n102\n103\n")
        for episode_id, raw in bodies.items():
            handle.writestr(f"{episode_id}.json", raw)
    index = tmp_path / "manifest.csv"
    _write_index(index, episode_count=3, total_bytes=sum(map(len, bodies.values())))

    sources = load_daily_index(index)
    assert len(sources) == 1
    inventory = archive_inventory(archive)
    assert [item.episode_id for item in inventory] == [101, 102, 103]
    assert select_archive_entries(inventory, count=2, seed=7) == select_archive_entries(
        inventory, count=2, seed=7
    )

    catalog = build_source_catalog(index, local_archives={"2026-08-13": archive})
    assert catalog["days"] == 1
    assert catalog["episodes"] == 3
    assert catalog["daily_sources"][0]["local_archive"]["episodes"] == 3

    selected = select_archive_entries(inventory, count=2, seed=11)
    records = extract_selected_episodes(
        archive,
        tmp_path / "episodes",
        selected,
        date="2026-08-13",
        split_seed=19,
    )
    assert len(records) == 2
    assert all(record.teacher_result == "win" for record in records)
    assert all(record.teacher_active_requests == 1 for record in records)
    assert {record.teacher_player_index for record in records} <= {0, 1}
    assert all((tmp_path / "episodes" / record.path).is_file() for record in records)


def test_index_rejects_slug_date_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    _write_index(path, episode_count=1, total_bytes=1)
    text = path.read_text(encoding="utf-8").replace("episodes-2026-08-13", "episodes-2026-08-12")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BCSourceError):
        load_daily_index(path)
