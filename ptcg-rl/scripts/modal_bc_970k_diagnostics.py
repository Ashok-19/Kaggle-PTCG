from __future__ import annotations

import hashlib
import json
import math
import pickle
import re
import statistics
import sys
from collections import Counter, defaultdict
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
EXACT_MANIFEST = Path("/data/materialized/bc-dragapult-hq-v2/manifest.json")
RUN_DIR = Path("/data/runs/bc-dragapult-970k-corrected-fresh-v1")
TRAINING_RECEIPT = RUN_DIR / "research-run-receipt.json"
CHECKPOINT = RUN_DIR / "970k/stage-d-exact-1150-best.pt"
OUTPUT_DIR = RUN_DIR / "diagnostics"
REPORT_PATH = OUTPUT_DIR / "teacher-forced-v1.json"
SCORING_CONTRACT = "corrected-primary-head-first-choice"

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

app = modal.App("kptcg-bc-970k-diagnostics", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bucket(index_zero_based: int) -> str:
    if index_zero_based < 4:
        return "001-004"
    if index_zero_based < 8:
        return "005-008"
    if index_zero_based < 16:
        return "009-016"
    if index_zero_based < 32:
        return "017-032"
    if index_zero_based < 64:
        return "033-064"
    if index_zero_based < 96:
        return "065-096"
    if index_zero_based < 128:
        return "097-128"
    return "129+"


def _option_bucket(count: int) -> str:
    if count <= 2:
        return "02"
    if count <= 5:
        return "03-05"
    if count <= 10:
        return "06-10"
    return "11+"


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


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
                raise RuntimeError("corrected decoder selected STOP before minimum count")
            stopped = True
            break
        if choice < 0 or choice >= len(available) or not bool(available[choice]):
            raise RuntimeError("corrected decoder selected an unavailable option")
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, options[choice])
        first = False
    return tuple(selected), stopped


def _teacher_nll(
    model: Any,
    output: Any,
    batch: Any,
    row: int,
    decision: Any,
) -> float:
    start = int(output.option_offsets[row])
    end = int(output.option_offsets[row + 1])
    options = output.option_embeddings[start:end]
    available = batch.option_available[start:end].clone()
    prefix = model.decoder_initial(output.hidden[row])
    teacher = tuple(decision.action.submitted_original_indices)
    teacher_stopped = bool(decision.action.stopped_early)
    minimum = int(decision.request.min_count)
    maximum = int(decision.request.max_count)
    total_log_probability = output.hidden[row].new_zeros(())

    for subchoice_index, choice in enumerate(teacher):
        if subchoice_index >= maximum:
            raise RuntimeError("teacher action selects beyond maximum count")
        can_stop = subchoice_index >= minimum
        if subchoice_index == 0:
            logits = model.decoder_first_logits(
                prefix,
                output.option_logits[start:end],
                available,
                can_stop,
            )
        else:
            logits = model.decoder_logits(prefix, options, available, can_stop)
        if choice < 0 or choice >= len(available) or not bool(available[choice]):
            raise RuntimeError("teacher action selects an unavailable option")
        total_log_probability = total_log_probability + torch.log_softmax(logits, dim=0)[choice]
        available[choice] = False
        prefix = model.decoder_advance(prefix, options[choice])

    if teacher_stopped:
        subchoice_index = len(teacher)
        if subchoice_index < minimum or subchoice_index >= maximum:
            raise RuntimeError("teacher STOP violates request bounds")
        if subchoice_index == 0:
            logits = model.decoder_first_logits(
                prefix,
                output.option_logits[start:end],
                available,
                True,
            )
        else:
            logits = model.decoder_logits(prefix, options, available, True)
        total_log_probability = total_log_probability + torch.log_softmax(logits, dim=0)[
            len(available)
        ]
    elif len(teacher) != maximum:
        raise RuntimeError("non-stopped teacher action does not reach maximum count")

    return float((-total_log_probability).detach().float().cpu())


def _group() -> dict[str, float]:
    return {
        "targets": 0.0,
        "nll": 0.0,
        "exact": 0.0,
        "equivalent": 0.0,
        "ambiguous": 0.0,
        "symmetry_floor": 0.0,
    }


def _update_group(
    group: dict[str, float],
    *,
    nll: float,
    exact: bool,
    equivalent: bool,
    ambiguous: bool,
    symmetry_floor: float,
) -> None:
    group["targets"] += 1
    group["nll"] += nll
    group["exact"] += int(exact)
    group["equivalent"] += int(equivalent)
    group["ambiguous"] += int(ambiguous)
    group["symmetry_floor"] += symmetry_floor


def _summarize(groups: dict[str, dict[str, float]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, values in sorted(groups.items()):
        targets = int(values["targets"])
        result[key] = {
            "policy_targets": targets,
            "mean_nll": values["nll"] / targets if targets else None,
            "exact_match_rate": values["exact"] / targets if targets else None,
            "representation_equivalent_match_rate": (
                values["equivalent"] / targets if targets else None
            ),
            "ambiguous_label_rate": values["ambiguous"] / targets if targets else None,
            "mean_irreducible_nll_floor_from_symmetry": (
                values["symmetry_floor"] / targets if targets else None
            ),
        }
    return result


def _first_deviation_summary(values: list[int | None]) -> dict[str, Any]:
    finite = [value for value in values if value is not None]
    histogram = Counter("none" if value is None else str(value) for value in values)
    return {
        "median": statistics.median(finite) if finite else None,
        "p25": _percentile(finite, 0.25),
        "p75": _percentile(finite, 0.75),
        "p90": _percentile(finite, 0.90),
        "zero_deviation_episodes": sum(value is None for value in values),
        "histogram": dict(sorted(histogram.items(), key=lambda item: (item[0] == "none", item[0]))),
    }


def _load_inputs(device: torch.device) -> tuple[list[Any], Any, dict[str, Any], str]:
    from bc_capacity_sweep import model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.network import PTCGPolicyV1
    from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state

    for path in (EXACT_CACHE, EXACT_MANIFEST, TRAINING_RECEIPT, CHECKPOINT):
        if not path.is_file():
            raise RuntimeError(f"required diagnostic input is missing: {path}")
    training_receipt = json.loads(TRAINING_RECEIPT.read_text(encoding="utf-8"))
    if training_receipt.get("scoring_contract") != SCORING_CONTRACT:
        raise RuntimeError("training receipt scoring contract differs from corrected contract")
    expected_sha256 = str(training_receipt["final_checkpoint_sha256"])
    if _sha256(CHECKPOINT) != expected_sha256:
        raise RuntimeError("970k checkpoint SHA differs from training receipt")

    with EXACT_CACHE.open("rb") as handle:
        episodes = pickle.load(handle)
    validation = [episode for episode in episodes if episode.split == "validation"]
    if len(validation) != 118:
        raise RuntimeError(f"expected 118 exact-v2 validation episodes, observed {len(validation)}")

    card_table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    model = PTCGPolicyV1(card_table, model_configs()["970k"]).to(device)
    load_training_checkpoint_model_state(
        CHECKPOINT,
        model=model,
        expected_sha256=expected_sha256,
    )
    model.eval()
    return validation, model, training_receipt, _sha256(EXACT_MANIFEST)


@app.function(
    gpu="RTX-PRO-6000",
    cpu=8,
    memory=65536,
    ephemeral_disk=524288,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run(diagnostic_code_commit: str) -> dict[str, Any]:
    from ptcg_rl.g1.semantic import SELECT_NAMES
    from ptcg_rl.g2.network import collate_projected

    if re.fullmatch(r"[0-9a-f]{40}", diagnostic_code_commit) is None:
        raise RuntimeError("diagnostic_code_commit must be a full lowercase Git SHA")
    device = torch.device("cuda")
    episodes, model, training_receipt, manifest_sha256 = _load_inputs(device)
    checkpoint_sha256 = str(training_receipt["final_checkpoint_sha256"])

    if REPORT_PATH.is_file():
        existing = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if (
            existing.get("diagnostic_code_commit") == diagnostic_code_commit
            and existing.get("checkpoint_sha256") == checkpoint_sha256
        ):
            return {"status": "EXISTS", **existing}
        raise RuntimeError("diagnostic report already exists for different code/checkpoint")

    states = model.initial_hidden(len(episodes), device)
    exact = 0
    equivalent = 0
    targets = 0
    total_nll = 0.0
    ambiguous_targets = 0
    symmetry_floor_total = 0.0
    maximum_multiplicity = 1
    main_total = 0
    main_exact = 0
    six_plus_total = 0
    six_plus_exact = 0
    first_exact_recurrent: list[int | None] = [None] * len(episodes)
    first_exact_policy: list[int | None] = [None] * len(episodes)
    first_semantic_policy: list[int | None] = [None] * len(episodes)
    policy_ordinals = [0] * len(episodes)
    by_recurrent_horizon: dict[str, dict[str, float]] = defaultdict(_group)
    by_policy_horizon: dict[str, dict[str, float]] = defaultdict(_group)
    by_option_count: dict[str, dict[str, float]] = defaultdict(_group)
    by_selection_type: dict[str, dict[str, float]] = defaultdict(_group)
    by_context: dict[str, dict[str, float]] = defaultdict(_group)

    maximum_length = max(len(episode.decisions) for episode in episodes)
    with torch.inference_mode():
        for time_index in range(maximum_length):
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
                policy_ordinals[episode_index] += 1
                policy_index_zero_based = policy_ordinals[episode_index] - 1
                start = int(output.option_offsets[local_index])
                end = int(output.option_offsets[local_index + 1])
                embeddings = output.option_embeddings[start:end]
                available = batch.option_available[start:end]
                teacher = tuple(decision.action.submitted_original_indices)
                teacher_stopped = bool(decision.action.stopped_early)
                greedy, greedy_stopped = _greedy_action(
                    model,
                    output,
                    batch,
                    local_index,
                    minimum=int(decision.request.min_count),
                    maximum=int(decision.request.max_count),
                )
                nll = _teacher_nll(model, output, batch, local_index, decision)
                exact_match = teacher == greedy and teacher_stopped == greedy_stopped
                equivalent_match = _representation_equivalent(
                    embeddings,
                    teacher,
                    teacher_stopped,
                    greedy,
                    greedy_stopped,
                )
                floor, ambiguous, multiplicity = _symmetry_floor(embeddings, available, teacher)
                maximum_multiplicity = max(maximum_multiplicity, multiplicity)

                targets += 1
                total_nll += nll
                exact += int(exact_match)
                equivalent += int(equivalent_match)
                ambiguous_targets += int(ambiguous)
                symmetry_floor_total += floor
                if not exact_match and first_exact_recurrent[episode_index] is None:
                    first_exact_recurrent[episode_index] = time_index + 1
                    first_exact_policy[episode_index] = policy_ordinals[episode_index]
                if not equivalent_match and first_semantic_policy[episode_index] is None:
                    first_semantic_policy[episode_index] = policy_ordinals[episode_index]

                option_count = int(embeddings.shape[0])
                selection_code = int(decision.projected.model.global_categorical_values[2])
                context_code = int(decision.projected.model.global_categorical_values[3])
                selection_key = f"{selection_code}:{SELECT_NAMES.get(selection_code, 'UNKNOWN')}"
                context_key = f"{selection_key}/context={context_code}"
                if selection_code == 0:
                    main_total += 1
                    main_exact += int(exact_match)
                if option_count >= 6:
                    six_plus_total += 1
                    six_plus_exact += int(exact_match)

                group_keys = (
                    (by_recurrent_horizon, _bucket(time_index)),
                    (by_policy_horizon, _bucket(policy_index_zero_based)),
                    (by_option_count, _option_bucket(option_count)),
                    (by_selection_type, selection_key),
                    (by_context, context_key),
                )
                for groups, key in group_keys:
                    _update_group(
                        groups[key],
                        nll=nll,
                        exact=exact_match,
                        equivalent=equivalent_match,
                        ambiguous=ambiguous,
                        symmetry_floor=floor,
                    )

    context_summary = _summarize(by_context)
    worst_contexts = sorted(
        (
            (key, value)
            for key, value in context_summary.items()
            if value["policy_targets"] >= 50
        ),
        key=lambda item: (item[1]["exact_match_rate"], -item[1]["policy_targets"]),
    )[:20]

    report = {
        "record_id": "bc-dragapult-970k-corrected-fresh-teacher-diagnostics-v1",
        "status": "PASS_BC_970K_CORRECTED_DIAGNOSTICS",
        "diagnostic_code_commit": diagnostic_code_commit,
        "training_code_commit": training_receipt["code_commit"],
        "scoring_contract": SCORING_CONTRACT,
        "checkpoint_path": str(CHECKPOINT),
        "checkpoint_sha256": checkpoint_sha256,
        "exact_manifest_sha256": manifest_sha256,
        "validation_episodes": len(episodes),
        "policy_targets": targets,
        "validation_mean_nll": total_nll / targets,
        "training_final_stage_validation_mean_nll": training_receipt["final_validation_mean_nll"],
        "exact_match_rate": exact / targets,
        "representation_equivalent_match_rate": equivalent / targets,
        "exact_mismatches_recovered_as_representation_equivalent": equivalent - exact,
        "ambiguous_label_rate": ambiguous_targets / targets,
        "mean_irreducible_nll_floor_from_symmetry": symmetry_floor_total / targets,
        "maximum_equivalent_option_multiplicity": maximum_multiplicity,
        "main_targets": main_total,
        "main_exact_match_rate": main_exact / main_total,
        "six_plus_option_targets": six_plus_total,
        "six_plus_option_exact_match_rate": six_plus_exact / six_plus_total,
        "first_exact_deviation_recurrent_index": _first_deviation_summary(first_exact_recurrent),
        "first_exact_deviation_policy_index": _first_deviation_summary(first_exact_policy),
        "first_representation_deviation_policy_index": _first_deviation_summary(first_semantic_policy),
        "by_recurrent_horizon": _summarize(by_recurrent_horizon),
        "by_policy_horizon": _summarize(by_policy_horizon),
        "by_option_count": _summarize(by_option_count),
        "by_selection_type": _summarize(by_selection_type),
        "worst_selection_contexts_min_50_targets": [
            {"context": key, **value} for key, value in worst_contexts
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report
