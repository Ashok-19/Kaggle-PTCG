namespace gpu_cabt {

static constexpr gc_u8 kSelectContextSetupBenchPokemon = 3;
static constexpr gc_u64 kBenchCapacityMask = 0xfull << 40;

__device__ __forceinline__ gc_i32 bench_capacity(const PlayerState& player) {
    const gc_i32 override_capacity = (gc_i32)((player.continual_state >> 40) & 0xfull);
    return override_capacity == 0 ? 5 : override_capacity;
}

__device__ __forceinline__ void setup_bench_pokemon(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index
) {
    state->select_type = kSelectTypeCard;
    state->select_context = kSelectContextSetupBenchPokemon;
    state->select_player = (gc_i8)player_index;
    state->select_min = 1;
    state->select_max = 1;

    const auto& hand = state->players[player_index].hand;
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        const gc_u8 ref = hand.values[index];
        const gc_i32 card_id = state->all_card[ref].card_id;
        if (card_id < 0 || card_id >= card_table_size) {
            runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }
        if (card_table[card_id].can_setup != 0) {
            add_setup_active_card_option(runtime, index, player_index);
            if (runtime->error_flags != 0) return;
        }
    }

    state->select_min = 0;
    gc_i32 remaining = bench_capacity(state->players[player_index])
        - (gc_i32)state->players[player_index].bench.count;
    if (remaining < 0) remaining = 0;
    state->select_max = (gc_i32)runtime->option_count < remaining
        ? (gc_i32)runtime->option_count : remaining;
    push_continuation(runtime, kContinuationSelectedSetupBenchPokemon);
    if (runtime->error_flags == 0 && runtime->continuation_count > 0) {
        auto& top = runtime->continuations[runtime->continuation_count - 1];
        top.arg_type = 1;
        top.arg0 = player_index;
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_force_setup_bench_case(
    unsigned char* raw_states,
    const gc_i32* player_indices,
    gc_i32 setup_card_id,
    gc_i32 filler_card_id,
    const gc_i32* eligible_counts,
    const gc_i32* bench_capacity_overrides,
    const gc_i32* bench_counts,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const gc_i32 player_index = player_indices[env_index];
    auto& player = state->players[player_index];
    const gc_i32 eligible = eligible_counts[env_index];
    for (gc_i32 index = 0; index < (gc_i32)player.hand.count; ++index) {
        const gc_u8 ref = player.hand.values[index];
        state->all_card[ref].card_id = index < eligible ? setup_card_id : filler_card_id;
    }
    const gc_u64 override_bits = ((gc_u64)(bench_capacity_overrides[env_index] & 0xf)) << 40;
    player.continual_state = (player.continual_state & ~gpu_cabt::kBenchCapacityMask)
        | override_bits;
    player.bench.count = (gc_u8)bench_counts[env_index];
}

extern "C" __global__ void gpu_cabt_setup_bench(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gpu_cabt::SetupCardStatic* card_table,
    gc_i32 card_table_size,
    const gc_i32* player_indices,
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
    if (player_index < 0 || player_index > 1) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }
    gpu_cabt::setup_bench_pokemon(
        state, runtime, card_table, card_table_size, player_index
    );
}

static constexpr gc_i32 kSetupBenchSnapshotSize = 68;

extern "C" __global__ void gpu_cabt_setup_bench_snapshot(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    const gc_i32* player_indices,
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
    const gc_i32 player_index = player_indices[env_index];
    const auto& player = state->players[player_index];
    gc_i32* row = output + (gc_i64)env_index * kSetupBenchSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.bench.count;
    row[cursor++] = gpu_cabt::bench_capacity(player);
    row[cursor++] = (gc_i32)state->select_type;
    row[cursor++] = (gc_i32)state->select_context;
    row[cursor++] = (gc_i32)state->select_player;
    row[cursor++] = state->select_min;
    row[cursor++] = state->select_max;
    row[cursor++] = (gc_i32)runtime->option_count;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[cursor++] = runtime->continuation_count > 0
        ? runtime->continuations[runtime->continuation_count - 1].arg0 : 0;
    row[cursor++] = (gc_i32)runtime->error_flags;
    for (gc_i32 index = 0; index < 8; ++index) {
        if (index < (gc_i32)runtime->option_count) {
            const auto& option = runtime->options[index];
            row[cursor++] = (gc_i32)option.type;
            row[cursor++] = (gc_i32)option.param0;
            row[cursor++] = (gc_i32)option.param1;
            row[cursor++] = (gc_i32)option.param2;
            row[cursor++] = (gc_i32)option.param3;
            row[cursor++] = (gc_i32)option.param4;
        } else {
            for (gc_i32 field = 0; field < 6; ++field) row[cursor++] = -1;
        }
    }
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = (gc_i32)state->setup_done[player_index];
    row[cursor++] = (gc_i32)player.active.count;
    row[cursor++] = (gc_i32)(player.continual_state >> 40) & 0xf;
    if (cursor != kSetupBenchSnapshotSize) row[0] = -999999;
}
