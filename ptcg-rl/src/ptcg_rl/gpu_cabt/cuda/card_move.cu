namespace gpu_cabt {

__device__ __forceinline__ void clear_card_state(CardState* card) {
    card->next_enemy_turn_end_state_battle_field = 0;
    #pragma unroll
    for (gc_i32 index = 0; index < 3; ++index) card->turn_state[index] = 0;
    card->ability_used.count = 0;
    #pragma unroll
    for (gc_i32 index = 0; index < 5; ++index) card->continual_state[index] = 0;
    card->damage = 0;
    card->skill_order = 0;
    card->take_attack_damage_this_turn = 0;
    card->take_attack_damage_pre_turn = 0;
}

__device__ __forceinline__ void clear_card_next_turn_state(CardState* card) {
    #pragma unroll
    for (gc_i32 index = 0; index < 4; ++index) {
        card->this_turn[index] = 0;
        card->next_turn[index] = 0;
    }
    card->this_turn_enemy[0] = 0;
    card->next_turn_enemy[0] = 0;
    card->next_enemy_turn_end_state = 0;
}

__device__ __forceinline__ void card_moved_non_field(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_u8 ref,
    gc_u8 new_area,
    gc_u8 reverse
) {
    CardState* card = &state->all_card[ref];
    if (card->area == new_area) return;
    const gc_u8 pre_area = card->area;
    if (pre_area == 4 || pre_area == 5 || new_area == 4 || new_area == 5) {
        runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }

    clear_card_state(card);
    card->move_counter = state->move_counter++;
    clear_card_next_turn_state(card);
    card->cannot_use_attack_id_non_active = 0;
    card->area = new_area;
    card->pre_area = pre_area;
    card->reverse = reverse;
    card->attach_move_counter = 0;
}

__device__ __forceinline__ gc_u8 move_last_deck_to_hand(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index
) {
    PlayerState* player = &state->players[player_index];
    if (player->deck.count == 0) return 0;
    if (player->hand.count >= kCardListCapacity) {
        runtime->error_flags |= kRuntimeErrorZoneOverflow;
        return 0;
    }
    const gc_i32 deck_index = (gc_i32)player->deck.count - 1;
    const gc_u8 ref = player->deck.values[deck_index];
    player->deck.count--;
    player->hand.values[player->hand.count++] = ref;
    card_moved_non_field(state, runtime, ref, kAreaHand, 0);
    return ref;
}

__device__ __forceinline__ void draw_cards(
    BattleCoreState* state,
    BattleRuntimeState* runtime,
    gc_i32 player_index,
    gc_i32 count
) {
    for (gc_i32 index = 0; index < count; ++index) {
        if (state->players[player_index].deck.count == 0) break;
        state->changed = 1;
        move_last_deck_to_hand(state, runtime, player_index);
        if (runtime->error_flags != 0) return;
    }
}

}  // namespace gpu_cabt
