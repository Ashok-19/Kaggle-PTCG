namespace gpu_cabt {

__device__ __forceinline__ gc_u8 move_last_hand_to_deck(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    auto& player = state->players[player_index];
    if (player.hand.count == 0) return 0;
    if (player.deck.count >= kCardListCapacity) {
        runtime->error_flags |= kRuntimeErrorZoneOverflow;
        return 0;
    }
    const gc_i32 hand_index = (gc_i32)player.hand.count - 1;
    const gc_u8 ref = player.hand.values[hand_index];
    player.hand.count--;
    player.deck.values[player.deck.count++] = ref;
    card_moved_non_field(state, runtime, ref, kAreaDeck, 0);
    return ref;
}

__device__ __forceinline__ void open_return_and_shuffle(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_u64 seed,
    gc_u64 stream
) {
    auto& player = state->players[player_index];
    while (player.hand.count > 0) {
        move_last_hand_to_deck(state, runtime, player_index);
        if (runtime->error_flags != 0) return;
    }
    if (player.deck.count > 0) {
        state->changed = 1;
        shuffle_deck_refs(&player.deck, seed, stream, &runtime->rng_draw_index);
    }
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_open_return_shuffle(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
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
    gpu_cabt::open_return_and_shuffle(
        state, runtime, player_index, seed, stream_base + (gc_u64)env_index
    );
}

static constexpr gc_i32 kOpenReturnSnapshotSize = 119;

extern "C" __global__ void gpu_cabt_open_return_shuffle_snapshot(
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
    gc_i32* row = output + (gc_i64)env_index * kOpenReturnSnapshotSize;
    gc_i32 cursor = 0;
    row[cursor++] = player_index;
    row[cursor++] = (gc_i32)player.hand.count;
    row[cursor++] = (gc_i32)player.deck.count;
    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = (gc_i32)(runtime->rng_draw_index & 0xffffffffull);
    row[cursor++] = (gc_i32)(runtime->rng_draw_index >> 32);
    for (gc_i32 index = 0; index < 60; ++index) row[cursor++] = (gc_i32)player.deck.values[index];

    gc_i32 moved_count = 0;
    for (gc_i32 ref = 1; ref < gpu_cabt::kAllCardCapacity && moved_count < 7; ++ref) {
        const auto& card = state->all_card[ref];
        if (
            card.player_index == player_index && card.area == gpu_cabt::kAreaDeck
            && card.pre_area == gpu_cabt::kAreaHand
        ) {
            row[cursor++] = ref;
            row[cursor++] = card.card_id;
            row[cursor++] = card.move_counter;
            row[cursor++] = (gc_i32)card.area;
            row[cursor++] = (gc_i32)card.pre_area;
            row[cursor++] = (gc_i32)card.reverse;
            row[cursor++] = card.attach_move_counter;
            moved_count++;
        }
    }
    row[cursor++] = moved_count;
    row[cursor++] = (gc_i32)state->first_player;
    if (cursor != kOpenReturnSnapshotSize) row[0] = -999999;
}
