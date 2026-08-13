namespace gpu_cabt {

__device__ __forceinline__ bool ability_seen(
    const BattleRuntimeState& runtime,
    gc_i32 player_index,
    gc_i32 skill_id
) {
    if (player_index < 0 || player_index > 1 || skill_id < 0 || skill_id >= kAbilitySetWordCount * 32) return false;
    return (runtime.ability_set[player_index][skill_id >> 5] & (1u << (skill_id & 31))) != 0;
}

__device__ __forceinline__ void ability_mark(
    BattleRuntimeState& runtime,
    gc_i32 player_index,
    gc_i32 skill_id
) {
    if (player_index < 0 || player_index > 1 || skill_id < 0 || skill_id >= kAbilitySetWordCount * 32) return;
    runtime.ability_set[player_index][skill_id >> 5] |= 1u << (skill_id & 31);
}

__device__ __forceinline__ bool skill_area_match(const RuleSkill& skill, gc_u8 area) {
    for (gc_i32 i = 0; i < (gc_i32)skill.area_count; ++i) if (skill.areas[i] == area) return true;
    return false;
}

__device__ __forceinline__ bool skill_has_continual(const RuleSkill& skill) {
    return (skill.trigger_count == 0 || skill.trigger_start_index > 0)
        && (skill.flags & kSkillFlagMainAbility) == 0;
}

__device__ __forceinline__ bool card_effect_before(
    const CardEffectOrderState& left,
    const CardEffectOrderState& right
) {
    if (left.priority != right.priority) return left.priority > right.priority;
    if (left.skill_order != right.skill_order) return left.skill_order < right.skill_order;
    return left.move_counter < right.move_counter;
}

__device__ __forceinline__ void sort_card_effects(BattleRuntimeState& runtime) {
    for (gc_i32 i = 1; i < (gc_i32)runtime.card_effect_count; ++i) {
        CardEffectOrderState value = runtime.card_effects[i];
        gc_i32 j = i;
        while (j > 0 && card_effect_before(value, runtime.card_effects[j - 1])) {
            runtime.card_effects[j] = runtime.card_effects[j - 1];
            --j;
        }
        runtime.card_effects[j] = value;
    }
}

__device__ __forceinline__ void clear_card_continual(CardState& card) {
    for (gc_i32 i = 0; i < 5; ++i) card.continual_state[i] = 0;
}

__device__ __forceinline__ void collect_card_effect(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) return;
    CardState& card = state.all_card[ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return;
    const RuleSkill* ability = get_ability(rules, card, *master);
    if (card_continual(card).fields.no_ability) { card.skill_order = 0; return; }
    if (ability == nullptr || !skill_has_continual(*ability) || !skill_area_match(*ability, card.area)) return;
    if (runtime.card_effect_count >= kCardEffectCapacity) {
        runtime.error_flags |= kRuntimeErrorCardEffectOverflow;
        return;
    }
    CardEffectOrderState& row = runtime.card_effects[runtime.card_effect_count++];
    row.ref = ref;
    row.priority = ability->priority;
    row.skill_order = card.skill_order;
    row.move_counter = card.move_counter;
}

__device__ __forceinline__ void remove_no_enemy_ability_targets(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 source_player,
    gc_u8 source_ref
) {
    if (source_ref == 0) return;
    const bool stadium_source = state.all_card[source_ref].area == 7;
    if (stadium_source) return;
    gc_i32 write = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.scratch_target_count; ++i) {
        const AreaRefState target = runtime.scratch_targets[i];
        const CardState& card = state.all_card[target.card];
        if (card_continual(card).fields.no_enemy_ability && card.player_index != source_player) continue;
        runtime.scratch_targets[write++] = target;
    }
    runtime.scratch_target_count = (gc_u16)write;
}

__device__ __noinline__ void static_effect(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref
) {
    CardState& card = state.all_card[ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return;
    const gc_i32 saved_skill_order = card.skill_order;
    card.skill_order = 2147483647;
    if (state_continual(state).fields.no_tool_effect && master->card_type == 2) return;
    const RuleSkill* ability = get_ability(rules, card, *master);
    if (ability == nullptr) return;
    if ((ability->flags & kSkillFlagNotStack) != 0 && ability_seen(runtime, card.player_index, ability->skill_id)) return;
    if (ability->effect_offset < 0 || ability->effect_offset + ability->effect_count > rules.effect_count) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition; return;
    }
    const RuleEffect* effects = rules.effects + ability->effect_offset;
    const AreaRefState area_ref = make_area_ref(state, ref);
    for (gc_i32 i = 0; i < ability->effect_count; ++i) {
        const RuleEffect& effect = effects[i];
        if ((effect.flags & kEffectFlagIsCondition) != 0) {
            if (satisfy_condition(state, runtime, rules, effects, ability->effect_count, i, ref, card.player_index)) continue;
            if (effect.fail_skip) { i += effect.fail_skip; continue; }
            return;
        }
        if (saved_skill_order == 2147483647) card.skill_order = state.current_skill_order++;
        else card.skill_order = saved_skill_order;
        if ((ability->flags & kSkillFlagNotStack) != 0) ability_mark(runtime, card.player_index, ability->skill_id);
        runtime.scratch_target_count = 0;
        target_list(
            state, runtime, rules, effect.target,
            runtime.scratch_targets, runtime.scratch_target_count,
            area_ref, card.player_index, false, kRuntimeErrorTargetOverflow
        );
        remove_no_enemy_ability_targets(state, runtime, card.player_index, ref);
        effect_continual(
            state, runtime, rules, effect,
            runtime.scratch_targets, runtime.scratch_target_count,
            card.player_index, ref
        );
        if (runtime.error_flags != 0) return;
    }
}

__device__ __forceinline__ void clear_sleep_paralyze_confuse(PlayerState& player) {
    player_active_state(player).fields.bad_status = 0;
}

__device__ __forceinline__ void clear_special_condition(PlayerState& player) {
    auto& active = player_active_state(player).fields;
    active.bad_status = 0;
    active.poison_damage_counter = 0;
    active.burned = false;
}

__device__ __noinline__ void refresh_effect(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    if (depth > 10) { runtime.error_flags |= kRuntimeErrorRefreshDepth; return; }
    state.continual_state = 0;
    for (gc_i32 p = 0; p < 2; ++p) {
        for (gc_i32 w = 0; w < kAbilitySetWordCount; ++w) runtime.ability_set[p][w] = 0;
        PlayerState& player = state.players[p];
        player.continual_state = 0;
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) clear_card_continual(state.all_card[player.active.values[i]]);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) clear_card_continual(state.all_card[player.bench.values[i]]);
        for (gc_i32 i = 0; i < (gc_i32)player.hand.count; ++i) clear_card_continual(state.all_card[player.hand.values[i]]);
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) clear_card_continual(state.all_card[player.tool.values[i]]);
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) clear_card_continual(state.all_card[player.energy.values[i]]);
    }

    runtime.card_effect_count = 0;
    for (gc_i32 p = 0; p < 2; ++p) {
        PlayerState& player = state.players[p];
        player.continual_state = 0;
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) collect_card_effect(state, runtime, rules, player.active.values[i]);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) collect_card_effect(state, runtime, rules, player.bench.values[i]);
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) collect_card_effect(state, runtime, rules, player.energy.values[i]);
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) collect_card_effect(state, runtime, rules, player.tool.values[i]);
        for (gc_i32 i = 0; i < (gc_i32)player.hand.count; ++i) collect_card_effect(state, runtime, rules, player.hand.values[i]);
    }
    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i) collect_card_effect(state, runtime, rules, state.stadium.values[i]);
    if (runtime.error_flags != 0) return;

    state.update_order = false;
    sort_card_effects(runtime);
    for (gc_i32 i = 0; i < (gc_i32)runtime.card_effect_count; ++i) {
        state.current_card_effect_index = i;
        static_effect(state, runtime, rules, runtime.card_effects[i].ref);
        if (runtime.error_flags != 0 || state.update_order) break;
    }
    if (runtime.error_flags != 0) return;
    if (state.update_order) {
        if (depth < 10) refresh_effect(state, runtime, rules, depth + 1);
        return;
    }
    for (gc_i32 p = 0; p < 2; ++p) {
        PlayerState& player = state.players[p];
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) {
            const CardState& card = state.all_card[player.active.values[i]];
            if (card_continual(card).fields.no_special_condition) clear_special_condition(player);
            if (card_continual(card).fields.no_sleep_paralyze_confuse) clear_sleep_paralyze_confuse(player);
        }
    }
}

}  // namespace gpu_cabt
