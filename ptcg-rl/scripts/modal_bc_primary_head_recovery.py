from __future__ import annotations

import hashlib
import json
import pickle
import statistics
import sys
from pathlib import Path
from typing import Any

import modal

if not modal.is_local():
    import torch

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
if not modal.is_local():
    sys.path.insert(0, str(PTCG_RL / "src"))
    sys.path.insert(0, str(PTCG_RL / "scripts"))

VOLUME_NAME = "kptcg-training"
CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2.pkl")
MANIFEST = Path("/data/materialized/bc-dragapult-hq-v2/manifest.json")
SOURCE = Path("/data/runs/bc-dragapult-final-v1/3.7m/3.7m/stage-d-exact-1150-best.pt")
SOURCE_SHA256 = "dec8a1a212bf8183f603042dc858eae3223d2fb0b27cb512fb60294bf098b145"
OUTPUT = Path("/data/runs/bc-dragapult-primary-head-recovery-v1/3.7m")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_capacity_sweep.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
    )
    .add_local_file(
        PTCG_RL / "scripts/bc_train_materialized.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train_materialized.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-primary-head-recovery", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_data() -> tuple[list[Any], list[Any], list[Any], list[Any], str]:
    from bc_capacity_sweep import _episode_subset, _records_for_split

    if not CACHE.is_file() or not MANIFEST.is_file():
        raise RuntimeError("exact-v2 cache or manifest is missing")
    with CACHE.open("rb") as handle:
        episodes = pickle.load(handle)
    manifest = json.loads(MANIFEST.read_text())
    records = list(manifest["records"])
    train_all_ids = {int(r["episode_id"]) for r in _records_for_split(records, "train")}
    val_all_ids = {int(r["episode_id"]) for r in _records_for_split(records, "validation")}
    train_elite_ids = {
        int(r["episode_id"])
        for r in _records_for_split(records, "train", minimum_teacher_score=1150.0)
    }
    val_elite_ids = {
        int(r["episode_id"])
        for r in _records_for_split(records, "validation", minimum_teacher_score=1150.0)
    }
    return (
        _episode_subset(episodes, train_all_ids),
        _episode_subset(episodes, val_all_ids),
        _episode_subset(episodes, train_elite_ids),
        _episode_subset(episodes, val_elite_ids),
        _sha256(MANIFEST),
    )


def _set_trainable(model: Any, head_only: bool) -> dict[str, int]:
    trainable = 0
    frozen = 0
    for name, parameter in model.named_parameters():
        enabled = not head_only or name.startswith("policy_state.") or name.startswith(
            "policy_interaction."
        )
        parameter.requires_grad_(enabled)
        if enabled:
            trainable += parameter.numel()
        else:
            frozen += parameter.numel()
    return {"trainable": trainable, "frozen": frozen}


def _greedy_action(
    model: Any,
    output: Any,
    batch: Any,
    row: int,
    *,
    minimum: int,
    maximum: int,
) -> tuple[tuple[int, ...], bool]:
    start = int(output.option_offsets[row])
    end = int(output.option_offsets[row + 1])
    options = output.option_embeddings[start:end]
    available = batch.option_available[start:end].clone()
    prefix = model.decoder_initial(output.hidden[row])
    selected: list[int] = []
    stopped = False
    first = True
    while len(selected) < maximum:
        can_stop = len(selected) >= minimum
        if first:
            logits = model.decoder_first_logits(
                prefix, output.option_logits[start:end], available, can_stop
            )
        else:
            logits = model.decoder_logits(prefix, options, available, can_stop)
        choice = int(torch.argmax(logits).item())
        if choice == len(available):
            stopped = True
            break
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, options[choice])
        first = False
    return tuple(selected), stopped


def _teacher_metrics(model: Any, episodes: list[Any], device: Any) -> dict[str, Any]:
    from ptcg_rl.g2.network import collate_projected

    states = model.initial_hidden(len(episodes), device)
    total = 0
    matches = 0
    main_total = 0
    main_matches = 0
    hard_total = 0
    hard_matches = 0
    first_deviation: list[int | None] = [None] * len(episodes)
    maximum_length = max(len(episode.decisions) for episode in episodes)
    model.eval()
    with torch.inference_mode():
        for time_index in range(maximum_length):
            active = [i for i, episode in enumerate(episodes) if time_index < len(episode.decisions)]
            if not active:
                continue
            decisions = [episodes[i].decisions[time_index] for i in active]
            batch = collate_projected(tuple(d.projected for d in decisions), device=device)
            output = model(batch, states[active])
            states[active] = output.hidden
            for row, episode_index in enumerate(active):
                decision = decisions[row]
                if decision.request.has_only_one_outcome:
                    continue
                greedy, greedy_stopped = _greedy_action(
                    model,
                    output,
                    batch,
                    row,
                    minimum=int(decision.request.min_count),
                    maximum=int(decision.request.max_count),
                )
                teacher = tuple(decision.action.submitted_original_indices)
                matched = (
                    greedy == teacher
                    and greedy_stopped == bool(decision.action.stopped_early)
                )
                total += 1
                matches += int(matched)
                selection_type = int(
                    decision.projected.model.global_categorical_values[2]
                )
                if selection_type == 0:
                    main_total += 1
                    main_matches += int(matched)
                if len(decision.request.options) >= 6:
                    hard_total += 1
                    hard_matches += int(matched)
                if not matched and first_deviation[episode_index] is None:
                    first_deviation[episode_index] = time_index + 1
    finite = [value for value in first_deviation if value is not None]
    return {
        "policy_targets": total,
        "exact_match_rate": matches / total,
        "main_targets": main_total,
        "main_exact_match_rate": main_matches / main_total,
        "six_plus_option_targets": hard_total,
        "six_plus_option_exact_match_rate": hard_matches / hard_total,
        "zero_deviation_episodes": sum(value is None for value in first_deviation),
        "first_deviation_median": statistics.median(finite) if finite else None,
    }


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    timeout=60 * 60 * 2,
    volumes={"/data": training_volume},
)
def run() -> dict[str, Any]:
    from bc_capacity_sweep import _pack_with_fallback, _train_stage, model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.network import PTCGPolicyV1
    from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state

    device = torch.device("cuda")
    train_all, val_all, train_elite, val_elite, manifest_sha = _load_data()
    config = model_configs()["3.7m"]
    table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    model = PTCGPolicyV1(table, config).to(device)
    restored = load_training_checkpoint_model_state(
        SOURCE, model=model, expected_sha256=SOURCE_SHA256
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)

    all_train_groups, all_batch = _pack_with_fallback(
        train_all,
        preferred_batch_size=512,
        sequence_length=32,
        seed=20260815,
        device=device,
    )
    all_val_groups, _ = _pack_with_fallback(
        val_all,
        preferred_batch_size=512,
        sequence_length=32,
        seed=20260815,
        device=device,
    )
    baseline_metrics = _teacher_metrics(model, val_all, device)
    print(json.dumps({"event": "primary_head_recovery_baseline", **baseline_metrics}, sort_keys=True), flush=True)

    head_counts = _set_trainable(model, True)
    print(json.dumps({"event": "primary_head_freeze", **head_counts}, sort_keys=True), flush=True)
    head_stage = _train_stage(
        model=model,
        model_label="3.7m-primary-head",
        model_config=config,
        stage_name="head-only-exact-all",
        materialized_manifest_sha256=manifest_sha,
        train_groups=all_train_groups,
        validation_groups=all_val_groups,
        output_dir=OUTPUT,
        learning_rate=3e-4,
        epochs=5,
        minimum_teacher_score=None,
        device=device,
        bf16=True,
        maximum_gradient_norm=1.0,
        weight_decay=1e-4,
        early_stopping_patience=2,
        early_stopping_min_delta=5e-4,
    )
    head_metrics = _teacher_metrics(model, val_all, device)
    print(json.dumps({"event": "primary_head_recovery_after_head_only", **head_metrics}, sort_keys=True), flush=True)

    _set_trainable(model, False)
    full_stage = _train_stage(
        model=model,
        model_label="3.7m-primary-head",
        model_config=config,
        stage_name="full-exact-all",
        materialized_manifest_sha256=manifest_sha,
        train_groups=all_train_groups,
        validation_groups=all_val_groups,
        output_dir=OUTPUT,
        learning_rate=1e-5,
        epochs=3,
        minimum_teacher_score=None,
        device=device,
        bf16=True,
        maximum_gradient_norm=1.0,
        weight_decay=1e-4,
        early_stopping_patience=2,
        early_stopping_min_delta=2.5e-4,
    )
    full_metrics = _teacher_metrics(model, val_all, device)
    print(json.dumps({"event": "primary_head_recovery_after_full_exact", **full_metrics}, sort_keys=True), flush=True)

    del all_train_groups, all_val_groups
    torch.cuda.empty_cache()
    elite_train_groups, elite_batch = _pack_with_fallback(
        train_elite,
        preferred_batch_size=512,
        sequence_length=32,
        seed=20260815,
        device=device,
    )
    elite_val_groups, _ = _pack_with_fallback(
        val_elite,
        preferred_batch_size=512,
        sequence_length=32,
        seed=20260815,
        device=device,
    )
    elite_stage = _train_stage(
        model=model,
        model_label="3.7m-primary-head",
        model_config=config,
        stage_name="full-exact-1150",
        materialized_manifest_sha256=manifest_sha,
        train_groups=elite_train_groups,
        validation_groups=elite_val_groups,
        output_dir=OUTPUT,
        learning_rate=5e-6,
        epochs=4,
        minimum_teacher_score=1150.0,
        device=device,
        bf16=True,
        maximum_gradient_norm=1.0,
        weight_decay=1e-4,
        early_stopping_patience=2,
        early_stopping_min_delta=2.5e-4,
    )
    final_metrics = _teacher_metrics(model, val_all, device)
    final_checkpoint = Path(elite_stage["checkpoint_path"])
    report = {
        "record_id": "bc-dragapult-primary-head-recovery-v1",
        "source_checkpoint_sha256": restored.payload_sha256,
        "final_checkpoint": str(final_checkpoint),
        "final_checkpoint_sha256": elite_stage["checkpoint_sha256"],
        "manifest_sha256": manifest_sha,
        "batch_sizes": {"exact_all": all_batch, "exact_1150": elite_batch},
        "baseline_metrics": baseline_metrics,
        "head_only_metrics": head_metrics,
        "full_exact_metrics": full_metrics,
        "final_metrics": final_metrics,
        "stages": [head_stage, full_stage, elite_stage],
    }
    report_path = OUTPUT / "recovery-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    training_volume.commit()
    print(
        json.dumps(
            {
                "event": "primary_head_recovery_complete",
                "checkpoint_sha256": elite_stage["checkpoint_sha256"],
                "final_metrics": final_metrics,
                "report_path": str(report_path),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(run.remote(), indent=2, sort_keys=True))
