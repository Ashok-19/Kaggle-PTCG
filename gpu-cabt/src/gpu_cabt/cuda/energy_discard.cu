namespace gpu_cabt {

__device__ __forceinline__ void after_energy_discard_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 energy_ref,
    gc_i32 attach_move_counter
) {
    if (energy_ref == 0 || energy_ref >= kAllCardCapacity) return;
    const CardState& energy = state.all_card[energy_ref];
    const RuleCardMaster* master = rule_card(rules, energy.card_id);
    if (master == nullptr || (master->card_id != 9 && master->card_id != 1268)) return;
    if (!on_attack(state) || !on_effect(state) || state.attacker == 0) return;
    const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
    if (effect_ref == 0 || effect_ref >= kAllCardCapacity) return;
    const CardState& attacker = state.all_card[state.attacker];
    const CardState& effect_card = state.all_card[effect_ref];
    if (attach_move_counter != attacker.move_counter || attach_move_counter != effect_card.move_counter) return;
    if (attacker.area != kAreaActive && attacker.area != kAreaBench) return;
    if (master->card_id == 1268) {
        const RuleCardMaster* attacker_master = rule_card(rules, attacker.card_id);
        if (attacker_master == nullptr
            || !contains_energy(get_card_energy_type(attacker, *attacker_master), kEnergyFire)) return;
    }
    if (master->ability_skill_id <= 0) return;
    if (runtime.temporary_trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return;
    }
    TriggeredAbilityState& ta = runtime.temporary_triggers[runtime.temporary_trigger_count++];
    ta = {};
    ta.trigger.type = 20;  // TriggerType::Attach
    ta.trigger.subject.card_index = state.attacker;
    ta.trigger.subject.move_counter = attacker.move_counter;
    ta.activate.skill_id = master->ability_skill_id;
    ta.activate.effect_card.card_index = energy_ref;
    ta.activate.effect_card.move_counter = energy.move_counter;
    ta.activate.use_player_index = energy.player_index;
}

}  // namespace gpu_cabt
