from __future__ import annotations

import importlib.util
import json
import stat
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v3.py"
BUILDER = ROOT / "scripts/kaggle/build_e01_production_recurrent_bc_notebook_v3.py"


def load_module():
    spec = importlib.util.spec_from_file_location("e01_notebook", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_has_standard_training_guards_without_approval_receipt() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert "--approval-receipt" not in source
    assert "notebook-request-sha256" not in source
    assert "verify_selected_replays" not in source
    assert "expected_package_sha256" not in source
    assert "MAXIMUM_EPOCHS = 4" in source
    assert "MAXIMUM_OPTIMIZER_STEPS = 844" in source
    assert "MAXIMUM_WALL_SECONDS = 21_600" in source
    assert "test_replay_bodies_read" in source


def test_builder_embeds_code_and_request_without_approval_receipt() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    assert "approval" not in source.lower()
    assert "IMPLEMENTATION" in source
    assert "REQUEST" in source
    assert "--implementation-source" in source
    assert "--request-source" in source


def test_checkpoint_reconstruction_uses_canonical_metadata() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        member_dir = root / module.CHECKPOINT_DIRECTORY
        member_dir.mkdir(parents=True)
        for index, name in enumerate(module.CHECKPOINT_MEMBERS):
            (member_dir / name).write_bytes(f"member-{index}".encode("utf-8"))
        checkpoint = module.ensure_checkpoint_package(root)
        assert checkpoint.is_file()
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


def test_request_and_wrapper_share_six_hour_wall_cap() -> None:
    module = load_module()
    request = json.loads(
        (ROOT / "configs/e01_production_recurrent_bc_request_v2.json").read_text(encoding="utf-8")
    )
    assert module.MAXIMUM_WALL_SECONDS == 21_600
    assert request["execution"]["maximum_wall_seconds"] == module.MAXIMUM_WALL_SECONDS


def test_training_module_exposes_direct_runtime_entrypoint() -> None:
    from ptcg_rl.g3.bc_production_v2 import execute_training

    assert callable(execute_training)
