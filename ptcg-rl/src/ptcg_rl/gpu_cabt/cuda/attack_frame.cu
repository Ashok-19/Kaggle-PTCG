namespace gpu_cabt {

static constexpr gc_u8 kMainActionAttackSpecialChoice = 9;
static constexpr gc_u8 kMainActionAttackPreEffects = 10;
static constexpr gc_u8 kMainActionAttackPostEffects = 11;
static constexpr gc_u8 kMainActionAttackSupporter = 12;
static constexpr gc_u8 kMainActionAttackAfterTriggers = 13;
static constexpr gc_u8 kMainActionAttackPreRefreshActive = 14;
static constexpr gc_u8 kMainActionAttackAfterRefresh = 15;
static constexpr gc_u8 kMainActionAttackDoubleChoice = 16;
static constexpr gc_u8 kMainActionAttackTurnCycle = 17;
static constexpr gc_u16 kPendingAttackSpecialChoiceLocal = 31;
static constexpr gc_u16 kPendingAttackDoubleChoiceLocal = 32;

__device__ __forceinline__ bool attack_frame_waiting(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime
) {
    return state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone
        || runtime.effect_execution_active || runtime.trigger_resolution_active
        || runtime.trigger_activation_waiting || runtime.refresh_process_active
        || runtime.ko_process_active || runtime.turn_cycle_active;
}

__device__ __forceinline__ void finish_attack_to_next_main_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    state.current_attack_id = 0;
    state.attacker = 0;
    runtime.main_action_stage = kMainActionAttackTurnCycle;
    start_turn_end_full(state, runtime, rules);
    if (runtime.error_flags != 0 || runtime.turn_cycle_active) return;
    runtime.main_action_active = 0;
    runtime.main_action_stage = kMainActionIdle;
    if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
}

__device__ __forceinline__ void begin_attack_after_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
);

__device__ __forceinline__ bool begin_attack_pre_refresh_active_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    const gc_i32 active_player = rule_active_player_index(state);
    while (runtime.refresh_cursor < 2) {
        const gc_i32 player = runtime.refresh_cursor == 0 ? 1 - active_player : active_player;
        if (begin_refresh_active_selection(state, runtime, player)) return true;
        ++runtime.refresh_cursor;
    }
    return false;
}

__device__ __forceinline__ void start_attack_full_refresh(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    runtime.refresh_cursor = 0;
    runtime.main_action_stage = kMainActionAttackAfterRefresh;
    start_refresh_full(state, runtime, rules);
    if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
    begin_attack_after_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void continue_attack_pre_refresh_active_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (begin_attack_pre_refresh_active_full(state, runtime)) return;
    start_attack_full_refresh(state, runtime, rules);
}

__device__ __forceinline__ void start_attack_pre_refresh_active_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    refresh_effect(state, runtime, rules, 0);
    if (runtime.error_flags != 0) return;
    runtime.main_action_stage = kMainActionAttackPreRefreshActive;
    runtime.refresh_cursor = 0;
    continue_attack_pre_refresh_active_full(state, runtime, rules);
}

__device__ __forceinline__ void continue_after_attack_triggers_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 guard = 0; guard < 256; ++guard) {
        if (runtime.error_flags != 0) return;
        if (runtime.trigger_count + runtime.temporary_trigger_count == 0) {
            start_attack_pre_refresh_active_full(state, runtime, rules);
            return;
        }
        refresh_effect(state, runtime, rules, 0);
        if (runtime.error_flags != 0) return;
        resolve_trigger_stack_full(state, runtime, rules, 0);
        if (runtime.error_flags != 0 || runtime.trigger_resolution_active
            || runtime.trigger_activation_waiting || runtime.effect_execution_active
            || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ void start_after_attack_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    state.attack_damage_change = 0;
    state.post_attack_effect = 0;
    state.post_effect_activate = 0;
    state.fail_attack = 0;
    clear_ability_full(state, runtime);
    runtime.main_action_stage = kMainActionAttackAfterTriggers;
    continue_after_attack_triggers_full(state, runtime, rules);
}

__device__ __forceinline__ bool pre_effect_can_create_damage(const RuleEffect& effect) {
    const gc_u8 type = effect.effect_type;
    return type == 73 || type == 74 || type == 76 || type == 78
        || type == 80 || type == 81 || type == 82 || type == 83
        || type == 84 || type == 85 || type == 86 || type == 88
        || type == 90 || type == 91 || type == 92 || type == 93
        || type == 94 || type == 95;
}

__device__ __forceinline__ void attack_damage_phase_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (state.fail_attack) return;
    const gc_i32 player = rule_active_player_index(state);
    const PlayerState& enemy = state.players[1 - player];
    if (enemy.active.count == 0 || state.attacker == 0) return;
    refresh_effect(state, runtime, rules, 0);
    if (runtime.error_flags != 0) return;
    const RuleAttack* attack = rule_attack(rules, state.current_attack_id);
    if (attack == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_u8 target_ref = enemy.active.values[0];
    const gc_u8 attacker_ref = state.attacker;
    gc_i32 base_damage = attack->damage + state.attack_damage_change;
    bool calculate = base_damage > 0;
    if (!calculate && attack->pre_effect_offset >= 0
        && attack->pre_effect_offset + attack->pre_effect_count <= rules.effect_count) {
        for (gc_i32 i = 0; i < attack->pre_effect_count; ++i) {
            if (pre_effect_can_create_damage(rules.effects[attack->pre_effect_offset + i])) {
                calculate = true;
                break;
            }
        }
    }
    if (!calculate) return;
    const CardState& attacker = state.all_card[attacker_ref];
    const RuleCardMaster* attacker_master = rule_card(rules, attacker.card_id);
    if (attacker_master == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    if (card_this_turn(attacker).fields.damage_change_my_attack != 0
        && master_has_attack(*attacker_master, attack->attack_id)) {
        base_damage += card_this_turn(attacker).fields.damage_change_my_attack;
    }
    const gc_i32 damage = calc_damage_full(
        state, rules, base_damage, target_ref, attacker_ref, true, attack
    );
    state.last_attack_damage = damage;
    if (card_continual(state.all_card[target_ref]).fields.no_damage_coin && damage > 0) {
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count != 0 && !attack_flag(attack, 5)) return;
    }
    add_damage_full(state, runtime, rules, target_ref, damage, true, attacker_ref, false, attack);
    if (runtime.error_flags == 0) after_damage_full(state, runtime, rules, target_ref, attacker_ref);
}

__device__ __forceinline__ void start_attack_post_effects_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    state.post_attack_effect = 1;
    runtime.main_action_stage = kMainActionAttackPostEffects;
    start_effect_execution(state, runtime, rules, 0, 0);
    if (runtime.error_flags != 0 || runtime.effect_execution_active
        || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
    start_after_attack_full(state, runtime, rules);
}

__device__ __forceinline__ void start_attack_pre_effects_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    clear_ability_full(state, runtime);
    state.effect_state.ability.effect_card.card_index = state.attacker;
    state.effect_state.ability.effect_card.move_counter =
        state.attacker > 0 ? state.all_card[state.attacker].move_counter : 0;
    state.effect_state.ability.use_player_index = (gc_i8)rule_active_player_index(state);
    state.post_attack_effect = 0;
    runtime.main_action_stage = kMainActionAttackPreEffects;
    start_effect_execution(state, runtime, rules, 0, 0);
    if (runtime.error_flags != 0 || runtime.effect_execution_active
        || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
    attack_damage_phase_full(state, runtime, rules);
    if (runtime.error_flags == 0) start_attack_post_effects_full(state, runtime, rules);
}

__device__ __forceinline__ bool attack_option_exists(const BattleRuntimeState& runtime, gc_i32 attack_id) {
    for (gc_i32 i = 0; i < (gc_i32)runtime.option_count; ++i)
        if (runtime.options[i].type == kOptionAttack && runtime.options[i].param0 == attack_id) return true;
    return false;
}

__device__ __forceinline__ bool begin_attack_choice_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 source_attack_id,
    bool optional
) {
    if (runtime.option_count == 0) {
        clear_select_full(state, runtime);
        return false;
    }
    state.select_type = kSelectAttack;
    state.select_context = kSelectContextAttack;
    state.select_player = (gc_i8)rule_active_player_index(state);
    state.select_min = optional ? 0 : 1;
    state.select_max = 1;
    runtime.pending_effect_kind = kPendingAttackSpecialChoiceLocal;
    runtime.pending_effect_arg0 = source_attack_id;
    runtime.main_action_stage = kMainActionAttackSpecialChoice;
    return true;
}

__device__ __forceinline__ void special_attack_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
);

__device__ __forceinline__ void selected_attack2_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (++state.turn_attack_count > 10000) {
        start_after_attack_full(state, runtime, rules);
        return;
    }
    const RuleAttack* attack = rule_attack(rules, state.current_attack_id);
    if (attack == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    if (attack_flag(attack, 2)) {
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count == 0) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
    }
    special_attack_proc_full(state, runtime, rules);
}

__device__ __forceinline__ void pre_confuse_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 player = rule_active_player_index(state);
    const PlayerState& ps = state.players[player];
    if (ps.active.count > 0 && ps.active.values[0] == state.attacker
        && player_active_state(ps).fields.bad_status == 3) {
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count == 0) {
            add_damage_full(state, runtime, rules, state.attacker, 30, false,
                            state.attacker, false, nullptr);
            if (runtime.error_flags == 0) start_after_attack_full(state, runtime, rules);
            return;
        }
    }
    selected_attack2_full(state, runtime, rules);
}

__device__ __forceinline__ void begin_selected_attack_id_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 attack_id,
    gc_i32 source_attack_id
) {
    const RuleAttack* attack = rule_attack(rules, attack_id);
    if (attack == nullptr || state.attacker == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const CardState& attacker = state.all_card[state.attacker];
    if (!satisfy_attack_state_condition_full(state, rules, attacker, *attack, source_attack_id)) {
        start_after_attack_full(state, runtime, rules);
        return;
    }
    state.current_attack_id = attack_id;
    selected_attack2_full(state, runtime, rules);
}

__device__ __forceinline__ void special_attack_proc_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const RuleAttack* source = rule_attack(rules, state.current_attack_id);
    if (source == nullptr || state.attacker == 0) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 source_id = source->attack_id;
    const gc_i32 player = rule_active_player_index(state);

    if (attack_flag(source, 11)) {
        PlayerState& ps = state.players[player];
        if (ps.deck.count == 0) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
        const gc_u8 ref = move_card_full(state, runtime, rules, player, kAreaDeck,
            (gc_i32)ps.deck.count - 1, 3, 0, false, false, false);
        if (runtime.error_flags != 0 || ref == 0) return;
        const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
        runtime.option_count = 0;
        runtime.selected_count = 0;
        if (master != nullptr && is_not_rule_pokemon_card(*master)) {
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i)
                if (master->attack_ids[i] > 0)
                    add_option_attack(runtime, master->attack_ids[i], source_id, -1);
        }
        if (!begin_attack_choice_full(state, runtime, source_id, false))
            start_after_attack_full(state, runtime, rules);
        return;
    }

    if (attack_flag(source, 3)) {
        runtime.option_count = 0;
        runtime.selected_count = 0;
        const PlayerState& ps = state.players[player];
        for (gc_i32 bi = 0; bi < (gc_i32)ps.bench.count; ++bi) {
            const RuleCardMaster* master = rule_card(rules, state.all_card[ps.bench.values[bi]].card_id);
            if (master == nullptr || !card_flag(*master, kCardFlagN)) continue;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const RuleAttack* candidate = master->attack_ids[i] > 0
                    ? rule_attack(rules, master->attack_ids[i]) : nullptr;
                if (candidate != nullptr && !attack_flag(candidate, 3))
                    add_option_attack(runtime, candidate->attack_id, source_id, -1);
            }
        }
        if (!begin_attack_choice_full(state, runtime, source_id, false))
            start_after_attack_full(state, runtime, rules);
        return;
    }

    if (attack_flag(source, 0) || attack_flag(source, 2) || attack_flag(source, 1)) {
        const PlayerState& enemy = state.players[1 - player];
        if (enemy.active.count == 0) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
        const RuleCardMaster* master = rule_card(rules, state.all_card[enemy.active.values[0]].card_id);
        if (master == nullptr || (attack_flag(source, 1) && !card_flag(*master, kCardFlagTera))) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
        runtime.option_count = 0;
        runtime.selected_count = 0;
        for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
            const RuleAttack* candidate = master->attack_ids[i] > 0
                ? rule_attack(rules, master->attack_ids[i]) : nullptr;
            if (candidate == nullptr) continue;
            if (attack_flag(source, 0) && attack_flag(candidate, 0)) continue;
            add_option_attack(runtime, candidate->attack_id, source_id, -1);
        }
        if (!begin_attack_choice_full(state, runtime, source_id, false))
            start_after_attack_full(state, runtime, rules);
        return;
    }

    if (attack_flag(source, 4)) {
        const gc_i32 enemy_player = 1 - player;
        PlayerState& enemy = state.players[enemy_player];
        runtime.option_count = 0;
        runtime.selected_count = 0;
        for (gc_i32 n = 0; n < 10 && enemy.deck.count > 0; ++n) {
            const gc_u8 ref = move_card_full(state, runtime, rules, enemy_player, kAreaDeck,
                (gc_i32)enemy.deck.count - 1, 12, 0, false, false, false);
            if (runtime.error_flags != 0 || ref == 0) return;
            const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
            if (master == nullptr || master->card_type != 0) continue;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const gc_i32 attack_id = master->attack_ids[i];
                if (attack_id > 0 && !attack_option_exists(runtime, attack_id))
                    add_option_attack(runtime, attack_id, source_id, -1);
            }
        }
        while (state.looking.count > 0) {
            move_card_full(state, runtime, rules, enemy_player, 12, 0, kAreaDeck,
                           0, false, false, false);
            if (runtime.error_flags != 0) return;
        }
        shuffle_player_deck(state, runtime, enemy_player);
        if (!begin_attack_choice_full(state, runtime, source_id, true))
            start_after_attack_full(state, runtime, rules);
        return;
    }

    if (attack_flag(source, 12)) {
        PlayerState& ps = state.players[player];
        if (ps.deck.count == 0) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
        const gc_u8 ref = move_card_full(state, runtime, rules, player, kAreaDeck,
            (gc_i32)ps.deck.count - 1, 3, 0, false, false, false);
        if (runtime.error_flags != 0 || ref == 0) return;
        const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
        const RuleSkill* skill = master != nullptr && master->card_type == 3
            ? rule_skill(rules, master->play_skill_id) : nullptr;
        if (skill == nullptr) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
        set_main_ability_full(state, runtime, skill->skill_id, state.attacker, player);
        if (!satisfy_skill_condition(state, runtime, rules, *skill, state.attacker,
                                     player, skill->trigger_start_index)) {
            clear_ability_full(state, runtime);
            start_after_attack_full(state, runtime, rules);
            return;
        }
        runtime.main_action_stage = kMainActionAttackSupporter;
        activate_ability_full(state, runtime, rules, 0);
        if (runtime.error_flags != 0 || runtime.effect_execution_active
            || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
        clear_ability_full(state, runtime);
        start_after_attack_full(state, runtime, rules);
        return;
    }

    state.turn_histories[0].turn_attack_id = state.src_attack_id;
    state.turn_histories[0].turn_attack_card = state.attacker;
    start_attack_pre_effects_full(state, runtime, rules);
}

__device__ __forceinline__ bool can_double_attack_option_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 attacker_ref,
    const RuleAttack& attack
) {
    if (!enough_energy(state, rules, attacker_ref, attack)) return false;
    if (!can_attack_card_full(state, rules, attacker_ref)) return false;
    if (attack.damage == 0 && !attack_flag(&attack, 19)
        && !satisfy_attack_effect_condition_full(state, runtime, rules, attacker_ref, attack)) return false;
    return true;
}

__device__ __forceinline__ void begin_attack_after_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (state.second_attack) {
        state.second_attack = 0;
        finish_attack_to_next_main_full(state, runtime, rules);
        return;
    }
    const gc_i32 player = rule_active_player_index(state);
    const PlayerState& ps = state.players[player];
    if (ps.active.count > 0 && ps.active.values[0] == state.attacker) {
        const gc_u8 active_ref = ps.active.values[0];
        const CardState& card = state.all_card[active_ref];
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        const gc_u8 status = player_active_state(ps).fields.bad_status;
        if (master != nullptr && card_continual(card).fields.double_attack
            && status != 1 && status != 2 && master_has_attack(*master, state.current_attack_id)) {
            runtime.option_count = 0;
            runtime.selected_count = 0;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const RuleAttack* candidate = master->attack_ids[i] > 0
                    ? rule_attack(rules, master->attack_ids[i]) : nullptr;
                if (candidate != nullptr && can_double_attack_option_full(
                        state, runtime, rules, active_ref, *candidate))
                    add_option_attack(runtime, candidate->attack_id, 0, -1);
            }
            if (runtime.option_count > 0) {
                set_select_full(state, runtime, kSelectAttack, kSelectContextAttack, player, 0, 1);
                for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                    const RuleAttack* candidate = master->attack_ids[i] > 0
                        ? rule_attack(rules, master->attack_ids[i]) : nullptr;
                    if (candidate != nullptr && can_double_attack_option_full(
                            state, runtime, rules, active_ref, *candidate))
                        add_option_attack(runtime, candidate->attack_id, 0, -1);
                }
                runtime.pending_effect_kind = kPendingAttackDoubleChoiceLocal;
                runtime.main_action_stage = kMainActionAttackDoubleChoice;
                return;
            }
        }
    }
    finish_attack_to_next_main_full(state, runtime, rules);
}

__device__ __forceinline__ void start_attack_from_main_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.main_action_active || runtime.main_action_stage != kMainActionAttackReady) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 player = rule_active_player_index(state);
    PlayerState& ps = state.players[player];
    gc_u8 attacker_ref = ps.active.count > 0 ? ps.active.values[0] : 0;
    if (runtime.main_attack_bench_index >= 0) {
        if (runtime.main_attack_bench_index >= (gc_i32)ps.bench.count) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        attacker_ref = ps.bench.values[runtime.main_attack_bench_index];
    }
    const RuleAttack* attack = rule_attack(rules, runtime.main_attack_id);
    if (attacker_ref == 0 || attack == nullptr
        || !can_attack_card_full(state, rules, attacker_ref)
        || !satisfy_attack_state_condition_full(
            state, rules, state.all_card[attacker_ref], *attack,
            runtime.main_src_attack_id)) {
        start_after_attack_full(state, runtime, rules);
        return;
    }
    state.current_attack_id = attack->attack_id;
    state.src_attack_id = runtime.main_src_attack_id == 0
        ? attack->attack_id : runtime.main_src_attack_id;
    state.attacker = attacker_ref;
    state.post_effect_activate = 0;
    state.fail_attack = 0;
    state.last_attack_damage = 0;
    state.turn_attack_count = 0;

    const CardNextTurnFields& turn = card_this_turn(state.all_card[attacker_ref]);
    if (turn.fields.attack_coin2) {
        select_coin_full(state, runtime, 2);
        if (state.coin_head_count < 2) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
    } else if (turn.fields.attack_coin) {
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count < 1) {
            start_after_attack_full(state, runtime, rules);
            return;
        }
    }
    pre_confuse_proc_full(state, runtime, rules);
}

__device__ __forceinline__ void resume_attack_special_choice_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingAttackSpecialChoiceLocal
        || state.select_type != kSelectAttack
        || (gc_i32)runtime.selected_count < state.select_min
        || (gc_i32)runtime.selected_count > state.select_max) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_i32 source_id = runtime.pending_effect_arg0;
    if (runtime.selected_count == 0) {
        clear_select_full(state, runtime);
        runtime.pending_effect_kind = kPendingNone;
        start_after_attack_full(state, runtime, rules);
        return;
    }
    const SelectOptionState* option = first_selected_option(runtime);
    if (option == nullptr || option->type != kOptionAttack) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_i32 attack_id = option->param0;
    clear_select_full(state, runtime);
    runtime.pending_effect_kind = kPendingNone;
    begin_selected_attack_id_full(state, runtime, rules, attack_id, source_id);
}

__device__ __forceinline__ void resume_attack_double_choice_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingAttackDoubleChoiceLocal
        || state.select_type != kSelectAttack
        || (gc_i32)runtime.selected_count < state.select_min
        || (gc_i32)runtime.selected_count > state.select_max) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    if (runtime.selected_count == 0) {
        clear_select_full(state, runtime);
        runtime.pending_effect_kind = kPendingNone;
        finish_attack_to_next_main_full(state, runtime, rules);
        return;
    }
    const SelectOptionState* option = first_selected_option(runtime);
    if (option == nullptr || option->type != kOptionAttack) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_i32 attack_id = option->param0;
    clear_select_full(state, runtime);
    runtime.pending_effect_kind = kPendingNone;
    const RuleAttack* attack = rule_attack(rules, attack_id);
    if (attack == nullptr || state.attacker == 0
        || !satisfy_attack_state_condition_full(
            state, rules, state.all_card[state.attacker], *attack, 0)) {
        finish_attack_to_next_main_full(state, runtime, rules);
        return;
    }
    state.second_attack = 1;
    state.current_attack_id = attack_id;
    selected_attack2_full(state, runtime, rules);
}

__device__ __forceinline__ void resume_attack_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.main_action_active || runtime.error_flags != 0) return;
    const gc_u8 stage = runtime.main_action_stage;
    if (stage == kMainActionAttackReady) {
        start_attack_from_main_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackSpecialChoice) {
        resume_attack_special_choice_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackDoubleChoice) {
        resume_attack_double_choice_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackPreEffects || stage == kMainActionAttackPostEffects
        || stage == kMainActionAttackSupporter) {
        if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) {
            resume_effect_selection_full(state, runtime, rules, 0);
            if (runtime.error_flags != 0 || runtime.effect_execution_active
                || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
        }
        if (stage == kMainActionAttackPreEffects) {
            attack_damage_phase_full(state, runtime, rules);
            if (runtime.error_flags == 0) start_attack_post_effects_full(state, runtime, rules);
        } else if (stage == kMainActionAttackPostEffects) {
            start_after_attack_full(state, runtime, rules);
        } else {
            clear_ability_full(state, runtime);
            start_after_attack_full(state, runtime, rules);
        }
        return;
    }
    if (stage == kMainActionAttackAfterTriggers) {
        if (runtime.pending_effect_kind == kPendingTriggerOrder) {
            resume_trigger_order_full(state, runtime, rules);
        } else if (runtime.trigger_activation_waiting || runtime.effect_execution_active
                   || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) {
            if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone)
                resume_effect_selection_full(state, runtime, rules, 0);
            continue_trigger_activation_full(state, runtime, rules);
        }
        if (runtime.error_flags != 0 || runtime.trigger_resolution_active
            || runtime.trigger_activation_waiting || runtime.effect_execution_active
            || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return;
        continue_after_attack_triggers_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackPreRefreshActive) {
        if (state.select_type != kSelectNone) {
            if (runtime.pending_effect_kind != kPendingRefreshActive) {
                runtime.error_flags |= kRuntimeErrorInvalidSelection;
                return;
            }
            resume_refresh_active_selection(state, runtime, rules);
            if (runtime.error_flags != 0) return;
        }
        continue_attack_pre_refresh_active_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackAfterRefresh) {
        if (!runtime.refresh_process_active) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        resume_refresh_full(state, runtime, rules);
        if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
        begin_attack_after_refresh_full(state, runtime, rules);
        return;
    }
    if (stage == kMainActionAttackTurnCycle) {
        if (!runtime.turn_cycle_active) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        resume_turn_cycle_full(state, runtime, rules);
        if (runtime.error_flags != 0 || runtime.turn_cycle_active) return;
        runtime.main_action_active = 0;
        runtime.main_action_stage = kMainActionIdle;
        if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
        return;
    }
    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
}

}  // namespace gpu_cabt
