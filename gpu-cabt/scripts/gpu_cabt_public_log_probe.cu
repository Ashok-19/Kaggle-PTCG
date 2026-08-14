extern "C" __global__ void gpu_cabt_public_log_burst_setup(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_i32 event_count
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(raw_states);
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(raw_runtimes);
    state.select_type = gpu_cabt::kSelectMain;
    state.select_player = 0;
    state.game_result = 0;
    runtime.error_flags = 0;
    runtime.public_log_count = 0;
    runtime.public_log_index[0] = 0;
    runtime.public_log_index[1] = 0;
    for (gc_i32 i = 0; i < event_count; ++i) {
        gpu_cabt::append_public_log(runtime, gpu_cabt::kLogCoin, 2, i & 1, (i >> 1) & 1);
    }
}

extern "C" __global__ void gpu_cabt_public_log_set_actor(
    unsigned char* raw_states,
    gc_i32 actor
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(raw_states);
    state.select_type = gpu_cabt::kSelectMain;
    state.select_player = (gc_i8)actor;
    state.game_result = 0;
}

extern "C" __global__ void gpu_cabt_public_log_terminal_setup(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_i32 actor
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(raw_states);
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(raw_runtimes);
    state.select_type = gpu_cabt::kSelectNone;
    state.select_player = (gc_i8)actor;
    state.game_result = 1;
    state.finish_reason = 1;
    runtime.error_flags = 0;
    runtime.public_log_count = 0;
    runtime.public_log_index[0] = 0;
    runtime.public_log_index[1] = 0;
    gpu_cabt::log_result(runtime, 0, 1);
}

extern "C" __global__ void gpu_cabt_public_log_runtime_snapshot(
    const unsigned char* raw_runtimes,
    gc_i32* out
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    const auto& runtime = *reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(raw_runtimes);
    out[0] = runtime.public_log_count;
    out[1] = runtime.public_log_index[0];
    out[2] = runtime.public_log_index[1];
    out[3] = (gc_i32)runtime.error_flags;
}

extern "C" __global__ void gpu_cabt_public_log_effect_win_setup(
    unsigned char* raw_states,
    unsigned char* raw_runtimes
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(raw_states);
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(raw_runtimes);
    state = {};
    runtime = {};
    state.select_player = 1;
    gpu_cabt::RuleEffect effect{};
    effect.effect_type = 116;
    effect.target.target_player = 3;
    gpu_cabt::RuleTableView rules{};
    gpu_cabt::effect_instant_111_135(state, runtime, rules, effect);
}
