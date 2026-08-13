namespace gpu_cabt {

__device__ __forceinline__ bool flip_coin_head(BattleRuntimeState& runtime) {
    return bounded_u32(runtime.rng_seed, runtime.rng_stream, &runtime.rng_draw_index, 2u) == 0u;
}

__device__ __forceinline__ gc_i32 select_coin_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 count
) {
    state.coin_head_count = 0;
    if (count <= 0) return 0;
    for (gc_i32 i = 0; i < count; ++i) if (flip_coin_head(runtime)) ++state.coin_head_count;
    return state.coin_head_count;
}

__device__ __noinline__ gc_i32 select_coin_until_tail_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    state.coin_head_count = 0;
    while (flip_coin_head(runtime)) {
        ++state.coin_head_count;
        if (state.coin_head_count >= 10000000) break;
    }
    return state.coin_head_count;
}

}  // namespace gpu_cabt
