namespace gpu_cabt {

__device__ __forceinline__ bool trigger_area_ref_equal(
    const AreaRef& native_ref,
    const AreaRefState& ref
) {
    return native_ref.card_index == ref.card && native_ref.move_counter == ref.move_counter;
}

__device__ __forceinline__ AreaRefState activate_effect_ref(const ActivateAbilityInfo& info) {
    AreaRefState result{};
    result.card = info.effect_card.card_index;
    result.move_counter = info.effect_card.move_counter;
    return result;
}

__device__ __forceinline__ bool is_trigger_target(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 subject_ref,
    const RuleTarget& target,
    gc_u8 effect_card_ref
) {
    if (target.target_player == 0) return true;
    if (subject_ref == 0 || effect_card_ref == 0) return false;
    const CardState& card = state.all_card[subject_ref];
    const CardState& effect_card = state.all_card[effect_card_ref];
    if (target.target_player != 3) {
        if (target.target_player == 1) {
            if (card.player_index != effect_card.player_index) return false;
        } else {
            if (card.player_index == effect_card.player_index) return false;
        }
    }
    bool match = false;
    for (gc_i32 i = 0; i < (gc_i32)target.area_count; ++i) {
        const gc_u8 area = target.areas[i];
        if (area == 15) {
            if (card.move_counter == effect_card.move_counter) { match = true; break; }
        } else if (area == 21) {
            if (card.move_counter == effect_card.attach_move_counter) { match = true; break; }
        } else if (area == 0 || card.area == area) {
            match = true;
            break;
        }
    }
    if (!match) return false;
    return is_target(
        state, runtime, rules, subject_ref, target,
        make_area_ref(state, effect_card_ref)
    );
}

__device__ __forceinline__ bool trigger_stack_contains_once(
    const TriggeredAbilityState* stack,
    gc_i32 count,
    gc_i32 skill_id,
    const AreaRefState& effect_ref
) {
    for (gc_i32 i = 0; i < count; ++i) {
        const ActivateAbilityInfo& info = stack[i].activate;
        if (info.skill_id == skill_id
            && info.effect_card.card_index == effect_ref.card
            && info.effect_card.move_counter == effect_ref.move_counter) {
            return true;
        }
    }
    return false;
}

__device__ __forceinline__ void trigger_list(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 trigger_type,
    gc_u8 subject_ref,
    gc_u8 object_ref,
    gc_u8 effect_card_ref,
    gc_i32 depth
) {
    if (effect_card_ref == 0 || effect_card_ref >= kAllCardCapacity) return;
    const CardState& card = state.all_card[effect_card_ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return;
    const RuleSkill* skill = get_ability(rules, card, *master);
    if (skill == nullptr || skill->trigger_count <= 0) return;
    if (!skill_area_match(*skill, card.area)) return;
    if (skill->trigger_offset < 0
        || skill->trigger_offset + skill->trigger_count > rules.trigger_count) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }

    for (gc_i32 trigger_index = 0; trigger_index < skill->trigger_count; ++trigger_index) {
        const RuleTrigger& trigger = rules.triggers[skill->trigger_offset + trigger_index];
        if (trigger.trigger_type == 0 || trigger.trigger_type != trigger_type) continue;
        if (!is_trigger_target(
                state, runtime, rules, subject_ref, trigger.subject, effect_card_ref)) {
            continue;
        }

        TriggeredAbilityState ta{};
        ta.trigger.type = trigger.trigger_type;
        ta.trigger.depth = (gc_i8)depth;
        if (subject_ref != 0) ta.trigger.subject = AreaRef{
            subject_ref, state.all_card[subject_ref].move_counter
        };
        if (object_ref != 0) ta.trigger.object = AreaRef{
            object_ref, state.all_card[object_ref].move_counter
        };

        if (skill->effect_count > 0) {
            const RuleEffect& first_effect = rules.effects[skill->effect_offset];
            if ((first_effect.flags & kEffectFlagIsCondition) != 0) {
                const gc_u8 condition = first_effect.condition_type;
                if (condition == 11 || condition == 12 || condition == 13 || condition == 15) {
                    const TriggerInfo saved = state.trigger_info;
                    state.trigger_info = ta.trigger;
                    const bool satisfy = satisfy_condition(
                        state, runtime, rules,
                        rules.effects + skill->effect_offset,
                        skill->effect_count,
                        0,
                        effect_card_ref,
                        card.player_index
                    );
                    state.trigger_info = saved;
                    if (!satisfy) break;
                }
            }
        }

        const AreaRefState effect_ref = make_area_ref(state, effect_card_ref);
        if ((skill->flags & kSkillFlagOnceTurn) != 0) {
            if (trigger_stack_contains_once(
                    runtime.triggers, runtime.trigger_count,
                    skill->skill_id, effect_ref)
                || trigger_stack_contains_once(
                    runtime.temporary_triggers, runtime.temporary_trigger_count,
                    skill->skill_id, effect_ref)) {
                break;
            }
        }

        ta.activate.skill_id = skill->skill_id;
        ta.activate.effect_card.card_index = effect_card_ref;
        ta.activate.effect_card.move_counter = state.all_card[effect_card_ref].move_counter;
        ta.activate.use_player_index = card.player_index;

        if ((skill->flags & kSkillFlagNotStack) != 0) {
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)runtime.temporary_trigger_count; ++i) {
                const TriggeredAbilityState& existing = runtime.temporary_triggers[i];
                if (existing.activate.skill_id == ta.activate.skill_id
                    && existing.trigger.subject.card_index == ta.trigger.subject.card_index) {
                    found = true;
                    break;
                }
            }
            if (found) break;
        }

        if (runtime.temporary_trigger_count >= kTriggerCapacity) {
            runtime.error_flags |= kRuntimeErrorTriggerOverflow;
            return;
        }
        runtime.temporary_triggers[runtime.temporary_trigger_count++] = ta;
        break;
    }
}

__device__ __noinline__ void pull_trigger(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 trigger_type,
    gc_u8 subject_ref,
    gc_u8 object_ref,
    gc_i32 depth
) {
    for (gc_i32 p = 0; p < 2; ++p) {
        const PlayerState& player = state.players[p];
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
            trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, player.active.values[i], depth);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
            trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, player.bench.values[i], depth);
        if (!state_continual(state).fields.no_tool_effect) {
            for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i)
                trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, player.tool.values[i], depth);
        }
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i)
            trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, player.energy.values[i], depth);
        for (gc_i32 i = 0; i < (gc_i32)player.trash.count; ++i)
            trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, player.trash.values[i], depth);
    }
    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i)
        trigger_list(state, runtime, rules, trigger_type, subject_ref, object_ref, state.stadium.values[i], depth);
}

}  // namespace gpu_cabt
