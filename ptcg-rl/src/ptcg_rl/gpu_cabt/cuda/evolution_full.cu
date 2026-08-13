namespace gpu_cabt {

__device__ __forceinline__ bool find_field_position(
    const BattleCoreState& state,
    gc_u8 ref,
    gc_i32& player_index,
    gc_u8& area,
    gc_i32& index
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    player_index = card.player_index; area = card.area;
    if (player_index < 0 || player_index > 1) return false;
    index = current_area_index(state.players[player_index], area, ref);
    return index >= 0;
}

__device__ __forceinline__ bool after_confuse_evolve(
    const BattleCoreState& state,
    const CardState& card
) {
    if (card.player_index < 0 || card.player_index > 1) return false;
    return player_active_state(state.players[card.player_index]).fields.bad_status == 3
        && card_continual(card).fields.not_recover_confuse_evolve;
}

__device__ __forceinline__ void clear_special_condition_full(PlayerState& player) {
    player.active_state = 0;
}

__device__ __noinline__ void devolve_ref_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 current_ref,
    gc_u8 to_area
) {
    if (current_ref == 0 || current_ref >= kAllCardCapacity) return;
    CardState& current = state.all_card[current_ref];
    const gc_i32 p = current.player_index;
    if (p < 0 || p > 1 || (current.area != kAreaActive && current.area != kAreaBench)) return;
    PlayerState& player = state.players[p];
    const gc_u8 field_area = current.area;
    const gc_i32 field_index = current_area_index(player, field_area, current_ref);
    if (field_index < 0) return;

    for (gc_i32 i = (gc_i32)player.pre_evolution.count - 1; i >= 0; --i) {
        const gc_u8 pre_ref = player.pre_evolution.values[i];
        CardState& pre = state.all_card[pre_ref];
        if (pre.attach_move_counter != current.move_counter) continue;
        if (to_area == kAreaHand && cannot_to_hand(state, current_ref)) continue;

        const bool keep_confuse = after_confuse_evolve(state, current);
        const gc_i32 move_counter = current.move_counter;
        const gc_i32 damage = current.damage;

        remove_list_at(player.pre_evolution, i);
        if (to_area == kAreaHand) {
            if (!push_list_back(player.hand, current_ref, runtime)) return;
            card_moved_full(state, runtime, current_ref, kAreaHand, false);
        } else {
            if (!push_list_back(player.deck, current_ref, runtime)) return;
            card_moved_full(state, runtime, current_ref, kAreaDeck, false);
        }
        if (runtime.error_flags != 0) return;

        if (field_area == kAreaActive) player.active.values[0] = pre_ref;
        else player.bench.values[field_index] = pre_ref;
        card_moved_full(state, runtime, pre_ref, field_area, false);
        pre.move_counter = move_counter;
        pre.damage = damage;
        state.changed = true;

        if (field_area == kAreaActive) {
            clear_special_condition_full(player);
            if (keep_confuse) player_active_state(player).fields.bad_status = 3;
        }
        refresh_effect(state, runtime, rules, 0);
        appear_proc(player, pre);
        return;
    }
}

__device__ __noinline__ void evolve_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 evolve_ref,
    gc_u8 in_play_ref_value,
    bool from_hand
) {
    if (evolve_ref == 0 || in_play_ref_value == 0) return;
    CardState& pre = state.all_card[in_play_ref_value];
    CardState& evolve = state.all_card[evolve_ref];
    const gc_i32 p = pre.player_index;
    if (p < 0 || p > 1 || evolve.player_index != p) return;
    if (pre.area != kAreaActive && pre.area != kAreaBench) return;
    PlayerState& player = state.players[p];
    if (from_hand && player_this_turn(player).fields.cannot_evolve) return;
    if (from_hand && player_continual(player).fields.cannot_play_ability_pokemon_not_rocket) {
        const RuleCardMaster* master = rule_card(rules, evolve.card_id);
        if (master != nullptr && get_ability(rules, evolve, *master) != nullptr
            && !card_flag(*master, kCardFlagTeamRocket)) return;
    }
    const bool keep_confuse = after_confuse_evolve(state, pre);
    const gc_i32 move_counter = pre.move_counter;
    const gc_i32 damage = pre.damage;
    const gc_u8 field_area = pre.area;
    const gc_i32 field_index = current_area_index(player, field_area, in_play_ref_value);
    const gc_i32 evolve_index = current_area_index(player, evolve.area, evolve_ref);
    if (field_index < 0 || evolve_index < 0) return;

    if (runtime.turn_evolve_count >= kTurnEvolveCapacity) {
        runtime.error_flags |= kRuntimeErrorTurnHistoryOverflow;
        return;
    }
    runtime.turn_evolve[runtime.turn_evolve_count++] = {in_play_ref_value, evolve_ref, 0};

    const gc_u8 source_area = evolve.area;
    remove_area_ref(state, runtime, p, source_area, evolve_index);
    if (!push_list_back(player.pre_evolution, in_play_ref_value, runtime)) return;
    card_moved_full(state, runtime, in_play_ref_value, 10, false);
    pre.attach_move_counter = move_counter;
    if (field_area == kAreaActive) player.active.values[0] = evolve_ref;
    else player.bench.values[field_index] = evolve_ref;
    card_moved_full(state, runtime, evolve_ref, field_area, false);
    evolve.move_counter = move_counter;
    evolve.damage = damage;
    if (field_area == kAreaActive) {
        clear_special_condition_full(player);
        if (keep_confuse) player_active_state(player).fields.bad_status = 3;
    }
    refresh_effect(state, runtime, rules, 0);
    if (from_hand) pull_trigger(state, runtime, rules, 8, evolve_ref, 0, 0);
    appear_proc(player, evolve);
    state.changed = true;
}

__device__ __noinline__ void transform_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 pre_ref,
    gc_u8 replacement_ref,
    bool old_to_deck
) {
    if (pre_ref == 0 || replacement_ref == 0
        || pre_ref >= kAllCardCapacity || replacement_ref >= kAllCardCapacity) return;
    CardState& pre = state.all_card[pre_ref];
    CardState& after = state.all_card[replacement_ref];
    if (pre.player_index < 0 || pre.player_index > 1 || pre.player_index != after.player_index) return;
    if (pre.area != kAreaActive && pre.area != kAreaBench) return;
    PlayerState& player = state.players[pre.player_index];
    const gc_u8 field_area = pre.area;
    const gc_i32 field_index = current_area_index(player, field_area, pre_ref);
    const gc_u8 replacement_area = after.area;
    gc_i32 replacement_index = current_area_index(player, replacement_area, replacement_ref);
    if (replacement_index < 0 || field_index < 0) return;

    const gc_u32 active_state = player.active_state;
    const gc_i32 replacement_card_id = after.card_id;
    const CardState copied_state = pre;
    remove_area_ref(state, runtime, pre.player_index, replacement_area, replacement_index);
    if (runtime.error_flags != 0) return;

    if (old_to_deck) {
        if (!push_list_back(player.deck, pre_ref, runtime)) return;
        card_moved_full(state, runtime, pre_ref, kAreaDeck, false);
    } else {
        if (!push_list_back(player.trash, pre_ref, runtime)) return;
        card_moved_full(state, runtime, pre_ref, 3, false);
    }
    if (runtime.error_flags != 0) return;

    after = copied_state;
    after.card_id = replacement_card_id;
    if (field_area == kAreaActive) player.active.values[0] = replacement_ref;
    else player.bench.values[field_index] = replacement_ref;
    player.active_state = active_state;

    for (gc_i32 i = 0; i < (gc_i32)runtime.trigger_count; ++i) {
        TriggeredAbilityState& ta = runtime.triggers[i];
        if (ta.trigger.subject.card_index == pre_ref) ta.trigger.subject.card_index = replacement_ref;
        if (ta.trigger.object.card_index == pre_ref) ta.trigger.object.card_index = replacement_ref;
    }
    state.changed = true;
    (void)rules;
}

}  // namespace gpu_cabt
