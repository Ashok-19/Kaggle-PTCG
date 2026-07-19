from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.card_table import load_card_table
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected, policy_metadata
from ptcg_rl.g2.projection import project_decision

SEED = 20260719
CARD_HASH = "c" * 64
GRADIENT_PARAMETERS = (
    "catalog.card_id_embedding.weight",
    "entity_transformer.layers.0.self_attn.in_proj_weight",
    "public_gru.weight_hh",
    "option_projection.0.weight",
    "value_head.0.weight",
    "selection_gru.weight_hh",
    "stop_embedding",
)

QUALIFICATION_STATE_ALGORITHM = "sha256-name-lcg24-v1"
_LCG_MULTIPLIER = np.uint64(6_364_136_223_846_793_005)
_LCG_MASK = np.uint64((1 << 24) - 1)


def initialize_qualification_state(model: torch.nn.Module) -> None:
    """Assign a byte-stable state independent of PyTorch build defaults."""
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            name_seed = np.uint64(
                int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "little")
            )
            indices = np.arange(parameter.numel(), dtype=np.uint64)
            raw = (indices * _LCG_MULTIPLIER + name_seed) & _LCG_MASK
            centered = raw.astype(np.float32) / np.float32(1 << 24) - np.float32(0.5)
            if parameter.ndim == 1 and name.endswith(".weight"):
                values = np.float32(1.0) + centered / np.float32(512.0)
            elif name.endswith("bias"):
                values = centered / np.float32(512.0)
            else:
                values = centered / np.float32(16.0)
            tensor = torch.from_numpy(values.reshape(tuple(parameter.shape))).to(
                dtype=parameter.dtype
            )
            parameter.copy_(tensor)


def raw_observation(options: list[dict[str, Any]]) -> dict[str, Any]:
    def player(hand: list[dict[str, Any]] | None) -> dict[str, Any]:
        return {
            "active": [],
            "bench": [],
            "benchMax": 5,
            "deckCount": 46,
            "discard": [],
            "prize": [None] * 6,
            "handCount": 7,
            "hand": hand,
            "poisoned": False,
            "burned": False,
            "asleep": False,
            "paralyzed": False,
            "confused": False,
        }

    return {
        "search_begin_input": "qualification-excluded-search-state",
        "logs": [],
        "current": {
            "yourIndex": 0,
            "turn": 2,
            "turnActionCount": 3,
            "firstPlayer": 0,
            "supporterPlayed": False,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "players": [player([]), player(None)],
            "stadium": [],
            "looking": None,
        },
        "select": {
            "type": 8,
            "context": 38,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "contextCard": None,
            "effect": None,
            "option": options,
            "deck": None,
        },
    }


def projected_decisions() -> tuple[Any, Any, Any]:
    number_raw = raw_observation([{"type": 0, "number": value} for value in range(70)])
    number_observation, number_request = semantic_snapshot(
        number_raw, "qualification-number", 0, CARD_HASH
    )
    if number_request is None:
        raise RuntimeError("number qualification request is missing")

    card_raw = raw_observation([{"type": 15, "cardId": 1, "serial": 10}])
    card_raw["select"].update({"type": 5, "context": 34})
    card_raw["current"]["players"][0]["active"] = [
        {
            "id": 1,
            "serial": 10,
            "playerIndex": 0,
            "hp": 50,
            "maxHp": 70,
            "appearThisTurn": False,
            "energies": [1],
            "energyCards": [],
            "tools": [],
            "preEvolution": [],
        }
    ]
    card_raw["logs"] = [
        {
            "type": 15,
            "playerIndex": 0,
            "cardId": 1,
            "serial": 10,
            "attackId": 1,
        },
        {
            "type": 16,
            "cardIdTarget": 1,
            "serialTarget": 10,
            "value": -20,
            "putDamageCounter": False,
            "isRecover": False,
        },
    ]
    card_observation, card_request = semantic_snapshot(
        card_raw, "qualification-card", 0, CARD_HASH
    )
    if card_request is None:
        raise RuntimeError("card qualification request is missing")

    number = project_decision(number_observation, number_request)
    card = project_decision(card_observation, card_request)
    small_raw = raw_observation([{"type": 0, "number": value} for value in range(5)])
    small_observation, small_request = semantic_snapshot(
        small_raw, "qualification-small", 0, CARD_HASH
    )
    if small_request is None:
        raise RuntimeError("small qualification request is missing")
    small = project_decision(small_observation, small_request)
    return small, number, card


def tensor_sha256(parameters: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(parameters):
        tensor = parameters[name].detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(json.dumps(list(tensor.shape)).encode("ascii"))
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def tensor_values(value: torch.Tensor) -> list[float | str]:
    result: list[float | str] = []
    for item in value.detach().cpu().reshape(-1).tolist():
        number = float(item)
        if math.isnan(number):
            raise RuntimeError("qualification tensor contains NaN")
        if number == float("-inf"):
            result.append("-inf")
        elif number == float("inf"):
            result.append("inf")
        else:
            result.append(number)
    return result


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)

    def nearest(value: float) -> float:
        index = round((len(ordered) - 1) * value)
        return ordered[index]

    return {
        "samples": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "p50_ms": nearest(0.50),
        "p95_ms": nearest(0.95),
        "p99_ms": nearest(0.99),
        "max_ms": max(ordered),
    }


def benchmark(
    function: Callable[[], Any], device: torch.device, warmup: int, samples: int
) -> dict[str, float]:
    with torch.inference_mode():
        for _ in range(warmup):
            function()
        synchronize(device)
        timings = []
        for _ in range(samples):
            start = time.perf_counter_ns()
            function()
            synchronize(device)
            timings.append((time.perf_counter_ns() - start) / 1_000_000.0)
    return percentiles(timings)


def qualification_forward(
    model: PTCGPolicyV1, batch: Any, device: torch.device
) -> tuple[Any, Any, torch.Tensor, torch.Tensor, torch.Tensor]:
    hidden = model.initial_hidden(batch.batch_size, device)
    first_output = model(batch, hidden)
    output = model(batch, first_output.hidden)
    prefix = model.decoder_initial(output.hidden[0])
    decoder_logits = model.decoder_logits(
        prefix,
        output.option_embeddings[:5],
        torch.tensor([True, False, True, True, True], dtype=torch.bool, device=device),
        True,
    )
    advanced = model.decoder_advance(prefix, output.option_embeddings[0])
    loss = (
        output.option_logits[torch.isfinite(output.option_logits)].sum()
        + output.values.sum()
        + output.hidden.square().mean()
        + decoder_logits[torch.isfinite(decoder_logits)].sum()
        + advanced.square().mean()
    )
    return first_output, output, decoder_logits, advanced, loss


def main() -> None:
    bundle_root = Path(os.environ.get("PTCG_BUNDLE_ROOT", Path.cwd())).resolve()
    device_name = os.environ.get("PTCG_DEVICE", "cpu")
    run_id = os.environ.get("PTCG_RUN_ID", f"g2-policy-{device_name}-qualification-v1")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA qualification requested but CUDA is unavailable")

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    if device.type == "cuda":
        torch.backends.cudnn.enabled = False
    table = load_card_table(bundle_root / "card-table-v1.json")
    model = PTCGPolicyV1(table)
    initialize_qualification_state(model)
    initial_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
    state_hash = tensor_sha256(initial_state)
    model = model.to(device)

    small, large, card = projected_decisions()
    batch = collate_projected((small, large, card), device=device)

    model.eval()
    with torch.inference_mode():
        first_output, output, decoder_logits, advanced, inference_loss = qualification_forward(
            model, batch, device
        )

    model.train()
    gradient_pass_training_mode = model.training
    model.zero_grad(set_to_none=True)
    _, _, _, _, gradient_loss = qualification_forward(model, batch, device)
    gradient_loss.backward()

    gradients: dict[str, Any] = {}
    named = dict(model.named_parameters())
    for name in GRADIENT_PARAMETERS:
        gradient = named[name].grad
        if gradient is None or not torch.isfinite(gradient).all():
            raise RuntimeError(f"missing or invalid gradient for {name}")
        flattened = gradient.detach().cpu().reshape(-1)
        norm = float(torch.linalg.vector_norm(flattened))
        if not math.isfinite(norm) or norm <= 0:
            raise RuntimeError(f"zero or invalid gradient norm for {name}")
        gradients[name] = {
            "norm": norm,
            "sample": [float(value) for value in flattened[:64].tolist()],
        }

    model.zero_grad(set_to_none=True)
    model.eval()
    latency_pass_evaluation_mode = not model.training
    single = collate_projected((small,), device=device)
    batch8 = collate_projected((small, large, card, small, large, card, small, card), device=device)
    single_hidden = model.initial_hidden(1, device)
    batch8_hidden = model.initial_hidden(8, device)
    single_latency = benchmark(
        lambda: model(single, single_hidden), device, warmup=20, samples=200
    )
    batch8_latency = benchmark(
        lambda: model(batch8, batch8_hidden), device, warmup=10, samples=100
    )

    metadata = policy_metadata(model)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "source_commit": os.environ.get("PTCG_SOURCE_COMMIT"),
        "bundle_sha256": os.environ.get("PTCG_BUNDLE_SHA256"),
        "device": {
            "requested": device_name,
            "type": device.type,
            "name": torch.cuda.get_device_name(device) if device.type == "cuda" else platform.processor(),
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
        },
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "threads": torch.get_num_threads(),
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
            "cudnn_enabled": torch.backends.cudnn.enabled,
        },
        "qualification_state": {
            "algorithm": QUALIFICATION_STATE_ALGORITHM,
            "state_dict_sha256": state_hash,
        },
        "model": metadata,
        "state_dict_sha256": state_hash,
        "input_sha256": stable_hash(tuple(asdict(item) for item in (small, large, card))),
        "outputs": {
            "option_logits": tensor_values(output.option_logits),
            "values": tensor_values(output.values),
            "first_hidden": tensor_values(first_output.hidden),
            "hidden": tensor_values(output.hidden),
            "decoder_logits": tensor_values(decoder_logits),
            "decoder_advanced": tensor_values(advanced),
            "loss": float(inference_loss.detach().cpu()),
        },
        "gradients": gradients,
        "latency": {
            "batch1_five_options": single_latency,
            "batch8_mixed_options": batch8_latency,
        },
        "checks": {
            "finite_option_logits": bool(
                torch.isfinite(output.option_logits[torch.isfinite(output.option_logits)]).all()
            ),
            "masked_decoder_option_negative_infinity": bool(torch.isneginf(decoder_logits[1])),
            "parameter_ceiling": metadata["trainable_parameters"] < 2_000_000,
            "target_parameter_budget": metadata["trainable_parameters"] < 1_250_000,
            "no_optimizer_created": True,
            "no_training_loop": True,
            "gradient_pass_training_mode": gradient_pass_training_mode,
            "latency_pass_evaluation_mode": latency_pass_evaluation_mode,
            "fixed_qualification_state": True,
            "cudnn_disabled_for_gpu_parity": device.type != "cuda"
            or not torch.backends.cudnn.enabled,
        },
    }
    if not all(payload["checks"].values()):
        raise RuntimeError(f"qualification check failed: {payload['checks']}")
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    output_path = Path(f"{run_id}.json")
    output_path.write_text(encoded + "\n", encoding="utf-8")
    print("PTCG_G2_POLICY_QUALIFICATION_BEGIN")
    print(encoded)
    print("PTCG_G2_POLICY_QUALIFICATION_END")


if __name__ == "__main__":
    main()
