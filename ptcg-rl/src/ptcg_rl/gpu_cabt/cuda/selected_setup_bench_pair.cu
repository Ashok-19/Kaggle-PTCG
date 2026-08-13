namespace gpu_cabt {

__device__ __forceinline__ bool load_selected_indices(
    BattleRuntimeState* runtime,
    const gc_i32* selected_counts,
    const gc_i32* selected_indices,
    gc_i32 selected_stride,
    gc_i32 env_index
) {
    const gc_i32 count = selected_counts[env_index];
    if (count < 0 || count > selected_stride || count > kSelectedCapacity) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    runtime->selected_count = (gc_u16)count;
    for (gc_i32 index = 0; index < count; ++index) {
        runtime->selected[index] = selected_indices[(gc_i64)env_index * selected_stride + index];
    }
    return true;
}

__device__ __forceinline__ void consume_selected_setup_bench(
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    if (runtime->continuation_count == 0) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const auto& top = runtime->continuations[runtime->continuation_count - 1];
    if (top.opcode != kContinuationSelectedSetupBenchPokemon || top.arg0 != player_index) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    runtime->continuation_count--;
}

__device__ __forceinline__ void reveal_setup_field(BattleCoreState* state) {
    for (gc_i32 player_index = 0; player_index < 2; ++player_index) {
        auto& player = state->players[player_index];
        if (player.active.count > 0) {
            state->all_card[player.active.values[0]].reverse = 0;
        }
        for (gc_i32 index = 0; index < (gc_i32)player.bench.count; ++index) {
            state->all_card[player.bench.values[index]].reverse = 0;
        }
    }
}

__device__ __forceinline__ void normalize_setup_active_move_counters(
    BattleCoreState* state,
    BattleRuntimeState* runtime
) {
    const gc_i32 first = state->first_player;
    if (first < 0 || first > 1) {
        runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 second = 1 - first;
    if (state->players[first].active.count == 0 || state->players[second].active.count == 0) {
        runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    CardState& first_card = state->all_card[state->players[first].active.values[0]];
    CardState& second_card = state->all_card[state->players[second].active.values[0]];
    if (first_card.move_counter > second_card.move_counter) {
        const gc_i32 tmp = first_card.move_counter;
        first_card.move_counter = second_card.move_counter;
        second_card.move_counter = tmp;
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_selected_setup_bench_first(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* player_indices,
    const gc_i32* selected_counts,
    const gc_i32* selected_indices,
    gc_i32 selected_stride,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    auto* runtime = reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    if (runtime->error_flags != 0) return;
    const gc_i32 player_index = player_indices[env_index];
    if (player_index != state->first_player) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }
    if (!gpu_cabt::load_selected_indices(
            runtime, selected_counts, selected_indices, selected_stride, env_index
        )) return;
    gpu_cabt::set_selected_card_targets(state, runtime);
    if (runtime->error_flags != 0) return;
    gpu_cabt::consume_selected_setup_bench(runtime, player_index);
}

extern "C" __global__ void gpu_cabt_selected_setup_bench_second_before_turn_start(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* player_indices,
    const gc_i32* selected_counts,
    const gc_i32* selected_indices,
    gc_i32 selected_stride,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    auto* runtime = reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    if (runtime->error_flags != 0) return;
    const gc_i32 player_index = player_indices[env_index];
    if (player_index != 1 - state->first_player) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }

    gpu_cabt::move_selected_targets_to_bench(state, runtime, state->first_player);
    if (runtime->error_flags != 0) return;
    if (!gpu_cabt::load_selected_indices(
            runtime, selected_counts, selected_indices, selected_stride, env_index
        )) return;
    gpu_cabt::set_selected_card_targets(state, runtime);
    if (runtime->error_flags != 0) return;
    gpu_cabt::move_selected_targets_to_bench(state, runtime, player_index);
    if (runtime->error_flags != 0) return;

    state->setup_done[0] = 0;
    state->setup_done[1] = 0;
    gpu_cabt::reveal_setup_field(state);
    gpu_cabt::normalize_setup_active_move_counters(state, runtime);
    if (runtime->error_flags != 0) return;
    gpu_cabt::consume_selected_setup_bench(runtime, player_index);
}

extern "C" __global__ void gpu_cabt_force_active_move_counter_swap_case(
    unsigned char* raw_states,
    const gc_i32* swap_flags,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count || swap_flags[env_index] == 0) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const gc_i32 first = state->first_player;
    const gc_i32 second = 1 - first;
    if (state->players[first].active.count == 0 || state->players[second].active.count == 0) return;
    auto& first_card = state->all_card[state->players[first].active.values[0]];
    auto& second_card = state->all_card[state->players[second].active.values[0]];
    if (first_card.move_counter < second_card.move_counter) {
        const gc_i32 tmp = first_card.move_counter;
        first_card.move_counter = second_card.move_counter;
        second_card.move_counter = tmp;
    }
}

static constexpr gc_i32 kSetupBenchPairSnapshotSize = 43;

extern "C" __global__ void gpu_cabt_setup_bench_pair_snapshot(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    gc_i32* output,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto* state = reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const auto* runtime = reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    gc_i32* row = output + (gc_i64)env_index * kSetupBenchPairSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = (gc_i32)state->setup_done[0];
    row[cursor++] = (gc_i32)state->setup_done[1];
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[cursor++] = (gc_i32)runtime->target_count;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->select_type;

    for (gc_i32 player_index = 0; player_index < 2; ++player_index) {
        const auto& player = state->players[player_index];
        row[cursor++] = (gc_i32)player.hand.count;
        row[cursor++] = (gc_i32)player.bench.count;
        row[cursor++] = player.active.count > 0 ? (gc_i32)player.active.values[0] : 0;
        if (player.active.count > 0) {
            const auto& active = state->all_card[player.active.values[0]];
            row[cursor++] = (gc_i32)active.reverse;
            row[cursor++] = active.move_counter;
        } else {
            row[cursor++] = -1;
            row[cursor++] = -1;
        }
        for (gc_i32 index = 0; index < 4; ++index) {
            row[cursor++] = index < (gc_i32)player.bench.count
                ? (gc_i32)player.bench.values[index] : -1;
        }
        for (gc_i32 index = 0; index < 4; ++index) {
            row[cursor++] = index < (gc_i32)player.bench.count
                ? (gc_i32)state->all_card[player.bench.values[index]].reverse : -1;
        }
        for (gc_i32 index = 0; index < 4; ++index) {
            row[cursor++] = index < (gc_i32)player.bench.count
                ? state->all_card[player.bench.values[index]].move_counter : -1;
        }
    }
    if (cursor != kSetupBenchPairSnapshotSize) row[0] = -999999;
}
