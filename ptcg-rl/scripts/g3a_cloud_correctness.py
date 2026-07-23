from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pydantic
import torch

from ptcg_rl.g3.cloud_execution import (
    CloudExecutionError,
    bind_independent_review,
    build_strict_evidence,
    validate_input_manifest,
)
from ptcg_rl.g3.cloud_plan import REQUIRED_SEEDS, REQUIRED_STREAMS, load_cloud_plan
from ptcg_rl.g3.cloud_runner import StreamTrainingSpecV1, run_training_stream
from ptcg_rl.g3.evaluation import (
    EvaluationContractError,
    canonical_json_bytes,
    load_evaluation_contract,
    load_json_object,
)
from ptcg_rl.g3.ppo import LocalExecutionLimitsV1

STREAM_RESULT_NAME = "stream-result.json"


class CloudScriptError(RuntimeError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix() if relative_to else path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def write_canonical(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    raw = canonical_json_bytes(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def run_git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise CloudScriptError(
            f"Git command failed ({' '.join(args)}): {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def verify_source_checkout(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    repository = root.parent
    head = run_git(repository, "rev-parse", "HEAD")
    tree = run_git(repository, "rev-parse", "HEAD^{tree}")
    status = run_git(repository, "status", "--porcelain", "--untracked-files=no")
    if head != plan["source"]["commit"]:
        raise CloudScriptError("checked-out source commit differs from the frozen plan")
    if tree != plan["source"]["tree"]:
        raise CloudScriptError("checked-out source tree differs from the frozen plan")
    if status:
        raise CloudScriptError("checked-out source tree is dirty")
    return {"commit": head, "tree": tree, "tracked_status_clean": True}


def verify_dependencies(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = plan["dependencies"]
    observed = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "pydantic": pydantic.__version__,
    }
    for name, version in observed.items():
        if version != expected[name]:
            raise CloudScriptError(
                f"dependency version differs for {name}: expected {expected[name]}, got {version}"
            )
    lock = root / expected["lock_path"]
    if not lock.is_file():
        raise CloudScriptError("dependency lock file is missing")
    if lock.stat().st_size != expected["lock_bytes"] or sha256_path(lock) != expected["lock_sha256"]:
        raise CloudScriptError("dependency lock bytes or SHA-256 differ")
    return {**observed, "lock": file_record(lock, relative_to=root)}


def apply_environment(plan: Mapping[str, Any]) -> dict[str, Any]:
    platform_plan = plan["platform"]
    for name, value in platform_plan["thread_environment"].items():
        os.environ[name] = value
    torch.set_num_threads(int(platform_plan["torch_intraop_threads"]))
    try:
        torch.set_num_interop_threads(int(platform_plan["torch_interop_threads"]))
    except RuntimeError:
        if torch.get_num_interop_threads() != int(platform_plan["torch_interop_threads"]):
            raise CloudScriptError("Torch inter-op threads were initialized above the frozen limit")
    if torch.cuda.is_available() or torch.cuda.device_count() != 0:
        raise CloudScriptError("unexpected GPU visibility in the CPU-only G3a plan")
    kernel_run_type = os.environ.get("KAGGLE_KERNEL_RUN_TYPE")
    if kernel_run_type != platform_plan["kernel_run_type"]:
        raise CloudScriptError(
            f"Kaggle kernel run type differs: expected {platform_plan['kernel_run_type']}, "
            f"got {kernel_run_type!r}"
        )
    affinity_count = None
    if hasattr(os, "sched_getaffinity"):
        affinity = sorted(os.sched_getaffinity(0))
        maximum = int(platform_plan["maximum_cpu_cores"])
        if len(affinity) > maximum and hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, set(affinity[:maximum]))
            affinity = sorted(os.sched_getaffinity(0))
        affinity_count = len(affinity)
        if affinity_count > maximum:
            raise CloudScriptError("CPU affinity exceeds the frozen four-core ceiling")
    return {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "os_cpu_count": os.cpu_count(),
        "affinity_cpu_count": affinity_count,
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "cuda_available": torch.cuda.is_available(),
        "cuda_count": torch.cuda.device_count(),
        "kernel_run_type": kernel_run_type,
        "expected_docker_image": platform_plan["docker_image"],
    }


def stream_task(stream: str) -> tuple[str, bool]:
    if stream == "recurrent-cue-v1-stateless":
        return "recurrent-cue-v1", True
    if stream not in REQUIRED_STREAMS:
        raise CloudScriptError(f"unknown stream: {stream}")
    return stream, False


def build_stream_spec(plan: Mapping[str, Any], *, seed: int, stream: str) -> StreamTrainingSpecV1:
    if seed not in REQUIRED_SEEDS:
        raise CloudScriptError(f"undeclared seed: {seed}")
    task_id, stateless = stream_task(stream)
    allocation = int(plan["work"]["allocations"][str(seed)][stream])
    interruption = plan["checkpoint"]["intentional_interruptions"][str(seed)]
    interrupt_after = (
        int(interruption["after_choices"]) if interruption["stream"] == stream else None
    )
    return StreamTrainingSpecV1(
        task_id=task_id,
        seed=seed,
        stateless=stateless,
        rollout_sampling=str(plan["work"]["rollout_sampling"]),
        rollout_seed_xor=int(plan["work"]["rollout_seed_xor"]),
        total_non_forced_choices=allocation,
        choices_per_update=int(plan["work"]["choices_per_update"]),
        ppo_epochs=int(plan["work"]["ppo_epochs"]),
        learning_rate=float(plan["work"]["learning_rate"]),
        adam_epsilon=float(plan["work"]["adam_epsilon"]),
        clip_coefficient=float(plan["work"]["clip_coefficient"]),
        value_clip_coefficient=float(plan["work"]["value_clip_coefficient"]),
        value_coefficient=float(plan["work"]["value_coefficient"]),
        entropy_coefficient=float(plan["work"]["entropy_coefficient"]),
        maximum_gradient_norm=float(plan["work"]["maximum_gradient_norm"]),
        checkpoint_cadence_choices=int(plan["checkpoint"]["cadence_choices"]),
        checkpoint_cadence_wall_seconds=int(plan["checkpoint"]["cadence_wall_seconds"]),
        evaluation_cadence_choices=int(plan["work"]["evaluation_cadence_choices"]),
        intentional_interrupt_after_choices=interrupt_after,
    )


def stream_command(args: argparse.Namespace) -> int:
    plan = load_cloud_plan(args.plan)
    spec = build_stream_spec(plan, seed=args.seed, stream=args.stream)
    limits = LocalExecutionLimitsV1(
        max_cpu_threads=int(plan["platform"]["torch_intraop_threads"]),
        max_worker_processes=1,
        max_non_forced_choices=spec.total_non_forced_choices,
        max_wall_seconds=int(plan["platform"]["stream_wall_cap_seconds"]),
        allow_cuda=False,
    )
    result = run_training_stream(
        spec=spec,
        output_dir=args.output,
        limits=limits,
        resume_from=args.resume,
        interrupt=args.interrupt,
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


def run_child(
    *,
    script: Path,
    root: Path,
    plan_path: Path,
    output: Path,
    seed: int,
    stream: str,
    interrupt: bool = False,
    resume: Path | None = None,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(script),
        "stream",
        "--root",
        str(root),
        "--plan",
        str(plan_path),
        "--output",
        str(output),
        "--seed",
        str(seed),
        "--stream",
        stream,
    ]
    if interrupt:
        command.append("--interrupt")
    if resume is not None:
        command.extend(["--resume", str(resume)])
    environment = dict(os.environ)
    try:
        return subprocess.run(
            command,
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise CloudScriptError(
            f"stream child exceeded the frozen timeout for {seed}/{stream}"
        ) from error


def failure_capsule(
    *,
    output: Path,
    phase: str,
    error: BaseException,
    stdout: str | None = None,
    stderr: str | None = None,
) -> None:
    if output.exists() and output.is_dir():
        capsule_path = output / "g3a-cloud-failure-capsule-v1.json"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        capsule_path = output.parent / "g3a-cloud-failure-capsule-v1.json"
    capsule = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_FAILURE_CAPSULE",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "phase": phase,
        "error_type": type(error).__name__,
        "error": str(error)[:4000],
        "stdout_tail": (stdout or "")[-8000:],
        "stderr_tail": (stderr or "")[-8000:],
        "traceback_tail": traceback.format_exc()[-12000:],
        "status": "FAILED",
        "policy_strength_established": False,
    }
    write_canonical(capsule_path, capsule)


def build_checkpoint_manifest(
    output: Path,
    results: Mapping[int, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    records = []
    for seed in REQUIRED_SEEDS:
        for stream in REQUIRED_STREAMS:
            result = results[seed][stream]
            for checkpoint in result["checkpoints"]:
                path = Path(checkpoint["path"])
                if not path.is_file():
                    raise CloudScriptError(f"checkpoint output is missing: {path}")
                observed = file_record(path, relative_to=output)
                if observed["bytes"] != checkpoint["payload_bytes"] or observed["sha256"] != checkpoint["payload_sha256"]:
                    raise CloudScriptError(f"checkpoint payload differs: {path}")
                manifest_path = path.with_name(path.name + ".manifest.json")
                if not manifest_path.is_file():
                    raise CloudScriptError(f"checkpoint manifest is missing: {manifest_path}")
                records.append(
                    {
                        "seed": seed,
                        "stream": stream,
                        "choices": checkpoint["choices"],
                        "payload": observed,
                        "manifest": file_record(manifest_path, relative_to=output),
                        "final": bool(checkpoint.get("final", False)),
                    }
                )
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_CHECKPOINT_MANIFEST",
        "records": records,
    }


def build_output_manifest(output: Path, *, manifest_name: str) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name == manifest_name or path.name.endswith(".partial"):
            continue
        record = file_record(path, relative_to=output)
        files[record["path"]] = {"bytes": record["bytes"], "sha256": record["sha256"]}
    if not files:
        raise CloudScriptError("output manifest cannot be empty")
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_OUTPUT_MANIFEST",
        "files": files,
    }


def run_command(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise CloudScriptError(f"output directory collision: {args.output}")
    plan = load_cloud_plan(args.plan)
    if plan["outputs"]["root"] != args.output.as_posix():
        raise CloudScriptError("requested output path differs from the frozen plan")
    manifest_value = load_json_object(args.input_manifest, "G3a cloud input manifest")
    if canonical_json_bytes(manifest_value) != args.input_manifest.read_bytes():
        raise CloudScriptError("input manifest must use canonical JSON")
    validate_input_manifest(
        manifest_value,
        plan=plan,
        config_path=args.plan,
        input_root=args.input_manifest.parent,
    )
    source = verify_source_checkout(args.root, plan)
    dependencies = verify_dependencies(args.root, plan)
    environment = apply_environment(plan)

    notebook_started = time.monotonic()
    notebook_wall_cap = int(plan["platform"]["notebook_wall_cap_seconds"])
    child_timeout = int(plan["platform"]["stream_wall_cap_seconds"]) + 60

    args.output.mkdir(parents=True)
    script = Path(__file__).resolve()
    results: dict[int, dict[str, dict[str, Any]]] = {}
    resume_receipts = []
    for seed in REQUIRED_SEEDS:
        results[seed] = {}
        interruption = plan["checkpoint"]["intentional_interruptions"][str(seed)]
        for stream in REQUIRED_STREAMS:
            if time.monotonic() - notebook_started > notebook_wall_cap:
                raise CloudScriptError("notebook exceeded the frozen overall wall cap")
            stream_dir = args.output / "streams" / f"seed-{seed}" / stream
            stream_dir.parent.mkdir(parents=True, exist_ok=True)
            interruption_receipt: dict[str, Any] | None = None
            if interruption["stream"] == stream:
                first = run_child(
                    script=script,
                    root=args.root,
                    plan_path=args.plan,
                    output=stream_dir,
                    seed=seed,
                    stream=stream,
                    interrupt=True,
                    timeout_seconds=child_timeout,
                )
                (stream_dir / "interrupt.stdout.txt").write_text(first.stdout, encoding="utf-8")
                (stream_dir / "interrupt.stderr.txt").write_text(first.stderr, encoding="utf-8")
                if first.returncode:
                    raise CloudScriptError(
                        f"intentional interruption child failed for {seed}/{stream}: {first.stderr[-2000:]}"
                    )
                interruption_receipt = load_json_object(
                    stream_dir / "interruption-receipt.json", "interruption receipt"
                )
                if interruption_receipt.get("status") != "INTERRUPTED":
                    raise CloudScriptError("intentional interruption receipt differs")
                checkpoint = Path(interruption_receipt["checkpoint_path"])
                second = run_child(
                    script=script,
                    root=args.root,
                    plan_path=args.plan,
                    output=stream_dir,
                    seed=seed,
                    stream=stream,
                    resume=checkpoint,
                    timeout_seconds=child_timeout,
                )
                (stream_dir / "resume.stdout.txt").write_text(second.stdout, encoding="utf-8")
                (stream_dir / "resume.stderr.txt").write_text(second.stderr, encoding="utf-8")
                if second.returncode:
                    raise CloudScriptError(
                        f"fresh-process resume child failed for {seed}/{stream}: {second.stderr[-2000:]}"
                    )
                resume_receipts.append(
                    {
                        "seed": seed,
                        "stream": stream,
                        "interruption_choices": interruption_receipt["choices"],
                        "checkpoint_path": interruption_receipt["checkpoint_path"],
                        "checkpoint_sha256": interruption_receipt["checkpoint_sha256"],
                        "fresh_process_restore": True,
                    }
                )
            else:
                completed = run_child(
                    script=script,
                    root=args.root,
                    plan_path=args.plan,
                    output=stream_dir,
                    seed=seed,
                    stream=stream,
                    timeout_seconds=child_timeout,
                )
                (stream_dir / "run.stdout.txt").write_text(completed.stdout, encoding="utf-8")
                (stream_dir / "run.stderr.txt").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode:
                    raise CloudScriptError(
                        f"stream child failed for {seed}/{stream}: {completed.stderr[-2000:]}"
                    )
            result = load_json_object(stream_dir / STREAM_RESULT_NAME, "stream result")
            if interruption_receipt is not None:
                result["checkpoints"] = [
                    *interruption_receipt.get("checkpoints", []),
                    *result.get("checkpoints", []),
                ]
                result["per_update_metrics"] = [
                    *interruption_receipt.get("per_update_metrics", []),
                    *result.get("per_update_metrics", []),
                ]
                write_canonical(stream_dir / STREAM_RESULT_NAME, result)
            results[seed][stream] = result
            if time.monotonic() - notebook_started > notebook_wall_cap:
                raise CloudScriptError("notebook exceeded the frozen overall wall cap")

    metrics = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_METRICS",
        "seeds": {str(seed): results[seed] for seed in REQUIRED_SEEDS},
    }
    metrics_record = write_canonical(args.output / "g3a-cloud-metrics-v1.json", metrics)
    checkpoint_manifest = build_checkpoint_manifest(args.output, results)
    checkpoint_record = write_canonical(
        args.output / "g3a-cloud-checkpoint-manifest-v1.json", checkpoint_manifest
    )
    resume_record = write_canonical(
        args.output / "g3a-cloud-resume-receipt-v1.json",
        {
            "schema_version": 1,
            "kind": "KPTCG_G3A_CLOUD_RESUME_RECEIPT",
            "status": "PASS",
            "receipts": resume_receipts,
        },
    )
    if len(resume_receipts) != len(REQUIRED_SEEDS):
        raise CloudScriptError("resume receipt count differs from the declared seeds")

    run_manifest = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_RUN_MANIFEST",
        "run_id": f"g3a-cloud-correctness-v1-{plan['source']['commit'][:12]}",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source": source,
        "runtime_config": file_record(args.plan),
        "input_manifest": file_record(args.input_manifest),
        "dependencies": dependencies,
        "environment": environment,
        "authorization": {
            "user_training_approval": True,
            "private_bounded_run": True,
            "submission_created": False,
            "external_service_mutated_by_runner": False,
        },
        "budget": {
            "aggregate_non_forced_choices_per_seed": plan["work"][
                "aggregate_non_forced_choices_per_seed"
            ],
            "allocations": plan["work"]["allocations"],
            "evaluation_choices_count_toward_budget": False,
        },
    }
    run_manifest_record = write_canonical(
        args.output / "g3a-cloud-run-manifest-v1.json", run_manifest
    )
    contract = load_evaluation_contract(args.root / "configs/g3a_evaluation_v1.json")
    evidence = build_strict_evidence(
        plan,
        contract=contract,
        run_id=run_manifest["run_id"],
        stream_results=results,
        artifact_hashes={
            "run_manifest_sha256": run_manifest_record["sha256"],
            "metrics_sha256": metrics_record["sha256"],
            "checkpoint_manifest_sha256": checkpoint_record["sha256"],
        },
    )
    evidence, review = bind_independent_review(contract, evidence)
    evidence_record = write_canonical(args.output / "g3a-cloud-evidence-v1.json", evidence)
    review_record = write_canonical(
        args.output / "g3a-cloud-independent-review-v1.json", review
    )
    if review_record["sha256"] != evidence["artifacts"]["independent_review_sha256"]:
        raise CloudScriptError("retained independent review hash differs from strict evidence")

    report = {
        "schema_version": 1,
        "record_id": "artifact-g3a-cloud-correctness-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_path": "g3a-cloud-correctness-report-v1.json",
        "producer": "g3a-cloud-correctness-runner",
        "producer_version": "1",
        "run_id": run_manifest["run_id"],
        "gate_id": "G3a",
        "kind": "KPTCG_G3A_CLOUD_CORRECTNESS_REPORT",
        "status": review["status"],
        "decision": review["decision"],
        "source_commit": plan["source"]["commit"],
        "scope": "Private bounded toy G3a recurrent PPO algorithm correctness only.",
        "authorization": {
            "user_training_approval": True,
            "submission_created": False,
            "modal_used": False,
        },
        "budget": {
            "aggregate_non_forced_choices_per_seed": plan["work"][
                "aggregate_non_forced_choices_per_seed"
            ],
            "allocations": plan["work"]["allocations"],
            "exact_budget_complete": True,
            "stateless_control_included_in_aggregate": True,
        },
        "artifacts": {
            "run_manifest": run_manifest_record,
            "metrics": metrics_record,
            "checkpoint_manifest": checkpoint_record,
            "resume_receipt": resume_record,
            "strict_evidence": evidence_record,
            "independent_review": review_record,
        },
        "claim": {
            "algorithm_proof_only": True,
            "policy_strength_claimed": False,
            "g3b_promotion_authorized": False,
        },
    }
    report_record = write_canonical(
        args.output / "g3a-cloud-correctness-report-v1.json", report
    )
    output_manifest = build_output_manifest(
        args.output, manifest_name="g3a-cloud-output-manifest-v1.json"
    )
    manifest_record = write_canonical(
        args.output / "g3a-cloud-output-manifest-v1.json", output_manifest
    )
    required = set(plan["outputs"]["required_files"])
    observed = {path.name for path in args.output.iterdir() if path.is_file()}
    missing = sorted(required - observed)
    if missing:
        raise CloudScriptError(f"required notebook outputs are missing: {missing}")
    summary = {
        "status": "PASS",
        "decision": review["decision"],
        "report": report_record,
        "independent_review": review_record,
        "output_manifest": manifest_record,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the frozen private G3a cloud correctness plan")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--root", type=Path, required=True)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--input-manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)

    stream = subparsers.add_parser("stream")
    stream.add_argument("--root", type=Path, required=True)
    stream.add_argument("--plan", type=Path, required=True)
    stream.add_argument("--output", type=Path, required=True)
    stream.add_argument("--seed", type=int, required=True)
    stream.add_argument("--stream", required=True)
    stream.add_argument("--interrupt", action="store_true")
    stream.add_argument("--resume", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "stream":
            return stream_command(args)
        return run_command(args)
    except (
        CloudScriptError,
        CloudExecutionError,
        EvaluationContractError,
        OSError,
        ValueError,
    ) as error:
        output = getattr(args, "output", Path("g3a-cloud-failed"))
        if isinstance(output, Path):
            failure_capsule(output=output, phase=args.command, error=error)
        print(f"G3a cloud correctness invalid: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
