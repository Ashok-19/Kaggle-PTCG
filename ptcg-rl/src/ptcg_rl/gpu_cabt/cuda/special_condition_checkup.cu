namespace gpu_cabt {

__device__ __forceinline__ bool player_has_checkup_condition(const PlayerState& player) {
    const PlayerActiveFields& active = player_active_state(player);
    return active.fields.bad_status == 1 || active.fields.bad_status == 2
        || active.fields.poison_damage_counter > 0 || active.fields.burned;
}

__device__ __forceinline__ void checkup_poison_player(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0) return;
    const PlayerActiveFields& active = player_active_state(player);
    if (active.fields.poison_damage_counter <= 0) return;
    const gc_u8 ref = player.active.values[0];
    const CardState& card = state.all_card[ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return;
    gc_i32 damage = (gc_i32)active.fields.poison_damage_counter * 10
        + (gc_i32)player_continual(player).fields.poison_damage_change;
    if (!contains_energy(get_card_energy_type(card, *master), kEnergyDarkness))
        damage += (gc_i32)player_continual(player).fields.poison_damage_change_not_darkness;
    if (damage > 0)
        add_damage_full(state, runtime, rules, ref, damage, false, ref, false, nullptr);
}

__device__ __forceinline__ void checkup_burn_player(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0 || !player_active_state(player).fields.burned) return;
    const gc_u8 ref = player.active.values[0];
    const gc_i32 damage = 20 + (gc_i32)player_continual(player).fields.burn_damage_change;
    if (damage > 0)
        add_damage_full(state, runtime, rules, ref, damage, false, ref, false, nullptr);
    select_coin_full(state, runtime, 1);
    if (state.coin_head_count > 0 && player_active_state(player).fields.burned)
        player_active_state(player).fields.burned = false;
}

__device__ __forceinline__ void checkup_sleep_player(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0 || player_active_state(player).fields.bad_status != 1) return;
    select_coin_full(state, runtime, 1);
    if (state.coin_head_count > 0)
        player_active_state(player).fields.bad_status = 0;
}

__device__ __forceinline__ void checkup_paralyze_active_player(BattleCoreState& state) {
    const gc_i32 player_index = rule_active_player_index(state);
    PlayerState& player = state.players[player_index];
    if (player.active.count > 0 && player_active_state(player).fields.bad_status == 2)
        player_active_state(player).fields.bad_status = 0;
}

__device__ __forceinline__ void special_condition_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 first = state.first_player == 1 ? 1 : 0;
    checkup_poison_player(state, runtime, rules, first);
    if (runtime.error_flags != 0) return;
    checkup_poison_player(state, runtime, rules, 1 - first);
    if (runtime.error_flags != 0) return;
    checkup_burn_player(state, runtime, rules, first);
    if (runtime.error_flags != 0) return;
    checkup_burn_player(state, runtime, rules, 1 - first);
    if (runtime.error_flags != 0) return;
    checkup_sleep_player(state, runtime, first);
    checkup_sleep_player(state, runtime, 1 - first);
    checkup_paralyze_active_player(state);
}

__device__ __forceinline__ bool append_special_condition_trigger(
    BattleRuntimeState& runtime
) {
    if (runtime.temporary_trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return false;
    }
    TriggeredAbilityState& trigger = runtime.temporary_triggers[runtime.temporary_trigger_count++];
    trigger = {};
    trigger.trigger.type = 0;
    trigger.trigger.depth = 0;
    trigger.activate.is_special_condition = 1;
    return true;
}

}  // namespace gpu_cabt
