namespace gpu_cabt {

__device__ __forceinline__ void clear_select_after_choice(
    BattleCoreState* state,
    BattleRuntimeState* runtime
) {
    state->select_type = 0;
    runtime->option_count = 0;
    runtime->selected_count = 0;
    state->context_card = 0;
    state->select_deck = 0;
}

__device__ __forceinline__ void consume_selected_is_first(
    BattleRuntimeState* runtime
) {
    if (runtime->continuation_count == 0) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    ContinuationState* top = &runtime->continuations[runtime->continuation_count - 1];
    if (top->opcode != kContinuationSelectedIsFirst) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    runtime->continuation_count--;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_opening_draw_after_is_first(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* selected_indices,
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

    const gc_i32 selected_index = selected_indices[env_index];
    if (selected_index < 0 || selected_index >= (gc_i32)runtime->option_count) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 selected_type = runtime->options[selected_index].type;
    if (selected_type != gpu_cabt::kSelectOptionYes && selected_type != gpu_cabt::kSelectOptionNo) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }

    state->first_player = selected_type == gpu_cabt::kSelectOptionYes
        ? state->select_player
        : (gc_i8)(1 - state->select_player);
    gpu_cabt::clear_select_after_choice(state, runtime);
    gpu_cabt::consume_selected_is_first(runtime);
    if (runtime->error_flags != 0) return;

    gpu_cabt::draw_cards(state, runtime, state->first_player, 7);
    gpu_cabt::draw_cards(state, runtime, 1 - state->first_player, 7);
    if (runtime->error_flags == 0) {
        gpu_cabt::push_continuation(runtime, gpu_cabt::kContinuationAfterOpeningDraw);
    }
}

static constexpr gc_i32 kOpeningDrawSnapshotSize = 249;

extern "C" __global__ void gpu_cabt_opening_draw_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kOpeningDrawSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->select_type;
    row[cursor++] = (gc_i32)state->select_context;
    row[cursor++] = (gc_i32)state->select_player;
    row[cursor++] = state->select_min;
    row[cursor++] = state->select_max;
    row[cursor++] = (gc_i32)runtime->option_count;
    row[cursor++] = (gc_i32)runtime->selected_count;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[cursor++] = (gc_i32)state->players[0].deck.count;
    row[cursor++] = (gc_i32)state->players[0].hand.count;
    row[cursor++] = (gc_i32)state->players[1].deck.count;
    row[cursor++] = (gc_i32)state->players[1].hand.count;

    for (gc_i32 player = 0; player < 2; ++player) {
        const auto& ps = state->players[player];
        for (gc_i32 index = 0; index < 53; ++index) row[cursor++] = (gc_i32)ps.deck.values[index];
        for (gc_i32 index = 0; index < 7; ++index) row[cursor++] = (gc_i32)ps.hand.values[index];
    }
    for (gc_i32 player = 0; player < 2; ++player) {
        const auto& hand = state->players[player].hand;
        for (gc_i32 index = 0; index < 7; ++index) {
            const gc_u8 ref = hand.values[index];
            const auto& card = state->all_card[ref];
            row[cursor++] = (gc_i32)ref;
            row[cursor++] = card.card_id;
            row[cursor++] = card.move_counter;
            row[cursor++] = (gc_i32)card.player_index;
            row[cursor++] = (gc_i32)card.area;
            row[cursor++] = (gc_i32)card.pre_area;
            row[cursor++] = (gc_i32)card.reverse;
            row[cursor++] = card.attach_move_counter;
        }
    }
    if (cursor != kOpeningDrawSnapshotSize) row[0] = -999999;
}
