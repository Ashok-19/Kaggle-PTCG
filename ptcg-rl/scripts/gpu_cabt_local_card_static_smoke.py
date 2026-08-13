from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.card_static import dense_setup_card_table, extract_setup_card_static
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module


def main() -> int:
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    engine_root = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    records = extract_setup_card_static(engine_root)
    dense_bytes, row_count = dense_setup_card_table(records)

    state_header = (repo_root / "src/ptcg_rl/gpu_cabt/native/state_core.h").read_text()
    static_header = (repo_root / "src/ptcg_rl/gpu_cabt/native/card_static.h").read_text()
    probe_source = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/card_static_probe.cu").read_text()
    module = load_cupy_module(
        cp,
        "\n".join((state_header, static_header, probe_source)),
        kernel_names=("gpu_cabt_card_static_probe",),
    )
    kernel = module.get_function("gpu_cabt_card_static_probe")

    host_table = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)
    card_ids = np.asarray([record.card_id for record in records], dtype=np.int32)
    expected = np.asarray(
        [
            [
                record.is_basic_pokemon,
                record.is_setup_doll,
                record.can_setup,
                record.can_setup_active,
            ]
            for record in records
        ],
        dtype=np.uint8,
    )
    device_table = cp.asarray(host_table)
    device_ids = cp.asarray(card_ids)
    output = cp.empty((len(records), 4), dtype=cp.uint8)
    threads = 128
    blocks = (len(records) + threads - 1) // threads
    kernel(
        (blocks,),
        (threads,),
        (device_table, np.int32(row_count), device_ids, output, np.int32(len(records))),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(output)
    differential_match = bool(np.array_equal(actual, expected))

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "record_count": len(records),
        "dense_row_count": row_count,
        "dense_table_bytes": len(dense_bytes),
        "differential_match": differential_match,
        "basic_pokemon_count": sum(record.is_basic_pokemon for record in records),
        "setup_doll_count": sum(record.is_setup_doll for record in records),
        "total_vram_bytes": int(total_vram),
        "free_vram_bytes": int(free_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
