namespace gpu_cabt {

__device__ __forceinline__ void erase_delay_triggers_for_player(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    gc_i32 write = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.delay_trigger_count; ++i) {
        const TriggeredAbilityState value = runtime.delay_triggers[i];
        const gc_u8 subject = value.trigger.subject.card_index;
        if (subject != 0 && subject < kAllCardCapacity
            && state.all_card[subject].player_index == player_index) {
            continue;
        }
        runtime.delay_triggers[write++] = value;
    }
    runtime.delay_trigger_count = (gc_u16)write;
}

__device__ __forceinline__ void card_moved_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref,
    gc_u8 new_area,
    bool reverse
) {
    if (ref == 0 || ref >= kAllCardCapacity) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    CardState& card = state.all_card[ref];
    if (card.area == new_area) return;
    const gc_u8 pre_area = card.area;
    if (pre_area == kAreaActive) {
        if (card.player_index >= 0 && card.player_index <= 1) {
            state.players[card.player_index].active_state = 0;
            erase_delay_triggers_for_player(state, runtime, card.player_index);
        }
    }

    if (pre_area == kAreaActive || pre_area == kAreaBench) {
        if (new_area != kAreaActive && new_area != kAreaBench) {
            clear_card_state(&card);
            card.move_counter = state.move_counter++;
        }
    } else {
        clear_card_state(&card);
        card.move_counter = state.move_counter++;
        if (new_area == kAreaActive || new_area == kAreaBench) {
            card_turn(card).fields.appear = true;
        }
    }

    if (new_area != kAreaActive) {
        if (new_area == kAreaBench && pre_area == kAreaActive) {
            const bool this_limit = card_this_turn(card).fields.cannot_attack_less_equal_energy2;
            const bool next_limit = card_next_turn(card).fields.cannot_attack_less_equal_energy2;
            clear_card_next_turn_state(&card);
            card_this_turn(card).fields.cannot_attack_less_equal_energy2 = this_limit;
            card_next_turn(card).fields.cannot_attack_less_equal_energy2 = next_limit;
        } else {
            clear_card_next_turn_state(&card);
        }
        card.cannot_use_attack_id_non_active = 0;
    }

    card.area = new_area;
    card.pre_area = pre_area;
    card.reverse = reverse ? 1 : 0;
    card.attach_move_counter = 0;
}

__device__ __forceinline__ gc_i32 area_count(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 area
) {
    if (player_index < 0 || player_index > 1) return 0;
    const PlayerState& p = state.players[player_index];
    switch (area) {
        case 1: return p.deck.count; case 2: return p.hand.count; case 3: return p.trash.count;
        case 4: return p.active.count; case 5: return p.bench.count; case 6: return p.prize.count;
        case 8: return p.energy.count; case 9: return p.tool.count; case 10: return p.pre_evolution.count;
        case 24: return p.temporary.count;
        case 7: return state.stadium.count; case 12: return state.looking.count; case 13: return state.playing.count;
        default: return 0;
    }
}

__device__ __forceinline__ gc_u8 area_ref_at(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 area,
    gc_i32 index
) {
    if (index < 0) return 0;
    const PlayerState& p = state.players[player_index];
    switch (area) {
        case 1: return index < p.deck.count ? p.deck.values[index] : 0;
        case 2: return index < p.hand.count ? p.hand.values[index] : 0;
        case 3: return index < p.trash.count ? p.trash.values[index] : 0;
        case 4: return index < p.active.count ? p.active.values[index] : 0;
        case 5: return index < p.bench.count ? p.bench.values[index] : 0;
        case 6: return index < p.prize.count ? p.prize.values[index] : 0;
        case 7: return index < state.stadium.count ? state.stadium.values[index] : 0;
        case 8: return index < p.energy.count ? p.energy.values[index] : 0;
        case 9: return index < p.tool.count ? p.tool.values[index] : 0;
        case 10: return index < p.pre_evolution.count ? p.pre_evolution.values[index] : 0;
        case 12: return index < state.looking.count ? state.looking.values[index] : 0;
        case 13: return index < state.playing.count ? state.playing.values[index] : 0;
        case 24: return index < p.temporary.count ? p.temporary.values[index] : 0;
        default: return 0;
    }
}

template <typename List>
__device__ __forceinline__ gc_u8 remove_list_at(List& list, gc_i32 index) {
    if (index < 0 || index >= (gc_i32)list.count) return 0;
    const gc_u8 ref = list.values[index];
    for (gc_i32 i = index + 1; i < (gc_i32)list.count; ++i) list.values[i - 1] = list.values[i];
    --list.count;
    return ref;
}

template <typename List>
__device__ __forceinline__ bool push_list_back(List& list, gc_u8 ref, BattleRuntimeState& runtime) {
    const gc_i32 capacity = (gc_i32)(sizeof(list.values) / sizeof(list.values[0]));
    if ((gc_i32)list.count >= capacity) { runtime.error_flags |= kRuntimeErrorZoneOverflow; return false; }
    list.values[list.count++] = ref;
    return true;
}

template <typename List>
__device__ __forceinline__ bool push_list_front(List& list, gc_u8 ref, BattleRuntimeState& runtime) {
    const gc_i32 capacity = (gc_i32)(sizeof(list.values) / sizeof(list.values[0]));
    if ((gc_i32)list.count >= capacity) { runtime.error_flags |= kRuntimeErrorZoneOverflow; return false; }
    for (gc_i32 i = list.count; i > 0; --i) list.values[i] = list.values[i - 1];
    list.values[0] = ref; ++list.count; return true;
}

__device__ __forceinline__ gc_u8 remove_area_ref(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index,
    gc_u8 area,
    gc_i32 index
) {
    if (player_index < 0 || player_index > 1) { runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return 0; }
    PlayerState& p = state.players[player_index];
    switch (area) {
        case 1: return remove_list_at(p.deck, index); case 2: return remove_list_at(p.hand, index);
        case 3: return remove_list_at(p.trash, index); case 4: return remove_list_at(p.active, index);
        case 5: return remove_list_at(p.bench, index); case 6: return remove_list_at(p.prize, index);
        case 7: return remove_list_at(state.stadium, index); case 8: return remove_list_at(p.energy, index);
        case 9: return remove_list_at(p.tool, index); case 10: return remove_list_at(p.pre_evolution, index);
        case 12: return remove_list_at(state.looking, index); case 13: return remove_list_at(state.playing, index);
        case 24: return remove_list_at(p.temporary, index);
        default: runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return 0;
    }
}

__device__ __forceinline__ bool push_area_ref(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index,
    gc_u8 area,
    gc_u8 ref
) {
    if (player_index < 0 || player_index > 1) { runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return false; }
    PlayerState& p = state.players[player_index];
    switch (area) {
        case 1: return push_list_back(p.deck, ref, runtime); case 14: return push_list_front(p.deck, ref, runtime);
        case 2: return push_list_back(p.hand, ref, runtime); case 3: return push_list_back(p.trash, ref, runtime);
        case 4: return push_list_back(p.active, ref, runtime); case 5: return push_list_back(p.bench, ref, runtime);
        case 6: return push_list_back(p.prize, ref, runtime); case 7: return push_list_back(state.stadium, ref, runtime);
        case 8: return push_list_back(p.energy, ref, runtime); case 9: return push_list_back(p.tool, ref, runtime);
        case 10: return push_list_back(p.pre_evolution, ref, runtime); case 12: return push_list_back(state.looking, ref, runtime);
        case 13: return push_list_back(state.playing, ref, runtime); case 24: return push_list_back(p.temporary, ref, runtime);
        default: runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return false;
    }
}

__device__ __forceinline__ bool cannot_to_hand(
    const BattleCoreState& state,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    if (card.area == 8 || card.area == 9 || card.area == 10) {
        const RefPositionState pos = attached_card_position(state, card);
        if (pos.ref == 0) return false;
        return card_continual(state.all_card[pos.ref]).fields.cannot_to_hand;
    }
    return card_continual(card).fields.cannot_to_hand;
}

__device__ __forceinline__ void appear_proc(
    PlayerState& player,
    CardState& card
) {
    if (!card_continual(card).fields.no_effect_enemy_attack) {
        if (player_next_turn(player).fields.cannot_attack_less_equal_energy2) {
            card_next_turn(card).fields.cannot_attack_less_equal_energy2 = true;
        } else if (player_this_turn(player).fields.cannot_attack_less_equal_energy2) {
            card_this_turn(card).fields.cannot_attack_less_equal_energy2 = true;
        }
    }
}

__device__ __noinline__ gc_u8 move_card_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_u8 from_area,
    gc_i32 from_index,
    gc_u8 to_area,
    gc_i32 open_type,
    bool with_attach,
    bool must_move,
    bool ko,
    bool no_log = false
) {
    if (from_area == to_area) { runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return 0; }
    gc_u8 ref = area_ref_at(state, player_index, from_area, from_index);
    if (ref == 0) { runtime.error_flags |= kRuntimeErrorInvalidSelection; return 0; }
    PlayerState& player = state.players[player_index];
    CardState& original = state.all_card[ref];
    const gc_u8 log_from_area = from_area == 24 ? original.pre_area : from_area;
    const RuleCardMaster* master = rule_card(rules, original.card_id);
    if (master == nullptr) { runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return ref; }

    if (from_area == 3) {
        if ((to_area == 2 || to_area == 1 || to_area == 14)
            && card_flag(*master, kCardFlagCannotToHandOrDeckInTrash)) return ref;
        if (to_area == 2 && player_continual(player).fields.cannot_trash_to_hand_ability_or_trainers
            && state.current_attack_id <= 0) return ref;
    }
    if (!must_move) {
        if (to_area == 2 && cannot_to_hand(state, ref)) {
            if (ko) to_area = 3; else return ref;
        }
        if (to_area == 5 && (from_area == 2 || (from_area == 12 && original.pre_area == 2))) {
            if (player_continual(player).fields.cannot_play_ability_pokemon_not_rocket) {
                if (get_ability(rules, original, *master) != nullptr && !card_flag(*master, kCardFlagTeamRocket)) return ref;
            }
        }
    }

    if (to_area == 7 && state.stadium.count > 0 && from_area != 7) {
        const gc_u8 old = state.stadium.values[0];
        const gc_i32 old_player = state.all_card[old].player_index;
        move_card_full(state, runtime, rules, old_player, 7, 0, 3, 0, false, false, false);
        if (runtime.error_flags != 0) return ref;
    }

    ref = remove_area_ref(state, runtime, player_index, from_area, from_index);
    if (runtime.error_flags != 0 || ref == 0) return ref;
    if (!push_area_ref(state, runtime, player_index, to_area, ref)) return ref;
    const gc_i32 old_move_counter = state.all_card[ref].move_counter;
    const gc_u8 normalized_to_area = to_area == 14 ? 1 : to_area;
    card_moved_full(state, runtime, ref, normalized_to_area, false);
    if (runtime.error_flags != 0) return ref;
    if (!no_log && to_area != 10)
        log_move_card(state, runtime, player_index, ref, log_from_area, to_area, open_type);
    if (runtime.error_flags != 0) return ref;

    if (from_area == 7) state.last_stadium_player = (gc_i8)player_index;
    else if (from_area == 6 && (to_area == 2 || to_area == 5)) {
        const CardState& moved = state.all_card[ref];
        if (state.phase == 1 && rule_active_player_index(state) == moved.player_index) {
            state.turn_histories[0].take_prize_count_turn_player += 1;
        }
    }

    if ((from_area == 4 && to_area != 5) || (from_area == 5 && to_area != 4)) {
        for (gc_i32 i = (gc_i32)player.pre_evolution.count - 1; i >= 0; --i) {
            const gc_u8 attached = player.pre_evolution.values[i];
            if (state.all_card[attached].attach_move_counter != old_move_counter) continue;
            const gc_u8 destination = with_attach ? to_area : (to_area == 2 ? 2 : 3);
            move_card_full(state, runtime, rules, player_index, 10, i, destination, 0, false, true, ko);
            if (runtime.error_flags != 0) return ref;
        }
        for (gc_i32 i = (gc_i32)player.energy.count - 1; i >= 0; --i) {
            const gc_u8 attached = player.energy.values[i];
            if (state.all_card[attached].attach_move_counter != old_move_counter) continue;
            const gc_u8 destination = with_attach ? to_area : 3;
            move_card_full(state, runtime, rules, player_index, 8, i, destination, 0, false, true, ko);
            if (runtime.error_flags != 0) return ref;
        }
        for (gc_i32 i = (gc_i32)player.tool.count - 1; i >= 0; --i) {
            const gc_u8 attached = player.tool.values[i];
            if (state.all_card[attached].attach_move_counter != old_move_counter) continue;
            const gc_u8 destination = with_attach ? to_area : 3;
            move_card_full(state, runtime, rules, player_index, 9, i, destination, 0, false, true, ko);
            if (runtime.error_flags != 0) return ref;
        }
    }

    if (to_area == 4 || to_area == 5) {
        refresh_effect(state, runtime, rules, 0);
        if (runtime.error_flags != 0) return ref;
        if (from_area != 4 && from_area != 5) appear_proc(player, state.all_card[ref]);
    }

    if (to_area == 5) {
        const CardState& moved = state.all_card[ref];
        if (rule_active_player_index(state) == moved.player_index && from_area != 4)
            pull_trigger(state, runtime, rules, 5, ref, 0, 0);
        if (from_area == 2) pull_trigger(state, runtime, rules, 3, ref, 0, 0);
        else if (from_area == 4) pull_trigger(state, runtime, rules, 4, ref, 0, 0);
    } else if (to_area == 4) {
        if (from_area == 5) {
            if (state.phase == 1) card_turn(state.all_card[ref]).fields.bench_to_active = true;
            pull_trigger(state, runtime, rules, 6, ref, 0, 0);
        }
    } else if (to_area == 3 && from_area == 1 && state.effect_state.on_effect) {
        const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
        if (effect_ref != 0) {
            const CardState& effect_card = state.all_card[effect_ref];
            const RuleCardMaster* effect_master = rule_card(rules, effect_card.card_id);
            if (effect_master != nullptr
                && (effect_master->card_type == 0 || effect_master->card_type == 1 || effect_master->card_type == 3)
                && effect_card.player_index != state.all_card[ref].player_index) {
                pull_trigger(state, runtime, rules, 7, ref, 0, 0);
            }
        }
    }
    (void)open_type;
    return ref;
}

__device__ __forceinline__ gc_u8 move_ref_card_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    gc_u8 to_area,
    gc_i32 open_type = 0,
    bool with_attach = false,
    bool must_move = false,
    bool ko = false
) {
    if (ref == 0 || ref >= kAllCardCapacity) return 0;
    const CardState& card = state.all_card[ref];
    const gc_i32 player_index = card.player_index;
    if (player_index < 0 || player_index > 1) return 0;
    const gc_i32 index = current_area_index(state.players[player_index], card.area, ref);
    if (index < 0 && card.area == 7) {
        for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i) {
            if (state.stadium.values[i] == ref) {
                return move_card_full(state, runtime, rules, player_index, card.area, i, to_area, open_type, with_attach, must_move, ko);
            }
        }
        return ref;
    }
    if (index < 0 && card.area == 12) {
        for (gc_i32 i = 0; i < (gc_i32)state.looking.count; ++i) if (state.looking.values[i] == ref)
            return move_card_full(state, runtime, rules, player_index, card.area, i, to_area, open_type, with_attach, must_move, ko);
    }
    if (index < 0 && card.area == 13) {
        for (gc_i32 i = 0; i < (gc_i32)state.playing.count; ++i) if (state.playing.values[i] == ref)
            return move_card_full(state, runtime, rules, player_index, card.area, i, to_area, open_type, with_attach, must_move, ko);
    }
    if (index < 0) return ref;
    return move_card_full(state, runtime, rules, player_index, card.area, index, to_area, open_type, with_attach, must_move, ko);
}

__device__ __noinline__ void switch_pokemon_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_i32 bench_index
) {
    PlayerState& player = state.players[player_index];
    gc_u8 active_ref = 0;
    if (player.active.count == 0) {
        active_ref = move_card_full(state, runtime, rules, player_index, 5, bench_index, 4, 0, false, false, false);
        refresh_effect(state, runtime, rules, 0);
    } else {
        if (bench_index < 0 || bench_index >= (gc_i32)player.bench.count) { runtime.error_flags |= kRuntimeErrorInvalidSelection; return; }
        const gc_u8 bench_ref = player.bench.values[bench_index];
        const gc_u8 old_active = player.active.values[0];
        log_switch(state, runtime, player_index, old_active, bench_ref);
        if (runtime.error_flags != 0) return;
        clear_special_condition_logged(state, runtime, player_index);
        if (runtime.error_flags != 0) return;
        player.active.values[0] = bench_ref;
        player.bench.values[bench_index] = old_active;
        card_moved_full(state, runtime, bench_ref, 4, false);
        card_moved_full(state, runtime, old_active, 5, false);
        active_ref = bench_ref;
        if (state.phase == 1) card_turn(state.all_card[active_ref]).fields.bench_to_active = true;
        refresh_effect(state, runtime, rules, 0);
        pull_trigger(state, runtime, rules, 4, old_active, 0, 0);
    }
    pull_trigger(state, runtime, rules, 6, active_ref, 0, 0);
}

}  // namespace gpu_cabt
