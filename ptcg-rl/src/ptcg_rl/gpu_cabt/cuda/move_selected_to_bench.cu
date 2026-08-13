namespace gpu_cabt {

static constexpr gc_u32 kBenchCardTurnStateAppear = 1u << 24;

__device__ __forceinline__ gc_i32 current_hand_index(
    const PlayerState& player,
    gc_u8 ref
) {
    for (gc_i32 index = 0; index < (gc_i32)player.hand.count; ++index) {
        if (player.hand.values[index] == ref) return index;
    }
    return -1;
}

__device__ __forceinline__ gc_u8 move_hand_ref_to_bench(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_u8 ref
) {
    auto& player = state->players[player_index];
    const gc_i32 hand_index = current_hand_index(player, ref);
    if (hand_index < 0) {
        runtime->error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    if (player.bench.count >= kBenchSizeMax) {
        runtime->error_flags |= kRuntimeErrorZoneOverflow;
        return 0;
    }
    for (gc_i32 index = hand_index; index + 1 < (gc_i32)player.hand.count; ++index) {
        player.hand.values[index] = player.hand.values[index + 1];
    }
    player.hand.count--;
    player.bench.values[player.bench.count++] = ref;

    CardState* card = &state->all_card[ref];
    if (card->area != kAreaHand) {
        runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
        return 0;
    }
    const gc_u8 pre_area = card->area;
    clear_card_state(card);
    card->move_counter = state->move_counter++;
    card->turn_state[1] |= kBenchCardTurnStateAppear;
    card->area = kAreaBench;
    card->pre_area = pre_area;
    card->reverse = 1;
    card->attach_move_counter = 0;
    return ref;
}

__device__ __forceinline__ void move_selected_targets_to_bench(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    for (gc_i32 index = 0; index < (gc_i32)runtime->target_count; ++index) {
        const gc_u8 ref = runtime->targets[index].card;
        if (move_hand_ref_to_bench(state, runtime, player_index, ref) == 0) return;
        if (runtime->error_flags != 0) return;
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_move_selected_to_bench(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
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
    gpu_cabt::move_selected_targets_to_bench(state, runtime, player_index);
}

static constexpr gc_i32 kMoveSelectedBenchSnapshotSize = 127;

extern "C" __global__ void gpu_cabt_move_selected_to_bench_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kMoveSelectedBenchSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.bench.count;
    row[cursor++] = (gc_i32)runtime->target_count;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    for (gc_i32 index = 0; index < 7; ++index) {
        row[cursor++] = index < (gc_i32)player.hand.count
            ? (gc_i32)player.hand.values[index] : -1;
    }
    for (gc_i32 index = 0; index < 8; ++index) {
        row[cursor++] = index < (gc_i32)player.bench.count
            ? (gc_i32)player.bench.values[index] : -1;
    }
    for (gc_i32 index = 0; index < 8; ++index) {
        if (index < (gc_i32)runtime->target_count) {
            const auto& target = runtime->targets[index];
            const auto& card = state->all_card[target.card];
            row[cursor++] = (gc_i32)target.card;
            row[cursor++] = target.move_counter;
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
            row[cursor++] = (gc_i32)card.turn_state[1];
        } else {
            for (gc_i32 field = 0; field < 13; ++field) row[cursor++] = -1;
        }
    }
    row[cursor++] = (gc_i32)state->first_player;
    if (cursor != kMoveSelectedBenchSnapshotSize) row[0] = -999999;
}
