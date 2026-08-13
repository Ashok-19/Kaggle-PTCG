namespace gpu_cabt {

__device__ __forceinline__ void append_turn_heal(
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    if (runtime.turn_heal_count >= kTurnCardCapacity) {
        runtime.error_flags |= kRuntimeErrorTurnHistoryOverflow;
        return;
    }
    runtime.turn_heal[runtime.turn_heal_count++] = ref;
}

__device__ __forceinline__ gc_i32 heal_card(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref,
    gc_i32 heal,
    bool record_heal
) {
    if (ref == 0 || ref >= kAllCardCapacity) return 0;
    CardState& card = state.all_card[ref];
    const gc_i32 source_damage = card.damage;
    card.damage -= heal;
    if (card.damage < 0) card.damage = 0;
    const gc_i32 healed = source_damage - card.damage;
    if (record_heal && healed > 0) append_turn_heal(runtime, ref);
    return healed;
}

__device__ __noinline__ void add_damage_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    gc_i32 damage,
    bool is_attack_damage,
    gc_u8 cause_ref,
    bool put_damage_counter,
    const RuleAttack* attack
) {
    if (ref == 0 || ref >= kAllCardCapacity) return;
    CardState& card = state.all_card[ref];
    const RuleCardMaster* target_master = rule_card(rules, card.card_id);
    if (target_master == nullptr) return;
    if (damage <= 0) return;
    const gc_i32 max_hp = get_max_hp(card, *target_master);
    if (card.damage >= max_hp) {
        card.damage += damage;
        return;
    }
    if (cause_ref == 0 || cause_ref >= kAllCardCapacity) cause_ref = ref;
    const CardState& cause_card = state.all_card[cause_ref];
    const RuleCardMaster* cause_master = rule_card(rules, cause_card.card_id);
    const bool enemy_attack_damage = is_attack_damage && cause_card.player_index != card.player_index;
    if (enemy_attack_damage && card.damage == 0 && damage >= max_hp) {
        card_turn(card).fields.ko_full = true;
    }
    card.damage += damage;
    if (card.damage >= max_hp) {
        card.damage = max_hp;
        CardTurnFields& turn = card_turn(card);
        turn.fields.ko = true;
        turn.fields.ko_cause_ref = cause_ref;
        if (is_attack_damage) turn.fields.ko_attack_damage = true;
        if (enemy_attack_damage) {
            turn.fields.ko_enemy_attack_damage = true;
            if (card.area == kAreaActive) turn.fields.ko_enemy_attack_damage_active = true;
            if (cause_master != nullptr) {
                if (is_ex(*cause_master)) turn.fields.ko_enemy_ex_attack_damage = true;
                if (card_flag(*cause_master, kCardFlagTera)) turn.fields.ko_enemy_terastal_attack_damage = true;
                if (card_flag(*cause_master, kCardFlagN)) turn.fields.ko_enemy_n_attack_damage = true;
                if (card_continual(cause_card).fields.basic_prize_plus1
                    && target_master->evolution_type == 1) turn.fields.ko_prize_plus1 = true;
                if (card_continual(card).fields.no_prize_ex && is_ex(*cause_master)) turn.fields.ko_prize_zero = true;
            }
        }
        if (attack != nullptr) {
            if ((attack->flags & (1u << 15)) != 0) turn.fields.ko_prize_plus1 = true;
            if ((attack->flags & (1u << 16)) != 0) turn.fields.ko_no_damage_and_effect_attack_next_enemy_turn = true;
        }
    }
    if (is_attack_damage) card.take_attack_damage_this_turn += damage;
    if (enemy_attack_damage) {
        pull_trigger(state, runtime, rules, 10, ref, cause_ref, 1);
        if (card.area == kAreaActive) {
            pull_trigger(state, runtime, rules, 11, ref, cause_ref, 1);
            for (gc_i32 i = (gc_i32)runtime.delay_trigger_count - 1; i >= 0; --i) {
                TriggeredAbilityState ta = runtime.delay_triggers[i];
                if (ta.trigger.type == 11 && ta.trigger.subject.card_index == ref) {
                    ta.trigger.object.card_index = cause_ref;
                    ta.trigger.object.move_counter = state.all_card[cause_ref].move_counter;
                    ta.trigger.depth = 1;
                    ta.trigger.value = damage;
                    if (runtime.temporary_trigger_count >= kTriggerCapacity) {
                        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
                        return;
                    }
                    runtime.temporary_triggers[runtime.temporary_trigger_count++] = ta;
                }
            }
        }
    }
    (void)put_damage_counter;
}

__device__ __forceinline__ bool prevent_effect_active(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1 || state.players[player_index].active.count == 0) return false;
    return is_prevent_effect(state, rules, state.players[player_index].active.values[0]);
}

__device__ __forceinline__ bool no_special_condition_card(
    const CardState& card,
    const RuleTableView& rules
) {
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    return card_continual(card).fields.no_special_condition
        || (master != nullptr && master->pokemon_type == 2);
}

__device__ __forceinline__ void effect_poison(
    BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_i32 damage_counter
) {
    if (prevent_effect_active(state, rules, player_index)) return;
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0) return;
    const CardState& card = state.all_card[player.active.values[0]];
    if (no_special_condition_card(card, rules)) return;
    if (player_active_state(player).fields.poison_damage_counter == damage_counter) return;
    state.changed = true;
    player_active_state(player).fields.poison_damage_counter = (gc_i8)damage_counter;
}

__device__ __forceinline__ void effect_burn(BattleCoreState& state, const RuleTableView& rules, gc_i32 player_index) {
    if (prevent_effect_active(state, rules, player_index)) return;
    PlayerState& player = state.players[player_index]; if (player.active.count == 0) return;
    const CardState& card = state.all_card[player.active.values[0]];
    if (no_special_condition_card(card, rules) || player_active_state(player).fields.burned) return;
    state.changed = true; player_active_state(player).fields.burned = true;
}

__device__ __forceinline__ void effect_sleep(BattleCoreState& state, const RuleTableView& rules, gc_i32 player_index) {
    if (prevent_effect_active(state, rules, player_index)) return;
    PlayerState& player = state.players[player_index]; if (player.active.count == 0) return;
    const CardState& card = state.all_card[player.active.values[0]];
    const auto& f = card_continual(card).fields;
    if (f.no_special_condition || f.no_sleep_paralyze_confuse || f.no_sleep) return;
    if (player_active_state(player).fields.bad_status == 1) return;
    state.changed = true; player_active_state(player).fields.bad_status = 1;
}

__device__ __forceinline__ void effect_paralyze(BattleCoreState& state, const RuleTableView& rules, gc_i32 player_index) {
    if (prevent_effect_active(state, rules, player_index)) return;
    PlayerState& player = state.players[player_index]; if (player.active.count == 0) return;
    const CardState& card = state.all_card[player.active.values[0]];
    const auto& f = card_continual(card).fields;
    if (f.no_special_condition || f.no_sleep_paralyze_confuse) return;
    if (player_active_state(player).fields.bad_status == 2) return;
    state.changed = true; player_active_state(player).fields.bad_status = 2;
}

__device__ __forceinline__ void effect_confuse(BattleCoreState& state, const RuleTableView& rules, gc_i32 player_index) {
    if (prevent_effect_active(state, rules, player_index)) return;
    PlayerState& player = state.players[player_index]; if (player.active.count == 0) return;
    const CardState& card = state.all_card[player.active.values[0]];
    const auto& f = card_continual(card).fields;
    if (f.no_special_condition || f.no_sleep_paralyze_confuse) return;
    if (player_active_state(player).fields.bad_status == 3) return;
    state.changed = true; player_active_state(player).fields.bad_status = 3;
}

}  // namespace gpu_cabt
