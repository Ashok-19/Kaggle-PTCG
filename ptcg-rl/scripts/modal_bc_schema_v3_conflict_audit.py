from __future__ import annotations

import hashlib
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import modal

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
VOLUME_NAME = "kptcg-training"
EXACT_CACHE = Path(
    "/data/cache/materialized-episode-objects-v1/"
    "bc-dragapult-hq-v2-featurefix-v3.pkl"
)
EXACT_MANIFEST = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3/manifest.json")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
)
app = modal.App("kptcg-bc-schema-v3-conflict-audit", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _model_digest(model: Any) -> bytes:
    return hashlib.sha256(pickle.dumps(model, protocol=5)).digest()


def _label(decision: Any) -> tuple[tuple[int, ...], bool]:
    transport = decision.projected.transport.original_indices
    original_to_model = {int(original): index for index, original in enumerate(transport)}
    selected = tuple(
        original_to_model[int(original)] for original in decision.action.submitted_original_indices
    )
    return selected, bool(decision.action.stopped_early)


def _summarize(groups: dict[bytes, Counter[Any]], total_targets: int) -> dict[str, Any]:
    repeated_groups = 0
    repeated_targets = 0
    conflicting_groups = 0
    conflicting_targets = 0
    excess_conflicting_targets = 0
    max_multiplicity = 0
    examples: list[dict[str, Any]] = []
    for key, labels in groups.items():
        count = sum(labels.values())
        max_multiplicity = max(max_multiplicity, count)
        if count > 1:
            repeated_groups += 1
            repeated_targets += count
        if len(labels) > 1:
            conflicting_groups += 1
            conflicting_targets += count
            excess_conflicting_targets += count - max(labels.values())
            if len(examples) < 12:
                examples.append(
                    {
                        "digest": key.hex(),
                        "count": count,
                        "labels": [
                            {"label": repr(label), "count": label_count}
                            for label, label_count in labels.most_common()
                        ],
                    }
                )
    return {
        "total_targets": total_targets,
        "unique_inputs": len(groups),
        "repeated_groups": repeated_groups,
        "repeated_targets": repeated_targets,
        "repeated_target_rate": repeated_targets / total_targets if total_targets else 0.0,
        "conflicting_groups": conflicting_groups,
        "conflicting_targets": conflicting_targets,
        "conflicting_target_rate": conflicting_targets / total_targets if total_targets else 0.0,
        "minimum_unavoidable_error_targets": excess_conflicting_targets,
        "minimum_unavoidable_error_rate": (
            excess_conflicting_targets / total_targets if total_targets else 0.0
        ),
        "deterministic_exact_ceiling": (
            1.0 - excess_conflicting_targets / total_targets if total_targets else 1.0
        ),
        "maximum_input_multiplicity": max_multiplicity,
        "examples": examples,
    }


@app.function(
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run() -> dict[str, Any]:
    sys.path.insert(0, "/workspace/ptcg-rl/src")
    from ptcg_rl.g2.models import MODEL_SCHEMA_VERSION, model_schema_sha256

    if not EXACT_CACHE.is_file() or not EXACT_MANIFEST.is_file():
        raise RuntimeError("schema-v3 exact cache or manifest is missing")
    manifest = json.loads(EXACT_MANIFEST.read_text(encoding="utf-8"))
    if MODEL_SCHEMA_VERSION != 3 or manifest.get("model_schema_sha256") != model_schema_sha256():
        raise RuntimeError("schema-v3 conflict audit source differs from current learner schema")

    with EXACT_CACHE.open("rb") as handle:
        episodes = pickle.load(handle)

    reports: dict[str, Any] = {}
    for split in ("train", "validation", "all"):
        selected = [episode for episode in episodes if split == "all" or episode.split == split]
        current_groups: dict[bytes, Counter[Any]] = defaultdict(Counter)
        prefix_groups: dict[bytes, Counter[Any]] = defaultdict(Counter)
        targets = 0
        episode_count = 0
        for episode in selected:
            episode_count += 1
            prefix = hashlib.sha256(b"kptcg-schema-v3-prefix-v1").digest()
            for decision in episode.decisions:
                current = _model_digest(decision.projected.model)
                prefix = hashlib.sha256(prefix + current).digest()
                if decision.request.forced:
                    continue
                label = _label(decision)
                current_groups[current][label] += 1
                prefix_groups[prefix][label] += 1
                targets += 1
        reports[split] = {
            "episodes": episode_count,
            "targets": targets,
            "current_state": _summarize(current_groups, targets),
            "full_recurrent_prefix": _summarize(prefix_groups, targets),
        }

    report = {
        "record_id": "bc-schema-v3-visible-label-conflict-audit-v1",
        "status": "PASS_BC_SCHEMA_V3_CONFLICT_AUDIT",
        "model_schema_version": MODEL_SCHEMA_VERSION,
        "model_schema_sha256": model_schema_sha256(),
        "exact_manifest_sha256": hashlib.sha256(EXACT_MANIFEST.read_bytes()).hexdigest(),
        "splits": reports,
    }
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(run.remote(), sort_keys=True))
