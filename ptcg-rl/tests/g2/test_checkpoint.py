from __future__ import annotations

import json
import stat
import struct
import warnings
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import pytest
import torch

from ptcg_rl.g2.card_table import write_card_table
from ptcg_rl.g2.checkpoint import (
    ARCHIVE_MODE,
    ARCHIVE_TIMESTAMP,
    CHECKPOINT_ATOL,
    CheckpointError,
    build_checkpoint_package,
    build_checkpoint_reference,
    canonical_json_bytes,
    decode_state_dict,
    encode_state_dict,
    load_checkpoint_package,
    state_dict_sha256,
    verify_checkpoint_reference,
    verify_source_tree,
)
from ptcg_rl.g2.network import PTCGPolicyV1

from .test_card_table import build_fixture
from .test_network import card_decision, number_decision

SOURCE_COMMIT = "1" * 40
EVIDENCE_SHA256 = "2" * 64


def write_archive(
    path: Path,
    entries: list[tuple[str, bytes, int, int, tuple[int, int, int, int, int, int]]],
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw, compression, mode, timestamp in entries:
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = compression
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, raw, compress_type=compression)


def read_entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def exact_entries(
    values: dict[str, bytes],
    *,
    order: list[str] | None = None,
    compression: dict[str, int] | None = None,
    modes: dict[str, int] | None = None,
    timestamps: dict[str, tuple[int, int, int, int, int, int]] | None = None,
) -> list[tuple[str, bytes, int, int, tuple[int, int, int, int, int, int]]]:
    order = order or sorted(values)
    compression = compression or {}
    modes = modes or {}
    timestamps = timestamps or {}
    return [
        (
            name,
            values[name],
            compression.get(name, zipfile.ZIP_STORED),
            modes.get(name, ARCHIVE_MODE),
            timestamps.get(name, ARCHIVE_TIMESTAMP),
        )
        for name in order
    ]


@pytest.fixture
def checkpoint_fixture(tmp_path: Path) -> dict[str, object]:
    table = build_fixture(tmp_path / "cards.csv")
    table_path = tmp_path / "card-table-v1.json"
    write_card_table(table, table_path)
    model = PTCGPolicyV1(table)
    decisions = (number_decision(5)[2], card_decision())
    reference = build_checkpoint_reference(model, decisions, fixture_id="unit-checkpoint-v1")
    source_root = tmp_path / "source"
    (source_root / "src").mkdir(parents=True)
    (source_root / "src/a.py").write_text("a = 1\n", encoding="utf-8")
    (source_root / "src/b.py").write_text("b = 2\n", encoding="utf-8")
    source_files = {
        "src/b.py": (source_root / "src/b.py").read_bytes(),
        "src/a.py": (source_root / "src/a.py").read_bytes(),
    }
    package = tmp_path / "checkpoint.zip"
    result = build_checkpoint_package(
        package,
        model,
        table_path.read_bytes(),
        reference,
        SOURCE_COMMIT,
        source_files,
        "reports/evaluations/test.json",
        EVIDENCE_SHA256,
        artifact_id="test-checkpoint-v1",
    )
    return {
        "table_path": table_path,
        "model": model,
        "decisions": decisions,
        "reference": reference,
        "source_root": source_root,
        "source_files": source_files,
        "package": package,
        "result": result,
    }


def test_state_format_is_order_independent_pickle_free_and_exact(
    checkpoint_fixture: dict[str, object],
) -> None:
    model = checkpoint_fixture["model"]
    assert isinstance(model, PTCGPolicyV1)
    state = model.state_dict()
    first_raw, first_records = encode_state_dict(state)
    reversed_state = OrderedDict(reversed(list(state.items())))
    second_raw, second_records = encode_state_dict(reversed_state)
    assert first_raw == second_raw
    assert first_records == second_records
    assert state_dict_sha256(state) == state_dict_sha256(reversed_state)
    assert b"PK\x03\x04" not in first_raw
    loaded, loaded_records = decode_state_dict(first_raw)
    assert loaded_records == first_records
    assert set(loaded) == set(state)
    for name in state:
        assert torch.equal(loaded[name], state[name].detach().cpu())


def test_reference_restores_mode_and_replays_actor_value_memory_decoder_and_logprob(
    checkpoint_fixture: dict[str, object],
) -> None:
    model = checkpoint_fixture["model"]
    decisions = checkpoint_fixture["decisions"]
    reference = checkpoint_fixture["reference"]
    assert isinstance(model, PTCGPolicyV1)
    assert isinstance(decisions, tuple)
    assert isinstance(reference, dict)
    model.train()
    rebuilt = build_checkpoint_reference(model, decisions, fixture_id="unit-checkpoint-v1")
    assert model.training is True
    assert rebuilt == reference
    assert reference["tolerance"] == {"atol": CHECKPOINT_ATOL, "rtol": 0.0}
    assert reference["action_trace"]["selected_option_indices"] == [0]
    assert reference["action_trace"]["stop_selected"] is True
    assert len(reference["action_trace"]["step_log_probabilities"]) == 2
    stats = verify_checkpoint_reference(model, decisions, reference)
    assert stats == {
        "status": "PASS",
        "numeric_values": stats["numeric_values"],
        "exact_values": stats["exact_values"],
        "max_abs_diff": 0.0,
        "max_abs_diff_path": None,
    }
    assert stats["numeric_values"] > 100
    assert stats["exact_values"] > 0


def test_package_is_deterministic_and_loads_with_strict_source_verification(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    package = checkpoint_fixture["package"]
    result = checkpoint_fixture["result"]
    model = checkpoint_fixture["model"]
    reference = checkpoint_fixture["reference"]
    source_files = checkpoint_fixture["source_files"]
    table_path = checkpoint_fixture["table_path"]
    source_root = checkpoint_fixture["source_root"]
    decisions = checkpoint_fixture["decisions"]
    assert isinstance(package, Path)
    assert isinstance(result, dict)
    assert isinstance(model, PTCGPolicyV1)
    assert isinstance(reference, dict)
    assert isinstance(source_files, dict)
    assert isinstance(table_path, Path)
    assert isinstance(source_root, Path)
    assert isinstance(decisions, tuple)

    duplicate = tmp_path / "duplicate.zip"
    reversed_sources = dict(reversed(list(source_files.items())))
    duplicate_result = build_checkpoint_package(
        duplicate,
        model,
        table_path.read_bytes(),
        reference,
        SOURCE_COMMIT,
        reversed_sources,
        "reports/evaluations/test.json",
        EVIDENCE_SHA256,
        artifact_id="test-checkpoint-v1",
    )
    assert package.read_bytes() == duplicate.read_bytes()
    assert result == duplicate_result
    assert result["package_bytes"] < 64 * 1024 * 1024
    loaded = load_checkpoint_package(
        package,
        expected_package_sha256=result["package_sha256"],
        expected_source_commit=SOURCE_COMMIT,
        source_root=source_root,
    )
    assert loaded.model.training is False
    assert loaded.package_bytes == result["package_bytes"]
    assert loaded.package_sha256 == result["package_sha256"]
    assert loaded.manifest["authorization"] == {
        "optimizer_included": False,
        "pickle_used": False,
        "training_loop_ran": False,
        "training_state_included": False,
    }
    assert verify_checkpoint_reference(loaded.model, decisions, loaded.reference)["status"] == "PASS"


def test_expected_identity_and_source_tree_fail_closed(
    checkpoint_fixture: dict[str, object]
) -> None:
    package = checkpoint_fixture["package"]
    result = checkpoint_fixture["result"]
    source_root = checkpoint_fixture["source_root"]
    assert isinstance(package, Path)
    assert isinstance(result, dict)
    assert isinstance(source_root, Path)
    with pytest.raises(CheckpointError, match="package SHA-256"):
        load_checkpoint_package(package, expected_package_sha256="0" * 64)
    with pytest.raises(CheckpointError, match="source commit"):
        load_checkpoint_package(package, expected_source_commit="3" * 40)
    source_file = source_root / "src/a.py"
    source_file.write_text("changed\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="source file differs"):
        load_checkpoint_package(package, source_root=source_root)
    source_file.write_text("a = 1\n", encoding="utf-8")
    source_file.unlink()
    source_file.symlink_to(source_root / "src/b.py")
    with pytest.raises(CheckpointError, match="symlink"):
        load_checkpoint_package(package, source_root=source_root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "entries differ"),
        ("extra", "entries differ"),
        ("duplicate", "duplicate"),
        ("compressed", "uncompressed"),
        ("symlink", "mode differs"),
        ("mode", "mode differs"),
        ("timestamp", "timestamp differs"),
        ("unsorted", "not sorted"),
    ],
)
def test_archive_structure_mutations_fail_closed(
    checkpoint_fixture: dict[str, object], tmp_path: Path, mutation: str, message: str
) -> None:
    package = checkpoint_fixture["package"]
    assert isinstance(package, Path)
    values = read_entries(package)
    path = tmp_path / f"{mutation}.zip"
    entries = exact_entries(values)
    if mutation == "missing":
        entries = [entry for entry in entries if entry[0] != "reference-v1.json"]
    elif mutation == "extra":
        values["../escape"] = b"x"
        entries = exact_entries(values)
    elif mutation == "duplicate":
        entries.append(next(entry for entry in entries if entry[0] == "state-v1.bin"))
    elif mutation == "compressed":
        entries = exact_entries(values, compression={"state-v1.bin": zipfile.ZIP_DEFLATED})
    elif mutation == "symlink":
        entries = exact_entries(values, modes={"state-v1.bin": stat.S_IFLNK | 0o777})
    elif mutation == "mode":
        entries = exact_entries(values, modes={"state-v1.bin": stat.S_IFREG | 0o644})
    elif mutation == "timestamp":
        entries = exact_entries(values, timestamps={"state-v1.bin": (2026, 1, 1, 0, 0, 0)})
    elif mutation == "unsorted":
        entries = exact_entries(values, order=list(reversed(sorted(values))))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_archive(path, entries)
    with pytest.raises(CheckpointError, match=message):
        load_checkpoint_package(path)


def rewrite_manifest_package(
    source: Path,
    destination: Path,
    transform: Callable[[dict[str, object], dict[str, bytes]], None],
) -> None:
    values = read_entries(source)
    manifest = json.loads(values["manifest.json"])
    transform(manifest, values)
    values["manifest.json"] = canonical_json_bytes(manifest)
    write_archive(destination, exact_entries(values))


def test_noncanonical_and_unknown_manifest_fields_fail_closed(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    package = checkpoint_fixture["package"]
    assert isinstance(package, Path)
    values = read_entries(package)
    manifest = json.loads(values["manifest.json"])
    values["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    noncanonical = tmp_path / "noncanonical.zip"
    write_archive(noncanonical, exact_entries(values))
    with pytest.raises(CheckpointError, match="not canonical"):
        load_checkpoint_package(noncanonical)

    unknown = tmp_path / "unknown.zip"

    def add_unknown(value: dict[str, object], _: dict[str, bytes]) -> None:
        value["unexpected"] = True

    rewrite_manifest_package(package, unknown, add_unknown)
    with pytest.raises(CheckpointError, match="keys differ"):
        load_checkpoint_package(unknown)


def test_manifest_config_schema_and_authorization_tampering_fail_closed(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    package = checkpoint_fixture["package"]
    assert isinstance(package, Path)
    cases: list[tuple[str, Callable[[dict[str, object], dict[str, bytes]], None], str]] = []

    def bad_config_hash(value: dict[str, object], _: dict[str, bytes]) -> None:
        value["model"]["config_sha256"] = "0" * 64  # type: ignore[index]

    def bad_schema(value: dict[str, object], _: dict[str, bytes]) -> None:
        value["schema_version"] = 99

    def bad_parameter_ceiling(value: dict[str, object], _: dict[str, bytes]) -> None:
        value["model"]["trainable_parameters"] = 2_000_000  # type: ignore[index]

    def bad_authorization(value: dict[str, object], _: dict[str, bytes]) -> None:
        value["authorization"]["optimizer_included"] = True  # type: ignore[index]

    cases.extend(
        [
            ("config", bad_config_hash, "config SHA-256"),
            ("schema", bad_schema, "unsupported checkpoint manifest"),
            ("ceiling", bad_parameter_ceiling, "outside the allowed range"),
            ("authorization", bad_authorization, "no-training contract"),
        ]
    )
    for name, transform, message in cases:
        path = tmp_path / f"manifest-{name}.zip"
        rewrite_manifest_package(package, path, transform)
        with pytest.raises(CheckpointError, match=message):
            load_checkpoint_package(path)


def test_semantically_corrupted_card_table_fails_even_with_updated_file_hash(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    package = checkpoint_fixture["package"]
    assert isinstance(package, Path)
    path = tmp_path / "bad-card-table.zip"

    def corrupt(value: dict[str, object], entries: dict[str, bytes]) -> None:
        table = json.loads(entries["card-table-v1.json"])
        table["table_sha256"] = "0" * 64
        raw = json.dumps(table, indent=2, sort_keys=True).encode() + b"\n"
        entries["card-table-v1.json"] = raw
        value["files"]["card-table-v1.json"] = {  # type: ignore[index]
            "bytes": len(raw),
            "sha256": __import__("hashlib").sha256(raw).hexdigest(),
        }

    rewrite_manifest_package(package, path, corrupt)
    with pytest.raises(CheckpointError, match="card table"):
        load_checkpoint_package(path)


def test_reference_drift_fails_after_internally_consistent_repackage(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    package = checkpoint_fixture["package"]
    decisions = checkpoint_fixture["decisions"]
    assert isinstance(package, Path)
    assert isinstance(decisions, tuple)
    path = tmp_path / "drift.zip"

    def drift(value: dict[str, object], entries: dict[str, bytes]) -> None:
        reference = json.loads(entries["reference-v1.json"])
        reference["action_trace"]["compound_log_probability"] += 0.01
        raw = canonical_json_bytes(reference)
        digest = __import__("hashlib").sha256(raw).hexdigest()
        entries["reference-v1.json"] = raw
        value["files"]["reference-v1.json"] = {"bytes": len(raw), "sha256": digest}  # type: ignore[index]
        value["reference"]["bytes"] = len(raw)  # type: ignore[index]
        value["reference"]["sha256"] = digest  # type: ignore[index]

    rewrite_manifest_package(package, path, drift)
    loaded = load_checkpoint_package(path)
    with pytest.raises(CheckpointError, match="numerical drift"):
        verify_checkpoint_reference(loaded.model, decisions, loaded.reference)


def test_unexpected_state_key_is_rejected_by_strict_model_load(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    model = checkpoint_fixture["model"]
    table_path = checkpoint_fixture["table_path"]
    reference = checkpoint_fixture["reference"]
    source_files = checkpoint_fixture["source_files"]
    assert isinstance(model, PTCGPolicyV1)
    assert isinstance(table_path, Path)
    assert isinstance(reference, dict)
    assert isinstance(source_files, dict)
    model.register_buffer("unexpected_checkpoint_buffer", torch.tensor(1, dtype=torch.int64))
    package = tmp_path / "unexpected-state.zip"
    build_checkpoint_package(
        package,
        model,
        table_path.read_bytes(),
        reference,
        SOURCE_COMMIT,
        source_files,
        "reports/evaluations/test.json",
        EVIDENCE_SHA256,
        artifact_id="test-checkpoint-v1",
    )
    with pytest.raises(CheckpointError, match="cannot load state"):
        load_checkpoint_package(package)


@pytest.mark.parametrize(
    ("raw_factory", "message"),
    [
        (lambda raw: b"X" + raw[1:], "magic"),
        (lambda raw: raw[:-1], "truncated"),
        (lambda raw: raw + b"x", "trailing"),
    ],
)
def test_state_stream_corruption_fails_closed(
    checkpoint_fixture: dict[str, object],
    raw_factory: Callable[[bytes], bytes],
    message: str,
) -> None:
    model = checkpoint_fixture["model"]
    assert isinstance(model, PTCGPolicyV1)
    raw, _ = encode_state_dict(model.state_dict())
    with pytest.raises(CheckpointError, match=message):
        decode_state_dict(raw_factory(raw))


def test_state_stream_rejects_unsupported_nonfinite_and_unsorted_records() -> None:
    with pytest.raises(CheckpointError, match="unsupported"):
        encode_state_dict({"x": torch.tensor([1.0], dtype=torch.float64)})
    with pytest.raises(CheckpointError, match="NaN or infinity"):
        encode_state_dict({"x": torch.tensor([float("nan")])})
    with pytest.raises(CheckpointError, match="NaN or infinity"):
        encode_state_dict({"x": torch.tensor([float("inf")])})
    with pytest.raises(CheckpointError, match="invalid state tensor name"):
        encode_state_dict({"../x": torch.tensor([1.0])})

    def record(name: str) -> bytes:
        name_raw = name.encode()
        data = struct.pack("<f", 1.0)
        return (
            struct.pack("<I", len(name_raw))
            + name_raw
            + struct.pack("<B", 1)
            + struct.pack("<B", 1)
            + struct.pack("<Q", 1)
            + struct.pack("<Q", len(data))
            + data
        )

    stream = b"KPTCG-G2-STATE\x00\x01" + struct.pack("<I", 2) + record("b") + record("a")
    with pytest.raises(CheckpointError, match="strictly sorted"):
        decode_state_dict(stream)


def test_source_paths_reject_noncanonical_and_control_character_forms(
    checkpoint_fixture: dict[str, object], tmp_path: Path
) -> None:
    model = checkpoint_fixture["model"]
    table_path = checkpoint_fixture["table_path"]
    reference = checkpoint_fixture["reference"]
    assert isinstance(model, PTCGPolicyV1)
    assert isinstance(table_path, Path)
    assert isinstance(reference, dict)
    for invalid in ("a//b.py", "a/../b.py", "a\x00b.py", "a\\b.py"):
        with pytest.raises(CheckpointError, match="canonical|safe"):
            build_checkpoint_package(
                tmp_path / "invalid.zip",
                model,
                table_path.read_bytes(),
                reference,
                SOURCE_COMMIT,
                {invalid: b"x"},
                "reports/evaluations/test.json",
                EVIDENCE_SHA256,
            )


def test_verify_source_tree_requires_all_declared_files(
    checkpoint_fixture: dict[str, object]
) -> None:
    result = checkpoint_fixture["result"]
    source_root = checkpoint_fixture["source_root"]
    assert isinstance(result, dict)
    assert isinstance(source_root, Path)
    manifest = result["manifest"]
    assert verify_source_tree(source_root, manifest) == {"status": "PASS", "files": 2}
    (source_root / "src/b.py").unlink()
    with pytest.raises(CheckpointError, match="missing"):
        verify_source_tree(source_root, manifest)
