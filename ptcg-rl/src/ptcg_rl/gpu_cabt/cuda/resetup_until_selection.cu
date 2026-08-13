namespace gpu_cabt {

__device__ __forceinline__ bool deck_has_basic(
    const BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index
) {
    const auto& deck = state->players[player_index].deck;
    for (gc_i32 index = 0; index < (gc_i32)deck.count; ++index) {
        const gc_u8 ref = deck.values[index];
        const gc_i32 card_id = state->all_card[ref].card_id;
        if (card_id < 0 || card_id >= card_table_size) {
            runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
            return false;
        }
        if (card_table[card_id].is_basic_pokemon != 0) return true;
    }
    return false;
}

__device__ __forceinline__ void resetup_until_selection(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index,
    gc_u64 seed,
    gc_u64 stream
) {
    for (gc_i32 attempt = 0; attempt < 64; ++attempt) {
        if (state->mulligan_count[player_index] < 47) {
            state->mulligan_count[player_index] += 1;
        }
        open_return_and_shuffle(state, runtime, player_index, seed, stream);
        if (runtime->error_flags != 0) return;
        draw_cards(state, runtime, player_index, 7);
        if (runtime->error_flags != 0) return;

        const HandSetupFlags flags = hand_setup_flags(
            state, card_table, card_table_size, player_index, runtime
        );
        if (runtime->error_flags != 0) return;

        if (flags.has_basic) {
            state->mulligan[player_index] = 0;
            push_player_continuation(
                runtime, kContinuationAfterResetupActivePokemon, player_index
            );
            setup_active_pokemon(
                state, runtime, card_table, card_table_size, player_index
            );
            return;
        }

        if (flags.has_doll) {
            push_player_continuation(
                runtime, kContinuationAfterResetupActivePokemon, player_index
            );
            push_player_continuation(
                runtime, kContinuationSetupActivePokemon, player_index
            );
            pre_setup_active_pokemon(
                state, runtime, card_table, card_table_size, player_index
            );
            return;
        }

        state->mulligan[player_index] = 1;
        if (!deck_has_basic(
                state, runtime, card_table, card_table_size, player_index
            )) {
            if (runtime->error_flags == 0) {
                runtime->error_flags |= kRuntimeErrorNoBasicPokemon;
            }
            return;
        }
    }
    runtime->error_flags |= kRuntimeErrorMulliganLoopLimit;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_resetup_until_selection(
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
    gpu_cabt::resetup_until_selection(
        state,
        runtime,
        card_table,
        card_table_size,
        player_index,
        seed,
        stream_base + (gc_u64)env_index
    );
}

static constexpr gc_i32 kResetupUntilSelectionSnapshotSize = 86;

extern "C" __global__ void gpu_cabt_resetup_until_selection_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kResetupUntilSelectionSnapshotSize;
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
    for (gc_i32 index = 0; index < 7; ++index) {
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
    for (gc_i32 index = 0; index < 6; ++index) {
        row[cursor++] = (gc_i32)player.deck.values[(gc_i32)player.deck.count - 1 - index];
    }
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = (gc_i32)state->setup_done[player_index];
    row[cursor++] = (gc_i32)player.prize.count;
    if (cursor != kResetupUntilSelectionSnapshotSize) row[0] = -999999;
}
