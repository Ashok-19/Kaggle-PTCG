from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.rule_static import extract_rule_tables


def _fnv(parts: tuple[bytes, ...]) -> int:
    value = 1469598103934665603
    for part in parts:
        for byte in part:
            value ^= byte
            value = (value * 1099511628211) & ((1 << 64) - 1)
    return value


def main() -> int:
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    blob = extract_rule_tables(official, repo_root)
    parts = (
        blob.cards,
        blob.skills,
        blob.attacks,
        blob.effects,
        blob.triggers,
        blob.substring_masks,
    )
    device_parts = [cp.asarray(np.frombuffer(part, dtype=np.uint8)) for part in parts]
    source = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in (
            "src/ptcg_rl/gpu_cabt/native/state_core.h",
            "src/ptcg_rl/gpu_cabt/native/rule_static.h",
            "src/ptcg_rl/gpu_cabt/cuda/rule_static_probe.cu",
        )
    )
    module = load_cupy_module(
        cp,
        source,
        kernel_names=("gpu_cabt_rule_static_probe", "gpu_cabt_rule_static_checksum"),
    )
    probe = cp.empty(22, dtype=cp.int32)
    module.get_function("gpu_cabt_rule_static_probe")(
        (1,),
        (1,),
        (
            *device_parts,
            np.int32(blob.card_count),
            np.int32(blob.skill_count),
            np.int32(blob.attack_count),
            np.int32(blob.effect_count),
            np.int32(blob.trigger_count),
            np.int32(blob.substring_mask_count),
            np.int32(blob.substring_mask_words),
            probe,
        ),
    )
    checksum = cp.empty(1, dtype=cp.uint64)
    checksum_args: list[object] = []
    for device, part in zip(device_parts, parts, strict=True):
        checksum_args.extend((device, np.int64(len(part))))
    checksum_args.append(checksum)
    module.get_function("gpu_cabt_rule_static_checksum")(
        (1,), (1,), tuple(checksum_args)
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(probe)
    gpu_checksum = int(cp.asnumpy(checksum)[0])
    cpu_checksum = _fnv(parts)
    strides_match = actual[:5].tolist() == [
        blob.card_stride,
        blob.skill_stride,
        blob.attack_stride,
        blob.effect_stride,
        blob.trigger_stride,
    ]
    counts_match = actual[5:12].tolist() == [
        blob.card_count,
        blob.skill_count,
        blob.attack_count,
        blob.effect_count,
        blob.trigger_count,
        blob.substring_mask_count,
        blob.substring_mask_words,
    ]
    sparse_ids_match = bool(
        actual[12] == 1
        and actual[13] == 1267
        and actual[14] == 2
        and actual[15] == 434
        and actual[16] == 1
        and actual[17] == 1556
    )
    checksum_match = gpu_checksum == cpu_checksum
    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    result = {
        "device": str(device_name),
        "table_bytes": blob.total_bytes,
        "cards": blob.card_count,
        "skills": blob.skill_count,
        "attacks": blob.attack_count,
        "effects": blob.effect_count,
        "triggers": blob.trigger_count,
        "substring_masks": blob.substring_mask_count,
        "strides_match": strides_match,
        "counts_match": counts_match,
        "sparse_ids_match": sparse_ids_match,
        "full_byte_checksum_match": checksum_match,
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all((strides_match, counts_match, sparse_ids_match, checksum_match)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
