namespace gpu_cabt {

__device__ __forceinline__ bool flip_coin_head(BattleRuntimeState& runtime) {
    return bounded_u32(runtime.rng_seed, runtime.rng_stream, &runtime.rng_draw_index, 2u) == 0u;
}

__device__ __forceinline__ gc_i32 coin_player_full(const BattleCoreState& state) {
    if (state.effect_state.on_effect) {
        const gc_i32 player = state.effect_state.ability.use_player_index;
        if (player >= 0 && player <= 1) return player;
    }
    if (state.first_player >= 0 && state.first_player <= 1) return rule_active_player_index(state);
    if (state.select_player >= 0 && state.select_player <= 1) return state.select_player;
    return 0;
}

__device__ __forceinline__ gc_i32 select_coin_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 count,
    gc_i32 player_index = -1
) {
    state.coin_head_count = 0;
    if (count <= 0) return 0;
    if (player_index < 0 || player_index > 1) player_index = coin_player_full(state);
    for (gc_i32 i = 0; i < count; ++i) {
        const bool head = flip_coin_head(runtime);
        log_coin(runtime, player_index, head);
        if (head) ++state.coin_head_count;
    }
    return state.coin_head_count;
}

__device__ __noinline__ gc_i32 select_coin_until_tail_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index = -1
) {
    state.coin_head_count = 0;
    if (player_index < 0 || player_index > 1) player_index = coin_player_full(state);
    while (true) {
        const bool head = flip_coin_head(runtime);
        log_coin(runtime, player_index, head);
        if (!head) break;
        ++state.coin_head_count;
        if (state.coin_head_count >= 10000000) break;
    }
    return state.coin_head_count;
}

}  // namespace gpu_cabt
