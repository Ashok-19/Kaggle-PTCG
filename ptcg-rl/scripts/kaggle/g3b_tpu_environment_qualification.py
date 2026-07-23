from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from ptcg_rl.g3.competence_plan import load_competence_plan

RECORD_ID = "g3b-tpu-environment-v1"
DEFAULT_WORKERS = (16, 32, 48, 64, 80, 96)
NETWORK_URLS = (
    "https://example.com/",
    "https://www.google.com/generate_204",
)
CHECKPOINT_PATH = Path("private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip")
CHECKPOINT_SHA256 = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
RELIABILITY_RECEIPT = "g2-neural-reliability-v1-receipt.json"
RELIABILITY_REVIEW = "g2-neural-reliability-v1-review.json"
T4X2_BASELINE_CHOICES_PER_SECOND = 228.59829116666842
SESSION_HARD_LIMIT_SECONDS = 12 * 60 * 60
INTERNAL_CHUNK_LIMIT_SECONDS = 8 * 60 * 60


class QualificationError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    display = (
        resolved.relative_to(relative_to.resolve()).as_posix()
        if relative_to is not None and resolved.is_relative_to(relative_to.resolve())
        else resolved.name
    )
    return {
        "path": display,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_path(resolved),
    }


def write_json(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    raw = canonical_json_bytes(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return {
        "path": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise QualificationError(f"JSON root is not an object: {path}")
    return value


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_text(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = 300.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode:
        raise QualificationError(
            f"command failed ({completed.returncode}): {' '.join(command)}; "
            f"stderr={completed.stderr[-3000:]}"
        )
    return completed


def command_record(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = run_text(command, cwd=cwd, env=env, timeout=timeout)
        return {
            "command": list(command),
            "returncode": completed.returncode,
            "wall_seconds": time.monotonic() - started,
            "stdout_tail": completed.stdout[-20000:],
            "stderr_tail": completed.stderr[-20000:],
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return {
            "command": list(command),
            "returncode": 124,
            "wall_seconds": time.monotonic() - started,
            "stdout_tail": stdout[-20000:],
            "stderr_tail": stderr[-20000:],
            "timeout": True,
        }


def git_state(root: Path, expected_commit: str, expected_tree: str) -> dict[str, Any]:
    repository = root.parent
    head = run_text(["git", "rev-parse", "HEAD"], cwd=repository, check=True).stdout.strip()
    tree = run_text(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repository, check=True
    ).stdout.strip()
    status = run_text(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repository,
        check=True,
    ).stdout
    if head != expected_commit:
        raise QualificationError(f"source commit differs: expected {expected_commit}, got {head}")
    if tree != expected_tree:
        raise QualificationError(f"source tree differs: expected {expected_tree}, got {tree}")
    if status:
        raise QualificationError("tracked source checkout is dirty")
    return {"commit": head, "tree": tree, "tracked_status_clean": True}


def statvfs_record(path: Path) -> dict[str, int]:
    stat = os.statvfs(path)
    return {
        "block_size": stat.f_frsize,
        "blocks": stat.f_blocks,
        "blocks_free": stat.f_bfree,
        "blocks_available": stat.f_bavail,
        "bytes_total": stat.f_blocks * stat.f_frsize,
        "bytes_free": stat.f_bfree * stat.f_frsize,
        "bytes_available": stat.f_bavail * stat.f_frsize,
    }


def proc_meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    path = Path("/proc/meminfo")
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        fields = raw.strip().split()
        if not fields or not fields[0].isdigit():
            continue
        value = int(fields[0])
        if len(fields) > 1 and fields[1].lower() == "kb":
            value *= 1024
        result[name] = value
    return result


def selected_environment() -> dict[str, str | None]:
    names = (
        "KAGGLE_KERNEL_RUN_TYPE",
        "KAGGLE_URL_BASE",
        "PJRT_DEVICE",
        "TPU_NAME",
        "TPU_WORKER_ID",
        "TPU_PROCESS_ADDRESSES",
        "JAX_PLATFORMS",
        "XLA_USE_BF16",
        "XRT_TPU_CONFIG",
    )
    return {name: os.environ.get(name) for name in names}


def runtime_manifest(root: Path) -> dict[str, Any]:
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    commands: dict[str, Any] = {}
    for name, command in {
        "lscpu_json": ["lscpu", "-J"],
        "numactl_hardware": ["numactl", "--hardware"],
        "free_bytes": ["free", "-b"],
        "df_project": ["df", "-B1", str(root)],
        "ulimit": ["bash", "-lc", "ulimit -a"],
    }.items():
        if shutil.which(command[0]) is None:
            commands[name] = {"available": False}
        else:
            commands[name] = {
                "available": True,
                **command_record(command, cwd=root, timeout=30),
            }
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname_sha256": hashlib.sha256(socket.gethostname().encode()).hexdigest(),
        },
        "cpu": {
            "os_cpu_count": os.cpu_count(),
            "affinity": affinity,
            "affinity_count": len(affinity) if affinity is not None else None,
        },
        "memory": proc_meminfo(),
        "resource_limits": {
            "nofile": list(resource.getrlimit(resource.RLIMIT_NOFILE)),
            "nproc": list(resource.getrlimit(resource.RLIMIT_NPROC)),
            "memlock": list(resource.getrlimit(resource.RLIMIT_MEMLOCK)),
        },
        "filesystems": {
            "dev_shm_exists": Path("/dev/shm").is_dir(),
            "dev_shm_statvfs": (
                statvfs_record(Path("/dev/shm")) if Path("/dev/shm").is_dir() else None
            ),
            "project_statvfs": statvfs_record(root),
        },
        "packages": {
            name: package_version(name)
            for name in (
                "numpy",
                "torch",
                "torch-xla",
                "jax",
                "jaxlib",
                "tensorflow",
                "psutil",
                "scipy",
            )
        },
        "environment": selected_environment(),
        "commands": commands,
        "budget": {
            "kaggle_hard_limit_seconds": SESSION_HARD_LIMIT_SECONDS,
            "internal_chunk_limit_seconds": INTERNAL_CHUNK_LIMIT_SECONDS,
            "hard_limit_directly_machine_verifiable": False,
        },
    }


def network_probe(require_blocked: bool) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for url in NETWORK_URLS:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                attempts.append({"url": url, "blocked": False, "status": int(response.status)})
        except Exception as error:
            attempts.append(
                {
                    "url": url,
                    "blocked": True,
                    "exception": type(error).__name__,
                    "message": str(error)[:500],
                }
            )
    blocked = all(item["blocked"] for item in attempts)
    if require_blocked and not blocked:
        raise QualificationError("outbound internet unexpectedly succeeded")
    return {
        "status": "PASS" if (blocked or not require_blocked) else "FAIL",
        "blocked": blocked,
        "required_blocked": require_blocked,
        "attempts": attempts,
    }


def verify_assets(root: Path, plan_path: Path) -> dict[str, Any]:
    loaded = load_competence_plan(plan_path, root)
    checkpoint = root / CHECKPOINT_PATH
    if not checkpoint.is_file() or checkpoint.is_symlink():
        raise QualificationError("exact G2 checkpoint is missing or a symlink")
    if sha256_path(checkpoint) != CHECKPOINT_SHA256:
        raise QualificationError("exact G2 checkpoint SHA-256 differs")
    return {
        "plan": file_record(plan_path, relative_to=root),
        "plan_semantic_sha256": loaded.semantic_sha256,
        "checkpoint": file_record(checkpoint, relative_to=root),
        "asset_contract_status": "PASS",
    }


def write_probe_script(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


JAX_PROBE = r'''
from __future__ import annotations
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import jax
import jax.numpy as jnp
from jax import lax

output = Path(os.environ["KPTCG_PROBE_OUTPUT"])
allow_non_tpu = os.environ.get("KPTCG_ALLOW_NON_TPU") == "1"
devices = jax.devices()
backend = jax.default_backend()
if not allow_non_tpu:
    if backend != "tpu":
        raise RuntimeError(f"JAX backend must be tpu, got {backend}")
    if len(devices) != 8:
        raise RuntimeError(f"expected exactly 8 JAX TPU devices, got {len(devices)}")

def timed(function):
    started = time.perf_counter()
    value = function()
    if hasattr(value, "block_until_ready"):
        value.block_until_ready()
    return time.perf_counter() - started, value

single_size = int(os.environ.get("KPTCG_JAX_SINGLE_SIZE", "1536"))
a = jnp.ones((single_size, single_size), dtype=jnp.bfloat16)
b = jnp.ones((single_size, single_size), dtype=jnp.bfloat16)
single = jax.jit(lambda left, right: left @ right)
compile_seconds, value = timed(lambda: single(a, b))
steady = [timed(lambda: single(a, b))[0] for _ in range(5)]
single_checksum = float(np.asarray(value[0, 0]))

local_count = jax.local_device_count()
multi_size = int(os.environ.get("KPTCG_JAX_MULTI_SIZE", "512"))
host = np.ones((local_count, multi_size, multi_size), dtype=np.float32)
pmap_matmul = jax.pmap(
    lambda x: lax.psum(
        jnp.asarray(x, dtype=jnp.bfloat16) @ jnp.asarray(x, dtype=jnp.bfloat16).T,
        "devices",
    ),
    axis_name="devices",
)
multi_compile_seconds, multi_value = timed(lambda: pmap_matmul(host))
multi_steady = [timed(lambda: pmap_matmul(host))[0] for _ in range(3)]
multi_checksum = float(np.asarray(multi_value[0, 0, 0]))

put_started = time.perf_counter()
put_value = jax.device_put(host)
put_value.block_until_ready()
host_to_device_seconds = time.perf_counter() - put_started
get_started = time.perf_counter()
roundtrip = np.asarray(put_value)
device_to_host_seconds = time.perf_counter() - get_started

memory = []
for device in devices:
    try:
        stats = device.memory_stats()
    except Exception as error:
        stats = {"error": f"{type(error).__name__}: {error}"}
    memory.append({"device": str(device), "memory_stats": stats})

record = {
    "status": "PASS",
    "backend": backend,
    "jax_version": jax.__version__,
    "jaxlib_version": getattr(jax.lib, "__version__", None),
    "platform": platform.platform(),
    "process_count": jax.process_count(),
    "process_index": jax.process_index(),
    "device_count": jax.device_count(),
    "local_device_count": local_count,
    "devices": [
        {
            "id": getattr(device, "id", None),
            "process_index": getattr(device, "process_index", None),
            "platform": getattr(device, "platform", None),
            "device_kind": getattr(device, "device_kind", None),
            "repr": str(device),
        }
        for device in devices
    ],
    "single_device": {
        "matrix_size": single_size,
        "compile_and_first_execute_seconds": compile_seconds,
        "steady_execute_seconds": steady,
        "checksum": single_checksum,
    },
    "all_devices": {
        "matrix_size_per_device": multi_size,
        "compile_and_first_execute_seconds": multi_compile_seconds,
        "steady_execute_seconds": multi_steady,
        "checksum": multi_checksum,
    },
    "transfers": {
        "bytes": int(host.nbytes),
        "host_to_device_seconds": host_to_device_seconds,
        "device_to_host_seconds": device_to_host_seconds,
        "roundtrip_equal": bool(np.array_equal(host, roundtrip)),
    },
    "memory": memory,
    "authorization": {
        "synthetic_tensors_only": True,
        "optimizer_created": False,
        "training_loop_ran": False,
        "cabt_games_ran": False,
    },
}
output.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
print(json.dumps(record, indent=2, sort_keys=True))
'''


TORCH_XLA_PROBE = r'''
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

import torch

from ptcg_rl.g2.checkpoint import load_checkpoint_package
from ptcg_rl.g2.network import collate_projected

root = Path(os.environ["KPTCG_ROOT"])
output = Path(os.environ["KPTCG_PROBE_OUTPUT"])
checkpoint = root / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
checkpoint_hash = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"

spec = importlib.util.spec_from_file_location(
    "kptcg_g2_policy_qualification",
    root / "scripts/kaggle/g2_policy_qualification.py",
)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load G2 qualification fixture module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
decisions = module.projected_decisions()
batch_cpu = collate_projected(decisions)

loaded = load_checkpoint_package(
    checkpoint,
    device="cpu",
    expected_package_sha256=checkpoint_hash,
    expected_source_commit=None,
    source_root=root,
)
model_cpu = loaded.model.eval()

def run_model(model, batch, device):
    hidden = model.initial_hidden(batch.batch_size, device)
    first = model(batch, hidden)
    second = model(batch, first.hidden)
    prefix = model.decoder_initial(second.hidden[0])
    available = torch.tensor([True, False, True, True, True], dtype=torch.bool, device=device)
    decoder = model.decoder_logits(prefix, second.option_embeddings[:5], available, True)
    advanced = model.decoder_advance(prefix, second.option_embeddings[0])
    return {
        "option_logits": second.option_logits,
        "values": second.values,
        "hidden": second.hidden,
        "decoder": decoder,
        "advanced": advanced,
    }

with torch.inference_mode():
    cpu = {
        name: value.detach().cpu()
        for name, value in run_model(model_cpu, batch_cpu, torch.device("cpu")).items()
    }

state_before = hashlib.sha256()
for name, tensor in sorted(model_cpu.state_dict().items()):
    state_before.update(name.encode())
    state_before.update(tensor.detach().cpu().contiguous().numpy().tobytes())
state_before_digest = state_before.hexdigest()

import torch_xla
import torch_xla.core.xla_model as xm
import torch_xla.debug.metrics as met

try:
    device = torch_xla.device()
except Exception:
    device = xm.xla_device()

loaded_xla = load_checkpoint_package(
    checkpoint,
    device="cpu",
    expected_package_sha256=checkpoint_hash,
    expected_source_commit=None,
    source_root=root,
)
model_xla = loaded_xla.model.to(device).eval()
batch_xla = batch_cpu.to(device)
started = time.perf_counter()
xla_values = run_model(model_xla, batch_xla, device)
xm.mark_step()
first_seconds = time.perf_counter() - started
copied = {name: value.detach().cpu() for name, value in xla_values.items()}

steady = []
for _ in range(3):
    started = time.perf_counter()
    values = run_model(model_xla, batch_xla, device)
    xm.mark_step()
    _ = values["values"].detach().cpu()
    steady.append(time.perf_counter() - started)

comparisons = {}
for name in cpu:
    left = cpu[name]
    right = copied[name]
    finite = torch.isfinite(left) & torch.isfinite(right)
    max_abs = float((left[finite] - right[finite]).abs().max().item()) if bool(finite.any()) else 0.0
    comparisons[name] = {
        "shape_equal": tuple(left.shape) == tuple(right.shape),
        "max_abs_diff_finite": max_abs,
        "inf_mask_equal": bool(torch.equal(torch.isinf(left), torch.isinf(right))),
        "nan_mask_equal": bool(torch.equal(torch.isnan(left), torch.isnan(right))),
    }

linear = torch.nn.Linear(128, 64).to(device)
synthetic = torch.ones((256, 128), dtype=torch.float32, device=device)
grad_started = time.perf_counter()
loss = linear(synthetic).square().mean()
loss.backward()
xm.mark_step()
gradient = linear.weight.grad.detach().cpu()
gradient_seconds = time.perf_counter() - grad_started
if not bool(torch.isfinite(gradient).all()):
    raise RuntimeError("synthetic XLA gradient is non-finite")

state_after = hashlib.sha256()
for name, tensor in sorted(model_xla.state_dict().items()):
    state_after.update(name.encode())
    state_after.update(tensor.detach().cpu().contiguous().numpy().tobytes())
state_after_digest = state_after.hexdigest()

max_diff = max(item["max_abs_diff_finite"] for item in comparisons.values())
passed = (
    max_diff <= 1e-3
    and all(
        item["shape_equal"] and item["inf_mask_equal"] and item["nan_mask_equal"]
        for item in comparisons.values()
    )
    and state_before_digest == state_after_digest
)

record = {
    "status": "PASS" if passed else "FAIL",
    "torch_version": torch.__version__,
    "torch_xla_version": getattr(torch_xla, "__version__", None),
    "device": str(device),
    "supported_devices": list(xm.get_xla_supported_devices()),
    "exact_model": {
        "checkpoint_sha256": checkpoint_hash,
        "batch_size": batch_cpu.batch_size,
        "first_compile_and_execute_seconds": first_seconds,
        "steady_execute_seconds": steady,
        "comparisons": comparisons,
        "max_abs_diff_finite": max_diff,
        "state_roundtrip_sha256_before": state_before_digest,
        "state_roundtrip_sha256_after": state_after_digest,
        "state_roundtrip_equal": state_before_digest == state_after_digest,
    },
    "synthetic_backward": {
        "wall_seconds": gradient_seconds,
        "loss": float(loss.detach().cpu()),
        "gradient_finite": True,
        "optimizer_created": False,
        "optimizer_steps": 0,
    },
    "metrics_report": met.short_metrics_report(),
    "authorization": {
        "meaningful_training_choices": 0,
        "optimizer_created": False,
        "optimizer_steps": 0,
        "training_loop_ran": False,
        "checkpoint_mutated": False,
    },
}
output.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
print(json.dumps(record, indent=2, sort_keys=True))
if not passed:
    raise RuntimeError("exact PTCG model XLA parity or state roundtrip failed")
'''


TORCH_XLA_MULTI_PROBE = r'''
from __future__ import annotations
import json
import os
from pathlib import Path

import torch
import torch_xla
import torch_xla.core.xla_model as xm

output_dir = Path(os.environ["KPTCG_MULTI_OUTPUT"])
output_dir.mkdir(parents=True, exist_ok=True)

def worker(index):
    try:
        try:
            device = torch_xla.device()
        except Exception:
            device = xm.xla_device()
        value = torch.tensor([float(index + 1)], device=device)
        reduced = xm.all_reduce(xm.REDUCE_SUM, value)
        xm.mark_step()
        payload = {
            "status": "PASS",
            "index": int(index),
            "device": str(device),
            "all_reduce_sum": float(reduced.detach().cpu().item()),
        }
    except Exception as error:
        payload = {
            "status": "FAIL",
            "index": int(index),
            "error": f"{type(error).__name__}: {error}",
        }
    (output_dir / f"worker-{index:02d}.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    )

def main():
    output_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(torch_xla, "launch"):
        torch_xla.launch(worker, args=())
    else:
        import torch_xla.distributed.xla_multiprocessing as xmp
        xmp.spawn(worker, args=(), start_method="spawn")

    records = [json.loads(path.read_text()) for path in sorted(output_dir.glob("worker-*.json"))]
    passed = (
        len(records) == 8
        and all(record.get("status") == "PASS" for record in records)
        and all(abs(float(record.get("all_reduce_sum", 0.0)) - 36.0) <= 1e-5 for record in records)
    )
    summary = {
        "status": "PASS" if passed else "FAIL",
        "workers": records,
        "expected_workers": 8,
        "expected_all_reduce_sum": 36.0,
        "authorization": {
            "synthetic_tensors_only": True,
            "optimizer_created": False,
            "training_loop_ran": False,
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not passed:
        raise RuntimeError("eight-device torch_xla collective probe failed")


if __name__ == "__main__":
    main()
'''


def run_isolated_probe(
    *,
    name: str,
    script: str,
    root: Path,
    output: Path,
    env: Mapping[str, str],
    timeout: float,
) -> dict[str, Any]:
    script_path = write_probe_script(output / "probe-scripts", f"{name}.py", script)
    result_path = output / "probes" / f"{name}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    probe_env = dict(os.environ)
    probe_env.update(env)
    probe_env["PYTHONPATH"] = str(root / "src")
    probe_env["KPTCG_ROOT"] = str(root)
    probe_env["KPTCG_PROBE_OUTPUT"] = str(result_path)
    record = command_record(
        [sys.executable, str(script_path)],
        cwd=root,
        env=probe_env,
        timeout=timeout,
    )
    record["result_exists"] = result_path.is_file()
    record["result"] = read_json(result_path) if result_path.is_file() else None
    if result_path.is_file():
        record["result_file"] = file_record(result_path, relative_to=output)
    return record


def run_torch_xla_multi(*, root: Path, output: Path, timeout: float) -> dict[str, Any]:
    script_path = write_probe_script(
        output / "probe-scripts", "torch_xla_multi_probe.py", TORCH_XLA_MULTI_PROBE
    )
    multi_output = output / "probes" / "torch-xla-multi"
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(root / "src"),
            "KPTCG_MULTI_OUTPUT": str(multi_output),
            "PJRT_DEVICE": os.environ.get("PJRT_DEVICE", "TPU"),
        }
    )
    record = command_record(
        [sys.executable, str(script_path)],
        cwd=root,
        env=env,
        timeout=timeout,
    )
    summary = multi_output / "summary.json"
    record["result_exists"] = summary.is_file()
    record["result"] = read_json(summary) if summary.is_file() else None
    if summary.is_file():
        record["result_file"] = file_record(summary, relative_to=output)
    return record


def disk_probe(output: Path, size_mib: int) -> dict[str, Any]:
    if size_mib <= 0:
        raise QualificationError("disk probe size must be positive")
    path = output / "io" / "disk-probe.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk = hashlib.sha256(b"kptcg-g3b-tpu-disk-probe-v1").digest() * (1024 * 32)
    total = size_mib * 1024 * 1024
    started = time.perf_counter()
    with path.open("wb") as handle:
        remaining = total
        while remaining:
            part = chunk[: min(len(chunk), remaining)]
            handle.write(part)
            remaining -= len(part)
        handle.flush()
        os.fsync(handle.fileno())
    write_seconds = time.perf_counter() - started
    started = time.perf_counter()
    digest = sha256_path(path)
    read_seconds = time.perf_counter() - started
    record = {
        "status": "PASS",
        "bytes": total,
        "sha256": digest,
        "write_seconds": write_seconds,
        "read_seconds": read_seconds,
        "write_mib_per_second": size_mib / max(write_seconds, 1e-9),
        "read_mib_per_second": size_mib / max(read_seconds, 1e-9),
    }
    path.unlink()
    return record


def checkpoint_atomic_roundtrip(root: Path, output: Path) -> dict[str, Any]:
    source = root / CHECKPOINT_PATH
    destination = output / "checkpoint-roundtrip" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with source.open("rb") as src, temporary.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    temporary.replace(destination)
    observed = file_record(destination, relative_to=output)
    if observed["sha256"] != CHECKPOINT_SHA256:
        raise QualificationError("atomic checkpoint roundtrip hash differs")
    verify_script = (
        "from pathlib import Path\n"
        "from ptcg_rl.g2.checkpoint import load_checkpoint_package\n"
        f"load_checkpoint_package(Path({str(destination)!r}), device='cpu', "
        f"expected_package_sha256={CHECKPOINT_SHA256!r}, expected_source_commit=None, "
        f"source_root=Path({str(root)!r}))\n"
    )
    verification = command_record(
        [sys.executable, "-c", verify_script],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        timeout=300,
    )
    if verification["returncode"] != 0:
        raise QualificationError("fresh-process checkpoint restore failed")
    return {"status": "PASS", "artifact": observed, "fresh_process_restore": verification}


def parse_workers(value: str) -> tuple[int, ...]:
    workers = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not workers or any(item <= 0 for item in workers):
        raise argparse.ArgumentTypeError("worker counts must be positive")
    if len(workers) != len(set(workers)):
        raise argparse.ArgumentTypeError("worker counts contain duplicates")
    return workers


def reliability_branch(
    *,
    root: Path,
    output: Path,
    workers: int,
    games_per_worker: int,
    timeout: float,
    numa_mode: str,
) -> dict[str, Any]:
    branch = output / "cabt-scaling" / f"workers-{workers:03d}-{numa_mode}"
    games = max(64, workers * games_per_worker)
    command = [
        sys.executable,
        str(root / "scripts/g2_neural_reliability.py"),
        "run",
        "--root",
        str(root),
        "--output-dir",
        str(branch),
        "--games",
        str(games),
        "--devices",
        "cpu:0",
        "--workers-per-device",
        str(workers),
        "--max-batch",
        str(min(max(8, workers // 2), 48)),
        "--batch-wait-ms",
        "1.0",
        "--game-timeout-seconds",
        "300",
        "--run-timeout-seconds",
        str(int(timeout)),
    ]
    if numa_mode == "interleave":
        if shutil.which("numactl") is None:
            return {
                "status": "SKIPPED",
                "reason": "numactl unavailable",
                "workers": workers,
                "games": games,
                "numa_mode": numa_mode,
            }
        command = ["numactl", "--interleave=all", *command]
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": str(root / "src"),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    run = command_record(command, cwd=root, env=environment, timeout=timeout + 120)
    receipt_path = branch / RELIABILITY_RECEIPT
    review_path = branch / RELIABILITY_REVIEW
    receipt = read_json(receipt_path) if receipt_path.is_file() else None
    review = read_json(review_path) if review_path.is_file() else None
    wall = float(receipt.get("wall_seconds", 0.0)) if receipt else 0.0
    choices = int(review.get("meaningful_choices", 0)) if review else 0
    completed_games = int(review.get("observed_games", 0)) if review else 0
    choices_per_second = choices / wall if wall > 0 else 0.0
    games_per_second = completed_games / wall if wall > 0 else 0.0
    status = (
        "PASS"
        if run["returncode"] == 0
        and receipt is not None
        and review is not None
        and receipt.get("status") == "PASS"
        and review.get("status") == "PASS"
        else "FAIL"
    )
    return {
        "status": status,
        "workers": workers,
        "games": games,
        "numa_mode": numa_mode,
        "command": run,
        "receipt_file": file_record(receipt_path, relative_to=output) if receipt_path.is_file() else None,
        "review_file": file_record(review_path, relative_to=output) if review_path.is_file() else None,
        "metrics": {
            "completed_games": completed_games,
            "meaningful_choices": choices,
            "wall_seconds": wall,
            "games_per_second": games_per_second,
            "choices_per_second": choices_per_second,
            "relative_to_t4x2_inference_only": choices_per_second / T4X2_BASELINE_CHOICES_PER_SECOND,
            "projected_one_million_choice_hours": (
                1_000_000 / choices_per_second / 3600.0 if choices_per_second > 0 else None
            ),
        },
        "receipt_status": receipt.get("status") if receipt else None,
        "review_status": review.get("status") if review else None,
        "authorization": receipt.get("authorization") if receipt else None,
    }


def cabt_scaling(
    *,
    root: Path,
    output: Path,
    workers: Sequence[int],
    games_per_worker: int,
    branch_timeout: float,
    run_numa_rerun: bool,
) -> dict[str, Any]:
    records = [
        reliability_branch(
            root=root,
            output=output,
            workers=count,
            games_per_worker=games_per_worker,
            timeout=branch_timeout,
            numa_mode="default",
        )
        for count in workers
    ]
    passed = [record for record in records if record["status"] == "PASS"]
    best = max(passed, key=lambda item: item["metrics"]["choices_per_second"]) if passed else None
    numa = None
    if run_numa_rerun and best is not None:
        numa = reliability_branch(
            root=root,
            output=output,
            workers=int(best["workers"]),
            games_per_worker=games_per_worker,
            timeout=branch_timeout,
            numa_mode="interleave",
        )
    return {
        "status": "PASS" if len(passed) == len(records) and records else "FAIL",
        "branches": records,
        "best_default": best,
        "best_interleave": numa,
        "all_branches_completed": len(passed) == len(records),
    }


def output_manifest(output: Path) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(output.rglob("*")):
        if (
            not path.is_file()
            or path.name.endswith(".partial")
            or path.name == f"{RECORD_ID}-output-manifest.json"
        ):
            continue
        record = file_record(path, relative_to=output)
        files[record["path"]] = {"bytes": record["bytes"], "sha256": record["sha256"]}
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3B_TPU_ENVIRONMENT_OUTPUT_MANIFEST",
        "files": files,
    }


def failure_capsule(output: Path, phase: str, error: BaseException) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(
        output / f"{RECORD_ID}-failure-capsule.json",
        {
            "schema_version": 1,
            "record_id": f"{RECORD_ID}-failure-capsule",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": "FAILED",
            "phase": phase,
            "error_type": type(error).__name__,
            "error": str(error)[:4000],
            "traceback_tail": traceback.format_exc()[-12000:],
            "policy_competence_claimed": False,
            "training_authorized": False,
        },
    )


def run_command(args: argparse.Namespace) -> int:
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise QualificationError(f"output directory collision: {output}")
    output.mkdir(parents=True)
    started = time.monotonic()
    phase = "source"
    try:
        source = git_state(root, args.expected_source_commit, args.expected_source_tree)
        phase = "assets"
        assets = verify_assets(root, args.plan.resolve(strict=True))
        phase = "runtime"
        runtime = runtime_manifest(root)
        affinity_count = runtime["cpu"]["affinity_count"] or runtime["cpu"]["os_cpu_count"] or 0
        if not args.allow_non_tpu and affinity_count < args.minimum_cpu_threads:
            raise QualificationError(
                f"expected at least {args.minimum_cpu_threads} CPU threads, got {affinity_count}"
            )
        phase = "network"
        network = network_probe(require_blocked=not args.allow_internet)
        phase = "disk"
        disk = disk_probe(output, args.disk_probe_mib)
        phase = "checkpoint"
        checkpoint = checkpoint_atomic_roundtrip(root, output)

        common_probe_env = {
            "KPTCG_ALLOW_NON_TPU": "1" if args.allow_non_tpu else "0",
            "PJRT_DEVICE": os.environ.get("PJRT_DEVICE", "TPU"),
        }
        phase = "jax"
        jax = run_isolated_probe(
            name="jax_tpu_probe",
            script=JAX_PROBE,
            root=root,
            output=output,
            env=common_probe_env,
            timeout=args.accelerator_probe_timeout_seconds,
        )
        phase = "torch-xla"
        torch_xla = run_isolated_probe(
            name="torch_xla_exact_model_probe",
            script=TORCH_XLA_PROBE,
            root=root,
            output=output,
            env=common_probe_env,
            timeout=args.accelerator_probe_timeout_seconds,
        )
        phase = "torch-xla-multi"
        torch_xla_multi = run_torch_xla_multi(
            root=root,
            output=output,
            timeout=args.accelerator_probe_timeout_seconds,
        )
        phase = "cabt-scaling"
        scaling = cabt_scaling(
            root=root,
            output=output,
            workers=args.worker_counts,
            games_per_worker=args.games_per_worker,
            branch_timeout=args.cabt_branch_timeout_seconds,
            run_numa_rerun=not args.skip_numa_rerun,
        )

        accelerator_pass = (
            args.allow_non_tpu
            or (
                jax["returncode"] == 0
                and jax.get("result", {}).get("status") == "PASS"
                and jax.get("result", {}).get("backend") == "tpu"
                and jax.get("result", {}).get("device_count") == 8
                and torch_xla["returncode"] == 0
                and torch_xla.get("result", {}).get("status") == "PASS"
                and torch_xla_multi["returncode"] == 0
                and torch_xla_multi.get("result", {}).get("status") == "PASS"
            )
        )
        best = scaling.get("best_default")
        best_choices = float(best["metrics"]["choices_per_second"]) if best is not None else 0.0
        platform_candidate = (
            accelerator_pass
            and scaling["status"] == "PASS"
            and best_choices >= args.minimum_choices_per_second
        )
        verdict = {
            "status": "PASS" if platform_candidate else "FAIL",
            "decision": (
                "QUALIFIED_FOR_EQUAL_BUDGET_TRAINING_CANARY"
                if platform_candidate
                else "NOT_QUALIFIED_FOR_TRAINING_CANARY"
            ),
            "requirements": {
                "exactly_eight_tpu_devices": not args.allow_non_tpu,
                "minimum_cpu_threads": args.minimum_cpu_threads,
                "minimum_choices_per_second": args.minimum_choices_per_second,
                "all_worker_sweep_branches_complete": True,
                "network_blocked": not args.allow_internet,
                "exact_model_xla_parity": True,
                "eight_device_collective": True,
                "checkpoint_fresh_process_restore": True,
            },
            "observed": {
                "accelerator_pass": accelerator_pass,
                "cabt_scaling_status": scaling["status"],
                "best_choices_per_second": best_choices,
                "best_worker_count": best["workers"] if best else None,
                "projected_one_million_choice_hours_inference_only": (
                    best["metrics"]["projected_one_million_choice_hours"] if best else None
                ),
            },
            "claim_boundaries": {
                "policy_competence_established": False,
                "ppo_training_throughput_established": False,
                "training_authorized": False,
                "submission_authorized": False,
                "environment_only": True,
            },
        }
        report = {
            "schema_version": 1,
            "record_id": RECORD_ID,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": verdict["status"],
            "decision": verdict["decision"],
            "source": source,
            "assets": assets,
            "runtime": runtime,
            "network": network,
            "disk": disk,
            "checkpoint": checkpoint,
            "jax": jax,
            "torch_xla": torch_xla,
            "torch_xla_multi": torch_xla_multi,
            "cabt_scaling": scaling,
            "verdict": verdict,
            "wall_seconds": time.monotonic() - started,
            "authorization": {
                "meaningful_training_choices": 0,
                "optimizer_created_by_environment_runner": False,
                "optimizer_steps": 0,
                "ppo_ran": False,
                "submission_created": False,
                "external_service_mutated_by_runner": False,
            },
        }
        report_record = write_json(output / f"{RECORD_ID}-report.json", report)
        manifest_record = write_json(
            output / f"{RECORD_ID}-output-manifest.json", output_manifest(output)
        )
        print(
            json.dumps(
                {
                    "status": verdict["status"],
                    "decision": verdict["decision"],
                    "report": report_record,
                    "manifest": manifest_record,
                    "output": str(output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if platform_candidate else 2
    except Exception as error:
        failure_capsule(output, phase, error)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Qualify the Kaggle TPU v5e-8 host for a future bounded G3b canary"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--worker-counts", type=parse_workers, default=DEFAULT_WORKERS)
    parser.add_argument("--games-per-worker", type=int, default=4)
    parser.add_argument("--minimum-cpu-threads", type=int, default=96)
    parser.add_argument("--minimum-choices-per-second", type=float, default=35.0)
    parser.add_argument("--disk-probe-mib", type=int, default=256)
    parser.add_argument("--accelerator-probe-timeout-seconds", type=float, default=1800)
    parser.add_argument("--cabt-branch-timeout-seconds", type=float, default=2400)
    parser.add_argument("--skip-numa-rerun", action="store_true")
    parser.add_argument("--allow-non-tpu", action="store_true")
    parser.add_argument("--allow-internet", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.games_per_worker <= 0:
        raise SystemExit("--games-per-worker must be positive")
    if args.minimum_cpu_threads <= 0:
        raise SystemExit("--minimum-cpu-threads must be positive")
    if args.minimum_choices_per_second <= 0:
        raise SystemExit("--minimum-choices-per-second must be positive")
    if args.disk_probe_mib <= 0:
        raise SystemExit("--disk-probe-mib must be positive")
    try:
        return run_command(args)
    except (QualificationError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"G3b TPU environment qualification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
