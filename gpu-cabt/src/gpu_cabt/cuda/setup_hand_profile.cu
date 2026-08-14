extern "C" __global__ void gpu_cabt_setup_hand_profile(
    const unsigned char* raw_states,
    const gpu_cabt::SetupCardStatic* card_table,
    gc_i32 card_table_size,
    gc_i32* output,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto* state = reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    gc_i32* row = output + (gc_i64)env_index * 10;

    for (gc_i32 player = 0; player < 2; ++player) {
        const auto& ps = state->players[player];
        gc_i32 has_basic = 0;
        gc_i32 has_doll = 0;
        gc_i32 active_count = 0;
        gc_i32 active_mask = 0;
        gc_i32 deck_basic_count = 0;
        bool invalid = false;

        for (gc_i32 index = 0; index < (gc_i32)ps.hand.count; ++index) {
            const gc_u8 ref = ps.hand.values[index];
            const gc_i32 card_id = state->all_card[ref].card_id;
            if (card_id < 0 || card_id >= card_table_size) {
                invalid = true;
                break;
            }
            const auto& meta = card_table[card_id];
            has_basic |= meta.is_basic_pokemon != 0;
            has_doll |= meta.is_setup_doll != 0;
            if (meta.can_setup_active != 0) {
                active_count++;
                if (index < 31) active_mask |= 1 << index;
            }
        }
        if (!invalid) {
            for (gc_i32 index = 0; index < (gc_i32)ps.deck.count; ++index) {
                const gc_u8 ref = ps.deck.values[index];
                const gc_i32 card_id = state->all_card[ref].card_id;
                if (card_id < 0 || card_id >= card_table_size) {
                    invalid = true;
                    break;
                }
                deck_basic_count += card_table[card_id].is_basic_pokemon != 0;
            }
        }

        const gc_i32 base = player * 5;
        if (invalid) {
            for (gc_i32 i = 0; i < 5; ++i) row[base + i] = -1;
        } else {
            row[base + 0] = has_basic;
            row[base + 1] = has_doll;
            row[base + 2] = active_count;
            row[base + 3] = active_mask;
            row[base + 4] = deck_basic_count;
        }
    }
}
