from __future__ import annotations

import hashlib
import json
import pickle
import re
import statistics
import sys
from collections import defaultdict
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
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2-featurefix-v3.pkl")
EXACT_MANIFEST = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3/manifest.json")
OUTPUT_DIR = Path("/data/runs/bc-dragapult-3p7m-schema-v3-learning-probe-v1")
REPORT_PATH = OUTPUT_DIR / "report.json"
MODEL_LABEL = "3.7m"
SCORING_CONTRACT = "corrected-primary-head-first-choice"
SEED = 20260815
SUBSET_EPISODES = 64
EPOCHS = 15
SEQUENCE_LENGTH = 32

VARIANTS = (
    {
        "label": "small8-lr2p5e5-clip1",
        "batch_size": 8,
        "learning_rate": 2.5e-5,
        "maximum_gradient_norm": 1.0,
    },
)

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

app = modal.App("kptcg-bc-3p7m-learning-probe", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_embedding(a: torch.Tensor, b: torch.Tensor) -> bool:
    return bool(torch.allclose(a, b, atol=1e-6, rtol=1e-5))


def _representation_equivalent(
    option_embeddings: torch.Tensor,
    teacher: tuple[int, ...],
    teacher_stopped: bool,
    greedy: tuple[int, ...],
    greedy_stopped: bool,
) -> bool:
    if teacher_stopped != greedy_stopped or len(teacher) != len(greedy):
        return False
    return all(
        _same_embedding(option_embeddings[teacher_index], option_embeddings[greedy_index])
        for teacher_index, greedy_index in zip(teacher, greedy, strict=True)
    )


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
                prefix,
                output.option_logits[start:end],
                available,
                can_stop,
            )
        else:
            logits = model.decoder_logits(prefix, options, available, can_stop)
        choice = int(torch.argmax(logits).item())
        if choice == len(available):
            if not can_stop:
                raise RuntimeError("probe decoder selected STOP before minimum count")
            stopped = True
            break
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, options[choice])
        first = False
    return tuple(selected), stopped


def _teacher_metrics(model: Any, episodes: list[Any], device: torch.device) -> dict[str, Any]:
    from ptcg_rl.g2.network import collate_projected

    states = model.initial_hidden(len(episodes), device)
    total = 0
    exact = 0
    equivalent = 0
    main_total = 0
    main_exact = 0
    first_deviation: list[int | None] = [None] * len(episodes)
    maximum_length = max(len(episode.decisions) for episode in episodes)
    model.eval()
    with torch.inference_mode():
        for time_index in range(maximum_length):
            active = [index for index, episode in enumerate(episodes) if time_index < len(episode.decisions)]
            if not active:
                continue
            decisions = [episodes[index].decisions[time_index] for index in active]
            batch = collate_projected(tuple(decision.projected for decision in decisions), device=device)
            output = model(batch, states[active])
            states[active] = output.hidden
            for row, episode_index in enumerate(active):
                decision = decisions[row]
                if decision.request.has_only_one_outcome:
                    continue
                start = int(output.option_offsets[row])
                end = int(output.option_offsets[row + 1])
                teacher = tuple(decision.action.submitted_original_indices)
                teacher_stopped = bool(decision.action.stopped_early)
                greedy, greedy_stopped = _greedy_action(
                    model,
                    output,
                    batch,
                    row,
                    minimum=int(decision.request.min_count),
                    maximum=int(decision.request.max_count),
                )
                exact_match = teacher == greedy and teacher_stopped == greedy_stopped
                equivalent_match = _representation_equivalent(
                    output.option_embeddings[start:end],
                    teacher,
                    teacher_stopped,
                    greedy,
                    greedy_stopped,
                )
                total += 1
                exact += int(exact_match)
                equivalent += int(equivalent_match)
                if int(decision.projected.model.global_categorical_values[2]) == 0:
                    main_total += 1
                    main_exact += int(exact_match)
                if not exact_match and first_deviation[episode_index] is None:
                    first_deviation[episode_index] = time_index + 1
    finite = [value for value in first_deviation if value is not None]
    return {
        "policy_targets": total,
        "exact_match_rate": exact / total,
        "representation_equivalent_match_rate": equivalent / total,
        "main_exact_match_rate": main_exact / main_total,
        "first_deviation_median": statistics.median(finite) if finite else None,
        "zero_deviation_episodes": sum(value is None for value in first_deviation),
    }


def _gradient_audit(model: Any, first_group: Any, device: torch.device) -> dict[str, Any]:
    from ptcg_rl.bc.training import packed_recurrent_chunk_loss

    model.train()
    model.zero_grad(set_to_none=True)
    chunk = first_group.chunks[0]
    hidden = model.initial_hidden(first_group.batch_size, device)
    result = packed_recurrent_chunk_loss(model, chunk, hidden=hidden, non_blocking=True)
    if result.loss is None:
        raise RuntimeError("first probe chunk unexpectedly contains no policy target")
    result.loss.backward()

    groups: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "parameters": 0.0,
            "parameters_with_gradient": 0.0,
            "parameters_with_nonzero_gradient": 0.0,
            "squared_gradient_norm": 0.0,
        }
    )
    no_gradient: list[str] = []
    zero_gradient: list[str] = []
    for name, parameter in model.named_parameters():
        prefix = name.split(".", 1)[0]
        group = groups[prefix]
        group["parameters"] += parameter.numel()
        if parameter.grad is None:
            no_gradient.append(name)
            continue
        group["parameters_with_gradient"] += parameter.numel()
        grad = parameter.grad.detach().float()
        norm = float(torch.linalg.vector_norm(grad).cpu())
        group["squared_gradient_norm"] += norm * norm
        if norm > 0.0:
            group["parameters_with_nonzero_gradient"] += parameter.numel()
        else:
            zero_gradient.append(name)

    summarized: dict[str, Any] = {}
    for prefix, values in sorted(groups.items()):
        parameter_count = int(values["parameters"])
        summarized[prefix] = {
            "parameters": parameter_count,
            "gradient_parameter_fraction": values["parameters_with_gradient"] / parameter_count,
            "nonzero_gradient_parameter_fraction": (
                values["parameters_with_nonzero_gradient"] / parameter_count
            ),
            "gradient_norm": values["squared_gradient_norm"] ** 0.5,
        }
    model.zero_grad(set_to_none=True)
    return {
        "loss": float(result.loss.detach().float().cpu()),
        "policy_targets": result.policy_targets,
        "groups": summarized,
        "parameters_without_gradient": no_gradient,
        "parameters_with_zero_gradient": zero_gradient,
    }


def _run_variant(
    *,
    variant: dict[str, Any],
    initial_state: dict[str, torch.Tensor],
    episodes: list[Any],
    card_table: Any,
    config: Any,
    device: torch.device,
) -> dict[str, Any]:
    from bc_capacity_sweep import _build_model, _pack
    from bc_train_materialized import train_epoch_packed, validate_packed

    model = _build_model(config, card_table, seed=SEED, device=device)
    model.load_state_dict(initial_state, strict=True)
    groups = _pack(
        episodes,
        batch_size=int(variant["batch_size"]),
        sequence_length=SEQUENCE_LENGTH,
        seed=SEED,
        device=device,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(variant["learning_rate"]),
        weight_decay=1e-4,
        fused=True,
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    baseline_nll = validate_packed(model, groups, device=device, bf16=True, maximum_groups=None)
    baseline_metrics = _teacher_metrics(model, episodes, device)
    history: list[dict[str, Any]] = []
    for epoch in range(1, EPOCHS + 1):
        training = train_epoch_packed(
            model,
            optimizer,
            scheduler,
            groups,
            device=device,
            bf16=True,
            maximum_gradient_norm=float(variant["maximum_gradient_norm"]),
            epoch=epoch,
            maximum_groups=None,
        )
        row: dict[str, Any] = {"epoch": epoch, "training": training}
        if epoch in {1, 5, 10, EPOCHS}:
            row["same_subset_validation"] = validate_packed(
                model,
                groups,
                device=device,
                bf16=True,
                maximum_groups=None,
            )
            row["teacher_metrics"] = _teacher_metrics(model, episodes, device)
        history.append(row)
        print(
            json.dumps(
                {
                    "event": "bc_3p7m_learning_probe_epoch",
                    "variant": variant["label"],
                    "epoch": epoch,
                    "training_nll": training["mean_nll"],
                    "gradient_clip_fraction": training["gradient_clip_fraction"],
                    "gradient_clip_scale_mean": training["gradient_clip_scale_mean"],
                    "targets_per_optimizer_step": training["policy_targets_per_optimizer_step"],
                    "same_subset_nll": (
                        row.get("same_subset_validation", {}).get("mean_nll")
                    ),
                    "semantic_match": row.get("teacher_metrics", {}).get(
                        "representation_equivalent_match_rate"
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    final_validation = validate_packed(model, groups, device=device, bf16=True, maximum_groups=None)
    final_metrics = _teacher_metrics(model, episodes, device)
    result = {
        **variant,
        "episode_groups": len(groups),
        "optimizer_steps_per_epoch": sum(len(group.chunks) for group in groups),
        "baseline_same_subset_nll": baseline_nll["mean_nll"],
        "baseline_teacher_metrics": baseline_metrics,
        "final_same_subset_nll": final_validation["mean_nll"],
        "final_teacher_metrics": final_metrics,
        "history": history,
    }
    del model, optimizer, scheduler, groups
    torch.cuda.empty_cache()
    return result


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run(code_commit: str) -> dict[str, Any]:
    from bc_capacity_sweep import _build_model, _pack, model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.models import MODEL_SCHEMA_VERSION, model_schema_sha256

    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise RuntimeError("code_commit must be a full lowercase Git SHA")
    if REPORT_PATH.is_file():
        existing = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if existing.get("code_commit") == code_commit:
            return {"status": "EXISTS", **existing}
        raise RuntimeError("learning-probe report already exists for different source")
    if not EXACT_CACHE.is_file() or not EXACT_MANIFEST.is_file():
        raise RuntimeError("exact-v2 cache or manifest is missing")
    manifest = json.loads(EXACT_MANIFEST.read_text(encoding="utf-8"))
    if MODEL_SCHEMA_VERSION != 3:
        raise RuntimeError(f"learning probe requires model schema v3, observed {MODEL_SCHEMA_VERSION}")
    if manifest.get("model_schema_sha256") != model_schema_sha256():
        raise RuntimeError("exact-v2 manifest model schema differs from current learner schema")

    with EXACT_CACHE.open("rb") as handle:
        all_episodes = pickle.load(handle)
    training = sorted(
        (episode for episode in all_episodes if episode.split == "train"),
        key=lambda episode: episode.episode_id,
    )
    episodes = training[:SUBSET_EPISODES]
    if len(episodes) != SUBSET_EPISODES:
        raise RuntimeError("exact-v2 cache does not contain enough training episodes")

    device = torch.device("cuda")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("3.7M learning probe requires CUDA BF16")
    torch.set_float32_matmul_precision("high")
    card_table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    config = model_configs()[MODEL_LABEL]
    initial_model = _build_model(config, card_table, seed=SEED, device=device)
    initial_state = {
        name: tensor.detach().clone()
        for name, tensor in initial_model.state_dict().items()
    }
    audit_groups = _pack(
        episodes,
        batch_size=8,
        sequence_length=SEQUENCE_LENGTH,
        seed=SEED,
        device=device,
    )
    gradient_audit = _gradient_audit(initial_model, audit_groups[0], device)
    del initial_model, audit_groups
    torch.cuda.empty_cache()

    variants = [
        _run_variant(
            variant=dict(variant),
            initial_state=initial_state,
            episodes=episodes,
            card_table=card_table,
            config=config,
            device=device,
        )
        for variant in VARIANTS
    ]
    best_semantic = max(
        variants,
        key=lambda row: row["final_teacher_metrics"]["representation_equivalent_match_rate"],
    )
    report = {
        "record_id": "bc-dragapult-3p7m-schema-v3-learning-probe-v1",
        "status": "PASS_BC_3P7M_LEARNING_PROBE",
        "code_commit": code_commit,
        "model_label": MODEL_LABEL,
        "trainable_parameters": 3_770_278,
        "scoring_contract": SCORING_CONTRACT,
        "exact_manifest_sha256": _sha256(EXACT_MANIFEST),
        "subset_episode_ids": [episode.episode_id for episode in episodes],
        "subset_episodes": len(episodes),
        "subset_policy_targets": sum(episode.policy_targets for episode in episodes),
        "epochs": EPOCHS,
        "sequence_length": SEQUENCE_LENGTH,
        "gradient_audit": gradient_audit,
        "variants": variants,
        "best_semantic_variant": best_semantic["label"],
        "best_semantic_match_rate": best_semantic["final_teacher_metrics"][
            "representation_equivalent_match_rate"
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report
