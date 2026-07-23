from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from ptcg_rl.g2.reliability import canonical_json_line, recalculate_reliability

from .test_reliability import valid_game_record


def load_script(root: Path):
    path = root / "scripts/g2_neural_reliability.py"
    spec = importlib.util.spec_from_file_location("g2_neural_reliability_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_worker(worker_id: int, games: int = 1) -> dict[str, Any]:
    return {
        "kind": "worker_done",
        "worker_id": worker_id,
        "server_id": 0,
        "assigned_games": games,
        "completed_games": games,
        "errors": [],
        "wall_seconds": 1.0,
        "peak_rss_mib": 100.0,
    }


def valid_server(
    server_id: int = 0,
    *,
    decisions: int = 2,
    batch_histogram: dict[str, int] | None = None,
) -> dict[str, Any]:
    histogram = batch_histogram or {"2": 1}
    return {
        "kind": "server_done",
        "server_id": server_id,
        "device": "cpu:0",
        "batch_histogram": histogram,
        "inference_calls": sum(histogram.values()),
        "decisions": decisions,
        "total_inference_ms": 5.0,
        "max_batch_inference_ms": 5.0,
        "errors": [],
        "peak_rss_mib": 200.0,
    }


def test_reliability_runner_has_explicit_sorted_source_allowlist() -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    files = module.SOURCE_FILES
    assert isinstance(files, tuple)
    assert files == tuple(sorted(files))
    assert len(files) == len(set(files))
    assert "scripts/g2_neural_reliability.py" in files
    assert "src/ptcg_rl/g2/reliability.py" in files
    assert "src/ptcg_rl/g2/checkpoint.py" in files
    assert all(not item.startswith("private/") for item in files)
    assert all(not item.startswith("reports/") for item in files)


def test_reliability_runner_contains_no_training_or_broad_source_discovery() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts/g2_neural_reliability.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    calls: set[str] = set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    lower = text.lower()
    assert "backward" not in calls
    assert "step" not in calls
    assert "rglob" not in calls
    assert "glob" not in calls
    assert "torch.optim" not in lower
    assert "torch.save" not in lower
    assert "torch.load" not in lower
    assert "pickle" not in imports
    assert "kaggle kernels push" not in lower
    assert "kaggle kernels" not in lower
    assert "--untracked-files=all" in text
    assert "multiprocessing_start_method\": \"spawn" in text
    assert "os.fsync" in text
    assert "canonical_json_line" in text
    assert "terminate_processes" in text


def test_device_parser_supports_distinct_cpu_servers_and_rejects_duplicates() -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    assert module.parse_devices("cpu:0,cpu:1") == ["cpu:0", "cpu:1"]
    assert module.parse_devices("cuda:0,cuda:1") == ["cuda:0", "cuda:1"]
    with pytest.raises(argparse.ArgumentTypeError, match="duplicates"):
        module.parse_devices("cpu,cpu")
    with pytest.raises(argparse.ArgumentTypeError, match="unsupported"):
        module.parse_devices("tpu:0")


def test_device_topology_requires_exact_t4x2(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    monkeypatch.setattr(module.torch.cuda, "device_count", lambda: 2)
    monkeypatch.setattr(module.torch.cuda, "get_device_name", lambda index: f"Tesla T4 #{index}")
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: True)
    topology = module.validate_device_topology(["cuda:0", "cuda:1"], True)
    assert topology["visible_cuda_device_count"] == 2
    assert topology["require_t4x2"] is True
    with pytest.raises(module.RunnerError, match="requires devices"):
        module.validate_device_topology(["cuda:0"], True)
    monkeypatch.setattr(module.torch.cuda, "get_device_name", lambda _: "Tesla P100")
    with pytest.raises(module.RunnerError, match="T4"):
        module.validate_device_topology(["cuda:0", "cuda:1"], True)


def test_device_topology_validates_cpu_alias_and_cuda_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    monkeypatch.setattr(module.torch.cuda, "device_count", lambda: 0)
    monkeypatch.setattr(module.torch.cuda, "get_device_name", lambda _: "")
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: False)
    topology = module.validate_device_topology(["cpu:0", "cpu:1"], False)
    assert topology["requested_devices"] == ["cpu:0", "cpu:1"]
    with pytest.raises(module.RunnerError, match="integer"):
        module.validate_device_topology(["cpu:x"], False)
    with pytest.raises(module.RunnerError, match="not visible"):
        module.validate_device_topology(["cuda:0"], False)



def test_inference_server_never_exceeds_declared_batch_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)

    class Connection:
        def __init__(self, request_id: int) -> None:
            self.messages = [
                {"kind": "request", "request_id": request_id},
                {"kind": "done"},
            ]
            self.responses: list[dict[str, Any]] = []

        def recv(self) -> dict[str, Any]:
            return self.messages.pop(0)

        def send(self, value: dict[str, Any]) -> None:
            self.responses.append(value)

    class ResultQueue:
        def __init__(self) -> None:
            self.values: list[dict[str, Any]] = []

        def put(self, value: dict[str, Any]) -> None:
            self.values.append(value)

    connections = [Connection(index) for index in range(10)]
    result_queue = ResultQueue()
    monkeypatch.setattr(
        module,
        "wait",
        lambda active, timeout=0.0: [item for item in active if item.messages],
    )
    monkeypatch.setattr(
        module,
        "load_server_model",
        lambda root, checkpoint, device: (object(), module.torch.device("cpu")),
    )
    observed_batches: list[int] = []

    def execute(model: object, messages: list[dict[str, Any]], device: Any):
        observed_batches.append(len(messages))
        return [{"selection": message["request_id"]} for message in messages]

    monkeypatch.setattr(module, "execute_inference_batch", execute)
    module.inference_server_process(
        str(root),
        0,
        "cpu:0",
        {},
        connections,
        4,
        0.0,
        result_queue,
    )

    assert observed_batches == [4, 4, 2]
    assert all(size <= 4 for size in observed_batches)
    assert result_queue.values[-1]["batch_histogram"] == {2: 1, 4: 2}
    assert result_queue.values[-1]["decisions"] == 10
    assert all(len(connection.responses) == 1 for connection in connections)


def test_process_evidence_passes_exact_worker_server_and_rss_accounting() -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    evidence = module.validate_process_evidence(
        [valid_worker(0), valid_worker(1)],
        [valid_server(decisions=2)],
        expected_workers=2,
        expected_servers=1,
        expected_engine_requests=2,
        max_batch=8,
        parent_peak_rss_mib=50.0,
    )
    assert evidence == {
        "status": "PASS",
        "failures": [],
        "expected_workers": 2,
        "observed_workers": 2,
        "expected_servers": 1,
        "observed_servers": 1,
        "expected_engine_requests": 2,
        "server_decisions": 2,
        "peak_process_rss_limit_mib": 6144.0,
        "max_observed_process_rss_mib": 200.0,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda workers, servers, kwargs: workers.pop(),
        lambda workers, servers, kwargs: workers[0].update(errors=["boom"]),
        lambda workers, servers, kwargs: workers[0].update(completed_games=0),
        lambda workers, servers, kwargs: workers[0].update(peak_rss_mib=6144.0),
        lambda workers, servers, kwargs: servers[0].update(errors=["boom"]),
        lambda workers, servers, kwargs: servers[0].update(decisions=3),
        lambda workers, servers, kwargs: servers[0].update(inference_calls=2),
        lambda workers, servers, kwargs: servers[0].update(batch_histogram={"9": 1}),
        lambda workers, servers, kwargs: servers[0].update(peak_rss_mib=float("nan")),
        lambda workers, servers, kwargs: kwargs.update(parent_peak_rss_mib=6144.0),
        lambda workers, servers, kwargs: kwargs.update(max_batch=0),
    ],
)
def test_process_evidence_rejects_each_accounting_or_resource_violation(
    mutation: Callable[[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]], None]
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    workers = [valid_worker(0), valid_worker(1)]
    servers = [valid_server(decisions=2)]
    kwargs = {
        "expected_workers": 2,
        "expected_servers": 1,
        "expected_engine_requests": 2,
        "max_batch": 8,
        "parent_peak_rss_mib": 50.0,
    }
    mutation(workers, servers, kwargs)
    evidence = module.validate_process_evidence(workers, servers, **kwargs)
    assert evidence["status"] == "FAIL"
    assert evidence["failures"]


def write_review_fixture(tmp_path: Path) -> tuple[Path, Path, str, str]:
    record = valid_game_record(0)
    games = tmp_path / "games.jsonl"
    games.write_bytes(canonical_json_line(record))
    games_raw = games.read_bytes()
    games_sha = hashlib.sha256(games_raw).hexdigest()
    embedded_review = recalculate_reliability([json.loads(games_raw)], 1)
    receipt = {
        "status": "PASS",
        "topology": {
            "games": 1,
            "total_workers": 1,
            "servers": 1,
            "max_batch": 1,
        },
        "outputs": {
            "games": {
                "path": games.as_posix(),
                "bytes": len(games_raw),
                "sha256": games_sha,
            }
        },
        "workers": [valid_worker(0)],
        "servers": [valid_server(decisions=2, batch_histogram={"1": 2})],
        "runtime": {"parent_peak_rss_mib": 50.0},
        "process_failures": [],
        "server_failures": [],
        "review": embedded_review,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    return games, receipt_path, games_sha, receipt_sha


def test_independent_review_recalculates_games_processes_and_receipt(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    games, receipt, games_sha, receipt_sha = write_review_fixture(tmp_path)
    output = tmp_path / "independent.json"
    result = module.review_command(
        SimpleNamespace(
            games=games,
            receipt=receipt,
            expected_games=1,
            expected_games_sha256=games_sha,
            expected_receipt_sha256=receipt_sha,
            output=output,
        )
    )
    assert result["status"] == "PASS"
    assert result["independent_process"] is True
    assert result["process_evidence"]["status"] == "PASS"
    assert result["receipt_comparison_failures"] == []
    assert output.is_file()


def test_independent_review_rejects_output_hash_and_receipt_drift(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    games, receipt, games_sha, receipt_sha = write_review_fixture(tmp_path)
    with pytest.raises(module.RunnerError, match="games JSONL"):
        module.review_command(
            SimpleNamespace(
                games=games,
                receipt=receipt,
                expected_games=1,
                expected_games_sha256="0" * 64,
                expected_receipt_sha256=receipt_sha,
                output=tmp_path / "bad-hash.json",
            )
        )

    value = json.loads(receipt.read_text())
    value["review"]["engine_requests"] += 1
    receipt.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    drifted_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    result = module.review_command(
        SimpleNamespace(
            games=games,
            receipt=receipt,
            expected_games=1,
            expected_games_sha256=games_sha,
            expected_receipt_sha256=drifted_sha,
            output=tmp_path / "drift.json",
        )
    )
    assert result["status"] == "FAIL"
    assert result["receipt_comparison_failures"] == ["engine_requests"]


def test_checkpoint_context_binds_tracked_policy_config(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    package = tmp_path / "private/checkpoint.zip"
    package.parent.mkdir(parents=True)
    package.write_bytes(b"checkpoint")
    config = module.PolicyConfigV1()
    config_path = tmp_path / "configs/g2_policy_v1.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "policy_config": asdict(config),
                "card_table_sha256": "c" * 64,
                "model_schema_sha256": "m" * 64,
            }
        )
    )
    report_path = tmp_path / module.CHECKPOINT_REPORT
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "status": "SUCCEEDED",
                "model": {
                    "config_sha256": config.config_sha256,
                    "card_table_sha256": "c" * 64,
                    "model_schema_sha256": "m" * 64,
                    "qualification_state_sha256": "q" * 64,
                },
                "private_artifacts": {
                    "package": {
                        "path": package.relative_to(tmp_path).as_posix(),
                        "bytes": package.stat().st_size,
                        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                    }
                },
            }
        )
    )
    parity_path = tmp_path / module.PARITY_REPORT
    parity_path.parent.mkdir(parents=True)
    parity_path.write_text(
        json.dumps(
            {
                "status": "SUCCEEDED",
                "decision": "PASS",
                "identity": {"qualification_state_sha256": "q" * 64},
            }
        )
    )
    context = module.checkpoint_context(tmp_path)
    assert context["config"]["public_hidden"] == 160
    assert module.PolicyConfigV1(**context["config"]).config_sha256 == context["model"][
        "config_sha256"
    ]


def test_initial_receipt_preserves_no_training_boundary(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    module = load_script(root)
    receipt = module.initial_receipt(
        "1" * 40,
        [],
        {"games": 1},
        {},
        {},
        tmp_path / "games.jsonl",
        tmp_path / "review.json",
    )
    assert receipt["status"] == "RUNNING"
    assert receipt["authorization"] == {
        "optimizer_created": False,
        "optimizer_steps": 0,
        "training_loop_ran": False,
        "training_state_included": False,
        "ppo_ran": False,
        "kaggle_run_launched_by_script": False,
    }
