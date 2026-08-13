from __future__ import annotations

import importlib.util
import stat
import tempfile
import zipfile
from pathlib import Path

from ptcg_rl.g3.bc_production_v2 import STRATA, select_smoke_records

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/kaggle/e01_recurrent_bc_smoke_notebook.py"
BUILDER = ROOT / "scripts/kaggle/build_e01_recurrent_bc_smoke_notebook.py"


def test_smoke_wrapper_is_bounded_and_has_no_approval_plumbing() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert "MAXIMUM_EPOCHS = 1" in source
    assert "MAXIMUM_OPTIMIZER_STEPS = 32" in source
    assert "approval" not in source.lower()
    assert "sha256" not in source.lower()
    assert "smoke_sample=True" in source
    assert "test_replay_bodies_read" in source


def test_smoke_builder_embeds_only_runtime_sources() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    assert "approval" not in source.lower()
    assert "IMPLEMENTATION" in source
    assert "REQUEST" in source
    assert "WRAPPER" in source


def test_smoke_selection_preserves_primary_strata_and_legacy() -> None:
    records = []
    episode_id = 1
    for stratum in STRATA:
        records.append({"episode_id": episode_id, "split": "train", "teacher_key": "majkel", "stratum": stratum})
        episode_id += 1
    records.extend(
        [
            {"episode_id": 10, "split": "train", "teacher_key": "flg", "stratum": "seat_0_win"},
            {"episode_id": 11, "split": "train", "teacher_key": "dries", "stratum": "seat_1_loss"},
            {"episode_id": 20, "split": "validation", "teacher_key": "majkel", "stratum": "seat_0_win"},
            {"episode_id": 21, "split": "validation", "teacher_key": "majkel", "stratum": "seat_1_win"},
        ]
    )
    selected = select_smoke_records(records, validation_episode_limit=1)
    selected_train = [item for item in selected if item["split"] == "train"]
    assert {item["stratum"] for item in selected_train if item["teacher_key"] == "majkel"} == set(STRATA)
    assert {item["teacher_key"] for item in selected_train if item["teacher_key"] != "majkel"} == {"flg", "dries"}
    assert sum(item["split"] == "validation" for item in selected) == 1


def test_smoke_wrapper_imports() -> None:
    spec = importlib.util.spec_from_file_location("e01_recurrent_bc_smoke_notebook", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MAXIMUM_EPOCHS == 1
    assert module.MAXIMUM_OPTIMIZER_STEPS == 32


def test_checkpoint_reconstruction_uses_canonical_zip_metadata() -> None:
    spec = importlib.util.spec_from_file_location("e01_recurrent_bc_smoke_notebook_zip", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        member_dir = root / module.CHECKPOINT_DIRECTORY
        member_dir.mkdir(parents=True)
        for index, name in enumerate(module.CHECKPOINT_MEMBERS):
            (member_dir / name).write_bytes(f"member-{index}".encode("utf-8"))
        checkpoint = module.ensure_checkpoint_package(root)
        with zipfile.ZipFile(checkpoint) as archive:
            infos = archive.infolist()
            assert [info.filename for info in infos] == sorted(module.CHECKPOINT_MEMBERS)
            for info in infos:
                assert info.date_time == module.CHECKPOINT_TIMESTAMP
                assert info.compress_type == zipfile.ZIP_STORED
                assert info.create_system == 3
                assert info.internal_attr == 0
                assert info.flag_bits == 0
                assert info.external_attr >> 16 == (stat.S_IFREG | 0o600)
