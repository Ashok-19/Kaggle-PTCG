from __future__ import annotations

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
MODEL_LABEL = "3.7m"
EXPECTED_CHECKPOINT_SHA256 = "7a29718bfd16d6c8ce50ba190c445624f221eec93ed59f37cf75d1f78ae56833"
EXPECTED_ARCHITECTURE_SHA256 = "80f5424a0d5bf67335f4a5d06fbbce1788193b8922bfbf23c97714ca6997c04d"
EXPECTED_MODEL_SCHEMA_SHA256 = "30066c174128f91a6b78eef3886021c97c6f0b57bd9c001afaef548f3d2081a4"
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2-featurefix-v3.pkl")
EXACT_CACHE_META = Path(str(EXACT_CACHE) + ".meta.json")
EXACT_MANIFEST = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3/manifest.json")
CHECKPOINT = Path(
    "/data/runs/bc-dragapult-final-v5-schema-v3-fused-update-density/3.7m/3.7m/"
    "stage-d-exact-1150-best.pt"
)
REPORT_PATH = Path("/data/reports/bc-v5-final-heldout-validation.json")
CHUNK_EPISODES = 32

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

app = modal.App("kptcg-bc-v5-final-heldout-validation", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)


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
                raise RuntimeError("validator decoder selected STOP before minimum count")
            stopped = True
            break
        if choice < 0 or choice >= len(available) or not bool(available[choice]):
            raise RuntimeError("validator decoder selected illegal option")
        selected.append(choice)
        available[choice] = False
        prefix = model.decoder_advance(prefix, options[choice])
        first = False
    return tuple(selected), stopped


def _validate_chunk(model: Any, episodes: list[Any], device: torch.device) -> dict[str, Any]:
    from ptcg_rl.g2.network import collate_projected

    states = model.initial_hidden(len(episodes), device)
    exact = 0
    equivalent = 0
    total = 0
    main_exact = 0
    main_total = 0
    by_selection_type: dict[str, dict[str, int]] = {}
    by_option_count: dict[str, dict[str, int]] = {}
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
                selection_key = str(int(decision.projected.model.global_categorical_values[2]))
                option_count = len(decision.projected.model.option_available_mask)
                if option_count <= 2:
                    option_bucket = "2_or_less"
                elif option_count <= 5:
                    option_bucket = "3_to_5"
                elif option_count <= 9:
                    option_bucket = "6_to_9"
                else:
                    option_bucket = "10_plus"
                for stats, key in (
                    (by_selection_type, selection_key),
                    (by_option_count, option_bucket),
                ):
                    row_stats = stats.setdefault(
                        key,
                        {"targets": 0, "exact": 0, "equivalent": 0},
                    )
                    row_stats["targets"] += 1
                    row_stats["exact"] += int(exact_match)
                    row_stats["equivalent"] += int(equivalent_match)
                total += 1
                exact += int(exact_match)
                equivalent += int(equivalent_match)
                if int(decision.projected.model.global_categorical_values[2]) == 0:
                    main_total += 1
                    main_exact += int(exact_match)
                if not exact_match and first_deviation[episode_index] is None:
                    first_deviation[episode_index] = time_index + 1
    return {
        "policy_targets": total,
        "exact_matches": exact,
        "representation_equivalent_matches": equivalent,
        "main_targets": main_total,
        "main_exact_matches": main_exact,
        "by_selection_type": by_selection_type,
        "by_option_count": by_option_count,
        "first_deviation": first_deviation,
    }


@app.function(
    gpu="T4",
    cpu=8,
    memory=32768,
    timeout=30 * 60,
    volumes={"/data": training_volume},
)
def validate() -> dict[str, Any]:
    from bc_capacity_sweep import model_configs
    from ptcg_rl.g2.card_table import load_card_table
    from ptcg_rl.g2.models import MODEL_SCHEMA_VERSION, model_schema_sha256
    from ptcg_rl.g2.network import PTCGPolicyV1
    from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state

    if MODEL_SCHEMA_VERSION != 3 or model_schema_sha256() != EXPECTED_MODEL_SCHEMA_SHA256:
        raise RuntimeError("model schema v3 preflight failed")
    for path in (EXACT_CACHE, EXACT_CACHE_META, EXACT_MANIFEST, CHECKPOINT, CHECKPOINT.with_name(CHECKPOINT.name + ".manifest.json")):
        if not path.is_file():
            raise RuntimeError(f"required validation artifact missing: {path}")

    manifest = json.loads(EXACT_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("model_schema_sha256") != EXPECTED_MODEL_SCHEMA_SHA256:
        raise RuntimeError("exact manifest model schema differs")
    records = list(manifest["records"])
    validation_ids = {int(record["episode_id"]) for record in records if record["split"] == "validation"}
    expected_targets = sum(int(record["policy_targets"]) for record in records if record["split"] == "validation")
    if len(validation_ids) != 118 or expected_targets != 13046:
        raise RuntimeError("held-out validation split contract differs")

    meta = json.loads(EXACT_CACHE_META.read_text(encoding="utf-8"))
    if meta.get("source_manifest_sha256") != manifest["manifest_sha256"]:
        raise RuntimeError("object cache provenance differs from exact manifest")
    with EXACT_CACHE.open("rb") as handle:
        all_episodes = pickle.load(handle)
    episodes = [episode for episode in all_episodes if int(episode.episode_id) in validation_ids]
    episodes.sort(key=lambda episode: int(episode.episode_id))
    if len(episodes) != 118 or {int(episode.episode_id) for episode in episodes} != validation_ids:
        raise RuntimeError("object cache does not contain exact validation episode set")

    device = torch.device("cuda")
    card_table = load_card_table(PTCG_RL / "private/g2/card-table-v1.json")
    model = PTCGPolicyV1(card_table, model_configs()[MODEL_LABEL]).to(device)
    if model.architecture_sha256 != EXPECTED_ARCHITECTURE_SHA256:
        raise RuntimeError("final model architecture hash differs")
    restored = load_training_checkpoint_model_state(
        CHECKPOINT,
        model=model,
        expected_sha256=EXPECTED_CHECKPOINT_SHA256,
    )
    model.eval()

    totals = {
        "policy_targets": 0,
        "exact_matches": 0,
        "representation_equivalent_matches": 0,
        "main_targets": 0,
        "main_exact_matches": 0,
    }
    by_selection_type: dict[str, dict[str, int]] = {}
    by_option_count: dict[str, dict[str, int]] = {}

    def merge_breakdown(
        destination: dict[str, dict[str, int]], source: dict[str, dict[str, int]]
    ) -> None:
        for key, values in source.items():
            target = destination.setdefault(
                key,
                {"targets": 0, "exact": 0, "equivalent": 0},
            )
            for metric in ("targets", "exact", "equivalent"):
                target[metric] += int(values[metric])
    deviations: list[int | None] = []
    for start in range(0, len(episodes), CHUNK_EPISODES):
        chunk = episodes[start : start + CHUNK_EPISODES]
        result = _validate_chunk(model, chunk, device)
        for key in totals:
            totals[key] += int(result[key])
        merge_breakdown(by_selection_type, result["by_selection_type"])
        merge_breakdown(by_option_count, result["by_option_count"])
        deviations.extend(result["first_deviation"])
        print(
            json.dumps(
                {
                    "event": "heldout_chunk_complete",
                    "episodes_complete": min(start + CHUNK_EPISODES, len(episodes)),
                    "episodes_total": len(episodes),
                    "policy_targets_complete": totals["policy_targets"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

    if totals["policy_targets"] != expected_targets:
        raise RuntimeError("evaluated policy target count differs from held-out manifest")
    finite_deviations = [value for value in deviations if value is not None]
    report = {
        "schema_version": 1,
        "record_id": "bc-v5-final-heldout-validation-v1",
        "status": "PASS",
        "checkpoint": {
            "path": str(CHECKPOINT),
            "sha256": restored.payload_sha256,
            "architecture_sha256": model.architecture_sha256,
            "trainable_parameters": model.trainable_parameter_count,
        },
        "corpus": {
            "manifest_sha256": manifest["manifest_sha256"],
            "model_schema_sha256": manifest["model_schema_sha256"],
            "validation_episodes": len(episodes),
            "validation_policy_targets": expected_targets,
        },
        "metrics": {
            **totals,
            "exact_match_rate": totals["exact_matches"] / totals["policy_targets"],
            "representation_equivalent_match_rate": (
                totals["representation_equivalent_matches"] / totals["policy_targets"]
            ),
            "main_exact_match_rate": totals["main_exact_matches"] / totals["main_targets"],
            "by_selection_type": {
                key: {
                    **values,
                    "exact_match_rate": values["exact"] / values["targets"],
                    "representation_equivalent_match_rate": (
                        values["equivalent"] / values["targets"]
                    ),
                }
                for key, values in sorted(by_selection_type.items(), key=lambda item: int(item[0]))
            },
            "selection_type_names": {
                "0": "MAIN",
                "1": "CARD",
                "2": "ATTACHED_CARD",
                "3": "CARD_OR_ATTACHED_CARD",
                "4": "ENERGY",
                "5": "SKILL",
                "6": "ATTACK",
                "7": "EVOLVE",
                "8": "COUNT",
                "9": "YES_NO",
                "10": "SPECIAL_CONDITION",
            },
            "by_option_count": {
                key: {
                    **values,
                    "exact_match_rate": values["exact"] / values["targets"],
                    "representation_equivalent_match_rate": (
                        values["equivalent"] / values["targets"]
                    ),
                }
                for key, values in sorted(by_option_count.items())
            },
            "first_deviation_median": (
                statistics.median(finite_deviations) if finite_deviations else None
            ),
            "zero_deviation_episodes": sum(value is None for value in deviations),
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial = REPORT_PATH.with_suffix(REPORT_PATH.suffix + ".partial")
    partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(REPORT_PATH)
    training_volume.commit()
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(validate.remote(), sort_keys=True))
