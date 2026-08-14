namespace gpu_cabt {

static constexpr gc_u32 kCardTurnStateAppear = 1u << 24;

__device__ __forceinline__ void consume_selected_setup_active(
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    if (runtime->continuation_count == 0) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const ContinuationState* top = &runtime->continuations[runtime->continuation_count - 1];
    if (top->opcode != kContinuationSelectedSetupActivePokemon || top->arg0 != player_index) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    runtime->continuation_count--;
}

__device__ __forceinline__ gc_u8 move_hand_to_active(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_i32 hand_index
) {
    auto& player = state->players[player_index];
    if (hand_index < 0 || hand_index >= (gc_i32)player.hand.count) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    if (player.active.count >= 1) {
        runtime->error_flags |= kRuntimeErrorZoneOverflow;
        return 0;
    }
    const gc_u8 ref = player.hand.values[hand_index];
    for (gc_i32 index = hand_index; index + 1 < (gc_i32)player.hand.count; ++index) {
        player.hand.values[index] = player.hand.values[index + 1];
    }
    player.hand.count--;
    player.active.values[player.active.count++] = ref;

    CardState* card = &state->all_card[ref];
    if (card->area != kAreaHand) {
        runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
        return 0;
    }
    const gc_u8 pre_area = card->area;
    clear_card_state(card);
    card->move_counter = state->move_counter++;
    card->turn_state[1] |= kCardTurnStateAppear;
    card->area = kAreaActive;
    card->pre_area = pre_area;
    card->reverse = 1;
    card->attach_move_counter = 0;
    return ref;
}

__device__ __forceinline__ void resolve_selected_setup_active(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_i32 selected_index
) {
    if (selected_index < 0 || selected_index >= (gc_i32)runtime->option_count) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const SelectOptionState option = runtime->options[selected_index];
    if (
        option.type != kSelectOptionCard || option.param0 != (gc_i16)kAreaHand
        || option.param2 != (gc_i16)player_index
    ) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    clear_select_after_choice(state, runtime);
    const gc_u8 ref = move_hand_to_active(
        state, runtime, player_index, (gc_i32)option.param1
    );
    if (runtime->error_flags != 0 || ref == 0) return;
    state->setup_done[player_index] = 1;
    consume_selected_setup_active(runtime, player_index);
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_selected_setup_active(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* player_indices,
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
    const gc_i32 player_index = player_indices[env_index];
    if (player_index < 0 || player_index > 1) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }
    gpu_cabt::resolve_selected_setup_active(
        state, runtime, player_index, selected_indices[env_index]
    );
}

extern "C" __global__ void gpu_cabt_force_basic_candidates(
    unsigned char* raw_states,
    const gc_i32* player_indices,
    gc_i32 basic0,
    gc_i32 basic1,
    gc_i32 basic2,
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
    const gc_i32 basics[3] = {basic0, basic1, basic2};
    for (gc_i32 index = 0; index < (gc_i32)hand.count; ++index) {
        state->all_card[hand.values[index]].card_id = index < 3 ? basics[index] : filler_card_id;
    }
}

static constexpr gc_i32 kSelectedSetupActiveSnapshotSize = 47;

extern "C" __global__ void gpu_cabt_selected_setup_active_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kSelectedSetupActiveSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = (gc_i32)state->setup_done[0];
    row[cursor++] = (gc_i32)state->setup_done[1];
    row[cursor++] = (gc_i32)state->mulligan[0];
    row[cursor++] = (gc_i32)state->mulligan[1];
    row[cursor++] = (gc_i32)state->select_type;
    row[cursor++] = (gc_i32)state->select_context;
    row[cursor++] = (gc_i32)state->select_player;
    row[cursor++] = state->select_min;
    row[cursor++] = state->select_max;
    row[cursor++] = (gc_i32)runtime->option_count;
    row[cursor++] = (gc_i32)runtime->selected_count;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.active.count;
    row[cursor++] = player.active.count > 0 ? (gc_i32)player.active.values[0] : 0;
    for (gc_i32 index = 0; index < 6; ++index) {
        row[cursor++] = index < (gc_i32)player.hand.count ? (gc_i32)player.hand.values[index] : -1;
    }
    const gc_u8 active_ref = player.active.count > 0 ? player.active.values[0] : 0;
    const auto& card = state->all_card[active_ref];
    row[cursor++] = card.card_id;
    row[cursor++] = card.move_counter;
    row[cursor++] = card.attach_move_counter;
    row[cursor++] = card.skill_order;
    row[cursor++] = card.damage;
    row[cursor++] = (gc_i32)card.player_index;
    row[cursor++] = (gc_i32)card.area;
    row[cursor++] = (gc_i32)card.pre_area;
    row[cursor++] = (gc_i32)card.reverse;
    row[cursor++] = (gc_i32)card.ability_used.count;
    row[cursor++] = (gc_i32)card.next_enemy_turn_end_state_battle_field;
    row[cursor++] = (gc_i32)card.next_enemy_turn_end_state;
    row[cursor++] = (gc_i32)card.turn_state[0];
    row[cursor++] = (gc_i32)card.turn_state[1];
    row[cursor++] = (gc_i32)card.turn_state[2];
    row[cursor++] = (gc_i32)card.continual_state[0];
    row[cursor++] = (gc_i32)card.continual_state[1];
    row[cursor++] = (gc_i32)card.continual_state[2];
    row[cursor++] = (gc_i32)card.continual_state[3];
    row[cursor++] = (gc_i32)card.continual_state[4];
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    if (cursor != kSelectedSetupActiveSnapshotSize) row[0] = -999999;
}
