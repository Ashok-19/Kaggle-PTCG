namespace gpu_cabt {

__device__ __forceinline__ void push_player_continuation(
    BattleRuntimeState* runtime,
    gc_u16 opcode,
    gc_i32 player_index
) {
    push_continuation(runtime, opcode);
    if (runtime->error_flags != 0 || runtime->continuation_count == 0) return;
    auto& top = runtime->continuations[runtime->continuation_count - 1];
    top.arg_type = 1;
    top.arg0 = player_index;
}

__device__ __forceinline__ void resetup_active_once(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index,
    gc_u64 seed,
    gc_u64 stream
) {
    if (state->mulligan_count[player_index] < 47) {
        state->mulligan_count[player_index] += 1;
    }
    open_return_and_shuffle(state, runtime, player_index, seed, stream);
    if (runtime->error_flags != 0) return;
    draw_cards(state, runtime, player_index, 7);
    if (runtime->error_flags != 0) return;
    push_player_continuation(runtime, kContinuationAfterResetupActivePokemon, player_index);
    push_player_continuation(runtime, kContinuationSetupActivePokemon, player_index);
    if (runtime->error_flags != 0) return;
    pre_setup_active_pokemon(state, runtime, card_table, card_table_size, player_index);
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_force_no_basic_hand(
    unsigned char* raw_states,
    const gc_i32* player_indices,
    gc_i32 filler_card_id,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const gc_i32 player_index = player_indices[env_index];
    auto& hand = state->players[player_index].hand;
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        state->all_card[hand.values[index]].card_id = filler_card_id;
    }
}

extern "C" __global__ void gpu_cabt_resetup_active_once(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gpu_cabt::SetupCardStatic* card_table,
    gc_i32 card_table_size,
    const gc_i32* player_indices,
    gc_u64 seed,
    gc_u64 stream_base,
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
    gpu_cabt::resetup_active_once(
        state,
        runtime,
        card_table,
        card_table_size,
        player_index,
        seed,
        stream_base + (gc_u64)env_index
    );
}

static constexpr gc_i32 kResetupSnapshotSize = 50;

extern "C" __global__ void gpu_cabt_resetup_active_once_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kResetupSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = state->mulligan_count[0];
    row[cursor++] = state->mulligan_count[1];
    row[cursor++] = (gc_i32)state->mulligan[0];
    row[cursor++] = (gc_i32)state->mulligan[1];
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.deck.count;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
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
    row[cursor++] = (gc_i32)(runtime->rng_draw_index & 0xffffffffull);
    row[cursor++] = (gc_i32)(runtime->rng_draw_index >> 32);
    for (gc_i32 index = 0; index < 7; ++index) {
        const gc_u8 ref = player.hand.values[index];
        row[cursor++] = (gc_i32)ref;
        row[cursor++] = state->all_card[ref].card_id;
    }
    for (gc_i32 index = 0; index < 12; ++index) {
        row[cursor++] = (gc_i32)player.deck.values[(gc_i32)player.deck.count - 1 - index];
    }
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = (gc_i32)state->setup_done[player_index];
    row[cursor++] = (gc_i32)player.prize.count;
    if (cursor != kResetupSnapshotSize) row[0] = -999999;
}
