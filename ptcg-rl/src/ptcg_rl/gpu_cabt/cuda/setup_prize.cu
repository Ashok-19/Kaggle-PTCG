namespace gpu_cabt {

__device__ __forceinline__ gc_u8 move_last_deck_to_prize(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    auto& player = state->players[player_index];
    if (player.deck.count == 0) return 0;
    if (player.prize.count >= kCardListCapacity) {
        runtime->error_flags |= kRuntimeErrorZoneOverflow;
        return 0;
    }
    const gc_i32 deck_index = (gc_i32)player.deck.count - 1;
    const gc_u8 ref = player.deck.values[deck_index];
    player.deck.count--;
    player.prize.values[player.prize.count++] = ref;
    card_moved_non_field(state, runtime, ref, kAreaPrize, 1);
    return ref;
}

__device__ __forceinline__ void setup_prize(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    for (gc_i32 index = 0; index < 6; ++index) {
        if (state->players[player_index].deck.count == 0) break;
        move_last_deck_to_prize(state, runtime, player_index);
        if (runtime->error_flags != 0) return;
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_setup_prize(
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
    gpu_cabt::setup_prize(state, runtime, player_index);
}

static constexpr gc_i32 kSetupPrizeSnapshotSize = 70;

extern "C" __global__ void gpu_cabt_setup_prize_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kSetupPrizeSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = (gc_i32)player.deck.count;
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.active.count;
    row[cursor++] = (gc_i32)player.prize.count;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = (gc_i32)state->setup_done[player_index];
    for (gc_i32 index = 0; index < 6; ++index) {
        const gc_u8 ref = player.prize.values[index];
        const auto& card = state->all_card[ref];
        row[cursor++] = (gc_i32)ref;
        row[cursor++] = card.card_id;
        row[cursor++] = card.move_counter;
        row[cursor++] = card.attach_move_counter;
        row[cursor++] = card.skill_order;
        row[cursor++] = card.damage;
        row[cursor++] = (gc_i32)card.player_index;
        row[cursor++] = (gc_i32)card.area;
        row[cursor++] = (gc_i32)card.pre_area;
        row[cursor++] = (gc_i32)card.reverse;
    }
    row[cursor++] = (gc_i32)state->first_player;
    if (cursor != kSetupPrizeSnapshotSize) row[0] = -999999;
}
