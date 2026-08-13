namespace gpu_cabt {

__device__ __forceinline__ void clear_ability_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    state.effect_state = {};
    state.trigger_info = {};
    state.context_card = 0;
    runtime.target_count = 0;
    runtime.pre_target_count = 0;
    state.selected_list.count = 0;
    state.each_list.count = 0;
    state.check_list.count = 0;
    state.removed_damage_counter = 0;
    state.effect_jump = 0;
    state.attach_active = 0;
}

__device__ __forceinline__ gc_i32 first_trigger_index(
    const BattleRuntimeState& runtime,
    gc_i32 depth
) {
    for (gc_i32 i = 0; i < (gc_i32)runtime.temporary_trigger_count; ++i) {
        if (runtime.temporary_triggers[i].trigger.depth == depth) return i;
    }
    return 0;
}

__device__ __forceinline__ bool push_trigger_stack(
    BattleRuntimeState& runtime,
    const TriggeredAbilityState& value
) {
    if (runtime.trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return false;
    }
    runtime.triggers[runtime.trigger_count++] = value;
    return true;
}

__device__ __forceinline__ void set_triggered_ability_full(
    BattleCoreState& state,
    const TriggeredAbilityState& ability
) {
    state.effect_state = {};
    state.effect_state.ability = ability.activate;
    state.trigger_info = ability.trigger;
}

__device__ __forceinline__ bool trigger_effect_card_available(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const TriggeredAbilityState& ability
) {
    const gc_u8 ref = ability.activate.effect_card.card_index;
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    if (card.move_counter != ability.activate.effect_card.move_counter) return false;
    if (card.area == 3 || card.area == kAreaDeck || card.area == kAreaHand || card.area == kAreaPrize) {
        const RuleSkill* skill = rule_skill(rules, ability.activate.skill_id);
        return skill != nullptr && card.area == 3
            && (skill->flags & kSkillFlagCanActivateTrash) != 0;
    }
    return true;
}

__device__ __forceinline__ bool satisfy_first_trigger_skill_condition(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const TriggeredAbilityState& ability
) {
    const RuleSkill* skill = rule_skill(rules, ability.activate.skill_id);
    if (skill == nullptr) return false;
    const gc_u8 ref = ability.activate.effect_card.card_index;
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    return satisfy_skill_condition(
        state, runtime, rules, *skill, ref, ability.activate.use_player_index,
        skill->trigger_start_index
    );
}

__device__ __forceinline__ bool trigger_card_ability_disabled(
    const BattleCoreState& state,
    const TriggeredAbilityState& ability
) {
    const gc_u8 ref = ability.activate.effect_card.card_index;
    return ref != 0 && ref < kAllCardCapacity
        && card_continual(state.all_card[ref]).fields.no_ability;
}

__device__ __forceinline__ void continue_trigger_resolution_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
);

__device__ __forceinline__ void finish_trigger_activation_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    clear_ability_full(state, runtime);
    runtime.trigger_activation_waiting = 0;
    if (depth != 0) {
        refresh_effect(state, runtime, rules, 0);
        if (runtime.error_flags != 0) return;
        continue_trigger_resolution_full(state, runtime, rules, depth);
    } else {
        runtime.trigger_resolution_active = 0;
    }
}

__device__ __forceinline__ void continue_trigger_activation_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.trigger_activation_waiting) return;
    if (runtime.error_flags != 0 || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone
        || runtime.effect_execution_active) return;
    finish_trigger_activation_full(
        state, runtime, rules, runtime.trigger_resolution_depth
    );
}

__device__ __forceinline__ void activate_trigger_ability_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const TriggeredAbilityState& ability,
    gc_i32 depth
) {
    runtime.trigger_activation_waiting = 1;
    if (trigger_card_ability_disabled(state, ability)
        || !satisfy_first_trigger_skill_condition(state, runtime, rules, ability)) {
        finish_trigger_activation_full(state, runtime, rules, depth);
        return;
    }
    activate_ability_full(state, runtime, rules, depth);
    continue_trigger_activation_full(state, runtime, rules);
}

__device__ __forceinline__ void continue_trigger_resolution_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    if (!runtime.trigger_resolution_active || runtime.error_flags != 0) return;
    if (runtime.trigger_activation_waiting || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) return;
    if (runtime.trigger_count == 0) {
        runtime.trigger_resolution_active = 0;
        return;
    }

    state.state_changed = 1;
    const TriggeredAbilityState ability = runtime.triggers[runtime.trigger_count - 1];
    if ((gc_i32)ability.trigger.depth < depth) {
        runtime.trigger_resolution_active = 0;
        return;
    }
    --runtime.trigger_count;

    if (ability.activate.is_special_condition) {
        runtime.trigger_activation_waiting = 1;
        special_condition_proc_full(state, runtime, rules);
        if (runtime.error_flags != 0) {
            runtime.trigger_resolution_active = 0;
            return;
        }
        finish_trigger_activation_full(state, runtime, rules, depth);
        return;
    }

    if (!trigger_effect_card_available(state, rules, ability)) {
        runtime.trigger_activation_waiting = 1;
        finish_trigger_activation_full(state, runtime, rules, depth);
        return;
    }

    set_triggered_ability_full(state, ability);
    activate_trigger_ability_full(state, runtime, rules, ability, depth);
}

__device__ __forceinline__ void resolve_trigger_stack_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    runtime.trigger_resolution_active = 1;
    runtime.trigger_resolution_depth = (gc_i8)depth;
    runtime.trigger_activation_waiting = 0;

    const gc_i32 first = first_trigger_index(runtime, depth);
    const gc_i32 count = (gc_i32)runtime.temporary_trigger_count - first;
    if (count > 0) {
        if (count >= 2) {
            gc_i32 select_player = rule_active_player_index(state);
            gc_u8 type = 0;
            for (gc_i32 i = first; i < (gc_i32)runtime.temporary_trigger_count; ++i)
                type = runtime.temporary_triggers[i].trigger.type;
            if (state.phase != 1 || type == 10 || type == 11)
                select_player = 1 - rule_active_player_index(state);

            set_select_full(
                state, runtime, kSelectSkill, kSelectContextSkillOrder,
                select_player, count, count
            );
            for (gc_i32 i = first; i < (gc_i32)runtime.temporary_trigger_count; ++i)
                add_option_skill_order(
                    state, runtime,
                    runtime.temporary_triggers[i].activate.effect_card.card_index
                );
            runtime.pending_effect_kind = kPendingTriggerOrder;
            runtime.pending_effect_arg0 = depth;
            runtime.pending_effect_arg1 = first;
            runtime.pending_effect_arg2 = count;
            return;
        }
        if (!push_trigger_stack(runtime, runtime.temporary_triggers[first])) return;
        runtime.temporary_trigger_count = (gc_u16)first;
    }
    continue_trigger_resolution_full(state, runtime, rules, depth);
}

__device__ __forceinline__ bool valid_trigger_order_response(
    const BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    if (state.select_type != kSelectSkill
        || (gc_i32)runtime.selected_count < state.select_min
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

__device__ __forceinline__ void resume_trigger_order_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingTriggerOrder
        || !valid_trigger_order_response(state, runtime)) {
        if (runtime.pending_effect_kind != kPendingTriggerOrder)
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_i32 depth = runtime.pending_effect_arg0;
    const gc_i32 first = runtime.pending_effect_arg1;
    const gc_i32 count = runtime.pending_effect_arg2;
    if (first < 0 || count < 0 || first + count > (gc_i32)runtime.temporary_trigger_count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    for (gc_i32 i = (gc_i32)runtime.selected_count - 1; i >= 0; --i) {
        const gc_i32 relative = runtime.selected[i];
        if (relative < 0 || relative >= count) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        if (!push_trigger_stack(runtime, runtime.temporary_triggers[first + relative])) return;
    }
    clear_select_full(state, runtime);
    runtime.temporary_trigger_count = (gc_u16)first;
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_arg0 = 0;
    runtime.pending_effect_arg1 = 0;
    runtime.pending_effect_arg2 = 0;
    continue_trigger_resolution_full(state, runtime, rules, depth);
}

}  // namespace gpu_cabt
