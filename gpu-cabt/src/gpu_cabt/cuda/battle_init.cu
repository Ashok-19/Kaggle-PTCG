namespace gpu_cabt {

__device__ __forceinline__ void zero_core_state(BattleCoreState* state) {
    gc_u8* bytes = reinterpret_cast<gc_u8*>(state);
    for (gc_i32 offset = 0; offset < (gc_i32)sizeof(BattleCoreState); ++offset) {
        bytes[offset] = 0;
    }
}

__device__ __forceinline__ void init_card(
    CardState* card,
    gc_i32 card_id,
    gc_i32 move_counter,
    gc_i8 player_index,
    gc_u8 area
) {
    card->card_id = card_id;
    card->move_counter = move_counter;
    card->player_index = player_index;
    card->area = area;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_battle_core_size(gc_u64* output) {
    if (blockIdx.x == 0 && threadIdx.x == 0) {
        output[0] = sizeof(gpu_cabt::BattleCoreState);
    }
}

extern "C" __global__ void gpu_cabt_init_battles(
    unsigned char* raw_states,
    const gc_i32* decks,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;

    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    gpu_cabt::zero_core_state(state);

    state->move_counter = 1;
    state->first_player = -1;

    // all_card[0] is deliberately left as the null card reference.
    for (gc_i32 player = 0; player < 2; ++player) {
        const gc_i32 card_index = 1 + player;
        gpu_cabt::init_card(
            &state->all_card[card_index],
            0,
            state->move_counter++,
            (gc_i8)player,
            gpu_cabt::kAreaPlayer
        );
    }

    gc_i32 card_index = 3;
    const gc_i32* env_decks = decks + (gc_i64)env_index * 2 * gpu_cabt::kDeckSize;
    for (gc_i32 player = 0; player < 2; ++player) {
        auto& player_state = state->players[player];
        player_state.player_index = (gc_i8)player;
        player_state.deck.count = (gc_u8)gpu_cabt::kDeckSize;
        const gc_i32* deck = env_decks + player * gpu_cabt::kDeckSize;
        for (gc_i32 input_index = 0; input_index < gpu_cabt::kDeckSize; ++input_index) {
            const gc_i32 index = card_index++;
            gpu_cabt::init_card(
                &state->all_card[index],
                deck[input_index],
                state->move_counter++,
                (gc_i8)player,
                gpu_cabt::kAreaDeck
            );
            player_state.deck.values[gpu_cabt::kDeckSize - input_index - 1] = (gc_u8)index;
        }
    }
}

static constexpr gc_i32 kInitSnapshotSize = 625;

extern "C" __global__ void gpu_cabt_init_snapshot(
    const unsigned char* raw_states,
    gc_i32* output,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto* state = reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    gc_i32* row = output + (gc_i64)env_index * kInitSnapshotSize;
    gc_i32 cursor = 0;

    row[cursor++] = state->move_counter;
    row[cursor++] = (gc_i32)state->first_player;
    row[cursor++] = state->turn;
    row[cursor++] = state->turn_action_count;
    row[cursor++] = state->effect_action_count;
    row[cursor++] = state->turn_attack_count;
    row[cursor++] = (gc_i32)state->phase;
    row[cursor++] = (gc_i32)state->game_result;
    row[cursor++] = (gc_i32)state->finish_reason;
    row[cursor++] = (gc_i32)state->players[0].player_index;
    row[cursor++] = (gc_i32)state->players[1].player_index;
    row[cursor++] = (gc_i32)state->players[0].deck.count;
    row[cursor++] = (gc_i32)state->players[1].deck.count;

    for (gc_i32 player = 0; player < 2; ++player) {
        for (gc_i32 index = 0; index < gpu_cabt::kDeckSize; ++index) {
            row[cursor++] = (gc_i32)state->players[player].deck.values[index];
        }
    }

    for (gc_i32 index = 0; index <= 122; ++index) {
        const auto& card = state->all_card[index];
        row[cursor++] = card.card_id;
        row[cursor++] = card.move_counter;
        row[cursor++] = (gc_i32)card.player_index;
        row[cursor++] = (gc_i32)card.area;
    }
}
