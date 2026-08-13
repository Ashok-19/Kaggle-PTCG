from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ptcg_rl.g3.bc_production_v2 import (
    ChunkRef,
    build_balanced_schedule,
    metadata_schedule_bound,
    retained_publication_records,
    training_records,
    validate_publication_request,
    validate_retained_dataset_remediation_request,
    validate_training_request,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v3.json"
PUBLICATION_REQUEST = ROOT / "configs/e01_production_bc_input_publication_request_v1.json"
REMEDIATION_REQUEST = ROOT / "configs/e01_production_bc_retained_dataset_remediation_request_v1.json"
TRAINING_REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_publication_selection_is_exact_and_excludes_test() -> None:
    records = retained_publication_records(_manifest())
    assert len(records) == 58
    assert sum(item["bytes"] for item in records) == 341_559_745
    assert Counter(item["split"] for item in records) == Counter({"train": 50, "validation": 8})
    assert Counter(item["teacher_key"] for item in records) == Counter({"flg": 48, "dries": 10})
    assert all(item["dataset_path"] == f"episodes/{item['episode_id']}.json" for item in records)
    assert not any(item["split"] == "test" for item in records)


def test_training_selection_and_metadata_step_cap_are_exact() -> None:
    records = training_records(_manifest())
    assert len(records) == 316
    assert Counter(item["split"] for item in records) == Counter({"train": 284, "validation": 32})
    assert Counter(item["source"] for item in records) == Counter(
        {"august_3_daily": 237, "retained_private": 58, "august_4_daily": 21}
    )
    assert sum(item["policy_loss_targets"] for item in records if item["split"] == "train") == 19_646
    assert sum(item["policy_loss_targets"] for item in records if item["split"] == "validation") == 2_318
    assert metadata_schedule_bound(records, 32) == {
        "legacy_chunk_upper": 211,
        "primary_stratum_chunk_upper_max": 206,
        "balanced_steps_per_epoch_upper": 211,
    }
    retained = [item for item in records if item["source"] == "retained_private"]
    assert len(retained) == 58
    assert all(item["dataset_path"] == f"{item['episode_id']}.json" for item in retained)
    assert not any(item["split"] == "test" for item in records)


def test_balanced_schedule_is_deterministic_four_primary_plus_one_legacy() -> None:
    chunks: list[ChunkRef] = []
    for index, stratum in enumerate(("seat_0_loss", "seat_0_win", "seat_1_loss", "seat_1_win")):
        chunks.extend(
            ChunkRef(
                episode_index=index,
                episode_id=100 + index * 10 + offset,
                teacher_key="majkel",
                stratum=stratum,
                start=offset * 32,
            )
            for offset in range(index + 1)
        )
    chunks.extend(
        ChunkRef(
            episode_index=10,
            episode_id=200 + offset,
            teacher_key="flg" if offset % 2 == 0 else "dries",
            stratum="seat_0_loss",
            start=offset * 32,
        )
        for offset in range(5)
    )
    first = build_balanced_schedule(chunks, seed=20260805, epochs=4)
    second = build_balanced_schedule(chunks, seed=20260805, epochs=4)
    assert first == second
    assert len(first) == 4
    assert all(len(epoch) == 5 for epoch in first)
    for epoch in first:
        for batch in epoch:
            assert len(batch) == 5
            assert [item.teacher_key for item in batch[:4]] == ["majkel"] * 4
            assert [item.stratum for item in batch[:4]] == [
                "seat_0_loss",
                "seat_0_win",
                "seat_1_loss",
                "seat_1_win",
            ]
            assert batch[4].teacher_key in {"flg", "dries"}


def test_canonical_requests_validate_without_replay_access() -> None:
    publication = validate_publication_request(ROOT, PUBLICATION_REQUEST)
    remediation = validate_retained_dataset_remediation_request(ROOT, REMEDIATION_REQUEST)
    training = validate_training_request(ROOT, TRAINING_REQUEST)
    assert publication.request["status"] == "READY_UNAUTHORIZED"
    assert remediation["status"] == "READY_UNAUTHORIZED"
    assert remediation["dataset"]["dataset_id"] == 11_514_316
    assert remediation["dataset"]["path_contract"] == "root_basename"
    assert training.request["status"] == "READY_UNAUTHORIZED"
    assert training.request["corpus"]["test_episodes_sealed"] == 46
    assert training.request["authorization"]["training"] is False
    assert training.request["authorization"]["optimizer_steps"] is False
