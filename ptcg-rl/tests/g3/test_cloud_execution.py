from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ptcg_rl.g3.cloud_execution import (
    CloudExecutionError,
    bind_independent_review,
    build_dashboard_report,
    build_strict_evidence,
    validate_input_manifest,
)
from ptcg_rl.g3.evaluation import canonical_json_bytes, load_evaluation_contract
from tests.g3.test_cloud_plan import REQUIRED_SEEDS, STREAMS, plan_fixture


def result(stream: str, seed: int, score: float) -> dict[str, object]:
    stateless = stream.endswith("-stateless")
    task_id = "recurrent-cue-v1" if stateless else stream
    fixed = {
        "task_id": task_id,
        "stateless": stateless,
        "score": score,
        "passed_cases": 2 if score == 1.0 else 1,
        "total_cases": 2,
        "cases": [],
    }
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3A_STREAM_RESULT",
        "status": "SUCCEEDED",
        "spec_sha256": "1" * 64,
        "task_id": task_id,
        "seed": seed,
        "stateless": stateless,
        "choices": 25_000,
        "updates": 391,
        "initial_score": 0.5,
        "final_score": score,
        "maximum_probability_replay_error": 0.0,
        "maximum_initial_ratio_error": 0.0,
        "maximum_gradient_norm_before_clip": 0.5,
        "final_model_sha256": "2" * 64,
        "fixed_evaluation_sha256": hashlib.sha256(canonical_json_bytes(fixed)).hexdigest(),
        "fixed_evaluation": fixed,
        "final_checkpoint_path": f"seed-{seed}/{stream}/checkpoint-025000.pt",
        "final_checkpoint_sha256": "3" * 64,
        "resume": {
            "resumed": stream == "recurrent-cue-v1",
            "checkpoint_sha256": "4" * 64 if stream == "recurrent-cue-v1" else None,
            "checkpoint_bytes": 100 if stream == "recurrent-cue-v1" else None,
            "restored_rng_states": ["python", "numpy", "torch_cpu"]
            if stream == "recurrent-cue-v1"
            else [],
            "fixed_evaluation_exact": True if stream == "recurrent-cue-v1" else None,
        },
        "checkpoints": [],
        "per_update_metrics": [],
        "wall_seconds": 1.0,
        "zero_tolerance_counters": {
            "crashes": 0,
            "fallbacks": 0,
            "hidden_state_cross_owner_events": 0,
            "invalid_actions": 0,
            "nan_inf": 0,
            "stale_inference_requests": 0,
            "timeouts": 0,
            "unclassified_truncations": 0,
        },
        "zero_tolerance_total": 0,
    }


def stream_results() -> dict[int, dict[str, dict[str, object]]]:
    values: dict[int, dict[str, dict[str, object]]] = {}
    for seed in REQUIRED_SEEDS:
        values[seed] = {
            "masked-bandit-v1": result("masked-bandit-v1", seed, 1.0),
            "recurrent-cue-v1": result("recurrent-cue-v1", seed, 1.0),
            "variable-option-multiselect-v1": result(
                "variable-option-multiselect-v1", seed, 1.0
            ),
            "recurrent-cue-v1-stateless": result(
                "recurrent-cue-v1-stateless", seed, 0.5
            ),
        }
    return values


def test_input_manifest_binds_dataset_version_config_and_bundle(tmp_path: Path) -> None:
    plan = plan_fixture()
    config = tmp_path / "config.json"
    config.write_bytes(canonical_json_bytes(plan))
    bundle = tmp_path / "g3a-cloud-source-v1.bundle"
    bundle.write_bytes(b"bundle")
    source_manifest = tmp_path / "g3a-cloud-source-manifest-v1.json"
    source_manifest.write_bytes(b"source-manifest")
    plan["assets"]["dataset"]["files"] = [
        {
            "path": bundle.name,
            "bytes": bundle.stat().st_size,
            "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        },
        {
            "path": source_manifest.name,
            "bytes": source_manifest.stat().st_size,
            "sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        },
    ]
    plan["source"]["bundle_manifest_sha256"] = hashlib.sha256(
        source_manifest.read_bytes()
    ).hexdigest()
    config.write_bytes(canonical_json_bytes(plan))
    manifest = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_INPUT_MANIFEST",
        "dataset": {
            "owner": "ashok205",
            "slug": "kptcg-g3a-correctness-inputs",
            "version": 1,
        },
        "source": {"commit": "1" * 40, "tree": "2" * 40},
        "files": [
            {
                "path": config.name,
                "bytes": config.stat().st_size,
                "sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                "role": "runtime_config",
            },
            {
                "path": bundle.name,
                "bytes": bundle.stat().st_size,
                "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
                "role": "source_bundle",
            },
            {
                "path": source_manifest.name,
                "bytes": source_manifest.stat().st_size,
                "sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
                "role": "source_manifest",
            },
        ],
    }
    validate_input_manifest(manifest, plan=plan, config_path=config, input_root=tmp_path)

    manifest["dataset"]["version"] = 2
    with pytest.raises(CloudExecutionError, match="dataset version"):
        validate_input_manifest(manifest, plan=plan, config_path=config, input_root=tmp_path)


def test_strict_evidence_requires_all_four_streams_and_exact_control_ceiling() -> None:
    contract = load_evaluation_contract(Path("configs/g3a_evaluation_v1.json"))
    results = stream_results()
    evidence = build_strict_evidence(
        plan_fixture(),
        contract=contract,
        run_id="g3a-cloud-correctness-v1-test",
        stream_results=results,
        artifact_hashes={
            "run_manifest_sha256": "4" * 64,
            "metrics_sha256": "5" * 64,
            "checkpoint_manifest_sha256": "6" * 64,
        },
    )
    assert evidence["budget"]["non_forced_choices_per_seed"] == [100_000] * 3
    assert evidence["seeds"][0]["tasks"]["recurrent-cue-v1"]["margin_vs_stateless"] == 0.5

    missing = stream_results()
    missing[REQUIRED_SEEDS[0]].pop(STREAMS[-1])
    with pytest.raises(CloudExecutionError, match="missing stream"):
        build_strict_evidence(
            plan_fixture(),
            contract=contract,
            run_id="g3a-cloud-correctness-v1-test",
            stream_results=missing,
            artifact_hashes={
                "run_manifest_sha256": "4" * 64,
                "metrics_sha256": "5" * 64,
                "checkpoint_manifest_sha256": "6" * 64,
            },
        )


def test_independent_review_hash_binding_is_stable() -> None:
    contract = load_evaluation_contract(Path("configs/g3a_evaluation_v1.json"))
    evidence = build_strict_evidence(
        plan_fixture(),
        contract=contract,
        run_id="g3a-cloud-correctness-v1-test",
        stream_results=stream_results(),
        artifact_hashes={
            "run_manifest_sha256": "4" * 64,
            "metrics_sha256": "5" * 64,
            "checkpoint_manifest_sha256": "6" * 64,
        },
    )
    bound, review = bind_independent_review(contract, evidence)
    assert review["decision"] == "PASS"
    assert bound["artifacts"]["independent_review_sha256"] == hashlib.sha256(
        canonical_json_bytes(review)
    ).hexdigest()


def test_dashboard_report_maps_status_only_plan_review_to_pass() -> None:
    report = build_dashboard_report(
        source_path="reports/artifacts/g3a-cloud-correctness-plan-v1.json",
        source_commit="1" * 40,
        plan=plan_fixture(),
        review={"status": "PASS", "failures": []},
        notebook={"path": "private/kaggle/notebooks/notebook.ipynb", "bytes": 1, "sha256": "7" * 64},
        input_manifest={"path": "private/kaggle/assets/manifest.json", "bytes": 1, "sha256": "8" * 64},
        runtime_estimate={"lower_seconds": 5_400, "upper_seconds": 10_800},
    )
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"


def test_dashboard_report_has_valid_envelope() -> None:
    report = build_dashboard_report(
        source_path="reports/artifacts/g3a-cloud-correctness-plan-v1.json",
        source_commit="1" * 40,
        plan=plan_fixture(),
        review={"status": "PASS", "decision": "PASS", "failures": []},
        notebook={"path": "private/kaggle/notebooks/notebook.ipynb", "bytes": 1, "sha256": "7" * 64},
        input_manifest={"path": "private/kaggle/assets/manifest.json", "bytes": 1, "sha256": "8" * 64},
        runtime_estimate={"lower_seconds": 5_400, "upper_seconds": 10_800},
    )
    for name in (
        "record_id",
        "created_at_utc",
        "source_path",
        "producer",
        "producer_version",
        "status",
        "gate_id",
        "decision",
    ):
        assert report[name]
    assert report["authorization"]["training_launch_authorized"] is False
    assert report["external_service_mutated"] is False
