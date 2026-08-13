from __future__ import annotations

import json

import numpy as np

from ptcg_rl.gpu_cabt.device_runtime import default_official_dir, repo_root
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.public_policy import public_looking_mode
from ptcg_rl.gpu_cabt.rule_static import extract_rule_tables
from ptcg_rl.gpu_cabt.source import build_cuda_source


_PROBE_SOURCE = r'''
extern "C" __global__ void gpu_cabt_policy_looking_probe(
    const gc_i32* raw,
    gc_i32* out,
    gc_i32 count
) {
    const gc_i32 i = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (i >= count) return;
    const gc_i32* row = raw + (gc_i64)i * 3;
    gpu_cabt::BattleCoreState state{};
    state.looking.count = (gc_u8)row[0];
    state.looking_player = (gc_i8)row[1];
    out[i] = gpu_cabt::policy_public_looking_mode(state, row[2]);
}

extern "C" __global__ void gpu_cabt_policy_phase_fixture(
    unsigned char* raw_states,
    unsigned char* raw_runtimes
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(raw_states);
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(raw_runtimes);
    state = {};
    runtime = {};
    state.select_type = gpu_cabt::kSelectMain;
    state.select_player = 0;
    state.first_player = 0;
    state.phase = 7;
    state.turn = 11;
    runtime.option_count = 0;
}
'''


def _upload_rule_bytes(cp, value: bytes):
    return cp.asarray(np.frombuffer(value, dtype=np.uint8).copy())


def main() -> None:
    import cupy as cp

    cases: list[tuple[int, int, int]] = []
    for actor in (0, 1):
        cases.extend(
            [
                (0, actor, actor),
                (3, actor, actor),
                (3, 2, actor),
                (3, actor + 3, actor),
                (3, 1 - actor, actor),
            ]
        )
    raw = np.asarray(cases, dtype=np.int32)
    kernel_names = (
        "gpu_cabt_runtime_info",
        "gpu_cabt_project_policy",
        "gpu_cabt_policy_looking_probe",
        "gpu_cabt_policy_phase_fixture",
    )
    module = load_cupy_module(
        cp,
        build_cuda_source() + "\n" + _PROBE_SOURCE,
        kernel_names=kernel_names,
    )

    raw_gpu = cp.asarray(raw)
    modes_gpu = cp.empty(len(cases), dtype=cp.int32)
    blocks = (len(cases) + 127) // 128
    module.get_function("gpu_cabt_policy_looking_probe")(
        (blocks,), (128,), (raw_gpu, modes_gpu, np.int32(len(cases)))
    )
    cp.cuda.Stream.null.synchronize()
    actual_modes = modes_gpu.get()
    expected_modes = np.asarray(
        [
            public_looking_mode(count=count, looking_player=looking_player, actor=actor)
            for count, looking_player, actor in cases
        ],
        dtype=np.int32,
    )

    info = cp.empty(14, dtype=cp.int32)
    module.get_function("gpu_cabt_runtime_info")((1,), (1,), (info,))
    cp.cuda.Stream.null.synchronize()
    abi = info.get().tolist()
    state_bytes, runtime_bytes = int(abi[0]), int(abi[1])
    global_width, player_width = int(abi[2]), int(abi[3])
    entity_capacity, entity_width = int(abi[4]), int(abi[5])
    option_capacity, option_width = int(abi[6]), int(abi[7])

    states = cp.empty(state_bytes, dtype=cp.uint8)
    runtimes = cp.empty(runtime_bytes, dtype=cp.uint8)
    module.get_function("gpu_cabt_policy_phase_fixture")((1,), (1,), (states, runtimes))

    rules = extract_rule_tables(default_official_dir(), repo_root())
    uploaded_rules = (
        _upload_rule_bytes(cp, rules.cards),
        _upload_rule_bytes(cp, rules.skills),
        _upload_rule_bytes(cp, rules.attacks),
        _upload_rule_bytes(cp, rules.effects),
        _upload_rule_bytes(cp, rules.triggers),
        _upload_rule_bytes(cp, rules.substring_masks),
        np.int32(rules.card_count),
        np.int32(rules.skill_count),
        np.int32(rules.attack_count),
        np.int32(rules.effect_count),
        np.int32(rules.trigger_count),
        np.int32(rules.substring_mask_count),
        np.int32(rules.substring_mask_words),
    )
    globals_gpu = cp.empty((1, global_width), dtype=cp.int32)
    players_gpu = cp.empty((1, 2, player_width), dtype=cp.int32)
    entities_gpu = cp.empty((1, entity_capacity, entity_width), dtype=cp.int32)
    entity_counts = cp.empty(1, dtype=cp.int32)
    options_gpu = cp.empty((1, option_capacity, option_width), dtype=cp.int32)
    option_counts = cp.empty(1, dtype=cp.int32)
    status = cp.empty(1, dtype=cp.uint32)
    module.get_function("gpu_cabt_project_policy")(
        (1,),
        (128,),
        (
            states,
            runtimes,
            *uploaded_rules,
            globals_gpu,
            players_gpu,
            entities_gpu,
            entity_counts,
            options_gpu,
            option_counts,
            status,
            np.int32(1),
        ),
    )
    cp.cuda.Stream.null.synchronize()
    globals_host = globals_gpu.get()[0]
    projection_status = int(status.get()[0])

    mismatches: list[dict[str, object]] = []
    if not np.array_equal(actual_modes, expected_modes):
        mismatches.append(
            {
                "label": "looking-mode",
                "actual": actual_modes.tolist(),
                "expected": expected_modes.tolist(),
            }
        )
    if projection_status != 0 or int(globals_host[4]) != 0:
        mismatches.append(
            {
                "label": "internal-phase",
                "projection_status": projection_status,
                "phase_slot": int(globals_host[4]),
            }
        )

    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "looking_cases": len(cases),
        "phase_slot": int(globals_host[4]),
        "projection_status": projection_status,
        "mismatches": mismatches,
    }
    print(json.dumps(result, sort_keys=True))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
