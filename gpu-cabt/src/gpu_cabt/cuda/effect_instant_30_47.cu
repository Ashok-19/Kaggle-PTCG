namespace gpu_cabt {

__device__ __forceinline__ void begin_damage_counter_any_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    set_select_full(state, runtime, kSelectCard, kSelectContextDamageCounterAny, effect_player_index(state));
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref(state, r)) continue;
        gc_u8 area = 0; gc_i32 index = -1; gc_i32 player = -1;
        if (card_position_for_ref(state, r.card, area, index, player)) add_option_card(runtime, area, index, player);
    }
    runtime.pending_effect_kind = kPendingDamageCounterAny;
}

__device__ __forceinline__ bool begin_damage_counter_switch_any(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 target_player
) {
    if (target_player < 0 || target_player > 1) return false;
    PlayerState& player = state.players[target_player];
    if (player.bench.count == 0) return false;
    ++state.effect_action_count;
    if (state.effect_action_count > 10000) return false;
    set_select_full(state, runtime, kSelectCard, kSelectContextRemoveDamageCounter,
                    effect_player_index(state), 0, 1);
    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        const CardState& card = state.all_card[ref];
        if (!is_prevent_effect(state, rules, ref)
            && !card_continual(card).fields.cannot_move_damage_counter && card.damage > 0) {
            add_option_card(runtime, kAreaActive, 0, target_player);
        }
    }
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
        const gc_u8 ref = player.bench.values[i];
        const CardState& card = state.all_card[ref];
        if (!is_prevent_effect(state, rules, ref)
            && !card_continual(card).fields.cannot_move_damage_counter && card.damage > 0) {
            add_option_card(runtime, kAreaBench, i, target_player);
        }
    }
    if (runtime.option_count == 0) { clear_select_full(state, runtime); return false; }
    runtime.pending_effect_kind = kPendingDamageCounterSwitchAny;
    runtime.pending_effect_substep = 0;
    runtime.pending_effect_arg0 = target_player;
    return true;
}

__device__ __forceinline__ bool begin_remove_damage_counter(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 start_index,
    gc_i32 maximum
) {
    for (gc_i32 i = start_index; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref(state, r)) continue;
        CardState& card = state.all_card[r.card];
        if (is_prevent_effect(state, rules, r.card)
            || card_continual(card).fields.cannot_move_damage_counter) {
            heal_card(state, runtime, r.card, 0, false);
            continue;
        }
        gc_i32 max_count = card.damage / 10;
        if (maximum < max_count) max_count = maximum;
        if (max_count >= 2) {
            state.changed = true;
            state.context_card = r.card;
            set_select_full(state, runtime, kSelectCount, kSelectContextRemoveDamageCounterCount,
                            effect_player_index(state));
            for (gc_i32 n = 1; n <= max_count; ++n) add_option_number(runtime, n);
            runtime.pending_effect_kind = kPendingRemoveDamageCounter;
            runtime.pending_effect_arg0 = i;
            return true;
        }
        if (max_count == 1) {
            state.changed = true;
            heal_card(state, runtime, r.card, 10, false);
            state.removed_damage_counter = 1;
        }
    }
    return false;
}

__device__ __forceinline__ void compact_effect_targets_after_heal(
    BattleRuntimeState& runtime,
    const gc_u8* keep,
    gc_i32 original_count
) {
    gc_i32 write = 0;
    for (gc_i32 i = 0; i < original_count; ++i) if (keep[i]) runtime.targets[write++] = runtime.targets[i];
    runtime.target_count = (gc_u16)write;
}

__device__ __noinline__ bool effect_instant_30_47(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    if (effect.effect_type < 30 || effect.effect_type > 47) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    const gc_i32 value2 = effect_value(state, runtime, effect, 1);
    const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
    switch (effect.effect_type) {
        case 30:  // DamageCounter
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref(state, r)) continue;
                gc_i32 damage = value * 10 + state.effect_state.damage_change;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 31:  // DamageCounterRemoved
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_i32 damage = state.removed_damage_counter * 10;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 32:  // DamageCounterDamaged
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_i32 damage = state.trigger_info.value;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 33:  // DamageCounterAny
            if (runtime.target_count == 0 || value <= 0) return true;
            state.remain_damage_counter = value;
            begin_damage_counter_any_selection(state, runtime);
            return true;
        case 34:  // DamageCounterDouble
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_i32 damage = state.all_card[r.card].damage;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 35:  // DamageCounterHp
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                const RuleCardMaster* master = rule_card(rules, state.all_card[r.card].card_id); if (master == nullptr) continue;
                gc_i32 damage = get_hp(state.all_card[r.card], *master) - value;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 36: {  // DamageCounterSwitchAny
            state.effect_action_count = 0;
            const gc_i32 owner = effect_player_index(state);
            for (gc_i32 p = 0; p < 2; ++p) {
                if (!is_target_player(owner, p, effect.target.target_player)) continue;
                if (begin_damage_counter_switch_any(state, runtime, rules, p)) return true;
            }
            return true;
        }
        case 37:  // DamageCounterTypeEnergyCountMe
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                const gc_i32 count = effect_ref == 0 ? 0
                    : attached_energy_type_count(state, rules, effect_player_index(state), effect_ref, (gc_u16)value);
                gc_i32 damage = value2 * count * 10;
                if (is_prevent_effect(state, rules, r.card) || is_prevent_damage_counter(state, rules, r.card)) damage = 0;
                add_damage_full(state, runtime, rules, r.card, damage, false, effect_ref, true, nullptr);
                if (damage > 0) state.changed = true;
            }
            return true;
        case 38:  // AttackDamage
            for (gc_i32 i = (gc_i32)runtime.target_count - 1; i >= 0; --i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                effect_attack_damage_full(state, runtime, rules, r.card, value + state.effect_state.damage_change);
            }
            return true;
        case 39:  // AttackDamageMulti
            for (gc_i32 i = 0; i < kSelectCountCapacity; ++i) state.select_counts[i] = 0;
            if (value <= 0) return true;
            set_select_full(state, runtime, kSelectCard, kSelectContextDamage, effect_player_index(state));
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_u8 area = 0; gc_i32 index = -1; gc_i32 player = -1;
                if (card_position_for_ref(state, r.card, area, index, player)) add_option_card(runtime, area, index, player);
            }
            runtime.pending_effect_kind = kPendingAttackDamageMulti;
            runtime.pending_effect_arg0 = value;
            runtime.pending_effect_arg1 = value2;
            runtime.pending_effect_arg2 = 0;
            return true;
        case 40:  // AttackDamageCoin
            for (gc_i32 i = (gc_i32)runtime.target_count - 1; i >= 0; --i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                select_coin_full(state, runtime, 1);
                if (state.coin_head_count > 0) effect_attack_damage_full(state, runtime, rules, r.card, value);
            }
            return true;
        case 41:  // RemoveDamageCounter
            if (!begin_remove_damage_counter(state, runtime, rules, 0, value) && !state.changed) state.effect_jump = 99;
            return true;
        case 42:  // RemoveDamageCounterAll
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                CardState& card = state.all_card[r.card];
                if (is_prevent_effect(state, rules, r.card) || card_continual(card).fields.cannot_move_damage_counter) {
                    heal_card(state, runtime, r.card, 0, false); continue;
                }
                state.removed_damage_counter = card.damage / 10;
                if (state.removed_damage_counter > 0) { state.changed = true; heal_card(state, runtime, r.card, card.damage, false); }
            }
            if (!state.changed) state.effect_jump = 99;
            return true;
        case 43: {  // Heal
            gc_u8 keep[kAreaRefCapacity] = {};
            const gc_i32 n = runtime.target_count;
            for (gc_i32 i = 0; i < n; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_i32 heal = is_prevent_effect(state, rules, r.card) ? 0 : value;
                const gc_i32 healed = heal_card(state, runtime, r.card, heal, true);
                if (healed > 0) { state.changed = true; keep[i] = 1; }
            }
            if ((effect.flags & kEffectFlagRemoveEffectedIfNoEffect) != 0) compact_effect_targets_after_heal(runtime, keep, n);
            return true;
        }
        case 44: {  // HealAll
            gc_u8 keep[kAreaRefCapacity] = {};
            const gc_i32 n = runtime.target_count;
            for (gc_i32 i = 0; i < n; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref(state, r)) continue;
                gc_i32 heal = is_prevent_effect(state, rules, r.card) ? 0 : state.all_card[r.card].damage;
                const gc_i32 healed = heal_card(state, runtime, r.card, heal, true);
                if (healed > 0) { state.changed = true; keep[i] = 1; }
            }
            if ((effect.flags & kEffectFlagRemoveEffectedIfNoEffect) != 0) compact_effect_targets_after_heal(runtime, keep, n);
            return true;
        }
        case 45:  // HealSand
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                const RuleCardMaster* master = rule_card(rules, state.all_card[r.card].card_id); if (master == nullptr) continue;
                state.changed = true;
                heal_card(state, runtime, r.card, card_flag(*master, kCardFlagArven) ? 100 : 30, true);
            }
            return true;
        case 46:  // ResetHp
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                CardState& card = state.all_card[r.card]; const RuleCardMaster* master = rule_card(rules, card.card_id); if (master == nullptr) continue;
                const gc_i32 damage = get_max_hp(card, *master) - value;
                if (damage < card.damage) {
                    state.changed = true; card.damage = damage;
                    CardTurnFields& f = card_turn(card);
                    f.fields.ko = false; f.fields.ko_attack_damage = false; f.fields.ko_enemy_attack_damage = false;
                    f.fields.ko_enemy_attack_damage_active = false; f.fields.ko_enemy_terastal_attack_damage = false;
                    f.fields.ko_enemy_n_attack_damage = false; f.fields.ko_full = false; f.fields.ko_prize_plus1 = false;
                    f.fields.ko_prize_decrease_once = false; f.fields.ko_prize_zero = false;
                    f.fields.ko_no_damage_and_effect_attack_next_enemy_turn = false;
                }
            }
            return true;
        case 47:  // Drain
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i]; if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                state.changed = true; heal_card(state, runtime, r.card, state.last_attack_damage, true);
            }
            return true;
    }
    (void)depth;
    return true;
}

}  // namespace gpu_cabt
