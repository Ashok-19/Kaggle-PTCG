from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ptcg_rl.g3.cloud_execution import build_dashboard_report
from ptcg_rl.g3.cloud_notebook import build_kaggle_notebook
from ptcg_rl.g3.cloud_plan import (
    EXPECTED_ALGORITHM_BOUNDARIES,
    REQUIRED_SEEDS,
    REQUIRED_STOP_CONDITIONS,
    REQUIRED_STREAMS,
    review_cloud_plan,
    validate_cloud_plan,
)
from ptcg_rl.g3.evaluation import canonical_json_bytes

DOCKER_IMAGE = (
    "gcr.io/kaggle-images/python@sha256:"
    "dafd4ce5668bbf1ad422e4c109e0f18c9623c3a7c7f48b0235f13142755c40b9"
)
DATASET_OWNER = "ashok205"
DATASET_SLUG = "kptcg-g3a-correctness-inputs"
DATASET_VERSION = 1
NOTEBOOK_OWNER = "ashok205"
NOTEBOOK_SLUG = "kptcg-g3a-cloud-correctness-v1"
NOTEBOOK_VERSION = 1
BUNDLE_NAME = "g3a-cloud-source-v1.bundle"
SOURCE_MANIFEST_NAME = "g3a-cloud-source-manifest-v1.json"
CONFIG_ASSET_NAME = "g3a-cloud-plan-v1.json"
INPUT_MANIFEST_NAME = "g3a-cloud-input-manifest-v1.json"
NOTEBOOK_NAME = "kptcg-g3a-cloud-correctness-v1.ipynb"

COMPLETED_NEGATIVE_RESULTS = [
    {
        "attempt": "raw_commit_bundle_ref",
        "result": "FAILED_CLOSED",
        "evidence": "git bundle create refused an empty bundle when given only a raw commit object",
        "resolution": "use symbolic HEAD and verify the advertised head equals the frozen commit",
        "rerun": "covered by test_build_bundle_is_nonempty_deterministic_and_head_bound",
    },
    {
        "attempt": "default_multithreaded_bundle_pack",
        "result": "FAILED_CLOSED",
        "evidence": "two valid default Git bundle builds were not byte-identical",
        "resolution": "freeze pack.threads=1 and retain duplicate byte comparison",
        "rerun": "duplicate bundle regression passes",
    },
    {
        "attempt": "stale_recurrent_evidence_path",
        "result": "FAILED_CLOSED",
        "evidence": "independent plan review rejected tests/g2/test_neural_policy.py because it does not exist",
        "resolution": "bind tests/g2/test_reliability.py and validate every evidence-matrix path",
        "rerun": "edge-case path regression passes",
    },
    {
        "attempt": "canonical_allocation_object_order",
        "result": "FAILED_CLOSED",
        "evidence": "clean-bundle review rejected canonical JSON because object key sorting changed iteration order",
        "resolution": "validate exact allocation membership independently of JSON object order",
        "rerun": "canonical plan round-trip regression passes",
    },
    {
        "attempt": "full_suite_g2_submicro_precision",
        "result": "COMPLETED_TRANSIENT_NEGATIVE",
        "evidence": "one existing G2 permutation test failed once with visually equal tensors at 1e-6 tolerance",
        "resolution": "no unsupported source change; isolate and repeat before full-suite rerun",
        "rerun": "isolated test passed six consecutive runs and the complete suite passed",
    },
]

CRITICAL_SOURCE_PATHS = (
    "uv.lock",
    "configs/g3a_evaluation_v1.json",
    "src/ptcg_rl/g3/ppo.py",
    "src/ptcg_rl/g3/checkpoint.py",
    "src/ptcg_rl/g3/toy.py",
    "src/ptcg_rl/g3/cloud_plan.py",
    "src/ptcg_rl/g3/cloud_runner.py",
    "src/ptcg_rl/g3/cloud_execution.py",
    "src/ptcg_rl/g3/cloud_notebook.py",
    "scripts/g3a_cloud_correctness.py",
    "scripts/g3a_review.py",
    "tests/g2/test_reliability.py",
    "tests/g3/test_ppo.py",
    "tests/g3/test_training_checkpoint.py",
    "tests/g3/test_cloud_plan.py",
    "tests/g3/test_cloud_runner.py",
    "tests/g3/test_cloud_execution.py",
    "tests/g3/test_cloud_notebook.py",
    "tests/g3/test_cloud_script.py",
)

EDGE_CASE_MATRIX = {
    "compound_action_and_masks": {
        "truncation_during_forced_chain": ["tests/g3/test_ppo.py"],
        "boundary_closure_and_exclusive_terminal_truncation": ["tests/g3/test_ppo.py"],
        "no_trace_continuation_across_boundary": ["tests/g3/test_ppo.py"],
        "terminal_outcome_both_players_and_no_interleaving": ["tests/g3/test_ppo.py"],
        "ordered_unique_selection_stop_and_min_max": [
            "tests/g3/test_ppo.py",
            "tests/g3/test_toy.py",
        ],
        "sealed_g2_decoder_probability_replay": ["tests/g3/test_ppo.py"],
    },
    "recurrent_ownership": {
        "reset_episode_owner_version": ["tests/g2/test_reliability.py"],
        "duplicate_idempotence_stale_and_out_of_order": ["tests/g2/test_reliability.py"],
        "worker_replacement_clears_owner_state": ["tests/g2/test_reliability.py"],
        "slices_do_not_cross_terminal_or_policy_version": ["tests/g3/test_ppo.py"],
        "long_forced_chains_without_ppo_nodes": ["tests/g3/test_ppo.py"],
        "policy_version_lag_zero": ["tests/g2/test_reliability.py"],
    },
    "checkpoint_resume": {
        "atomic_cleanup_hash_mismatch_and_truncation": [
            "tests/g3/test_training_checkpoint.py"
        ],
        "noncanonical_manifest_and_wrong_model_state": [
            "tests/g3/test_training_checkpoint.py"
        ],
        "optimizer_scheduler_counters_league_rollout_restore": [
            "tests/g3/test_training_checkpoint.py",
            "tests/g3/test_cloud_runner.py",
        ],
        "python_numpy_torch_rng_restore": [
            "tests/g3/test_training_checkpoint.py",
            "tests/g3/test_cloud_runner.py",
        ],
        "cuda_rng_mismatch_and_unsafe_payload_rejection": [
            "tests/g3/test_training_checkpoint.py"
        ],
        "fresh_process_fixed_evaluation_and_exact_final_budget": [
            "tests/g3/test_cloud_runner.py"
        ],
    },
    "cloud_notebook": {
        "missing_input_and_wrong_dataset_version": ["tests/g3/test_cloud_execution.py"],
        "wrong_source_commit_dirty_source_and_hash_mismatch": [
            "tests/g3/test_cloud_plan.py",
            "tests/g3/test_cloud_execution.py",
        ],
        "output_collision_and_interrupted_notebook": [
            "tests/g3/test_cloud_runner.py",
            "tests/g3/test_cloud_script.py",
        ],
        "missing_report_and_dashboard_envelope": ["tests/g3/test_cloud_execution.py"],
        "single_thin_notebook_and_no_saved_outputs": ["tests/g3/test_cloud_notebook.py"],
        "output_pagination_and_download_parity": ["tests/g3/test_cloud_plan.py"],
        "dual_authorization": ["tests/g3/test_cloud_script.py"],
    },
}


def run_git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(f"Git command failed ({' '.join(args)}): {completed.stderr.strip()}")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix() if root else path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def write_canonical(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    raw = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return {
        "path": path.as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_bundle(repository: Path, output: Path, commit: str) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    first = output.with_suffix(output.suffix + ".first")
    second = output.with_suffix(output.suffix + ".second")
    for candidate in (first, second):
        candidate.unlink(missing_ok=True)
        completed = subprocess.run(
            [
                "git",
                "-c",
                "pack.threads=1",
                "bundle",
                "create",
                str(candidate),
                "HEAD",
            ],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(f"Git bundle creation failed: {completed.stderr.strip()}")
        verify = subprocess.run(
            ["git", "bundle", "verify", str(candidate)],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if verify.returncode:
            raise RuntimeError(f"Git bundle verification failed: {verify.stderr.strip()}")
        listed = subprocess.run(
            ["git", "bundle", "list-heads", str(candidate)],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        if listed.returncode or commit not in listed.stdout:
            raise RuntimeError("Git bundle does not contain the exact source commit")
    if first.read_bytes() != second.read_bytes():
        raise RuntimeError("duplicate Git bundle builds are not byte-identical")
    first.replace(output)
    second.unlink(missing_ok=True)
    return record(output)


def independent_review_from_bundle(
    *,
    bundle_path: Path,
    config_path: Path,
    expected_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="kptcg-g3a-plan-review-") as temporary:
        checkout = Path(temporary) / "repo"
        clone = subprocess.run(
            ["git", "clone", "--quiet", str(bundle_path), str(checkout)],
            check=False,
            capture_output=True,
            text=True,
        )
        if clone.returncode:
            raise RuntimeError(f"independent review clone failed: {clone.stderr.strip()}")
        head = run_git(checkout, "rev-parse", "HEAD")
        tree = run_git(checkout, "rev-parse", "HEAD^{tree}")
        status = run_git(checkout, "status", "--porcelain")
        if head != expected_commit or status:
            raise RuntimeError("independent review checkout identity or cleanliness differs")
        project = checkout / "ptcg-rl"
        code = """
import json
import sys
from pathlib import Path
from ptcg_rl.g3.cloud_plan import load_cloud_plan, review_cloud_plan
plan = load_cloud_plan(Path(sys.argv[1]))
review = review_cloud_plan(
    plan,
    root=Path(sys.argv[2]),
    expected_source_commit=sys.argv[3],
)
print(json.dumps(review, sort_keys=True, separators=(\",\", \":\"), allow_nan=False))
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(project / "src")
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(config_path),
                str(project),
                expected_commit,
            ],
            cwd=project,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                f"independent review process failed: {completed.stderr.strip()}"
            )
        try:
            review = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("independent review output is not JSON") from error
        if not isinstance(review, dict):
            raise RuntimeError("independent review output must be an object")
        return review, {
            "fresh_process": True,
            "clean_bundle_checkout": True,
            "source_commit": head,
            "source_tree": tree,
            "python_executable": sys.executable,
            "stdout_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        }


def platform_comparison() -> list[dict[str, Any]]:
    return [
        {
            "platform": "private-kaggle-cpu",
            "selected": True,
            "availability": (
                "verified 2026-07-22 through connected private notebook metadata, saved status, "
                "output listing, and individual output download"
            ),
            "cpu_limit": "four-core hard ceiling; two active Torch threads; one inter-op; zero workers",
            "internet_off": "private notebook metadata is internet-off and two runtime probes must fail",
            "checkpoint_persistence": (
                "atomic versioned checkpoints and manifests retained under saved notebook output"
            ),
            "output_retention_download": (
                "MCP saved-output listing, pagination fields, and named-file download verified"
            ),
            "reproducibility": (
                "exact Git bundle, commit/tree, Kaggle image digest, uv.lock hash, config, input "
                "manifest, and one notebook hash"
            ),
            "wall_limit": "internal notebook cap 14400 seconds and per-stream cap 2400 seconds",
            "runtime_basis": (
                "maximum retained two-thread local wall 14.104740312 seconds per 1024 choices; "
                "twelve 25000-choice streams plus checkpoint and process overhead"
            ),
            "cost_quota": "private CPU notebook; expected cost USD 0 and accelerator quota use 0",
            "rejection_reasons": [],
        },
        {
            "platform": "private-colab-cpu",
            "selected": False,
            "availability": (
                "manual session only; no connected session-status, retained-output listing, or "
                "automatic output retrieval path is available to this project"
            ),
            "cpu_limit": "free CPU resources and topology are dynamic and not guaranteed",
            "internet_off": "no frozen notebook-level internet-off control was verified",
            "checkpoint_persistence": (
                "runtime VM is ephemeral; reliable persistence would require Drive or manual transfer"
            ),
            "output_retention_download": "manual download or external Drive mutation would be required",
            "reproducibility": "base runtime versions and resources can change across sessions",
            "wall_limit": (
                "official FAQ says free notebooks can run at most twelve hours but limits are dynamic"
            ),
            "runtime_basis": "no retained project-native Colab timing measurement exists",
            "cost_quota": "free tier may cost USD 0 but availability and limits are dynamic",
            "rejection_reasons": [
                "no verifiable internet-off, persistent checkpoint, and automated output retrieval chain"
            ],
        },
        {
            "platform": "github-actions-private-cpu",
            "selected": False,
            "availability": (
                "official hosted runner exists, but no authorized workflow or private Kaggle asset "
                "integration exists in this repository"
            ),
            "cpu_limit": "official standard private Linux runner specification is two CPUs",
            "internet_off": "hosted jobs are networked by default; no frozen isolation is implemented",
            "checkpoint_persistence": "requires explicit artifact uploads before job termination",
            "output_retention_download": (
                "artifact APIs exist but are not integrated with the current project workflow"
            ),
            "reproducibility": "runner labels are mutable and no exact hosted image digest is frozen",
            "wall_limit": "official hosted job maximum is six hours",
            "runtime_basis": "two CPUs are plausible but no retained project timing exists",
            "cost_quota": "would consume private Actions minutes and artifact storage",
            "rejection_reasons": [
                "no repository-supported private-asset workflow and no authorized external workflow mutation"
            ],
        },
    ]


def build_plan(
    *,
    commit: str,
    tree: str,
    bundle_record: dict[str, Any],
    source_manifest_record: dict[str, Any],
    lock_record: dict[str, Any],
) -> dict[str, Any]:
    allocations = {
        str(seed): {stream: 25_000 for stream in REQUIRED_STREAMS}
        for seed in REQUIRED_SEEDS
    }
    plan = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_CORRECTNESS_PLAN",
        "plan_id": "g3a-cloud-correctness-v1",
        "authorization": {
            "training_launch_authorized": False,
            "external_mutation_authorized": False,
            "submission_authorized": False,
        },
        "algorithm_boundaries": dict(EXPECTED_ALGORITHM_BOUNDARIES),
        "stop_conditions": list(REQUIRED_STOP_CONDITIONS),
        "source": {
            "commit": commit,
            "tree": tree,
            "require_clean_checkout": True,
            "bundle_manifest_sha256": source_manifest_record["sha256"],
        },
        "platform": {
            "selected": "private-kaggle-cpu",
            "private": True,
            "internet": False,
            "gpu": False,
            "tpu": False,
            "maximum_cpu_cores": 4,
            "worker_processes": 0,
            "torch_intraop_threads": 2,
            "torch_interop_threads": 1,
            "thread_environment": {
                "OMP_NUM_THREADS": "2",
                "MKL_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "notebook_wall_cap_seconds": 14_400,
            "stream_wall_cap_seconds": 2_400,
            "docker_image": DOCKER_IMAGE,
            "kernel_run_type": "Batch",
        },
        "dependencies": {
            "python": "3.12.13",
            "torch": "2.10.0+cpu",
            "numpy": "2.0.2",
            "pydantic": "2.12.3",
            "lock_path": "uv.lock",
            "lock_bytes": lock_record["bytes"],
            "lock_sha256": lock_record["sha256"],
        },
        "platform_comparison": platform_comparison(),
        "work": {
            "seeds": list(REQUIRED_SEEDS),
            "aggregate_non_forced_choices_per_seed": 100_000,
            "allocations": allocations,
            "stateless_control_included_in_aggregate": True,
            "choices_per_update": 64,
            "ppo_epochs": 4,
            "learning_rate": 0.005,
            "adam_epsilon": 0.00001,
            "clip_coefficient": 0.2,
            "value_clip_coefficient": 0.2,
            "value_coefficient": 0.5,
            "entropy_coefficient": 0.01,
            "maximum_gradient_norm": 0.5,
            "evaluation_choices_count_toward_budget": False,
            "evaluation_cadence_choices": 4_096,
            "no_result_dependent_extension": True,
        },
        "checkpoint": {
            "cadence_choices": 4_096,
            "cadence_wall_seconds": 300,
            "maximum_payload_bytes": 536_870_912,
            "intentional_interruptions": {
                str(REQUIRED_SEEDS[0]): {
                    "stream": "recurrent-cue-v1",
                    "after_choices": 12_288,
                },
                str(REQUIRED_SEEDS[1]): {
                    "stream": "variable-option-multiselect-v1",
                    "after_choices": 12_288,
                },
                str(REQUIRED_SEEDS[2]): {
                    "stream": "recurrent-cue-v1-stateless",
                    "after_choices": 12_288,
                },
            },
            "fresh_process_restore_required": True,
            "fixed_evaluation_atol": 0.00001,
            "fixed_evaluation_rtol": 0.0,
            "content_addressed_retention": True,
        },
        "assets": {
            "dataset": {
                "owner": DATASET_OWNER,
                "slug": DATASET_SLUG,
                "version": DATASET_VERSION,
                "publication_state": "PREPARED_LOCAL_NOT_PUBLISHED",
                "files": [bundle_record, source_manifest_record],
            },
            "notebook": {
                "owner": NOTEBOOK_OWNER,
                "slug": NOTEBOOK_SLUG,
                "version": NOTEBOOK_VERSION,
                "publication_state": "PREPARED_LOCAL_NOT_PUBLISHED",
            },
        },
        "outputs": {
            "root": "/kaggle/working/kptcg-g3a-cloud-correctness-v1/output",
            "required_files": [
                "g3a-cloud-correctness-report-v1.json",
                "g3a-cloud-independent-review-v1.json",
                "g3a-cloud-output-manifest-v1.json",
                "g3a-cloud-resume-receipt-v1.json",
            ],
            "collision_policy": "FAIL_IF_EXISTS",
        },
        "acceptance": {
            "recurrent_minimum_score": 0.85,
            "stateless_maximum_score": 0.5,
            "recurrent_minimum_margin": 0.25,
            "maximum_probability_error": 0.00001,
            "budget_relative_drift_maximum": 0.0025,
            "zero_tolerance_total": 0,
            "strength_claim_allowed": False,
            "g3b_promotion_allowed": False,
        },
        "edge_case_evidence": {
            "compound_action": ["tests/g3/test_ppo.py", "tests/g3/test_toy.py"],
            "recurrent_ownership": [
                "tests/g2/test_reliability.py",
                "tests/g3/test_ppo.py",
            ],
            "checkpoint_resume": [
                "tests/g3/test_training_checkpoint.py",
                "tests/g3/test_cloud_runner.py",
            ],
            "cloud_notebook": [
                "tests/g3/test_cloud_plan.py",
                "tests/g3/test_cloud_execution.py",
                "tests/g3/test_cloud_notebook.py",
                "tests/g3/test_cloud_script.py",
            ],
        },
    }
    return validate_cloud_plan(plan)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze deterministic G3a Kaggle plan assets")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-report", type=Path, required=True)
    parser.add_argument("--review-report", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    repository = root.parent
    config_path = args.config if args.config.is_absolute() else root / args.config
    plan_report_path = (
        args.plan_report if args.plan_report.is_absolute() else root / args.plan_report
    )
    review_report_path = (
        args.review_report if args.review_report.is_absolute() else root / args.review_report
    )
    asset_dir = args.asset_dir if args.asset_dir.is_absolute() else root / args.asset_dir
    notebook_path = args.notebook if args.notebook.is_absolute() else root / args.notebook

    if notebook_path.name != NOTEBOOK_NAME:
        raise SystemExit(f"notebook filename must remain {NOTEBOOK_NAME}")

    head = run_git(repository, "rev-parse", "HEAD")
    tree = run_git(repository, "rev-parse", "HEAD^{tree}")
    status = run_git(repository, "status", "--porcelain", "--untracked-files=no")
    if status:
        raise SystemExit("source worktree must be clean before freezing G3a assets")
    asset_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = asset_dir / BUNDLE_NAME
    bundle_record = build_bundle(repository, bundle_path, head)
    lock_path = root / "uv.lock"
    lock_record = record(lock_path, root=root)

    critical_records = []
    for relative in CRITICAL_SOURCE_PATHS:
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"critical source path is missing: {relative}")
        tracked = run_git(repository, "ls-files", "--error-unmatch", f"ptcg-rl/{relative}")
        if not tracked:
            raise SystemExit(f"critical source path is not tracked: {relative}")
        critical_records.append(record(path, root=root))
    source_manifest = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_SOURCE_MANIFEST",
        "source_commit": head,
        "source_tree": tree,
        "include_rule": "entire tracked Git tree at source_commit",
        "exclude_rule": "all untracked, ignored, private, generated, and working-tree-only files",
        "bundle": bundle_record,
        "dependency_lock": lock_record,
        "critical_files": critical_records,
    }
    source_manifest_path = asset_dir / SOURCE_MANIFEST_NAME
    source_manifest_record = write_canonical(source_manifest_path, source_manifest)
    source_manifest_record = {
        "path": SOURCE_MANIFEST_NAME,
        "bytes": source_manifest_record["bytes"],
        "sha256": source_manifest_record["sha256"],
    }

    plan = build_plan(
        commit=head,
        tree=tree,
        bundle_record=bundle_record,
        source_manifest_record=source_manifest_record,
        lock_record=lock_record,
    )
    config_record = write_canonical(config_path, plan)
    config_asset_path = asset_dir / CONFIG_ASSET_NAME
    shutil.copyfile(config_path, config_asset_path)
    config_asset_record = record(config_asset_path)

    input_manifest = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_INPUT_MANIFEST",
        "dataset": {
            "owner": DATASET_OWNER,
            "slug": DATASET_SLUG,
            "version": DATASET_VERSION,
        },
        "source": {"commit": head, "tree": tree},
        "files": [
            {**config_asset_record, "role": "runtime_config"},
            {**bundle_record, "role": "source_bundle"},
            {**source_manifest_record, "role": "source_manifest"},
        ],
    }
    input_manifest_path = asset_dir / INPUT_MANIFEST_NAME
    input_manifest_record = write_canonical(input_manifest_path, input_manifest)

    notebook_record = build_kaggle_notebook(
        notebook_path,
        source_commit=head,
        source_tree=tree,
        bundle_name=BUNDLE_NAME,
        bundle_sha256=bundle_record["sha256"],
        plan_name=CONFIG_ASSET_NAME,
        plan_sha256=config_asset_record["sha256"],
        input_manifest_name=INPUT_MANIFEST_NAME,
        input_manifest_sha256=input_manifest_record["sha256"],
    )
    notebook_record["path"] = notebook_path.relative_to(root).as_posix()
    input_manifest_public_record = {
        "path": input_manifest_path.relative_to(root).as_posix(),
        "bytes": input_manifest_record["bytes"],
        "sha256": input_manifest_record["sha256"],
    }

    local_review = review_cloud_plan(plan, root=root, expected_source_commit=head)
    review, review_execution = independent_review_from_bundle(
        bundle_path=bundle_path,
        config_path=config_path,
        expected_commit=head,
    )
    if canonical_json_bytes(review) != canonical_json_bytes(local_review):
        raise SystemExit("fresh-process independent review differs from local review")
    now = datetime.now(UTC).isoformat()
    review_envelope = {
        "schema_version": 1,
        "record_id": "artifact-g3a-cloud-correctness-plan-review-v1",
        "created_at_utc": now,
        "updated_at_utc": now,
        "source_path": review_report_path.relative_to(root).as_posix(),
        "producer": "g3a-cloud-plan-independent-reviewer",
        "producer_version": "1",
        "run_id": f"g3a-cloud-plan-review-v1-{head[:12]}",
        "gate_id": "G3a",
        "kind": "KPTCG_G3A_CLOUD_PLAN_REVIEW_REPORT",
        "status": "SUCCEEDED",
        "decision": "PASS",
        "source_commit": head,
        "review": review,
        "review_execution": review_execution,
        "training_launched": False,
        "external_service_mutated": False,
        "policy_strength_established": False,
    }
    review_record = write_canonical(review_report_path, review_envelope)

    measured_max = 14.104740312000104
    linear_seconds = measured_max * 25_000 / 1_024 * 12
    runtime_estimate = {
        "measured_max_wall_seconds_per_1024_choices": measured_max,
        "linear_twelve_stream_seconds": linear_seconds,
        "lower_seconds": 5_400,
        "upper_seconds": 10_800,
        "notebook_hard_cap_seconds": 14_400,
        "uncertainty": (
            "allows 31-161 percent overhead above the retained two-thread linear extrapolation "
            "for Kaggle variability, checkpoint I/O, fresh processes, manifests, and review"
        ),
    }
    plan_report = build_dashboard_report(
        source_path=plan_report_path.relative_to(root).as_posix(),
        source_commit=head,
        plan=plan,
        review=review,
        notebook=notebook_record,
        input_manifest=input_manifest_public_record,
        runtime_estimate=runtime_estimate,
    )
    plan_report.update(
        {
            "runtime_config": {
                "path": config_path.relative_to(root).as_posix(),
                "bytes": config_record["bytes"],
                "sha256": config_record["sha256"],
            },
            "source_bundle": {
                **bundle_record,
                "path": bundle_path.relative_to(root).as_posix(),
            },
            "source_manifest": {
                "path": source_manifest_path.relative_to(root).as_posix(),
                "bytes": source_manifest_record["bytes"],
                "sha256": source_manifest_record["sha256"],
            },
            "independent_review_report": {
                "path": review_report_path.relative_to(root).as_posix(),
                "bytes": review_record["bytes"],
                "sha256": review_record["sha256"],
            },
            "independent_review_execution": review_execution,
            "edge_case_matrix": EDGE_CASE_MATRIX,
            "completed_negative_results": COMPLETED_NEGATIVE_RESULTS,
            "provenance_layers": [
                "source commit/tree and deterministic Git bundle",
                "source manifest binding bundle, lock, and critical files",
                "canonical runtime config binding source and dataset version",
                "canonical input manifest binding config, bundle, and source manifest",
                "single notebook binding config, bundle, and input-manifest hashes",
                "independent plan review binding clean source commit and evidence paths",
            ],
            "asset_publication": {
                "dataset": "PREPARED_LOCAL_NOT_PUBLISHED",
                "notebook": "PREPARED_LOCAL_NOT_PUBLISHED",
                "automatic_dataset_version_update_available": False,
                "external_mutation_authorized": False,
            },
            "manual_launch_steps": [
                "Publish or update only the stable private dataset slug to numeric version 1 using the prepared asset directory after explicit approval.",
                "Create or update only the stable private notebook slug to numeric version 1 using the prepared single notebook after explicit approval.",
                "Attach dataset version 1, select CPU, keep Internet OFF, GPU OFF, and TPU OFF.",
                "Set KPTCG_G3A_TRAINING_APPROVED=YES only after approving this exact plan.",
                "Run all cells and do not edit the notebook or attached versions.",
            ],
            "kill_procedure": [
                "Use Kaggle Stop Session immediately if a failure capsule appears, the output root collides, resource settings differ, or the internal four-hour cap approaches.",
                "Do not restart from the notebook UI without retaining the saved output and reviewing the failure capsule.",
                "A fresh approved rerun must use the same immutable config or a newly reviewed plan version.",
            ],
            "download_workflow": [
                "Read saved notebook status; UI state alone is insufficient.",
                "List all saved outputs with pagination until no next page remains.",
                "Download g3a-cloud-output-manifest-v1.json first and verify its local bytes and SHA-256.",
                "Download every manifest-listed file individually or by ZIP, then compare both methods when available.",
                "Require every local SHA-256 and byte count to equal the notebook manifest before review.",
            ],
        }
    )
    plan_report_record = write_canonical(plan_report_path, plan_report)

    dataset_metadata = {
        "title": "KPTCG G3a Correctness Inputs",
        "id": f"{DATASET_OWNER}/{DATASET_SLUG}",
        "isPrivate": True,
        "version": DATASET_VERSION,
        "files": [
            CONFIG_ASSET_NAME,
            BUNDLE_NAME,
            SOURCE_MANIFEST_NAME,
            INPUT_MANIFEST_NAME,
        ],
        "publication_state": "PREPARED_LOCAL_NOT_PUBLISHED",
    }
    write_canonical(
        asset_dir.parent / "g3a-cloud-correctness-dataset-metadata.local.json",
        dataset_metadata,
    )

    summary = {
        "source_commit": head,
        "source_tree": tree,
        "config": config_record,
        "bundle": bundle_record,
        "source_manifest": source_manifest_record,
        "input_manifest": input_manifest_public_record,
        "notebook": notebook_record,
        "review_report": review_record,
        "plan_report": plan_report_record,
        "training_launched": False,
        "external_service_mutated": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"G3a cloud plan freeze failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
