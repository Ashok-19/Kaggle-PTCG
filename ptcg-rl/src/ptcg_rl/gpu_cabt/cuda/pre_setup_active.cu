namespace gpu_cabt {

static constexpr gc_u8 kSelectContextMulligan = 43;

struct HandSetupFlags {
    gc_u8 has_basic;
    gc_u8 has_doll;
};

__device__ __forceinline__ HandSetupFlags hand_setup_flags(
    const BattleCoreState* state,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index,
    BattleRuntimeState* runtime
) {
    HandSetupFlags result = {0, 0};
    const auto& hand = state->players[player_index].hand;
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        const gc_u8 ref = hand.values[index];
        const gc_i32 card_id = state->all_card[ref].card_id;
        if (card_id < 0 || card_id >= card_table_size) {
            runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
            return result;
        }
        const auto& meta = card_table[card_id];
        result.has_basic |= meta.is_basic_pokemon != 0;
        result.has_doll |= meta.is_setup_doll != 0;
    }
    return result;
}

__device__ __forceinline__ void pre_setup_active_pokemon(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32 player_index
) {
    const HandSetupFlags flags = hand_setup_flags(
        state, card_table, card_table_size, player_index, runtime
    );
    if (runtime->error_flags != 0) return;

    if (flags.has_basic) {
        state->mulligan[player_index] = 0;
        return;
    }
    if (flags.has_doll) {
        state->select_type = kSelectTypeYesNo;
        state->select_context = kSelectContextMulligan;
        state->select_player = (gc_i8)player_index;
        state->select_min = 1;
        state->select_max = 1;
        add_option(runtime, kSelectOptionYes);
        add_option(runtime, kSelectOptionNo);
        push_continuation(runtime, kContinuationSelectedMulligan);
        if (runtime->continuation_count > 0) {
            runtime->continuations[runtime->continuation_count - 1].arg_type = 1;
            runtime->continuations[runtime->continuation_count - 1].arg0 = player_index;
        }
        return;
    }
    state->mulligan[player_index] = 1;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_pre_setup_active(
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
    gpu_cabt::pre_setup_active_pokemon(
        state, runtime, card_table, card_table_size, player_index
    );
}

extern "C" __global__ void gpu_cabt_force_setup_doll_hand(
    unsigned char* raw_states,
    const gc_i32* player_indices,
    gc_i32 doll_card_id,
    gc_i32 filler_card_id,
    gc_i32 case_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= case_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const gc_i32 player_index = player_indices[env_index];
    auto& hand = state->players[player_index].hand;
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        const gc_u8 ref = hand.values[index];
        state->all_card[ref].card_id = index == 0 ? doll_card_id : filler_card_id;
    }
}

static constexpr gc_i32 kPreSetupSnapshotSize = 20;

extern "C" __global__ void gpu_cabt_pre_setup_active_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kPreSetupSnapshotSize;
    const gc_i32 player_index = player_indices[env_index];
    row[0] = player_index;
    row[1] = (gc_i32)state->mulligan[0];
    row[2] = (gc_i32)state->mulligan[1];
    row[3] = (gc_i32)state->select_type;
    row[4] = (gc_i32)state->select_context;
    row[5] = (gc_i32)state->select_player;
    row[6] = state->select_min;
    row[7] = state->select_max;
    row[8] = (gc_i32)runtime->option_count;
    row[9] = runtime->option_count > 0 ? (gc_i32)runtime->options[0].type : -1;
    row[10] = runtime->option_count > 1 ? (gc_i32)runtime->options[1].type : -1;
    row[11] = (gc_i32)runtime->continuation_count;
    row[12] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[13] = runtime->continuation_count > 0
        ? runtime->continuations[runtime->continuation_count - 1].arg0 : -1;
    row[14] = (gc_i32)runtime->error_flags;
    row[15] = (gc_i32)state->players[player_index].hand.count;
    row[16] = (gc_i32)state->players[player_index].deck.count;
    row[17] = (gc_i32)state->first_player;
    row[18] = state->move_counter;
    row[19] = (gc_i32)state->changed;
}
