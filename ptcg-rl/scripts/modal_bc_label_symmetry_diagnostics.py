from __future__ import annotations

import json
import math
import pickle
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
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2.pkl")
CHECKPOINT = Path("/data/runs/bc-dragapult-final-v1/3.7m/3.7m/stage-d-exact-1150-best.pt")
CHECKPOINT_SHA256 = "dec8a1a212bf8183f603042dc858eae3223d2fb0b27cb512fb60294bf098b145"

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

app = modal.App("kptcg-bc-label-symmetry-diagnostics", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _load() -> tuple[list[Any], Any, torch.device]:
    from bc_capacity_sweep import model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.network import PTCGPolicyV1
    from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state

    with EXACT_CACHE.open("rb") as handle:
        episodes = pickle.load(handle)
    validation = [episode for episode in episodes if episode.split == "validation"]
    device = torch.device("cuda")
    table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    model = PTCGPolicyV1(table, model_configs()["3.7m"]).to(device)
    load_training_checkpoint_model_state(CHECKPOINT, model=model, expected_sha256=CHECKPOINT_SHA256)
    model.eval()
    return validation, model, device


def _greedy(
    model: Any,
    hidden: torch.Tensor,
    option_embeddings: torch.Tensor,
    available: torch.Tensor,
    minimum: int,
    maximum: int,
) -> tuple[tuple[int, ...], bool]:
    prefix = model.decoder_initial(hidden)
    selected: list[int] = []
    stopped = False
    available = available.clone()
    while len(selected) < maximum:
        can_stop = len(selected) >= minimum
        logits = model.decoder_logits(prefix, option_embeddings, available, can_stop)
        choice = int(torch.argmax(logits).item())
        if choice == option_embeddings.shape[0]:
            stopped = True
            break
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, option_embeddings[choice])
    return tuple(selected), stopped


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
        _same_embedding(option_embeddings[t], option_embeddings[g])
        for t, g in zip(teacher, greedy, strict=True)
    )


def _symmetry_floor(
    option_embeddings: torch.Tensor,
    available: torch.Tensor,
    selected: tuple[int, ...],
) -> tuple[float, bool, int]:
    available = available.clone()
    floor = 0.0
    ambiguous = False
    maximum_multiplicity = 1
    for choice in selected:
        equivalents = [
            index
            for index in range(option_embeddings.shape[0])
            if bool(available[index])
            and _same_embedding(option_embeddings[choice], option_embeddings[index])
        ]
        multiplicity = max(1, len(equivalents))
        maximum_multiplicity = max(maximum_multiplicity, multiplicity)
        if multiplicity > 1:
            ambiguous = True
            floor += math.log(multiplicity)
        available[choice] = False
    return floor, ambiguous, maximum_multiplicity


def _group() -> dict[str, float]:
    return {
        "targets": 0.0,
        "exact": 0.0,
        "equivalent": 0.0,
        "ambiguous": 0.0,
        "symmetry_floor": 0.0,
    }


def _summarize(groups: dict[str, dict[str, float]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, values in sorted(groups.items()):
        targets = int(values["targets"])
        result[key] = {
            "policy_targets": targets,
            "exact_match_rate": values["exact"] / targets if targets else None,
            "representation_equivalent_match_rate": values["equivalent"] / targets if targets else None,
            "ambiguous_label_rate": values["ambiguous"] / targets if targets else None,
            "mean_irreducible_nll_floor_from_symmetry": values["symmetry_floor"] / targets if targets else None,
        }
    return result


@app.function(
    gpu="RTX-PRO-6000",
    cpu=8,
    memory=65536,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run() -> dict[str, Any]:
    from ptcg_rl.g1.semantic import SELECT_NAMES
    from ptcg_rl.g2.network import collate_projected

    episodes, model, device = _load()
    states = model.initial_hidden(len(episodes), device)
    exact = 0
    equivalent = 0
    targets = 0
    ambiguous_targets = 0
    symmetry_floor_total = 0.0
    maximum_multiplicity = 1
    first_exact: list[int | None] = [None] * len(episodes)
    first_semantic: list[int | None] = [None] * len(episodes)
    by_option_count: dict[str, dict[str, float]] = defaultdict(_group)
    by_select_type: dict[str, dict[str, float]] = defaultdict(_group)
    by_context: dict[str, dict[str, float]] = defaultdict(_group)

    with torch.inference_mode():
        for time_index in range(max(len(episode.decisions) for episode in episodes)):
            active = [index for index, episode in enumerate(episodes) if time_index < len(episode.decisions)]
            if not active:
                continue
            decisions = [episodes[index].decisions[time_index] for index in active]
            batch = collate_projected(tuple(decision.projected for decision in decisions), device=device)
            output = model(batch, states[active])
            states[active] = output.hidden

            for local_index, episode_index in enumerate(active):
                decision = decisions[local_index]
                if decision.request.has_only_one_outcome:
                    continue
                start = int(output.option_offsets[local_index])
                end = int(output.option_offsets[local_index + 1])
                embeddings = output.option_embeddings[start:end]
                available = batch.option_available[start:end]
                teacher = tuple(decision.action.submitted_original_indices)
                teacher_stopped = bool(decision.action.stopped_early)
                greedy, greedy_stopped = _greedy(
                    model,
                    output.hidden[local_index],
                    embeddings,
                    available,
                    int(decision.request.min_count),
                    int(decision.request.max_count),
                )
                exact_match = teacher == greedy and teacher_stopped == greedy_stopped
                equivalent_match = _representation_equivalent(
                    embeddings, teacher, teacher_stopped, greedy, greedy_stopped
                )
                floor, ambiguous, multiplicity = _symmetry_floor(embeddings, available, teacher)
                maximum_multiplicity = max(maximum_multiplicity, multiplicity)
                targets += 1
                exact += int(exact_match)
                equivalent += int(equivalent_match)
                ambiguous_targets += int(ambiguous)
                symmetry_floor_total += floor
                if not exact_match and first_exact[episode_index] is None:
                    first_exact[episode_index] = time_index + 1
                if not equivalent_match and first_semantic[episode_index] is None:
                    first_semantic[episode_index] = time_index + 1

                option_count = embeddings.shape[0]
                option_key = "02" if option_count <= 2 else "03-05" if option_count <= 5 else "06-10" if option_count <= 10 else "11+"
                select_code = int(decision.projected.model.global_categorical_values[2])
                context_code = int(decision.projected.model.global_categorical_values[3])
                select_key = f"{select_code}:{SELECT_NAMES.get(select_code, 'UNKNOWN')}"
                context_key = f"{select_key}/context={context_code}"
                for group in (by_option_count[option_key], by_select_type[select_key], by_context[context_key]):
                    group["targets"] += 1
                    group["exact"] += int(exact_match)
                    group["equivalent"] += int(equivalent_match)
                    group["ambiguous"] += int(ambiguous)
                    group["symmetry_floor"] += floor

    finite_exact = [value for value in first_exact if value is not None]
    finite_semantic = [value for value in first_semantic if value is not None]
    context_summary = _summarize(by_context)
    worst_contexts = sorted(
        (
            (key, value)
            for key, value in context_summary.items()
            if value["policy_targets"] >= 50
        ),
        key=lambda item: (item[1]["representation_equivalent_match_rate"], -item[1]["policy_targets"]),
    )[:20]

    report = {
        "record_id": "bc-dragapult-label-symmetry-diagnostics-v1",
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "validation_episodes": len(episodes),
        "policy_targets": targets,
        "exact_match_rate": exact / targets,
        "representation_equivalent_match_rate": equivalent / targets,
        "exact_mismatches_recovered_as_representation_equivalent": equivalent - exact,
        "ambiguous_label_rate": ambiguous_targets / targets,
        "mean_irreducible_nll_floor_from_symmetry": symmetry_floor_total / targets,
        "maximum_equivalent_option_multiplicity": maximum_multiplicity,
        "episodes_with_zero_exact_deviations": sum(value is None for value in first_exact),
        "episodes_with_zero_representation_deviations": sum(value is None for value in first_semantic),
        "first_exact_deviation_median": statistics.median(finite_exact) if finite_exact else None,
        "first_representation_deviation_median": statistics.median(finite_semantic) if finite_semantic else None,
        "by_option_count": _summarize(by_option_count),
        "by_selection_type": _summarize(by_select_type),
        "worst_selection_contexts_min_50_targets": [
            {"context": key, **value} for key, value in worst_contexts
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(run.remote(), indent=2, sort_keys=True))
