namespace gpu_cabt {

__device__ __forceinline__ void consume_selected_mulligan(
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    if (runtime->continuation_count == 0) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const ContinuationState* top = &runtime->continuations[runtime->continuation_count - 1];
    if (top->opcode != kContinuationSelectedMulligan || top->arg0 != player_index) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    runtime->continuation_count--;
}

__device__ __forceinline__ void resolve_selected_mulligan(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_i32 selected_index
) {
    if (selected_index < 0 || selected_index >= (gc_i32)runtime->option_count) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 selected_type = runtime->options[selected_index].type;
    if (selected_type != kSelectOptionYes && selected_type != kSelectOptionNo) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    state->mulligan[player_index] = selected_type == kSelectOptionYes ? 1 : 0;
    clear_select_after_choice(state, runtime);
    consume_selected_mulligan(runtime, player_index);
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_selected_mulligan(
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
    gpu_cabt::resolve_selected_mulligan(
        state, runtime, player_index, selected_indices[env_index]
    );
}

static constexpr gc_i32 kSelectedMulliganSnapshotSize = 17;

extern "C" __global__ void gpu_cabt_selected_mulligan_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kSelectedMulliganSnapshotSize;
    row[0] = player_index;
    row[1] = (gc_i32)state->mulligan[0];
    row[2] = (gc_i32)state->mulligan[1];
    row[3] = (gc_i32)state->select_type;
    row[4] = (gc_i32)state->select_context;
    row[5] = (gc_i32)state->select_player;
    row[6] = state->select_min;
    row[7] = state->select_max;
    row[8] = (gc_i32)runtime->option_count;
    row[9] = (gc_i32)runtime->selected_count;
    row[10] = (gc_i32)runtime->continuation_count;
    row[11] = runtime->continuation_count > 0
        ? (gc_i32)runtime->continuations[runtime->continuation_count - 1].opcode : 0;
    row[12] = (gc_i32)runtime->error_flags;
    row[13] = (gc_i32)state->players[player_index].hand.count;
    row[14] = (gc_i32)state->players[player_index].deck.count;
    row[15] = state->move_counter;
    row[16] = (gc_i32)state->changed;
}
