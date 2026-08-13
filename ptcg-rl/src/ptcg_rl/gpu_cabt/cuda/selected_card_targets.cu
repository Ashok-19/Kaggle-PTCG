namespace gpu_cabt {

__device__ __forceinline__ gc_u8 option_card_ref(
    const BattleCoreState* state,
    BattleRuntimeState* runtime,
    const SelectOptionState& option
) {
    if (option.type != kSelectOptionCard) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    const gc_i32 player_index = option.param2;
    if (player_index < 0 || player_index > 1) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    if (option.param0 == (gc_i16)kAreaHand) {
        const auto& hand = state->players[player_index].hand;
        const gc_i32 hand_index = option.param1;
        if (hand_index < 0 || hand_index >= (gc_i32)hand.count) {
            runtime->error_flags |= kRuntimeErrorInvalidSelection;
            return 0;
        }
        return hand.values[hand_index];
    }
    runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
    return 0;
}

__device__ __forceinline__ void set_selected_card_targets(
    BattleCoreState* state,
    BattleRuntimeState* runtime
) {
    runtime->target_count = 0;
    for (gc_i32 selected_pos = 0; selected_pos < (gc_i32)runtime->selected_count; ++selected_pos) {
        const gc_i32 option_index = runtime->selected[selected_pos];
        if (option_index < 0 || option_index >= (gc_i32)runtime->option_count) {
            runtime->error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        if (runtime->target_count >= kTargetCapacity) {
            runtime->error_flags |= kRuntimeErrorTargetOverflow;
            return;
        }
        const SelectOptionState& option = runtime->options[option_index];
        const gc_u8 ref = option_card_ref(state, runtime, option);
        if (runtime->error_flags != 0 || ref == 0) return;
        AreaRefState& target = runtime->targets[runtime->target_count++];
        target.card = ref;
        target.reserved0 = 0;
        target.reserved1 = 0;
        target.move_counter = state->all_card[ref].move_counter;
    }
    clear_select_after_choice(state, runtime);
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_capture_selected_card_targets(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
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
    const gc_i32 count = selected_counts[env_index];
    if (count < 0 || count > selected_stride || count > gpu_cabt::kSelectedCapacity) {
        runtime->error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
        return;
    }
    runtime->selected_count = (gc_u16)count;
    for (gc_i32 index = 0; index < count; ++index) {
        runtime->selected[index] = selected_indices[(gc_i64)env_index * selected_stride + index];
    }
    gpu_cabt::set_selected_card_targets(state, runtime);
}

static constexpr gc_i32 kSelectedTargetSnapshotSize = 48;

extern "C" __global__ void gpu_cabt_selected_card_targets_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kSelectedTargetSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = (gc_i32)runtime->target_count;
    row[cursor++] = (gc_i32)runtime->option_count;
    row[cursor++] = (gc_i32)runtime->selected_count;
    row[cursor++] = (gc_i32)state->select_type;
    row[cursor++] = (gc_i32)state->select_context;
    row[cursor++] = (gc_i32)state->select_player;
    row[cursor++] = state->select_min;
    row[cursor++] = state->select_max;
    row[cursor++] = (gc_i32)state->context_card;
    row[cursor++] = (gc_i32)state->select_deck;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[cursor++] = (gc_i32)runtime->error_flags;
    for (gc_i32 index = 0; index < 8; ++index) {
        if (index < (gc_i32)runtime->target_count) {
            const auto& target = runtime->targets[index];
            row[cursor++] = (gc_i32)target.card;
            row[cursor++] = target.move_counter;
            row[cursor++] = state->all_card[target.card].card_id;
            row[cursor++] = (gc_i32)state->all_card[target.card].area;
        } else {
            for (gc_i32 field = 0; field < 4; ++field) row[cursor++] = -1;
        }
    }
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = (gc_i32)state->first_player;
    if (cursor != kSelectedTargetSnapshotSize) row[0] = -999999;
}
