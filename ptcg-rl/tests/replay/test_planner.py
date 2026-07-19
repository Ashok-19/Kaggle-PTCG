from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from ptcg_rl.replay.planner import (
    PlannerConfig,
    ReplayPlanError,
    build_plan,
    verify_plan,
)


def config(max_files: int = 6, max_total_bytes: int = 10_000) -> PlannerConfig:
    return PlannerConfig.from_mapping(
        {
            "schema_version": 1,
            "planner_version": "test-v1",
            "seed": 17,
            "source_date": "2026-07-18",
            "index_dataset": {
                "owner": "kaggle",
                "slug": "pokemon-tcg-ai-battle-episodes-index",
                "version": 33,
            },
            "daily_dataset": {
                "owner": "kaggle",
                "slug": "pokemon-tcg-ai-battle-episodes-2026-07-18",
                "version": 1,
            },
            "caps": {
                "max_files": max_files,
                "max_total_bytes": max_total_bytes,
                "max_file_bytes": 1_000,
            },
            "quotas": {
                "elite_dual": max_files // 2,
                "elite_avg": max_files // 3,
                "broad_time": max_files - max_files // 2 - max_files // 3,
            },
            "time_blocks": 3,
            "quantiles": {"avg_score": 0.75, "min_score": 0.5},
        }
    )


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_receipt(path: Path, manifest: Path, slug: str, version: int) -> None:
    raw = manifest.read_bytes()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_owner": "kaggle",
                "dataset_slug": slug,
                "dataset_version": version,
                "requested_filename": "manifest.csv",
                "actual_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_at_utc": "2026-07-19T00:00:00Z",
                "provider": "fixture",
            }
        ),
        encoding="utf-8",
    )


def fixture_files(tmp_path: Path, sizes: list[int] | None = None) -> tuple[Path, Path, Path, Path]:
    sizes = sizes or [100] * 12
    daily_rows = []
    for index, size in enumerate(sizes):
        score = 1000 - index
        daily_rows.append(
            {
                "episode_id": str(90000000 + index),
                "create_time": f"2026-07-18T{index:02d}:00:00.0000000",
                "avg_score": score,
                "min_score": score - (index % 4) * 20,
                "sum_score": score * 2,
                "agent_count": 2,
                "size_bytes": size,
            }
        )
    daily = tmp_path / "daily.csv"
    write_csv(
        daily,
        [
            "episode_id",
            "create_time",
            "avg_score",
            "min_score",
            "sum_score",
            "agent_count",
            "size_bytes",
        ],
        daily_rows,
    )
    index = tmp_path / "index.csv"
    write_csv(
        index,
        [
            "date",
            "daily_dataset_slug",
            "daily_dataset_url",
            "episode_count",
            "total_bytes",
            "top_avg_score",
            "median_avg_score",
        ],
        [
            {
                "date": "2026-07-18",
                "daily_dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-07-18",
                "daily_dataset_url": "fixture",
                "episode_count": len(daily_rows),
                "total_bytes": sum(sizes),
                "top_avg_score": 1000,
                "median_avg_score": 995,
            }
        ],
    )
    index_receipt = tmp_path / "index-receipt.json"
    daily_receipt = tmp_path / "daily-receipt.json"
    write_receipt(
        index_receipt,
        index,
        "pokemon-tcg-ai-battle-episodes-index",
        33,
    )
    write_receipt(
        daily_receipt,
        daily,
        "pokemon-tcg-ai-battle-episodes-2026-07-18",
        1,
    )
    return index, index_receipt, daily, daily_receipt


def test_plan_is_deterministic_stratified_and_verifiable(tmp_path: Path) -> None:
    files = fixture_files(tmp_path)
    first = build_plan(config(), *files)
    second = build_plan(config(), *files)
    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["selected_items"] == second["selected_items"]
    assert first["summary"]["selected_files"] == 6
    assert first["summary"]["episode_json_transferred"] == 0
    assert set(item["stratum"] for item in first["selected_items"]) == {
        "elite_dual",
        "elite_avg",
        "broad_time",
    }
    assert verify_plan(first)["status"] == "pass"
    assert len(first["rows"]) == 12
    assert all(row["inclusion_probability"] >= 0 for row in first["rows"])


def test_total_byte_cap_reduces_quota_without_selecting_oversize(tmp_path: Path) -> None:
    sizes = [900, 900, 900, 900, 900, 900, 900, 900, 900, 900, 1_500, 1_500]
    files = fixture_files(tmp_path, sizes)
    plan = build_plan(config(max_files=6, max_total_bytes=2_800), *files)
    assert plan["summary"]["selected_files"] <= 3
    assert plan["summary"]["selected_bytes"] <= 2_800
    assert plan["summary"]["oversize_rows"] == 2
    assert all(item["declared_bytes"] <= 1_000 for item in plan["selected_items"])


def test_receipt_mismatch_fails_closed(tmp_path: Path) -> None:
    index, index_receipt, daily, daily_receipt = fixture_files(tmp_path)
    value = json.loads(daily_receipt.read_text(encoding="utf-8"))
    value["dataset_version"] = 2
    daily_receipt.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ReplayPlanError, match="receipt mismatch"):
        build_plan(config(), index, index_receipt, daily, daily_receipt)


def test_unknown_config_key_is_rejected() -> None:
    value = {
        "schema_version": 1,
        "planner_version": "test",
        "seed": 1,
        "source_date": "2026-07-18",
        "index_dataset": {"owner": "kaggle", "slug": "index", "version": 1},
        "daily_dataset": {
            "owner": "kaggle",
            "slug": "pokemon-tcg-ai-battle-episodes-2026-07-18",
            "version": 1,
        },
        "caps": {"max_files": 1, "max_total_bytes": 10, "max_file_bytes": 10},
        "quotas": {"elite_dual": 1, "elite_avg": 0, "broad_time": 0},
        "time_blocks": 1,
        "quantiles": {"avg_score": 0.8, "min_score": 0.7},
        "unexpected": True,
    }
    with pytest.raises(ReplayPlanError, match="unknown keys"):
        PlannerConfig.from_mapping(value)
