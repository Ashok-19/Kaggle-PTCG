namespace gpu_cabt {

__device__ __forceinline__ gc_u8 selected_effect_ref(const BattleCoreState& state) {
    const gc_i32 i = state.effect_state.selected_list_index;
    return i >= 0 && i < (gc_i32)state.selected_list.count ? state.selected_list.values[i] : 0;
}

__device__ __forceinline__ void push_delay_effect_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    const AreaRefState& subject
) {
    if (!valid_area_ref_not_prevented(state, rules, subject)) return;
    gc_i32 card_id = 0;
    if (effect.parent_attack_id > 0) {
        const RuleAttack* a = rule_attack(rules, effect.parent_attack_id);
        if (a != nullptr) card_id = a->card_id;
    } else if (effect.parent_skill_id > 0) {
        const RuleSkill* s = rule_skill(rules, effect.parent_skill_id);
        if (s != nullptr) card_id = s->card_id;
    }
    const RuleCardMaster* master = rule_card(rules, card_id);
    if (master == nullptr || master->delay_skill_id <= 0) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const RuleSkill* delay = rule_skill(rules, master->delay_skill_id);
    if (delay == nullptr || delay->trigger_count <= 0) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    if (runtime.delay_trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return;
    }
    const RuleTrigger* trigger = (delay->trigger_offset >= 0 && delay->trigger_offset < rules.trigger_count)
        ? &rules.triggers[delay->trigger_offset] : nullptr;
    if (trigger == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
    TriggeredAbilityState ta{};
    ta.trigger.type = trigger->trigger_type;
    ta.trigger.subject.card_index = subject.card;
    ta.trigger.subject.move_counter = subject.move_counter;
    ta.activate.skill_id = delay->skill_id;
    ta.activate.effect_card.card_index = effect_ref;
    ta.activate.effect_card.move_counter = effect_ref ? state.all_card[effect_ref].move_counter : 0;
    ta.activate.use_player_index = effect_ref ? state.all_card[effect_ref].player_index : effect_player_index(state);
    runtime.delay_triggers[runtime.delay_trigger_count++] = ta;
    state.changed = true;
}

__device__ __noinline__ bool effect_instant_56_71(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    if (effect.effect_type < 56 || effect.effect_type > 71) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    switch (effect.effect_type) {
        case 56:
        case 58:
        case 60:
        case 62:
        case 67:
        case 68:
            select_card_targets(state, runtime, rules, effect);
            return true;
        case 57: {
            const gc_u8 evolve_ref = selected_effect_ref(state);
            if (!evolve_ref) return true;
            const bool from_hand = state.all_card[evolve_ref].area == 2;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                state.changed = true;
                evolve_proc_full(state, runtime, rules, evolve_ref, runtime.targets[i].card, from_hand);
            }
            return true;
        }
        case 59: {
            const gc_u8 base_ref = selected_effect_ref(state);
            if (!base_ref) return true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                const gc_u8 evolve_ref = runtime.targets[i].card;
                state.changed = true;
                evolve_proc_full(state, runtime, rules, evolve_ref, base_ref, state.all_card[evolve_ref].area == 2);
                break;
            }
            return true;
        }
        case 61: {
            const gc_u8 target_ref = selected_effect_ref(state);
            if (!target_ref) return true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                state.changed = true;
                attach_proc_full(state, runtime, rules, runtime.targets[i].card, target_ref, true);
                if (state.all_card[target_ref].area == kAreaActive) state.attach_active = 1;
            }
            return true;
        }
        case 63: {
            const gc_u8 target_ref = state.effect_state.ability.effect_card.card_index;
            if (!target_ref) return true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                state.changed = true;
                attach_proc_full(state, runtime, rules, runtime.targets[i].card, target_ref, true);
            }
            return true;
        }
        case 64:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                for (gc_i32 j = 0; j < (gc_i32)state.selected_list.count; ++j) {
                    state.changed = true;
                    attach_proc_full(state, runtime, rules, state.selected_list.values[j], r.card, true);
                }
                if (state.all_card[r.card].area == kAreaActive) state.attach_active = 1;
                break;
            }
            return true;
        case 65:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                const gc_u8 target_ref = runtime.targets[i].card;
                for (gc_i32 j = 0; j < (gc_i32)state.selected_list.count; ++j) {
                    const gc_u8 energy_ref = state.selected_list.values[j];
                    state.changed = true;
                    if (is_prevent_effect(state, rules, target_ref)) move_ref_card_full(state, runtime, rules, energy_ref, 3);
                    else switch_energy_proc_full(state, energy_ref, target_ref);
                }
                break;
            }
            return true;
        case 66: {
            const gc_u8 attach_ref = selected_effect_ref(state);
            if (!attach_ref) return true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                state.changed = true;
                attach_proc_full(state, runtime, rules, attach_ref, runtime.targets[i].card, true);
                if (state.all_card[runtime.targets[i].card].area == kAreaActive) state.attach_active = 1;
            }
            return true;
        }
        case 69: {
            const gc_u8 energy_ref = selected_effect_ref(state);
            if (!energy_ref) return true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                const gc_u8 target_ref = runtime.targets[i].card;
                state.changed = true;
                if (is_prevent_effect(state, rules, target_ref)) move_ref_card_full(state, runtime, rules, energy_ref, 3);
                else switch_energy_proc_full(state, energy_ref, target_ref);
            }
            return true;
        }
        case 70:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i)
                push_delay_effect_full(state, runtime, rules, effect, runtime.targets[i]);
            return true;
        case 71:
            select_coin_full(state, runtime, value);
            return true;
    }
    return true;
}

}  // namespace gpu_cabt
