namespace gpu_cabt {

static constexpr gc_u8 kSelectTypeCard = 2;
static constexpr gc_u8 kSelectContextSetupActivePokemon = 2;
static constexpr gc_u8 kSelectOptionCard = 3;

__device__ __forceinline__ void add_setup_active_card_option(
    BattleRuntimeState* runtime,
    gc_i32 hand_index,
    gc_i32 player_index
) {
    if (runtime->option_count >= kOptionCapacity) {
        runtime->error_flags |= kRuntimeErrorOptionOverflow;
        return;
    }
    SelectOptionState* option = &runtime->options[runtime->option_count++];
    gc_u8* bytes = reinterpret_cast<gc_u8*>(option);
    #pragma unroll
    for (gc_i32 index = 0; index < (gc_i32)sizeof(SelectOptionState); ++index) bytes[index] = 0;
    option->type = kSelectOptionCard;
    option->param0 = (gc_i16)kAreaHand;
    option->param1 = (gc_i16)hand_index;
    option->param2 = (gc_i16)player_index;
}

__device__ __forceinline__ void setup_active_pokemon(
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
    if (!flags.has_basic && !flags.has_doll) state->mulligan[player_index] = 1;

    if (state->mulligan[player_index]) {
        bool no_basic_deck = true;
        const auto& deck = state->players[player_index].deck;
        for (gc_i32 index = 0; index < (gc_i32)deck.count; ++index) {
            const gc_u8 ref = deck.values[index];
            const gc_i32 card_id = state->all_card[ref].card_id;
            if (card_id < 0 || card_id >= card_table_size) {
                runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
                return;
            }
            if (card_table[card_id].is_basic_pokemon != 0) {
                no_basic_deck = false;
                break;
            }
        }
        if (no_basic_deck && !flags.has_basic) {
            runtime->error_flags |= kRuntimeErrorNoBasicPokemon;
        }
        return;
    }

    state->select_type = kSelectTypeCard;
    state->select_context = kSelectContextSetupActivePokemon;
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
        if (card_table[card_id].can_setup_active != 0) {
            add_setup_active_card_option(runtime, index, player_index);
            if (runtime->error_flags != 0) return;
        }
    }
    push_continuation(runtime, kContinuationSelectedSetupActivePokemon);
    if (runtime->continuation_count > 0) {
        runtime->continuations[runtime->continuation_count - 1].arg_type = 1;
        runtime->continuations[runtime->continuation_count - 1].arg0 = player_index;
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_setup_active(
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
    gpu_cabt::setup_active_pokemon(
        state, runtime, card_table, card_table_size, player_index
    );
}

extern "C" __global__ void gpu_cabt_force_no_basic_player(
    unsigned char* raw_states,
    const gc_i32* player_indices,
    gc_i32 filler_card_id,
    gc_i32 start_index,
    gc_i32 case_count
) {
    const gc_i32 local_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (local_index >= case_count) return;
    const gc_i32 env_index = start_index + local_index;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const gc_i32 player_index = player_indices[env_index];
    auto& hand = state->players[player_index].hand;
    auto& deck = state->players[player_index].deck;
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        state->all_card[hand.values[index]].card_id = filler_card_id;
    }
    for (gc_i32 index = 0; index < (gc_i32)deck.count; ++index) {
        state->all_card[deck.values[index]].card_id = filler_card_id;
    }
}

static constexpr gc_i32 kSetupActiveSnapshotSize = 60;

extern "C" __global__ void gpu_cabt_setup_active_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kSetupActiveSnapshotSize;
    row[0] = player_index;
    row[1] = (gc_i32)state->mulligan[0];
    row[2] = (gc_i32)state->mulligan[1];
    row[3] = (gc_i32)state->select_type;
    row[4] = (gc_i32)state->select_context;
    row[5] = (gc_i32)state->select_player;
    row[6] = state->select_min;
    row[7] = state->select_max;
    row[8] = (gc_i32)runtime->option_count;
    row[9] = (gc_i32)runtime->continuation_count;
    row[10] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[11] = runtime->continuation_count > 0
        ? runtime->continuations[runtime->continuation_count - 1].arg0 : 0;
    row[12] = (gc_i32)runtime->error_flags;
    row[13] = (gc_i32)state->players[player_index].hand.count;
    row[14] = (gc_i32)state->players[player_index].deck.count;
    gc_i32 cursor = 15;
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
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    if (cursor != kSetupActiveSnapshotSize) row[0] = -999999;
}
