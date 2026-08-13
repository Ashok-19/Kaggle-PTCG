namespace gpu_cabt {

__device__ __forceinline__ bool validate_selected_response(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    if (state.select_type == kSelectNone) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    if ((gc_i32)runtime.selected_count < state.select_min
        || (gc_i32)runtime.selected_count > state.select_max) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const gc_i32 index = runtime.selected[i];
        if (index < 0 || index >= (gc_i32)runtime.option_count) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return false;
        }
        for (gc_i32 j = 0; j < i; ++j) {
            if (runtime.selected[j] == index) {
                runtime.error_flags |= kRuntimeErrorInvalidSelection;
                return false;
            }
        }
    }
    return true;
}

__device__ __forceinline__ const SelectOptionState* first_selected_option(
    const BattleRuntimeState& runtime
) {
    if (runtime.selected_count == 0) return nullptr;
    const gc_i32 index = runtime.selected[0];
    if (index < 0 || index >= (gc_i32)runtime.option_count) return nullptr;
    return &runtime.options[index];
}

__device__ __forceinline__ bool selected_yes_full(const BattleRuntimeState& runtime) {
    const SelectOptionState* option = first_selected_option(runtime);
    return option != nullptr && option->type == kOptionYes;
}

__device__ __forceinline__ bool selected_list_contains(const BattleCoreState& state, gc_u8 ref) {
    for (gc_i32 i = 0; i < (gc_i32)state.selected_list.count; ++i)
        if (state.selected_list.values[i] == ref) return true;
    return false;
}

__device__ __forceinline__ bool append_selected_list_ref(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    if (state.selected_list.count >= kCardListCapacity) {
        runtime.error_flags |= kRuntimeErrorZoneOverflow;
        return false;
    }
    state.selected_list.values[state.selected_list.count++] = ref;
    return true;
}

__device__ __forceinline__ bool current_waiting_effect(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    EffectSpanState& span,
    const RuleEffect*& effect
) {
    effect = nullptr;
    if (!runtime.effect_execution_active || !runtime.effect_instance_waiting) return false;
    if (!current_effect_span(state, rules, span)) return false;
    if (runtime.effect_cursor < 0 || runtime.effect_cursor >= span.count) return false;
    effect = &span.effects[runtime.effect_cursor];
    return true;
}

__device__ __forceinline__ void finish_waiting_effect_and_run(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_substep = 0;
    runtime.effect_instance_waiting = 0;
    finish_effect_instance(state, runtime, effect);
    run_effect_execution(state, runtime, rules, depth);
}

__device__ __forceinline__ void dispatch_waiting_effect_and_run(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_substep = 0;
    runtime.effect_instance_waiting = 0;
    const bool waiting = dispatch_effect_after_selection(state, runtime, rules, effect, depth);
    if (waiting) {
        runtime.effect_instance_waiting = 1;
        return;
    }
    finish_effect_instance(state, runtime, effect);
    run_effect_execution(state, runtime, rules, depth);
}

__device__ __forceinline__ void collect_selected_card_targets(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    AreaRefState chosen[kAreaRefCapacity];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const SelectOptionState& option = runtime.options[runtime.selected[i]];
        const gc_u8 ref = option_card_ref(state, option);
        if (ref == 0) continue;
        if (count >= kAreaRefCapacity) {
            runtime.error_flags |= kRuntimeErrorTargetOverflow;
            return;
        }
        chosen[count++] = make_area_ref(state, ref);
    }
    clear_select_full(state, runtime);
    runtime.target_count = (gc_u16)count;
    for (gc_i32 i = 0; i < count; ++i) runtime.targets[i] = chosen[i];
}

__device__ __forceinline__ void collect_selected_attached_targets(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    bool energy
) {
    AreaRefState chosen[kAreaRefCapacity];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const SelectOptionState& option = runtime.options[runtime.selected[i]];
        const gc_u8 ref = option_attached_ref(state, option, energy);
        if (ref == 0) continue;
        if (count >= kAreaRefCapacity) {
            runtime.error_flags |= kRuntimeErrorTargetOverflow;
            return;
        }
        chosen[count++] = make_area_ref(state, ref);
    }
    clear_select_full(state, runtime);
    runtime.target_count = (gc_u16)count;
    for (gc_i32 i = 0; i < count; ++i) runtime.targets[i] = chosen[i];
}

__device__ __forceinline__ void collect_selected_card_or_attached_targets(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    AreaRefState chosen[kAreaRefCapacity];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const SelectOptionState& option = runtime.options[runtime.selected[i]];
        gc_u8 ref = 0;
        if (option.type == kOptionCard) ref = option_card_ref(state, option);
        else if (option.type == kOptionEnergyCard) ref = option_attached_ref(state, option, true);
        else if (option.type == kOptionToolCard) ref = option_attached_ref(state, option, false);
        if (ref == 0) continue;
        if (count >= kAreaRefCapacity) {
            runtime.error_flags |= kRuntimeErrorTargetOverflow;
            return;
        }
        chosen[count++] = make_area_ref(state, ref);
    }
    clear_select_full(state, runtime);
    runtime.target_count = (gc_u16)count;
    for (gc_i32 i = 0; i < count; ++i) runtime.targets[i] = chosen[i];
}

__device__ __forceinline__ bool begin_next_energy_choice(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_u8 context,
    gc_i32 select_player
) {
    gc_i32 minimum = state.remain_energy_cost <= 0 ? 0 : 1;
    if ((effect.flags & kEffectFlagEnergyMaxSelect) != 0) {
        if (state.remain_energy_cost < state.energy_cost || on_attack_effect(state)) minimum = 0;
    }
    set_select_full(state, runtime, kSelectEnergy, context, select_player, minimum, 1);
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (r.card == 0 || selected_list_contains(state, r.card)) continue;
        if (!valid_area_ref(state, r) || is_prevent_effect(state, rules, r.card)) continue;
        const CardState& energy = state.all_card[r.card];
        const RefPositionState pos = attached_card_position(state, energy);
        if (pos.ref == 0) continue;
        const gc_i32 ordinal = attached_ordinal(state, energy.player_index, r.card, true);
        if (ordinal < 0) continue;
        const gc_i32 units = get_energy_info(state, rules, energy, pos.ref).count;
        add_option_energy(runtime, pos.area, pos.index, energy.player_index, ordinal, units);
    }
    if (runtime.option_count == 0) {
        clear_select_full(state, runtime);
        return false;
    }
    runtime.pending_effect_kind = kPendingEnergyMove;
    runtime.pending_effect_substep = 0;
    return true;
}

__device__ __forceinline__ void finish_energy_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    clear_select_full(state, runtime);
    state.energy_cost = 0;
    state.remain_energy_cost = 0;
    state.selected_energy_card_count = 0;
    state.selecting_energy_pokemon_ref = 0;
    runtime.target_count = 0;
}

__device__ __forceinline__ bool resume_energy_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    const gc_u8 context = state.select_context;
    const gc_i32 select_player = state.select_player;
    if (runtime.selected_count == 0) {
        finish_energy_selection(state, runtime);
        return false;
    }
    const SelectOptionState option = *first_selected_option(runtime);
    const gc_u8 ref = option_attached_ref(state, option, true);
    if (ref == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    const gc_i32 player_index = state.all_card[ref].player_index;
    const gc_i32 old_attach = state.all_card[ref].attach_move_counter;
    if (!append_selected_list_ref(state, runtime, ref)) return false;
    clear_select_full(state, runtime);

    if (!is_prevent_effect(state, rules, ref)) {
        const gc_i32 index = current_area_index(state.players[player_index], 8, ref);
        if (context == kSelectContextDiscardEnergy && index >= 0) {
            move_card_full(state, runtime, rules, player_index, 8, index, 3, 0, false, false, false);
            after_energy_discard_full(state, runtime, rules, ref, old_attach);
        } else if (context == kSelectContextToDeckEnergy && index >= 0) {
            move_card_full(state, runtime, rules, player_index, 8, index, 1, 0, false, false, false);
        } else if (context == kSelectContextToHandEnergy && index >= 0) {
            move_card_full(state, runtime, rules, player_index, 8, index, 2, 0, false, false, false);
        } else if (context != kSelectContextSwitchEnergy) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return false;
        }
    }
    state.remain_energy_cost -= option.param4;
    ++state.selected_energy_card_count;
    if (state.energy_cost > state.selected_energy_card_count
        && begin_next_energy_choice(state, runtime, rules, effect, context, select_player)) return true;
    finish_energy_selection(state, runtime);
    return false;
}

__device__ __forceinline__ bool resume_generic_effect_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    const gc_u16 substep = runtime.pending_effect_substep;
    if (substep == kPendingSubstepGenericEvolve) {
        const SelectOptionState option = *first_selected_option(runtime);
        const gc_i32 player_index = state.select_player;
        const gc_u8 evolve_ref = area_ref_at(state, player_index, (gc_u8)option.param0, option.param1);
        const gc_u8 target_ref = area_ref_at(state, player_index, (gc_u8)option.param2, option.param3);
        clear_select_full(state, runtime);
        if (evolve_ref == 0 || target_ref == 0) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return false;
        }
        state.changed = 1;
        evolve_proc_full(state, runtime, rules, evolve_ref, target_ref, state.all_card[evolve_ref].area == kAreaHand);
        finish_waiting_effect_and_run(state, runtime, rules, effect, depth);
        return true;
    }
    if (substep == kPendingSubstepGenericAttached) {
        collect_selected_attached_targets(state, runtime, effect.effect_select_type == kEffectSelectMaxEnergyCard);
        if (runtime.error_flags == 0) dispatch_waiting_effect_and_run(state, runtime, rules, effect, depth);
        return true;
    }
    if (substep == kPendingSubstepGenericCardOrAttached) {
        collect_selected_card_or_attached_targets(state, runtime);
        if (runtime.error_flags == 0) dispatch_waiting_effect_and_run(state, runtime, rules, effect, depth);
        return true;
    }
    if (substep == kPendingSubstepGenericCard) {
        collect_selected_card_targets(state, runtime);
        if (runtime.error_flags == 0) dispatch_waiting_effect_and_run(state, runtime, rules, effect, depth);
        return true;
    }
    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
    return false;
}

__device__ __forceinline__ bool begin_lucky_bonus_prize_select(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1 || state.players[player_index].prize.count == 0) return false;
    set_select_full(state, runtime, kSelectCard, kSelectContextToHand, player_index, 1, 1);
    for (gc_i32 i = 0; i < (gc_i32)state.players[player_index].prize.count; ++i)
        add_option_card(runtime, kAreaPrize, i, player_index);
    runtime.pending_effect_kind = kPendingPrizeLuckyBonusCoin;
    runtime.pending_effect_arg0 = player_index;
    return true;
}

__device__ __forceinline__ bool resume_lucky_bonus(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_u8 ref = (gc_u8)runtime.pending_effect_arg0;
    if (ref == 0 || ref >= kAllCardCapacity) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    const gc_i32 player_index = state.all_card[ref].player_index;
    const bool yes = selected_yes_full(runtime);
    clear_select_full(state, runtime);
    const gc_i32 index = current_area_index(state.players[player_index], 24, ref);
    if (index < 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    if (yes) {
        move_card_full(state, runtime, rules, player_index, 24, index, kAreaBench, 0, false, false, false);
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count > 0 && begin_lucky_bonus_prize_select(state, runtime, player_index)) return true;
    } else {
        move_card_full(state, runtime, rules, player_index, 24, index, kAreaHand, 1, false, false, false);
    }
    runtime.pending_effect_kind = kPendingNone;
    if (queue_next_lucky_bonus(state, runtime, rules)) return true;
    return false;
}

__device__ __forceinline__ bool resume_lucky_bonus_prize(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    collect_selected_card_targets(state, runtime);
    if (runtime.error_flags != 0) return false;
    prize_to_hand_full(state, runtime, rules);
    if (runtime.pending_effect_kind != kPendingNone || state.select_type != kSelectNone) return true;
    if (queue_next_lucky_bonus(state, runtime, rules)) return true;
    return false;
}

__device__ __forceinline__ bool reopen_damage_counter_any(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    if (state.remain_damage_counter <= 0) return false;
    begin_damage_counter_any_selection(state, runtime);
    return runtime.option_count != 0;
}

__device__ __forceinline__ bool resume_damage_counter_any(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const SelectOptionState option = runtime.options[runtime.selected[i]];
        const gc_u8 ref = option_card_ref(state, option);
        if (ref == 0) continue;
        gc_i32 damage = 10;
        if (is_prevent_effect(state, rules, ref) || is_prevent_damage_counter(state, rules, ref)) damage = 0;
        if (damage > 0) {
            state.changed = 1;
            state.all_card[ref].damage += damage;
        }
    }
    clear_select_full(state, runtime);
    --state.remain_damage_counter;
    return reopen_damage_counter_any(state, runtime);
}

__device__ __forceinline__ bool resume_damage_counter_switch_any(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 target_player = runtime.pending_effect_arg0;
    if (runtime.pending_effect_substep == 0) {
        if (runtime.selected_count == 0) {
            clear_select_full(state, runtime);
            return false;
        }
        const SelectOptionState option = *first_selected_option(runtime);
        const gc_u8 remove_ref = option_card_ref(state, option);
        clear_select_full(state, runtime);
        if (remove_ref == 0) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return false;
        }
        heal_card(state, runtime, remove_ref, 10, false);
        set_select_full(state, runtime, kSelectCard, kSelectContextDamageCounter, effect_player_index(state));
        const PlayerState& player = state.players[target_player];
        if (player.active.count > 0 && player.active.values[0] != remove_ref)
            add_option_card(runtime, kAreaActive, 0, target_player);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
            if (player.bench.values[i] != remove_ref) add_option_card(runtime, kAreaBench, i, target_player);
        runtime.pending_effect_kind = kPendingDamageCounterSwitchAny;
        runtime.pending_effect_substep = 1;
        return runtime.option_count != 0;
    }
    const SelectOptionState option = *first_selected_option(runtime);
    const gc_u8 add_ref = option_card_ref(state, option);
    clear_select_full(state, runtime);
    if (add_ref == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    gc_i32 damage = 10;
    if (is_prevent_effect(state, rules, add_ref) || is_prevent_damage_counter(state, rules, add_ref)) damage = 0;
    state.all_card[add_ref].damage += damage;
    return begin_damage_counter_switch_any(state, runtime, rules, target_player);
}

__device__ __forceinline__ bool resume_remove_damage_counter(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    const gc_i32 target_index = runtime.pending_effect_arg0;
    const gc_u8 context_ref = state.context_card;
    const SelectOptionState option = *first_selected_option(runtime);
    gc_i32 count = option.param0;
    clear_select_full(state, runtime);
    if (context_ref == 0 || context_ref >= kAllCardCapacity) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    if (is_prevent_effect(state, rules, context_ref)) count = 0;
    heal_card(state, runtime, context_ref, count * 10, false);
    state.removed_damage_counter = count;
    const gc_i32 maximum = effect_value(state, runtime, effect, 0);
    return begin_remove_damage_counter(state, runtime, rules, target_index + 1, maximum);
}

__device__ __forceinline__ bool reopen_attack_damage_multi(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    set_select_full(state, runtime, kSelectCard, kSelectContextDamage, effect_player_index(state));
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref(state, r)) continue;
        gc_u8 area = 0; gc_i32 index = -1; gc_i32 player = -1;
        if (card_position_for_ref(state, r.card, area, index, player)) add_option_card(runtime, area, index, player);
    }
    runtime.pending_effect_kind = kPendingAttackDamageMulti;
    return runtime.option_count != 0;
}

__device__ __forceinline__ bool resume_attack_damage_multi(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 total = runtime.pending_effect_arg0;
    const gc_i32 damage_each = runtime.pending_effect_arg1;
    gc_i32 done = runtime.pending_effect_arg2;
    const SelectOptionState option = *first_selected_option(runtime);
    if (option.param0 == kAreaActive) ++state.select_counts[0];
    else if (option.param0 == kAreaBench && option.param1 >= 0 && option.param1 < kBenchSizeMax)
        ++state.select_counts[1 + option.param1];
    else {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    clear_select_full(state, runtime);
    ++done;
    runtime.pending_effect_arg0 = total;
    runtime.pending_effect_arg1 = damage_each;
    runtime.pending_effect_arg2 = done;
    if (done < total && reopen_attack_damage_multi(state, runtime)) {
        runtime.pending_effect_arg0 = total;
        runtime.pending_effect_arg1 = damage_each;
        runtime.pending_effect_arg2 = done;
        return true;
    }
    const gc_i32 player_index = 1 - effect_player_index(state);
    const PlayerState& player = state.players[player_index];
    for (gc_i32 i = 0; i < kSelectCountCapacity; ++i) {
        const gc_i32 count = state.select_counts[i];
        if (count <= 0) continue;
        gc_u8 ref = 0;
        if (i == 0) ref = player.active.count > 0 ? player.active.values[0] : 0;
        else if (i - 1 < (gc_i32)player.bench.count) ref = player.bench.values[i - 1];
        if (ref) effect_attack_damage_full(state, runtime, rules, ref, damage_each * count);
    }
    return false;
}

__device__ __forceinline__ bool begin_next_disable_attack(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 start_index
) {
    for (gc_i32 i = start_index; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState r = runtime.targets[i];
        if (!valid_area_ref_not_prevented(state, rules, r)) continue;
        const RuleCardMaster* master = rule_card(rules, state.all_card[r.card].card_id);
        if (master == nullptr) continue;
        set_select_full(state, runtime, kSelectAttack, kSelectContextDisableAttack, effect_player_index(state));
        for (gc_i32 j = 0; j < kRuleCardAttackCapacity; ++j) {
            const gc_i32 attack_id = master->attack_ids[j];
            if (attack_id > 0) add_option_attack(runtime, attack_id, attack_id);
        }
        if (runtime.option_count == 0) { clear_select_full(state, runtime); continue; }
        runtime.pending_effect_kind = kPendingDisableAttack;
        runtime.pending_effect_arg0 = r.card;
        runtime.pending_effect_arg1 = i;
        return true;
    }
    return false;
}

__device__ __forceinline__ bool resume_disable_attack(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_u8 ref = (gc_u8)runtime.pending_effect_arg0;
    const gc_i32 index = runtime.pending_effect_arg1;
    const SelectOptionState option = *first_selected_option(runtime);
    clear_select_full(state, runtime);
    if (ref == 0 || ref >= kAllCardCapacity || option.type != kOptionAttack) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    card_next_turn(state.all_card[ref]).fields.cannot_use_attack_id2 = option.param0;
    return begin_next_disable_attack(state, runtime, rules, index + 1);
}

__device__ __forceinline__ void apply_selected_special_condition(
    BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_i32 condition
) {
    if (condition == 0) effect_poison(state, rules, player_index, 1);
    else if (condition == 1) effect_burn(state, rules, player_index);
    else if (condition == 2) effect_sleep(state, rules, player_index);
    else if (condition == 3) effect_paralyze(state, rules, player_index);
    else if (condition == 4) effect_confuse(state, rules, player_index);
}

__device__ __forceinline__ void recover_selected_special_condition(
    BattleCoreState& state,
    gc_i32 player_index,
    gc_i32 condition
) {
    if (player_index < 0 || player_index > 1) return;
    auto& active = player_active_state(state.players[player_index]).fields;
    if (condition == 0) active.poison_damage_counter = 0;
    else if (condition == 1) active.burned = false;
    else if (condition >= 2 && condition <= 4) active.bad_status = 0;
}

__device__ __noinline__ void resume_effect_selection_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    if (!validate_selected_response(state, runtime)) return;
    const gc_u16 kind = runtime.pending_effect_kind;
    const gc_u16 substep = runtime.pending_effect_substep;

    if (kind == kPendingSelectActivate && substep == kPendingSubstepAbilityActivate) {
        const bool yes = selected_yes_full(runtime);
        const RuleSkill* skill = rule_skill(rules, state.effect_state.ability.skill_id);
        clear_select_full(state, runtime);
        runtime.pending_effect_kind = kPendingNone;
        runtime.pending_effect_substep = 0;
        if (yes && skill != nullptr) {
            const gc_i32 start = skill->trigger_start_index > 0 ? skill->trigger_start_index : 0;
            activate_ability_body(state, runtime, rules, *skill, start, depth);
        }
        return;
    }
    if (kind == kPendingSelectEffect
        && (substep == kPendingSubstepAbilityFirstEffect || substep == kPendingSubstepAbilityEnemyEffect)) {
        const bool yes = selected_yes_full(runtime);
        const gc_i32 second_start = runtime.pending_effect_arg0;
        const RuleSkill* skill = rule_skill(rules, state.effect_state.ability.skill_id);
        clear_select_full(state, runtime);
        runtime.pending_effect_kind = kPendingNone;
        runtime.pending_effect_substep = 0;
        if (skill != nullptr) {
            const gc_i32 start = yes ? (skill->trigger_start_index > 0 ? skill->trigger_start_index : 0) : second_start;
            activate_ability_body(state, runtime, rules, *skill, start, depth);
        }
        return;
    }

    EffectSpanState span{};
    const RuleEffect* effect = nullptr;
    if (!current_waiting_effect(state, runtime, rules, span, effect) || effect == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }

    if (kind == kPendingEffectSelection) {
        resume_generic_effect_selection(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingEnergyMove) {
        const bool waiting = resume_energy_selection(state, runtime, rules, *effect);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingPrizeLuckyBonus) {
        const bool waiting = resume_lucky_bonus(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingPrizeLuckyBonusCoin) {
        const bool waiting = resume_lucky_bonus_prize(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingDamageCounterAny) {
        const bool waiting = resume_damage_counter_any(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingDamageCounterSwitchAny) {
        const bool waiting = resume_damage_counter_switch_any(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingRemoveDamageCounter) {
        const bool waiting = resume_remove_damage_counter(state, runtime, rules, *effect);
        if (runtime.error_flags != 0 || waiting) return;
        if (!state.changed) state.effect_jump = 99;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingAttackDamageMulti) {
        const bool waiting = resume_attack_damage_multi(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingAttackDamagePutCounter) {
        const SelectOptionState option = *first_selected_option(runtime);
        const gc_i32 count = option.param0;
        const gc_i32 multiplier = runtime.pending_effect_arg0;
        const gc_u8 ref = state.effect_state.ability.effect_card.card_index;
        clear_select_full(state, runtime);
        if (ref) add_damage_full(state, runtime, rules, ref, count * 10, false, ref, true, nullptr);
        state.attack_damage_change = multiplier * count;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingDisableAttack) {
        const bool waiting = resume_disable_attack(state, runtime, rules);
        if (runtime.error_flags != 0 || waiting) return;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingSpecialCondition) {
        const SelectOptionState option = *first_selected_option(runtime);
        const gc_i32 player_index = runtime.pending_effect_arg0;
        clear_select_full(state, runtime);
        apply_selected_special_condition(state, rules, player_index, option.param0);
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingRecoverSpecialCondition) {
        const SelectOptionState option = *first_selected_option(runtime);
        const gc_i32 player_index = runtime.pending_effect_arg0;
        clear_select_full(state, runtime);
        recover_selected_special_condition(state, player_index, option.param0);
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingMoreDevolve) {
        const bool yes = selected_yes_full(runtime);
        const gc_u8 ref = (gc_u8)runtime.pending_effect_arg0;
        clear_select_full(state, runtime);
        if (yes && ref) {
            refresh_effect(state, runtime, rules, 0);
            devolve_ref_full(state, runtime, rules, ref, kAreaHand);
        }
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingSelectActivate && substep == 0) {
        const bool yes = selected_yes_full(runtime);
        clear_select_full(state, runtime);
        if (!yes) state.effect_jump = 99;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }
    if (kind == kPendingSelectEffect && substep == 0) {
        const bool yes = selected_yes_full(runtime);
        const gc_i32 jump = runtime.pending_effect_arg0;
        clear_select_full(state, runtime);
        if (!yes) state.effect_jump = (gc_u8)jump;
        finish_waiting_effect_and_run(state, runtime, rules, *effect, depth);
        return;
    }

    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
}

}  // namespace gpu_cabt
