from __future__ import annotations

import json
import pickle
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import modal
import torch

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
VOLUME_NAME = "kptcg-training"
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2.pkl")
INCUMBENT_CHECKPOINT = Path(
    "/data/runs/bc-dragapult-final-v1/3.7m/3.7m/stage-d-exact-1150-best.pt"
)
CHALLENGER_CHECKPOINT = Path(
    "/data/runs/bc-dragapult-final-v1-stage-d-continuation-v1/3.7m/stage-d-exact-1150-best.pt"
)
INCUMBENT_SHA256 = "dec8a1a212bf8183f603042dc858eae3223d2fb0b27cb512fb60294bf098b145"
CHALLENGER_SHA256 = "7cb163dbe2e2b1fd63d59cc52b1eee896fd4e23954b3c6f8893da15c9440b4f4"

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

app = modal.App("kptcg-bc-root-cause-diagnostics", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _bucket(index: int) -> str:
    if index < 32:
        return "001-032"
    if index < 64:
        return "033-064"
    if index < 96:
        return "065-096"
    if index < 128:
        return "097-128"
    return "129+"


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


def _load_validation_episodes() -> list[Any]:
    if not EXACT_CACHE.is_file():
        raise RuntimeError(f"exact object cache is missing: {EXACT_CACHE}")
    with EXACT_CACHE.open("rb") as handle:
        episodes = pickle.load(handle)
    validation = [episode for episode in episodes if episode.split == "validation"]
    if not validation:
        raise RuntimeError("exact object cache contains no validation episodes")
    return validation


def _load_model(checkpoint: Path, expected_sha256: str, device: torch.device) -> Any:
    sys.path.insert(0, "/workspace/ptcg-rl/src")
    sys.path.insert(0, "/workspace/ptcg-rl/scripts")
    from bc_capacity_sweep import model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.network import PTCGPolicyV1
    from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state

    card_table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    model = PTCGPolicyV1(card_table, model_configs()["3.7m"]).to(device)
    restored = load_training_checkpoint_model_state(
        checkpoint,
        model=model,
        expected_sha256=expected_sha256,
    )
    model.eval()
    return model, restored


def _greedy_action(
    model: Any,
    hidden: torch.Tensor,
    option_embeddings: torch.Tensor,
    available: torch.Tensor,
    minimum_count: int,
    maximum_count: int,
) -> tuple[tuple[int, ...], bool]:
    if maximum_count == 0:
        return (), False
    prefix = model.decoder_initial(hidden)
    selected: list[int] = []
    stopped = False
    available = available.clone()
    while len(selected) < maximum_count:
        can_stop = len(selected) >= minimum_count
        logits = model.decoder_logits(prefix, option_embeddings, available, can_stop)
        choice = int(torch.argmax(logits).item())
        if choice == option_embeddings.shape[0]:
            if not can_stop:
                raise RuntimeError("decoder selected STOP before minimum count")
            stopped = True
            break
        if choice < 0 or choice >= option_embeddings.shape[0] or not bool(available[choice]):
            raise RuntimeError("decoder selected an unavailable option")
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, option_embeddings[choice])
    return tuple(selected), stopped


def _diagnose(
    *,
    model: Any,
    episodes: list[Any],
    mode: str,
    reset_interval: int | None,
    device: torch.device,
) -> dict[str, Any]:
    sys.path.insert(0, "/workspace/ptcg-rl/src")
    from ptcg_rl.bc.training import replay_compound_action
    from ptcg_rl.g1.models import CompoundActionV1
    from ptcg_rl.g2.network import collate_projected

    hidden_states = model.initial_hidden(len(episodes), device)
    total_nll = 0.0
    policy_targets = 0
    exact_matches = 0
    first_deviation: list[int | None] = [None] * len(episodes)
    policy_decisions_per_episode = [0] * len(episodes)
    bucket_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"nll": 0.0, "targets": 0.0, "matches": 0.0}
    )
    option_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"nll": 0.0, "targets": 0.0, "matches": 0.0}
    )

    maximum_length = max(len(episode.decisions) for episode in episodes)
    with torch.inference_mode():
        for time_index in range(maximum_length):
            active = [index for index, episode in enumerate(episodes) if time_index < len(episode.decisions)]
            if not active:
                continue
            decisions = [episodes[index].decisions[time_index] for index in active]
            if mode == "stateless":
                hidden_batch = model.initial_hidden(len(active), device)
            else:
                hidden_batch = hidden_states[active]
                if reset_interval is not None and time_index > 0 and time_index % reset_interval == 0:
                    hidden_batch = model.initial_hidden(len(active), device)
            batch = collate_projected(tuple(decision.projected for decision in decisions), device=device)
            output = model(batch, hidden_batch)
            if mode != "stateless":
                hidden_states[active] = output.hidden

            for local_index, episode_index in enumerate(active):
                decision = decisions[local_index]
                if decision.request.has_only_one_outcome:
                    continue
                policy_decisions_per_episode[episode_index] += 1
                start = int(output.option_offsets[local_index])
                end = int(output.option_offsets[local_index + 1])
                available = batch.option_available[start:end]
                option_embeddings = output.option_embeddings[start:end]
                replay = replay_compound_action(
                    initial_prefix=model.decoder_initial(output.hidden[local_index]),
                    option_embeddings=option_embeddings,
                    available_mask=available,
                    action=CompoundActionV1(
                        selected_indices=tuple(decision.action.submitted_original_indices),
                        stopped=bool(decision.action.stopped_early),
                    ),
                    minimum_count=int(decision.request.min_count),
                    maximum_count=int(decision.request.max_count),
                    decoder_logits=model.decoder_logits,
                    decoder_advance=model.decoder_advance,
                )
                nll = float((-replay.log_probability).detach().float().cpu())
                greedy_selected, greedy_stopped = _greedy_action(
                    model,
                    output.hidden[local_index],
                    option_embeddings,
                    available,
                    int(decision.request.min_count),
                    int(decision.request.max_count),
                )
                matched = (
                    greedy_selected == tuple(decision.action.submitted_original_indices)
                    and greedy_stopped == bool(decision.action.stopped_early)
                )
                total_nll += nll
                policy_targets += 1
                exact_matches += int(matched)
                if not matched and first_deviation[episode_index] is None:
                    first_deviation[episode_index] = time_index + 1

                horizon = _bucket(time_index)
                bucket_stats[horizon]["nll"] += nll
                bucket_stats[horizon]["targets"] += 1
                bucket_stats[horizon]["matches"] += int(matched)
                option_count = len(decision.projected.model.option_available_mask)
                option_key = (
                    "02" if option_count <= 2 else "03-05" if option_count <= 5 else "06-10" if option_count <= 10 else "11+"
                )
                option_stats[option_key]["nll"] += nll
                option_stats[option_key]["targets"] += 1
                option_stats[option_key]["matches"] += int(matched)

    def summarize_groups(groups: dict[str, dict[str, float]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in sorted(groups):
            targets = int(groups[key]["targets"])
            result[key] = {
                "policy_targets": targets,
                "mean_nll": groups[key]["nll"] / targets if targets else None,
                "greedy_exact_action_match_rate": groups[key]["matches"] / targets if targets else None,
            }
        return result

    finite_first = [value for value in first_deviation if value is not None]
    zero_deviation = sum(value is None for value in first_deviation)
    return {
        "mode": mode,
        "reset_interval": reset_interval,
        "episodes": len(episodes),
        "policy_targets": policy_targets,
        "mean_nll": total_nll / policy_targets,
        "greedy_exact_action_matches": exact_matches,
        "greedy_exact_action_match_rate": exact_matches / policy_targets,
        "episodes_with_zero_greedy_deviations": zero_deviation,
        "zero_deviation_episode_rate": zero_deviation / len(episodes),
        "first_greedy_deviation_recurrent_index": {
            "median": statistics.median(finite_first) if finite_first else None,
            "p25": _percentile(finite_first, 0.25),
            "p75": _percentile(finite_first, 0.75),
            "p90": _percentile(finite_first, 0.90),
        },
        "policy_decisions_per_episode": {
            "mean": sum(policy_decisions_per_episode) / len(policy_decisions_per_episode),
            "median": statistics.median(policy_decisions_per_episode),
        },
        "by_recurrent_horizon": summarize_groups(bucket_stats),
        "by_option_count": summarize_groups(option_stats),
    }


@app.function(
    gpu="RTX-PRO-6000",
    cpu=8,
    memory=65536,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run() -> dict[str, Any]:
    device = torch.device("cuda")
    episodes = _load_validation_episodes()
    incumbent, incumbent_receipt = _load_model(INCUMBENT_CHECKPOINT, INCUMBENT_SHA256, device)
    incumbent_full = _diagnose(
        model=incumbent,
        episodes=episodes,
        mode="full_memory",
        reset_interval=None,
        device=device,
    )
    incumbent_reset32 = _diagnose(
        model=incumbent,
        episodes=episodes,
        mode="reset_32",
        reset_interval=32,
        device=device,
    )
    incumbent_stateless = _diagnose(
        model=incumbent,
        episodes=episodes,
        mode="stateless",
        reset_interval=None,
        device=device,
    )
    del incumbent
    torch.cuda.empty_cache()

    challenger, challenger_receipt = _load_model(CHALLENGER_CHECKPOINT, CHALLENGER_SHA256, device)
    challenger_full = _diagnose(
        model=challenger,
        episodes=episodes,
        mode="full_memory",
        reset_interval=None,
        device=device,
    )

    report = {
        "record_id": "bc-dragapult-root-cause-diagnostics-v1",
        "schema_version": 1,
        "validation_episodes": len(episodes),
        "incumbent": {
            "checkpoint_sha256": incumbent_receipt.payload_sha256,
            "full_memory": incumbent_full,
            "reset_32": incumbent_reset32,
            "stateless": incumbent_stateless,
        },
        "challenger": {
            "checkpoint_sha256": challenger_receipt.payload_sha256,
            "full_memory": challenger_full,
        },
        "derived": {
            "memory_nll_gain_vs_stateless": incumbent_stateless["mean_nll"] - incumbent_full["mean_nll"],
            "memory_exact_match_gain_vs_stateless": incumbent_full["greedy_exact_action_match_rate"]
            - incumbent_stateless["greedy_exact_action_match_rate"],
            "long_memory_nll_gain_vs_reset32": incumbent_reset32["mean_nll"] - incumbent_full["mean_nll"],
            "long_memory_exact_match_gain_vs_reset32": incumbent_full["greedy_exact_action_match_rate"]
            - incumbent_reset32["greedy_exact_action_match_rate"],
            "challenger_nll_gain": incumbent_full["mean_nll"] - challenger_full["mean_nll"],
            "challenger_exact_match_gain": challenger_full["greedy_exact_action_match_rate"]
            - incumbent_full["greedy_exact_action_match_rate"],
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(run.remote(), indent=2, sort_keys=True))
