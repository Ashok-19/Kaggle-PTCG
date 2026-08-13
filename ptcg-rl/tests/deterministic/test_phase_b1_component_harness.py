from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from ptcg_rl.deterministic.b1_component_harness import (
    B1ComponentPlanV1,
    ProcessRuntimeSamplerV1,
    STAGE_CANARY,
    STAGE_SCREEN,
    prepare_runtime_manifests,
    sha256_json,
)
from ptcg_rl.deterministic.b1_policy import RuntimeRouteReceiptV1, runtime_receipt_binding_sha256


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "configs/deterministic/phase_b1_component_qualification_v2.json"


def _metrics(plan: B1ComponentPlanV1, *, cpu: float = 0.5, rss: int = 1024, reliability: dict[str, int] | None = None) -> dict:
    counters = {key: 0 for key in plan.payload["reliability_counters"]}
    if reliability:
        counters.update(reliability)
    return {
        "latency_samples_ms": [float((index % 3) + 1) for index in range(32)],
        "p99_latency_ms": 3.0,
        "component_cpu_seconds": cpu,
        "game_count": 24,
        "request_count": 240,
        "peak_rss_bytes": rss,
        "per_arm": {"B0": 8, "B1-A": 8, "B1-B": 8},
        "per_seat": {"0": 12, "1": 12},
        "reliability_counters": counters,
    }


def _manifest(plan: B1ComponentPlanV1, tmp_path: Path, run_id: str) -> dict[str, str]:
    return prepare_runtime_manifests(
        plan,
        run_id=run_id,
        stage=STAGE_CANARY,
        artifact_root=tmp_path,
        source_manifest_path=f"{run_id}-source.json",
        process_manifest_path=f"{run_id}-process.json",
        platform="linux",
        process_identity={"pid": os.getpid(), "start_token": f"test-{run_id}", "executable": sys.executable},
    )


def _raw(plan: B1ComponentPlanV1, manifest: dict[str, str], *, run_id: str, metrics: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "stage": STAGE_CANARY,
        "games": [
            {"game_index": index, "arm": cell["arm"], "anchor": cell["anchor"], "candidate_seat": cell["candidate_seat"], "outcome": "DRAW"}
            for index, cell in enumerate(plan.arm_matrix())
        ],
        "runtime_metrics": metrics or _metrics(plan),
        "metric_provenance": {
            "schema_version": 1,
            "kind": "B1_METRIC_PROVENANCE_V1",
            "run_id": run_id,
            "stage": STAGE_CANARY,
            "plan_sha256": plan.plan_sha256,
            **manifest,
            "sampler_kind": "ProcessRuntimeSamplerV1",
            "platform": "linux",
        },
    }


def _seal(plan: B1ComponentPlanV1, tmp_path: Path, *, run_id: str, metrics: dict | None = None) -> tuple[dict, dict[str, str], Path, Path]:
    manifest = _manifest(plan, tmp_path, run_id)
    raw = _raw(plan, manifest, run_id=run_id, metrics=metrics)
    artifact = tmp_path / f"{run_id}.raw.json"
    sidecar = tmp_path / f"{run_id}.raw.json.sha256.json"
    envelope = plan.seal_evidence(
        run_id=run_id,
        raw_evidence=raw,
        source_receipts={
            "source_manifest_path": manifest["source_manifest_path"],
            "source_manifest_sha256": manifest["source_manifest_sha256"],
        },
        last_completed_game=24,
        raw_artifact_path=artifact,
        sidecar_path=sidecar,
        artifact_root=tmp_path,
    )
    return envelope, manifest, artifact, sidecar


def test_component_plan_requires_exact_stage0_canary_and_gates_192_screen():
    plan = B1ComponentPlanV1.from_path(PLAN)
    assert plan.arms == ("B0", "B1-A", "B1-B")
    assert len(plan.arm_matrix(STAGE_CANARY)) == 24
    assert all(cell["games"] == 1 for cell in plan.arm_matrix(STAGE_CANARY))
    assert plan.canary_games_all_arms == 24
    assert plan.games_per_arm == 64
    assert plan.games_all_arms == 192
    with pytest.raises(ValueError, match="review receipt"):
        plan.arm_matrix(STAGE_SCREEN)


@pytest.mark.parametrize(
    ("field_path", "value", "message"),
    [
        (("runtime_receipt",), "/inside/repository/receipt.json", "repository"),
        (("runtime_receipt_sha256",), "a" * 64, "content hash"),
        (("candidate", "deck_path"), "/inside/repository/deck.csv", "repository|exact component plan"),
        (("knowledge_base", "sha256"), "a" * 64, "knowledge-base|exact component plan"),
    ],
)
def test_component_plan_rejects_dependency_and_receipt_mutations(tmp_path: Path, field_path, value, message: str):
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    mutated = tmp_path / "component-plan-mutated.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        B1ComponentPlanV1.from_path(mutated)


def test_standalone_runtime_receipt_requires_exact_parsed_content_and_plan_binding(tmp_path: Path):
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    payload["runtime_receipt"] = "configs/deterministic/phase_b1_native_route_receipt_v1.json"
    mutated = tmp_path / "component-plan-mutated.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="runtime receipt"):
        B1ComponentPlanV1.from_path(mutated)


def test_content_addressed_0444_manifests_seal_and_resume(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="b1-canary-001")
    assert envelope["sealed"] is True
    assert envelope["native_launch_authorized"] is False
    assert envelope["raw_evidence_sha256"] == sha256_json(json.loads(artifact.read_text(encoding="utf-8")))
    assert envelope["process_manifest_sha256"] == manifest["process_manifest_sha256"]
    assert envelope["source_manifest_sha256"] == manifest["source_manifest_sha256"]
    assert os.stat(artifact).st_mode & 0o222 == 0
    assert os.stat(sidecar).st_mode & 0o222 == 0
    plan.verify_resume(
        envelope,
        source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
        raw_artifact_path=artifact,
        sidecar_path=sidecar,
        artifact_root=tmp_path,
    )


def test_manifest_missing_mutation_and_arbitrary_digest_are_rejected(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    run_id = "manifest-missing"
    manifest = _manifest(plan, tmp_path, run_id)
    raw = _raw(plan, manifest, run_id=run_id)
    (tmp_path / manifest["process_manifest_path"]).unlink()
    with pytest.raises(ValueError, match="process manifest"):
        plan.seal_evidence(
            run_id=run_id,
            raw_evidence=raw,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            last_completed_game=24,
            raw_artifact_path=tmp_path / "missing.raw.json",
            artifact_root=tmp_path,
        )

    run_id = "arbitrary-source"
    manifest = _manifest(plan, tmp_path, run_id)
    raw = _raw(plan, manifest, run_id=run_id)
    with pytest.raises(ValueError, match="typed source-manifest"):
        plan.seal_evidence(
            run_id=run_id,
            raw_evidence=raw,
            source_receipts={"policy": "a" * 64},
            last_completed_game=24,
            raw_artifact_path=tmp_path / "arbitrary.raw.json",
            artifact_root=tmp_path,
        )


def test_resume_rejects_source_and_process_manifest_content_tampering(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="manifest-tamper")
    source_path = tmp_path / manifest["source_manifest_path"]
    source_path.chmod(0o644)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["sources"][next(iter(source["sources"]))]["sha256"] = "a" * 64
    source_path.write_bytes(json.dumps(source, sort_keys=True, separators=(",", ":")).encode())
    source_path.chmod(0o444)
    with pytest.raises(ValueError, match="source manifest|digest"):
        plan.verify_resume(
            envelope,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )


def test_process_manifest_dependency_and_identity_mutation_is_rejected(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="process-tamper")
    process_path = tmp_path / manifest["process_manifest_path"]
    process_path.chmod(0o644)
    process = json.loads(process_path.read_text(encoding="utf-8"))
    process["process_identity"]["start_token"] = "different-process"
    process_path.write_bytes(json.dumps(process, sort_keys=True, separators=(",", ":")).encode())
    process_path.chmod(0o444)
    with pytest.raises(ValueError, match="process manifest|digest"):
        plan.verify_resume(
            envelope,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )

    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="process-scope-tamper")
    process_path = tmp_path / manifest["process_manifest_path"]
    process_path.chmod(0o644)
    process = json.loads(process_path.read_text(encoding="utf-8"))
    process["dependency_receipts"]["card_table"]["scope"] = "UNAUTHORIZED_SCOPE"
    process_path.write_bytes(json.dumps(process, sort_keys=True, separators=(",", ":")).encode())
    process_path.chmod(0o444)
    with pytest.raises(ValueError, match="process manifest|digest"):
        plan.verify_resume(
            envelope,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )


def test_stage1_requires_actual_post_run_independent_attestation_and_parent_receipt(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    with pytest.raises(ValueError, match="review receipt"):
        plan.arm_matrix(STAGE_SCREEN)

    run_id = "self-authored-review"
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id=run_id)
    review_path = tmp_path / plan.payload["independent_attestation"]["review_artifact_path"]
    parent_path = tmp_path / plan.payload["independent_attestation"]["parent_authorization_path"]
    review_path.parent.mkdir(parents=True, exist_ok=True)
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    review = {
        "schema_version": 1,
        "kind": "B1_INDEPENDENT_STAGE0_ATTESTATION_V1",
        "status": "PASS",
        "scope": "B1_STAGE0_CANARY_INDEPENDENT_REVIEW",
        "plan_sha256": plan.plan_sha256,
        "stage": STAGE_CANARY,
        "run_id": run_id,
        "reviewer_id": "self",
        "reviewer_role": "INDEPENDENT_REVIEWER",
        "reviewer_authority_sha256": "a" * 64,
        "audited_commit": "a" * 40,
        "audited_source_sha256": {},
        "runtime_receipt_path": plan.payload["runtime_receipt"],
        "runtime_receipt_sha256": plan.payload["runtime_receipt_sha256"],
        "capability_evidence": RuntimeRouteReceiptV1.from_path(ROOT / plan.payload["runtime_receipt"]).payload["provenance"]["capability_evidence"],
        "canary_evidence_path": artifact.name,
        "canary_evidence_sha256": envelope["raw_evidence_sha256"],
        "canary_sidecar_path": sidecar.name,
        "canary_sidecar_sha256": envelope["sidecar_sha256"],
        "parent_authorization_path": plan.payload["independent_attestation"]["parent_authorization_path"],
        "parent_authorization_sha256": "b" * 64,
        "post_run_stage0": True,
        "stage0_game_count": 24,
        "native_launch_authorized": False,
        "screen_unlocked": True,
    }
    review_path.write_bytes(json.dumps(review, sort_keys=True, separators=(",", ":")).encode())
    review_path.chmod(0o444)
    parent_path.write_bytes(b"{}")
    parent_path.chmod(0o444)
    pointer = {
        "review_artifact_path": plan.payload["independent_attestation"]["review_artifact_path"],
        "review_artifact_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "canary_evidence_path": artifact.name,
        "canary_evidence_sha256": envelope["raw_evidence_sha256"],
        "canary_sidecar_path": sidecar.name,
        "canary_sidecar_sha256": envelope["sidecar_sha256"],
        "parent_authorization_path": plan.payload["independent_attestation"]["parent_authorization_path"],
        "parent_authorization_sha256": hashlib.sha256(parent_path.read_bytes()).hexdigest(),
    }
    with pytest.raises(ValueError, match="parent-authorized|configured receipt|hash"):
        plan.arm_matrix(STAGE_SCREEN, canary_review=pointer, artifact_root=tmp_path)


def test_component_metrics_require_finite_p99_rss_and_reliability_maps(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    bad_p99 = _metrics(plan)
    bad_p99["p99_latency_ms"] = float("nan")
    with pytest.raises(ValueError, match="p99"):
        _seal(plan, tmp_path, run_id="bad-p99", metrics=bad_p99)
    bad_rss = _metrics(plan, rss=536870913)
    with pytest.raises(ValueError, match="RSS"):
        _seal(plan, tmp_path, run_id="bad-rss", metrics=bad_rss)
    bad_counter = _metrics(plan, reliability={"failures": 1})
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="defect-stop", metrics=bad_counter)
    assert envelope["reliability_gate_pass"] is False
    with pytest.raises(ValueError, match="reliability defect"):
        plan.verify_resume(
            envelope,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )


def test_resume_recomputes_reliability_and_enforces_run_lineage(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="lineage-a")
    forged = dict(envelope)
    forged["reliability_gate_pass"] = False
    with pytest.raises(ValueError, match="sidecar|retained evidence"):
        plan.verify_resume(
            forged,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )
    with pytest.raises(ValueError, match="nonzero resume cursor"):
        plan.verify_resume(
            {**envelope, "previous_cursor": 1},
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )


def test_metric_sample_cardinality_and_manifest_digest_are_required(tmp_path: Path):
    plan = B1ComponentPlanV1.from_path(PLAN)
    too_few = _metrics(plan)
    too_few["latency_samples_ms"] = [1.0] * 31
    too_few["p99_latency_ms"] = 1.0
    with pytest.raises(ValueError, match="at least 32"):
        _seal(plan, tmp_path, run_id="few-samples", metrics=too_few)
    envelope, manifest, artifact, sidecar = _seal(plan, tmp_path, run_id="metric-lineage")
    artifact.chmod(0o644)
    raw = json.loads(artifact.read_text(encoding="utf-8"))
    raw["metric_provenance"]["process_manifest_sha256"] = "e" * 64
    artifact.write_bytes(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())
    artifact.chmod(0o444)
    with pytest.raises(ValueError, match="digest|canonical"):
        plan.verify_resume(
            envelope,
            source_receipts={"source_manifest_path": manifest["source_manifest_path"], "source_manifest_sha256": manifest["source_manifest_sha256"]},
            raw_artifact_path=artifact,
            sidecar_path=sidecar,
            artifact_root=tmp_path,
        )


def test_process_sampler_emits_finite_cpu_rss_and_percentile_evidence():
    plan = B1ComponentPlanV1.from_path(PLAN)
    sampler = ProcessRuntimeSamplerV1()
    sampler.start()
    for index in range(32):
        sampler.observe_latency_ms(float((index % 2) + 1))
    metrics = sampler.finish(
        game_count=24,
        request_count=240,
        per_arm={"B0": 8, "B1-A": 8, "B1-B": 8},
        per_seat={"0": 12, "1": 12},
        reliability_counters={key: 0 for key in plan.payload["reliability_counters"]},
    )
    assert metrics.p99_latency_ms == 2.0
    assert metrics.component_cpu_seconds >= 0
    assert metrics.peak_rss_bytes >= 0


def test_receipt_binding_digest_excludes_only_cross_file_fields():
    receipt = RuntimeRouteReceiptV1.from_path(ROOT / "configs/deterministic/phase_b1_native_route_receipt_v2.json")
    assert runtime_receipt_binding_sha256(receipt.payload) == receipt.payload["provenance"]["runtime_receipt_binding_sha256"]
