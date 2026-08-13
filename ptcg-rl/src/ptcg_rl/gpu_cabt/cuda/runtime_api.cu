extern "C" __global__ void gpu_cabt_runtime_info(gc_i32* out) {
    if (blockIdx.x != 0 || threadIdx.x != 0 || out == nullptr) return;
    out[0] = (gc_i32)sizeof(gpu_cabt::BattleCoreState);
    out[1] = (gc_i32)sizeof(gpu_cabt::BattleRuntimeState);
    out[2] = gpu_cabt::kPolicyGlobalWidth;
    out[3] = gpu_cabt::kPolicyPlayerWidth;
    out[4] = gpu_cabt::kPolicyEntityCapacity;
    out[5] = gpu_cabt::kPolicyEntityWidth;
    out[6] = gpu_cabt::kPolicyOptionCapacity;
    out[7] = gpu_cabt::kPolicyOptionWidth;
    out[8] = gpu_cabt::kSelectedCapacity;
    out[9] = gpu_cabt::kDeckSize;
    out[10] = gpu_cabt::kAllCardCapacity;
    out[11] = gpu_cabt::kOptionCapacity;
    out[12] = gpu_cabt::kPublicLogCapacity;
    out[13] = gpu_cabt::kPublicEventWidth;
}

extern "C" __global__ void gpu_cabt_runtime_status(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    gc_u32* error_flags,
    gc_u8* game_results,
    gc_u8* select_types,
    gc_i8* select_players,
    gc_i32* turns,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto& state = *reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    const auto& runtime = *reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    error_flags[env_index] = runtime.error_flags;
    game_results[env_index] = state.game_result;
    select_types[env_index] = state.select_type;
    select_players[env_index] = state.select_player;
    turns[env_index] = state.turn;
}
