namespace gpu_cabt {

__device__ __forceinline__ void select_card_targets(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    bool clear = true;
    if (effect.loop_count > 0 && state.effect_state.selected_list_index > 0) clear = false;
    if ((effect.flags & kEffectFlagNotClearSelectedList) != 0) clear = false;
    if (clear) state.selected_list.count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref(state, r) || is_prevent_effect(state, rules, r.card)) continue;
        if (state.selected_list.count >= kCardListCapacity) {
            runtime.error_flags |= kRuntimeErrorZoneOverflow;
            return;
        }
        state.selected_list.values[state.selected_list.count++] = r.card;
    }
}

__device__ __forceinline__ void shuffle_target_refs(
    BattleRuntimeState& runtime
) {
    for (gc_i32 i = (gc_i32)runtime.target_count - 1; i > 0; --i) {
        const gc_u32 j = bounded_u32(runtime.rng_seed, runtime.rng_stream,
                                     &runtime.rng_draw_index, (gc_u32)(i + 1));
        const AreaRefState tmp = runtime.targets[i];
        runtime.targets[i] = runtime.targets[j];
        runtime.targets[j] = tmp;
    }
}

__device__ __forceinline__ bool lucky_bonus_candidate(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr || !card.reverse) return false;
    const RuleSkill* ability = get_ability(rules, card, *master);
    if (ability == nullptr || (ability->flags & kSkillFlagLuckyBonus) == 0) return false;
    if (card.player_index < 0 || card.player_index > 1) return false;
    return remaining_bench(state, card.player_index) > 0
        && state.phase == 1 && rule_active_player_index(state) == card.player_index;
}

__device__ __forceinline__ bool queue_next_lucky_bonus(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 p = 0; p < 2; ++p) {
        PlayerState& player = state.players[p];
        for (gc_i32 i = 0; i < (gc_i32)player.temporary.count; ++i) {
            const gc_u8 ref = player.temporary.values[i];
            const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
            const RuleSkill* ability = master == nullptr ? nullptr : get_ability(rules, state.all_card[ref], *master);
            if (ability == nullptr || (ability->flags & kSkillFlagLuckyBonus) == 0) continue;
            if (remaining_bench(state, p) <= 0) {
                move_card_full(state, runtime, rules, p, 24, i, 2, 1, false, false, false);
                if (runtime.error_flags != 0) return false;
                --i;
                continue;
            }
            state.context_card = ref;
            set_select_full(state, runtime, kSelectYesNo, kSelectContextActivate, p);
            add_option_yes_no(runtime);
            runtime.pending_effect_kind = kPendingPrizeLuckyBonus;
            runtime.pending_effect_arg0 = ref;
            return true;
        }
    }
    return false;
}

__device__ __forceinline__ void prize_to_hand_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    gc_u8 rest[kAreaRefCapacity] = {};
    gc_i32 rest_count = 0;
    for (gc_i32 i = (gc_i32)runtime.target_count - 1; i >= 0; --i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref(state, r)) continue;
        if (lucky_bonus_candidate(state, rules, r.card)) {
            const CardState& card = state.all_card[r.card];
            const gc_i32 index = current_area_index(state.players[card.player_index], card.area, r.card);
            if (index >= 0) {
                remove_area_ref(state, runtime, card.player_index, card.area, index);
                push_area_ref(state, runtime, card.player_index, 24, r.card);
            }
        } else if (rest_count < kAreaRefCapacity) {
            rest[rest_count++] = r.card;
        } else runtime.error_flags |= kRuntimeErrorTargetOverflow;
    }
    for (gc_i32 i = rest_count - 1; i >= 0; --i) {
        const gc_u8 ref = rest[i];
        if (ref == 0 || ref >= kAllCardCapacity) continue;
        const CardState& card = state.all_card[ref];
        const gc_i32 index = current_area_index(state.players[card.player_index], card.area, ref);
        if (index >= 0) move_card_full(state, runtime, rules, card.player_index, card.area, index, 2, 1, false, false, false);
    }
    if (runtime.error_flags == 0) queue_next_lucky_bonus(state, runtime, rules);
}

__device__ __noinline__ bool effect_instant_0_29(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    if (effect.effect_type > 29) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    const gc_i32 owner = effect_player_index(state);
    switch (effect.effect_type) {
        case 0: return true;
        case 1: select_card_targets(state, runtime, rules, effect); return true;
        case 2:  // ForEach
            state.each_list.count = 0;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                if (state.each_list.count >= kCardListCapacity) { runtime.error_flags |= kRuntimeErrorZoneOverflow; break; }
                state.each_list.values[state.each_list.count++] = r.card;
            }
            return true;
        case 3:  // Ko
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                CardState& card = state.all_card[r.card]; const RuleCardMaster* master = rule_card(rules, card.card_id); if (master == nullptr) continue;
                state.changed = true; card.damage = get_max_hp(card, *master); card_turn(card).fields.ko = true;
            }
            return true;
        case 4: case 6: case 7: {  // ToHand variants
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 2, effect.effect_type == 6 ? 1 : 0, effect.effect_type == 7);
            }
            return true;
        }
        case 5: prize_to_hand_full(state, runtime, rules); return true;
        case 8:  // ToTrash
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                const gc_i32 attach = state.all_card[r.card].attach_move_counter;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 3);
                after_energy_discard_full(state, runtime, rules, r.card, attach);
            }
            return true;
        case 9: case 10: case 11: case 12: {  // ToDeck variants
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                gc_i32 open = 0; if (effect.effect_type == 11) open = 1; else if (effect.effect_type == 12) open = owner + 3;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 1, open, effect.effect_type == 10);
            }
            return true;
        }
        case 13: case 14: {  // ToDeckAndShuffle variants
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 1, effect.effect_type == 14 ? 1 : 0);
            }
            for (gc_i32 p = 0; p < 2; ++p) if (is_target_player(owner, p, effect.target.target_player)) shuffle_player_deck(state, runtime, p);
            return true;
        }
        case 15: case 16: case 17: {  // Deck bottom variants
            if (effect.effect_type == 17 && runtime.target_count >= 2) shuffle_target_refs(runtime);
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                state.changed = true;
                move_ref_card_full(state, runtime, rules, r.card, 14, effect.effect_type == 15 ? 0 : effect.effect_type == 16 ? 1 : 2);
            }
            return true;
        }
        case 18:  // ToActiveAndTrashActive
            if (runtime.target_count != 1) { if (runtime.target_count > 1) runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return true; }
            if (valid_area_ref(state, runtime.targets[0])) {
                const gc_u8 ref = runtime.targets[0].card; CardState& card = state.all_card[ref]; const RuleCardMaster* master = rule_card(rules, card.card_id);
                if (master != nullptr && !card_flag(*master, kCardFlagTransformOnly)) {
                    state.changed = true; PlayerState& p = state.players[card.player_index];
                    if (p.active.count > 0) move_card_full(state, runtime, rules, card.player_index, 4, 0, 3, 0, false, false, false);
                    move_ref_card_full(state, runtime, rules, ref, 4);
                }
            }
            return true;
        case 19:  // ToBench
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                CardState& card = state.all_card[r.card]; const RuleCardMaster* master = rule_card(rules, card.card_id); if (master == nullptr) continue;
                if (card.area != kAreaActive && card_flag(*master, kCardFlagTransformOnly)) continue;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 5);
            }
            return true;
        case 20:  // ToPrize
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                CardState& card = state.all_card[r.card];
                const gc_i32 open = card.area == 12 && state.looking_player >= 3 ? 2 : 1;
                state.changed = true; const gc_u8 moved = move_ref_card_full(state, runtime, rules, r.card, 6, open);
                if (moved) state.all_card[moved].reverse = 1;
            }
            return true;
        case 21:  // ToLooking
            state.looking_player = (gc_i8)effect_looking_player_index(state, effect);
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                state.changed = true; move_ref_card_full(state, runtime, rules, r.card, 12, looking_open_type(state));
            }
            return true;
        case 22:  // ToPlayingFirst
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                move_ref_card_full(state, runtime, rules, r.card, 13); break;
            }
            return true;
        case 23:  // Switch
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                CardState& card = state.all_card[r.card]; const gc_i32 p = card.player_index;
                if (p < 0 || p > 1 || state.players[p].active.count == 0) continue;
                const gc_u8 active = state.players[p].active.values[0]; gc_u8 effected = r.card;
                if ((effect.flags & kEffectFlagEffectTargetBench) != 0) effected = r.card;
                else if ((effect.flags & kEffectFlagEffectTargetActive) != 0 || (owner != p && state.select_player != p)) effected = active;
                if (is_prevent_effect(state, rules, effected) || card.area != kAreaBench) continue;
                const gc_i32 index = current_area_index(state.players[p], kAreaBench, r.card); if (index < 0) continue;
                state.changed = true; switch_pokemon_full(state, runtime, rules, p, index);
                if ((effect.flags & kEffectFlagSetTargetSwitchBench) != 0) { runtime.target_count = 1; runtime.targets[0] = make_area_ref(state, active); break; }
            }
            return true;
        case 24:  // SwitchDeck
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                CardState& card = state.all_card[r.card]; if (card.player_index < 0 || card.player_index > 1 || state.players[card.player_index].deck.count == 0) continue;
                state.changed = true; draw_cards(&state, &runtime, card.player_index, 1); move_ref_card_full(state, runtime, rules, r.card, 1, 1);
            }
            return true;
        case 25: select_card_targets(state, runtime, rules, effect); return true;
        case 26: case 27: case 28: {  // LookDeck variants
            if (effect.effect_type != 28 && state.looking.count != 0) { runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return true; }
            gc_i32 count = value; const gc_i32 p = effect_target_player_index(state, effect); if (p < 0 || p > 1) return true;
            PlayerState& player = state.players[p]; if (count > (gc_i32)player.deck.count) count = player.deck.count; if (count <= 0) return true;
            state.looking_player = (gc_i8)effect_looking_player_index(state, effect) + (effect.effect_type == 27 ? 3 : 0);
            for (gc_i32 n = 0; n < count; ++n) {
                const gc_i32 index = effect.effect_type == 28 ? 0 : (gc_i32)player.deck.count - 1;
                state.changed = true; move_card_full(state, runtime, rules, p, 1, index, 12, effect.effect_type == 27 ? 2 : looking_open_type(state), false, false, false);
            }
            return true;
        }
        case 29: {  // LookAndReturn: native emits synthetic movement logs only.
            if (runtime.target_count == 0) return true;
            gc_i32 open_type = owner + 3;
            const AreaRefState first_ref = runtime.targets[0];
            if (valid_area_ref(state, first_ref) && state.all_card[first_ref.card].area == kAreaHand)
                open_type = 0;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref(state, r)) continue;
                const CardState& card = state.all_card[r.card];
                log_move_card(state, runtime, card.player_index, r.card, card.area, 12, open_type);
            }
            if (value == 1) open_type = 0;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref(state, r)) continue;
                CardState& card = state.all_card[r.card];
                log_move_card(state, runtime, card.player_index, r.card, 12, card.area, open_type);
                if (value == 1) card.reverse = 0;
            }
            return true;
        }
    }
    (void)depth;
    return true;
}

}  // namespace gpu_cabt
