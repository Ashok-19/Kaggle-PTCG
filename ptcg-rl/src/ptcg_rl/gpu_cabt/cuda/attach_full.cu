namespace gpu_cabt {

__device__ __forceinline__ bool can_attach_energy_full(
    const RuleCardMaster& energy_master,
    const RuleCardMaster& pokemon_master
) {
    if (card_flag(energy_master, kCardFlagOnlyTeamRocket)
        && !card_flag(pokemon_master, kCardFlagTeamRocket)) return false;
    return true;
}

__device__ __forceinline__ gc_i32 remaining_tool_capacity_full(
    const BattleCoreState& state,
    const CardState& pokemon
) {
    const gc_i32 attached = attached_tool_count(state, pokemon);
    const CardContinualFields& f = card_continual(pokemon);
    const gc_i32 capacity = f.fields.tool4 ? 4 : f.fields.tool2 ? 2 : 1;
    return capacity - attached;
}

__device__ __forceinline__ void append_temporary_trigger(
    BattleRuntimeState& runtime,
    const TriggeredAbilityState& ta
) {
    if (runtime.temporary_trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return;
    }
    runtime.temporary_triggers[runtime.temporary_trigger_count++] = ta;
}

__device__ __noinline__ gc_u8 attach_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 source_ref,
    gc_u8 target_ref,
    bool is_effect
) {
    if (source_ref == 0 || target_ref == 0
        || source_ref >= kAllCardCapacity || target_ref >= kAllCardCapacity) return 0;
    CardState& source = state.all_card[source_ref];
    const CardState& target = state.all_card[target_ref];
    const RuleCardMaster* source_master = rule_card(rules, source.card_id);
    const RuleCardMaster* target_master = rule_card(rules, target.card_id);
    if (source_master == nullptr || target_master == nullptr) return 0;
    if (target.area != kAreaActive && target.area != kAreaBench) return 0;
    if (source.player_index < 0 || source.player_index > 1 || source.player_index != target.player_index) return 0;
    PlayerState& player = state.players[source.player_index];
    const gc_u8 from_area = source.area;
    const gc_i32 source_index = current_area_index(player, from_area, source_ref);
    if (source_index < 0) return 0;

    if (player_this_turn(player).fields.cannot_play_special_energy
        && from_area == kAreaHand && source_master->card_type == 6) return 0;
    if (card_this_turn(target).fields.cannot_hand_attach_energy
        && from_area == kAreaHand && is_energy_card(source_master->card_type)) {
        move_card_full(state, runtime, rules, source.player_index, from_area, source_index, 3, 0, false, false, false);
        return 0;
    }
    if (is_energy_card(source_master->card_type)
        && !can_attach_energy_full(*source_master, *target_master)) return 0;
    if (source_master->card_type == 2 && remaining_tool_capacity_full(state, target) <= 0) return 0;

    gc_u8 moved = 0;
    if (source_master->card_type == 2) {
        moved = move_card_full(state, runtime, rules, source.player_index, from_area, source_index, 9, 0, false, true, false);
    } else {
        if (!is_effect) state_turn(state).fields.energy_played = true;
        moved = move_card_full(state, runtime, rules, source.player_index, from_area, source_index, 8, 0, false, true, false);
    }
    if (moved == 0 || runtime.error_flags != 0) return moved;
    state.all_card[moved].attach_move_counter = state.all_card[target_ref].move_counter;

    if (from_area == kAreaHand) {
        if (is_energy_card(source_master->card_type)) {
            pull_trigger(state, runtime, rules, 9, target_ref, 0, 0);
            for (gc_i32 i = (gc_i32)runtime.delay_trigger_count - 1; i >= 0; --i) {
                const TriggeredAbilityState& ta = runtime.delay_triggers[i];
                if (ta.trigger.type == 9 && ta.trigger.subject.card_index == target_ref) {
                    append_temporary_trigger(runtime, ta);
                    if (runtime.error_flags != 0) return moved;
                }
            }
        }
        if (source_master->play_skill_id > 0) {
            if (source_master->card_type == 2 && state_continual(state).fields.no_tool_effect) return moved;
            const RuleSkill* play = rule_skill(rules, source_master->play_skill_id);
            if (play != nullptr && (play->flags & kSkillFlagAttachBench) != 0 && target.area != kAreaBench) return moved;
            TriggeredAbilityState ta{};
            ta.trigger.type = 20;
            ta.trigger.subject.card_index = target_ref;
            ta.trigger.subject.move_counter = state.all_card[target_ref].move_counter;
            ta.activate.skill_id = source_master->play_skill_id;
            ta.activate.effect_card.card_index = moved;
            ta.activate.effect_card.move_counter = state.all_card[moved].move_counter;
            ta.activate.use_player_index = source.player_index;
            append_temporary_trigger(runtime, ta);
        }
    }
    return moved;
}

__device__ __forceinline__ void switch_energy_proc_full(
    BattleCoreState& state,
    gc_u8 energy_ref,
    gc_u8 pokemon_ref
) {
    if (energy_ref == 0 || pokemon_ref == 0
        || energy_ref >= kAllCardCapacity || pokemon_ref >= kAllCardCapacity) return;
    state.all_card[energy_ref].attach_move_counter = state.all_card[pokemon_ref].move_counter;
}

}  // namespace gpu_cabt
