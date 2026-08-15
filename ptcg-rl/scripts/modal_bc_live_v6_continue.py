from __future__ import annotations

import gc
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import modal

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
VOLUME_NAME = "kptcg-training"
LIVE_DIR = Path("/data/materialized/bc-dragapult-live-v6-featurefix-v3")
LIVE_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-live-v6-featurefix-v3.pkl")
EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3")
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2-featurefix-v3.pkl")
V5_CHECKPOINT = Path(
    "/data/runs/bc-dragapult-final-v5-schema-v3-fused-update-density/3.7m/3.7m/stage-d-exact-1150-best.pt"
)
V5_CHECKPOINT_SHA256 = "7a29718bfd16d6c8ce50ba190c445624f221eec93ed59f37cf75d1f78ae56833"
OUTPUT_ROOT = Path("/data/runs/bc-dragapult-final-v6-live-continue/3.7m")
MODEL_LABEL = "3.7m"
BATCH_SIZE = 16
SEQUENCE_LENGTH = 32
MAX_TARGETS_PER_STEP = 512.0
EXACT_ANCHOR_TOLERANCE = 0.015
LIVE_ALL_TOLERANCE = 0.005

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_train_materialized.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train_materialized.py",
    )
    .add_local_file(
        PTCG_RL / "scripts/bc_capacity_sweep.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-dragapult-live-v6-continue", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric(validation: dict[str, Any]) -> float:
    return float(validation["mean_nll"])


@app.function(
    gpu="T4",
    cpu=8,
    memory=32768,
    timeout=3 * 60 * 60,
    volumes={"/data": training_volume},
)
def run(source_commit: str, force: bool = False) -> dict[str, Any]:
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit):
        raise ValueError("source_commit must be an exact lowercase Git SHA")
    for path, label in (
        (LIVE_DIR / "manifest.json", "live-v6 materialized manifest"),
        (EXACT_DIR / "manifest.json", "exact-v2 materialized manifest"),
        (V5_CHECKPOINT, "v5 checkpoint"),
    ):
        if not path.is_file():
            raise RuntimeError(f"missing {label}: {path}")
    if _sha256_file(V5_CHECKPOINT) != V5_CHECKPOINT_SHA256:
        raise RuntimeError("v5 checkpoint SHA-256 differs from frozen continuation source")
    report_path = OUTPUT_ROOT / "live-v6-continuation-report.json"
    if OUTPUT_ROOT.exists():
        if report_path.is_file() and not force:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "report_path": str(report_path),
                "report_sha256": _sha256_file(report_path),
                "final_checkpoint": report.get("final_checkpoint"),
            }
        if not force:
            raise RuntimeError(f"partial v6 continuation output exists: {OUTPUT_ROOT}")
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)

    sys.path.insert(0, "/workspace/ptcg-rl/scripts")
    sys.path.insert(0, "/workspace/ptcg-rl/src")
    import bc_capacity_sweep as sweep
    from bc_train_materialized import train_epoch_packed, validate_packed
    from ptcg_rl.g3.checkpoint import (
        load_training_checkpoint_model_state,
        save_training_checkpoint,
    )

    device = sweep.torch.device("cuda")
    if not sweep.torch.cuda.is_available():
        raise RuntimeError("v6 continuation requires CUDA")
    if not sweep.torch.cuda.is_bf16_supported():
        raise RuntimeError("v6 continuation requires BF16 support")
    sweep.torch.set_float32_matmul_precision("high")
    sweep.torch.cuda.reset_peak_memory_stats(device)

    card_table = sweep.load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    config = sweep.model_configs()[MODEL_LABEL]
    model = sweep._build_model(config, card_table, seed=20260816, device=device)
    initializer = load_training_checkpoint_model_state(
        V5_CHECKPOINT,
        model=model,
        expected_sha256=V5_CHECKPOINT_SHA256,
    )

    live_manifest, live_records = sweep.load_materialized_manifest(LIVE_DIR)
    exact_manifest, exact_records = sweep.load_materialized_manifest(EXACT_DIR)
    for manifest, label in ((live_manifest, "live-v6"), (exact_manifest, "exact-v2")):
        if manifest.get("card_data_sha256") != card_table.card_data_sha256:
            raise RuntimeError(f"{label} card-data hash differs from trainer card table")

    live_train_records = sweep._records_for_split(live_records, "train", minimum_teacher_score=1050.0)
    live_validation_records = sweep._records_for_split(live_records, "validation", minimum_teacher_score=1050.0)
    exact_train_records = sweep._records_for_split(exact_records, "train")
    exact_validation_records = sweep._records_for_split(exact_records, "validation")
    if not live_train_records or not live_validation_records:
        raise RuntimeError("live-v6 has no train/validation records after 1050 floor")

    live_episodes, live_load_source = sweep._load_or_build_object_cache(
        root=LIVE_DIR,
        records=[*live_train_records, *live_validation_records],
        workers=8,
        manifest_sha256=str(live_manifest["manifest_sha256"]),
        cache_path=LIVE_CACHE,
        corpus_label="live-v6",
    )
    exact_episodes, exact_load_source = sweep._load_or_build_object_cache(
        root=EXACT_DIR,
        records=[*exact_train_records, *exact_validation_records],
        workers=8,
        manifest_sha256=str(exact_manifest["manifest_sha256"]),
        cache_path=EXACT_CACHE,
        corpus_label="exact-v2-anchor",
    )
    live_train = [episode for episode in live_episodes if episode.split == "train"]
    live_validation = [episode for episode in live_episodes if episode.split == "validation"]
    exact_validation = [episode for episode in exact_episodes if episode.split == "validation"]

    def subset(records: list[dict[str, Any]], episodes: list[Any], floor: float) -> list[Any]:
        ids = {
            int(record["episode_id"])
            for record in records
            if float(record.get("teacher_score_qualification_value") or 0.0) >= floor
        }
        return sweep._episode_subset(episodes, ids)

    live_train_1090 = subset(live_train_records, live_train, 1090.0)
    live_train_1150 = subset(live_train_records, live_train, 1150.0)
    live_validation_1090 = subset(live_validation_records, live_validation, 1090.0)
    live_validation_1150 = subset(live_validation_records, live_validation, 1150.0)

    exact_validation_groups, _ = sweep._pack_with_fallback(
        exact_validation,
        preferred_batch_size=BATCH_SIZE,
        sequence_length=SEQUENCE_LENGTH,
        seed=2026081601,
        device=device,
    )
    live_validation_groups, _ = sweep._pack_with_fallback(
        live_validation,
        preferred_batch_size=BATCH_SIZE,
        sequence_length=SEQUENCE_LENGTH,
        seed=2026081602,
        device=device,
    )
    live_validation_1090_groups = (
        sweep._pack_with_fallback(
            live_validation_1090,
            preferred_batch_size=BATCH_SIZE,
            sequence_length=SEQUENCE_LENGTH,
            seed=2026081603,
            device=device,
        )[0]
        if live_validation_1090
        else None
    )
    live_validation_1150_groups = (
        sweep._pack_with_fallback(
            live_validation_1150,
            preferred_batch_size=BATCH_SIZE,
            sequence_length=SEQUENCE_LENGTH,
            seed=2026081604,
            device=device,
        )[0]
        if live_validation_1150
        else None
    )

    def validate_views() -> dict[str, Any]:
        exact = validate_packed(
            model, exact_validation_groups, device=device, bf16=True, maximum_groups=None
        )
        live_all = validate_packed(
            model, live_validation_groups, device=device, bf16=True, maximum_groups=None
        )
        result: dict[str, Any] = {"exact_anchor": exact, "live_all": live_all}
        if live_validation_1090_groups is not None:
            result["live_1090"] = validate_packed(
                model,
                live_validation_1090_groups,
                device=device,
                bf16=True,
                maximum_groups=None,
            )
        if live_validation_1150_groups is not None:
            result["live_1150"] = validate_packed(
                model,
                live_validation_1150_groups,
                device=device,
                bf16=True,
                maximum_groups=None,
            )
        return result

    baseline = validate_views()
    baseline_exact = _metric(baseline["exact_anchor"])
    baseline_live_all = _metric(baseline["live_all"])
    print(
        json.dumps(
            {
                "event": "live_v6_baseline",
                "exact_anchor_nll": baseline_exact,
                "live_all_nll": baseline_live_all,
                "live_1090_nll": _metric(baseline["live_1090"]) if "live_1090" in baseline else None,
                "live_1150_nll": _metric(baseline["live_1150"]) if "live_1150" in baseline else None,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    stages: list[dict[str, Any]] = [
        {
            "name": "stage-e-live-coverage-1050",
            "episodes": live_train,
            "learning_rate": 1.0e-5,
            "epochs": 4,
            "selection_view": "live_all",
        },
        {
            "name": "stage-f-live-high-1090",
            "episodes": live_train_1090,
            "learning_rate": 5.0e-6,
            "epochs": 4,
            "selection_view": "live_1090" if live_validation_1090_groups is not None else "live_all",
        },
    ]
    if len(live_train_1150) >= 64 and live_validation_1150_groups is not None:
        stages.append(
            {
                "name": "stage-g-live-elite-1150",
                "episodes": live_train_1150,
                "learning_rate": 2.5e-6,
                "epochs": 3,
                "selection_view": "live_1150",
            }
        )

    best_checkpoint_path = V5_CHECKPOINT
    best_checkpoint_sha256 = V5_CHECKPOINT_SHA256
    best_views = baseline
    stage_reports: list[dict[str, Any]] = []

    for stage_index, stage in enumerate(stages):
        episodes = stage["episodes"]
        if not episodes:
            continue
        train_groups, effective_batch = sweep._pack_with_fallback(
            episodes,
            preferred_batch_size=BATCH_SIZE,
            sequence_length=SEQUENCE_LENGTH,
            seed=2026081610 + stage_index,
            device=device,
            maximum_targets_per_optimizer_step=MAX_TARGETS_PER_STEP,
        )
        targets, optimizer_steps, targets_per_step = sweep._optimizer_update_density(train_groups)
        if targets_per_step > MAX_TARGETS_PER_STEP:
            raise RuntimeError("v6 continuation update density exceeded the 512-target guard")
        optimizer = sweep.torch.optim.AdamW(
            model.parameters(),
            lr=float(stage["learning_rate"]),
            weight_decay=1.0e-4,
            fused=True,
        )
        scheduler = sweep.torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
        stage_history: list[dict[str, Any]] = []
        stage_best_target = _metric(best_views[stage["selection_view"]])
        stage_best_checkpoint: Path | None = None
        stage_best_sha: str | None = None
        epochs_without_improvement = 0

        print(
            json.dumps(
                {
                    "event": "live_v6_stage_start",
                    "stage": stage["name"],
                    "episodes": len(episodes),
                    "policy_targets": targets,
                    "optimizer_steps": optimizer_steps,
                    "targets_per_optimizer_step": targets_per_step,
                    "effective_batch_size": effective_batch,
                    "learning_rate": stage["learning_rate"],
                    "selection_view": stage["selection_view"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

        for epoch in range(1, int(stage["epochs"]) + 1):
            training = train_epoch_packed(
                model,
                optimizer,
                scheduler,
                train_groups,
                device=device,
                bf16=True,
                maximum_gradient_norm=1.0,
                epoch=epoch,
                maximum_groups=None,
            )
            views = validate_views()
            exact_nll = _metric(views["exact_anchor"])
            live_all_nll = _metric(views["live_all"])
            target_nll = _metric(views[stage["selection_view"]])
            eligible = (
                exact_nll <= baseline_exact + EXACT_ANCHOR_TOLERANCE
                and live_all_nll <= baseline_live_all + LIVE_ALL_TOLERANCE
            )
            improved = eligible and target_nll < stage_best_target - 1.0e-4
            checkpoint_record: dict[str, Any] | None = None
            if improved:
                stage_best_target = target_nll
                epochs_without_improvement = 0
                path = OUTPUT_ROOT / f"{stage['name']}-best.pt"
                receipt = save_training_checkpoint(
                    path,
                    model=model,
                    optimizer=optimizer,
                    scheduler=scheduler,
                    scaler=None,
                    counters={"stage_epoch": epoch},
                    league={
                        "kind": "dragapult-live-v6-continuation",
                        "source_commit": source_commit,
                        "stage": stage["name"],
                        "selection_view": stage["selection_view"],
                        "live_manifest_sha256": live_manifest["manifest_sha256"],
                        "exact_anchor_manifest_sha256": exact_manifest["manifest_sha256"],
                        "v5_initializer_sha256": V5_CHECKPOINT_SHA256,
                        "exact_anchor_tolerance": EXACT_ANCHOR_TOLERANCE,
                        "live_all_tolerance": LIVE_ALL_TOLERANCE,
                    },
                    rollout_boundary={"completed_stage": stage["name"], "completed_epoch": epoch},
                    include_cuda_rng=True,
                )
                stage_best_checkpoint = path
                stage_best_sha = str(receipt["payload_sha256"])
                checkpoint_record = {
                    "path": str(path),
                    "sha256": stage_best_sha,
                    "bytes": int(receipt["payload_bytes"]),
                }
            else:
                epochs_without_improvement += 1
            row = {
                "epoch": epoch,
                "training": training,
                "validation": views,
                "eligible": eligible,
                "selection_target_nll": target_nll,
                "improved": improved,
                "checkpoint": checkpoint_record,
            }
            stage_history.append(row)
            print(
                json.dumps(
                    {
                        "event": "live_v6_stage_epoch",
                        "stage": stage["name"],
                        "epoch": epoch,
                        "training_nll": training["mean_nll"],
                        "exact_anchor_nll": exact_nll,
                        "live_all_nll": live_all_nll,
                        "selection_target_nll": target_nll,
                        "eligible": eligible,
                        "improved": improved,
                        "targets_per_second": training["policy_targets_per_second"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if epochs_without_improvement >= 2:
                break

        if stage_best_checkpoint is not None and stage_best_sha is not None:
            load_training_checkpoint_model_state(
                stage_best_checkpoint,
                model=model,
                expected_sha256=stage_best_sha,
            )
            best_checkpoint_path = stage_best_checkpoint
            best_checkpoint_sha256 = stage_best_sha
            best_views = validate_views()
            stage_accepted = True
        else:
            load_training_checkpoint_model_state(
                best_checkpoint_path,
                model=model,
                expected_sha256=best_checkpoint_sha256,
            )
            stage_accepted = False
        stage_reports.append(
            {
                "stage": stage["name"],
                "learning_rate": stage["learning_rate"],
                "requested_epochs": stage["epochs"],
                "episodes": len(episodes),
                "update_density": {
                    "policy_targets": targets,
                    "optimizer_steps": optimizer_steps,
                    "targets_per_optimizer_step": targets_per_step,
                    "effective_batch_size": effective_batch,
                },
                "selection_view": stage["selection_view"],
                "accepted": stage_accepted,
                "best_checkpoint_path": str(stage_best_checkpoint) if stage_best_checkpoint else None,
                "best_checkpoint_sha256": stage_best_sha,
                "history": stage_history,
            }
        )
        del train_groups, optimizer, scheduler
        gc.collect()
        sweep.torch.cuda.empty_cache()

    final_views = validate_views()
    final_optimizer = sweep.torch.optim.AdamW(model.parameters(), lr=1.0e-6, weight_decay=0.0, fused=True)
    final_scheduler = sweep.torch.optim.lr_scheduler.LambdaLR(final_optimizer, lr_lambda=lambda _step: 1.0)
    final_path = OUTPUT_ROOT / "final-selected.pt"
    final_receipt = save_training_checkpoint(
        final_path,
        model=model,
        optimizer=final_optimizer,
        scheduler=final_scheduler,
        scaler=None,
        counters={"accepted_live_stages": sum(int(stage["accepted"]) for stage in stage_reports)},
        league={
            "kind": "dragapult-live-v6-final-selection",
            "source_commit": source_commit,
            "v5_initializer_sha256": V5_CHECKPOINT_SHA256,
            "selected_source_checkpoint_path": str(best_checkpoint_path),
            "selected_source_checkpoint_sha256": best_checkpoint_sha256,
            "quality_weighting": "curriculum exposure: 1050+ once, 1090+ additional stage, 1150+ optional additional stage",
        },
        rollout_boundary={"completed": True},
        include_cuda_rng=True,
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "bc-dragapult-live-v6-continuation",
        "status": "PASS_BC_LIVE_V6_CONTINUATION",
        "source_commit": source_commit,
        "device": str(device),
        "gpu_name": sweep.torch.cuda.get_device_name(device),
        "model_label": MODEL_LABEL,
        "trainable_parameters": model.trainable_parameter_count,
        "architecture_sha256": model.architecture_sha256,
        "initializer": {
            "path": str(V5_CHECKPOINT),
            "sha256": initializer.payload_sha256,
            "bytes": initializer.payload_bytes,
        },
        "corpora": {
            "live_manifest_sha256": live_manifest["manifest_sha256"],
            "exact_anchor_manifest_sha256": exact_manifest["manifest_sha256"],
            "live_load_source": live_load_source,
            "exact_load_source": exact_load_source,
            "live_train_1050": len(live_train),
            "live_train_1090": len(live_train_1090),
            "live_train_1150": len(live_train_1150),
            "live_validation_1050": len(live_validation),
            "live_validation_1090": len(live_validation_1090),
            "live_validation_1150": len(live_validation_1150),
            "exact_anchor_validation": len(exact_validation),
        },
        "selection_contract": {
            "baseline_exact_anchor_nll": baseline_exact,
            "baseline_live_all_nll": baseline_live_all,
            "maximum_exact_anchor_regression": EXACT_ANCHOR_TOLERANCE,
            "maximum_live_all_regression": LIVE_ALL_TOLERANCE,
            "best_checkpoint_restored_after_each_stage": True,
        },
        "baseline_validation": baseline,
        "stages": stage_reports,
        "final_validation": final_views,
        "final_checkpoint": {
            "path": str(final_path),
            "sha256": final_receipt["payload_sha256"],
            "bytes": final_receipt["payload_bytes"],
            "selected_source_checkpoint_path": str(best_checkpoint_path),
            "selected_source_checkpoint_sha256": best_checkpoint_sha256,
        },
        "peak_allocated_bytes": int(sweep.torch.cuda.max_memory_allocated(device)),
        "peak_reserved_bytes": int(sweep.torch.cuda.max_memory_reserved(device)),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    print(
        json.dumps(
            {
                "event": "live_v6_continuation_complete",
                "final_checkpoint_sha256": report["final_checkpoint"]["sha256"],
                "baseline_exact_anchor_nll": baseline_exact,
                "final_exact_anchor_nll": _metric(final_views["exact_anchor"]),
                "baseline_live_all_nll": baseline_live_all,
                "final_live_all_nll": _metric(final_views["live_all"]),
                "accepted_live_stages": sum(int(stage["accepted"]) for stage in stage_reports),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return {
        "status": report["status"],
        "report_path": str(report_path),
        "report_sha256": _sha256_file(report_path),
        "final_checkpoint": report["final_checkpoint"],
        "baseline_exact_anchor_nll": baseline_exact,
        "final_exact_anchor_nll": _metric(final_views["exact_anchor"]),
        "baseline_live_all_nll": baseline_live_all,
        "final_live_all_nll": _metric(final_views["live_all"]),
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PTCG_RL, text=True
    ).strip()
    print(json.dumps(run.remote(source_commit, force), indent=2, sort_keys=True))
