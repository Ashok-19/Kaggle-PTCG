namespace gpu_cabt {

static constexpr gc_u8 kMainActionIdle = 0;
static constexpr gc_u8 kMainActionPlaySkill = 1;
static constexpr gc_u8 kMainActionAbility = 2;
static constexpr gc_u8 kMainActionRetreatPreRefresh = 3;
static constexpr gc_u8 kMainActionRetreatEnergy = 4;
static constexpr gc_u8 kMainActionRetreatSwitch = 5;
static constexpr gc_u8 kMainActionPostRefresh = 6;
static constexpr gc_u8 kMainActionTurnCycle = 7;
static constexpr gc_u8 kMainActionAttackReady = 8;

__device__ __forceinline__ bool append_turn_play_full(
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    if (runtime.turn_play_count >= kTurnCardCapacity) {
        runtime.error_flags |= kRuntimeErrorTurnHistoryOverflow;
        return false;
    }
    runtime.turn_play[runtime.turn_play_count++] = ref;
    return true;
}

__device__ __forceinline__ void set_main_ability_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 skill_id,
    gc_u8 effect_ref,
    gc_i32 use_player
) {
    clear_ability_full(state, runtime);
    state.effect_state.ability.skill_id = skill_id;
    state.effect_state.ability.effect_card.card_index = effect_ref;
    state.effect_state.ability.effect_card.move_counter =
        effect_ref > 0 && effect_ref < kAllCardCapacity ? state.all_card[effect_ref].move_counter : 0;
    state.effect_state.ability.use_player_index = (gc_i8)use_player;
}

__device__ __forceinline__ gc_u8 in_play_ref_at(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 area,
    gc_i32 index
) {
    if (player_index < 0 || player_index > 1) return 0;
    if (area == kAreaActive) return index == 0 && state.players[player_index].active.count > 0
        ? state.players[player_index].active.values[0] : 0;
    if (area == kAreaBench) return index >= 0 && index < (gc_i32)state.players[player_index].bench.count
        ? state.players[player_index].bench.values[index] : 0;
    if (area == 7) return index >= 0 && index < (gc_i32)state.stadium.count
        ? state.stadium.values[index] : 0;
    return 0;
}

__device__ __forceinline__ void finish_playing_cards_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 player = rule_active_player_index(state);
    clear_ability_full(state, runtime);
    while (state.playing.count > 0) {
        const gc_u8 ref = state.playing.values[0];
        const gc_i32 owner = ref > 0 && ref < kAllCardCapacity ? state.all_card[ref].player_index : player;
        move_card_full(state, runtime, rules, owner, 13, 0, 3, 0, false, false, false, true);
        if (runtime.error_flags != 0) return;
    }
}

__device__ __forceinline__ void finish_main_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    runtime.main_action_stage = kMainActionPostRefresh;
    start_refresh_full(state, runtime, rules);
    if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
    runtime.main_action_active = 0;
    runtime.main_action_stage = kMainActionIdle;
    if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
}

__device__ __forceinline__ bool start_retreat_switch_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    const gc_i32 player = rule_active_player_index(state);
    const PlayerState& ps = state.players[player];
    if (ps.active.count == 0 || ps.bench.count == 0) return false;
    set_select_full(state, runtime, kSelectCard, kSelectContextSwitch, player, 1, 1);
    for (gc_i32 i = 0; i < (gc_i32)ps.bench.count; ++i)
        add_option_card(runtime, kAreaBench, i, player);
    runtime.pending_effect_kind = kPendingMainRetreatSwitch;
    runtime.main_action_stage = kMainActionRetreatSwitch;
    return true;
}

__device__ __forceinline__ bool start_retreat_energy_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 cost
) {
    const gc_i32 player = rule_active_player_index(state);
    if (player < 0 || player > 1 || state.players[player].active.count == 0) return false;
    const gc_u8 active_ref = state.players[player].active.values[0];
    const gc_i32 move_counter = state.all_card[active_ref].move_counter;
    runtime.target_count = 0;
    const PlayerState& ps = state.players[player];
    for (gc_i32 i = 0; i < (gc_i32)ps.energy.count; ++i) {
        const gc_u8 ref = ps.energy.values[i];
        if (state.all_card[ref].attach_move_counter != move_counter) continue;
        if (runtime.target_count >= kAreaRefCapacity) {
            runtime.error_flags |= kRuntimeErrorTargetOverflow;
            return false;
        }
        runtime.targets[runtime.target_count++] = make_area_ref(state, ref);
    }
    state.selected_list.count = 0;
    state.energy_cost = cost;
    state.remain_energy_cost = cost;
    state.selected_energy_card_count = 0;
    state.selecting_energy_pokemon_ref = active_ref;
    RuleEffect effect{};
    if (!begin_next_energy_choice(state, runtime, rules, effect, kSelectContextDiscardEnergy, player)) {
        finish_energy_selection(state, runtime);
        return false;
    }
    runtime.main_action_stage = kMainActionRetreatEnergy;
    return true;
}

__device__ __forceinline__ void continue_retreat_after_pre_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (state.fail_retreat) {
        finish_main_refresh_full(state, runtime, rules);
        return;
    }
    const gc_i32 player = rule_active_player_index(state);
    if (state.players[player].active.count == 0) {
        finish_main_refresh_full(state, runtime, rules);
        return;
    }
    const gc_u8 active_ref = state.players[player].active.values[0];
    const RuleCardMaster* master = rule_card(rules, state.all_card[active_ref].card_id);
    if (master == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 cost = retreat_cost(state.all_card[active_ref], *master);
    if (cost > 0 && start_retreat_energy_full(state, runtime, rules, cost)) return;
    if (runtime.error_flags != 0) return;
    if (start_retreat_switch_full(state, runtime)) return;
    finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void start_retreat_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    const gc_i32 player = rule_active_player_index(state);
    if (player < 0 || player > 1 || state.players[player].active.count == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    state.fail_retreat = 0;
    state_turn(state).fields.retreated = true;
    const gc_u8 active_ref = state.players[player].active.values[0];
    pull_trigger(state, runtime, rules, 19, active_ref, 0, 0);
    if (runtime.error_flags != 0) return;
    runtime.main_action_stage = kMainActionRetreatPreRefresh;
    start_refresh_full(state, runtime, rules);
    if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
    continue_retreat_after_pre_full(state, runtime, rules);
}

__device__ __forceinline__ void execute_main_play_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 hand_index
) {
    const gc_i32 player = rule_active_player_index(state);
    if (hand_index < 0 || hand_index >= (gc_i32)state.players[player].hand.count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 ref = state.players[player].hand.values[hand_index];
    const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
    if (master == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    log_play(state, runtime, player, ref);
    if (runtime.error_flags != 0) return;
    if (master->card_type == 0) {
        move_card_full(state, runtime, rules, player, kAreaHand, hand_index, kAreaBench, 0, false, false, false, true);
        if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
        return;
    }
    if (master->card_type == 4) {
        state_turn(state).fields.stadium_played = true;
        move_card_full(state, runtime, rules, player, kAreaHand, hand_index, 7, 0, false, false, false, true);
        if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
        return;
    }
    if (master->play_skill_id <= 0) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    if (master->card_type == 3) {
        state_turn(state).fields.supporter_played = true;
        if (!append_turn_play_full(runtime, ref)) return;
    }
    if (card_flag(*master, kCardFlagToBench)) {
        move_card_full(state, runtime, rules, player, kAreaHand, hand_index, kAreaBench, 0, false, false, false, true);
        if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
        return;
    }
    const gc_u8 moved = move_card_full(state, runtime, rules, player, kAreaHand, hand_index, 13, 0, false, false, false, true);
    if (runtime.error_flags != 0 || moved == 0) return;
    runtime.main_action_stage = kMainActionPlaySkill;
    set_main_ability_full(state, runtime, master->play_skill_id, moved, player);
    activate_ability_full(state, runtime, rules, 0);
    if (runtime.error_flags != 0 || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) return;
    finish_playing_cards_full(state, runtime, rules);
    if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void execute_main_attach_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const SelectOptionState& option
) {
    const gc_i32 player = rule_active_player_index(state);
    if (option.param0 != kAreaHand || option.param1 < 0
        || option.param1 >= (gc_i32)state.players[player].hand.count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 source_ref = state.players[player].hand.values[option.param1];
    const gc_u8 target_ref = in_play_ref_at(state, player, (gc_u8)option.param2, option.param3);
    if (source_ref == 0 || target_ref == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    attach_proc_full(state, runtime, rules, source_ref, target_ref, false);
    if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void execute_main_evolve_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const SelectOptionState& option
) {
    const gc_i32 player = rule_active_player_index(state);
    if (option.param0 != kAreaHand || option.param1 < 0
        || option.param1 >= (gc_i32)state.players[player].hand.count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 evolve_ref = state.players[player].hand.values[option.param1];
    const gc_u8 target_ref = in_play_ref_at(state, player, (gc_u8)option.param2, option.param3);
    if (evolve_ref == 0 || target_ref == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    evolve_proc_full(state, runtime, rules, evolve_ref, target_ref, true);
    if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void execute_main_ability_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const SelectOptionState& option
) {
    const gc_i32 player = rule_active_player_index(state);
    const gc_u8 ref = in_play_ref_at(state, player, (gc_u8)option.param0, option.param1);
    if (ref == 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
    const RuleSkill* skill = master == nullptr ? nullptr : get_ability(rules, state.all_card[ref], *master);
    if (skill == nullptr) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    runtime.main_action_stage = kMainActionAbility;
    set_main_ability_full(state, runtime, skill->skill_id, ref, player);
    activate_ability_full(state, runtime, rules, 0);
    if (runtime.error_flags != 0 || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) return;
    clear_ability_full(state, runtime);
    finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void execute_main_discard_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const SelectOptionState& option
) {
    const gc_i32 player = rule_active_player_index(state);
    move_card_full(state, runtime, rules, player, (gc_u8)option.param0, option.param1,
                   3, 0, false, false, false);
    if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void start_selected_main_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (state.select_type != kSelectMain || !validate_selected_response(state, runtime)) return;
    const SelectOptionState* selected_ptr = first_selected_option(runtime);
    if (selected_ptr == nullptr) return;
    const SelectOptionState selected = *selected_ptr;
    clear_select_full(state, runtime);
    runtime.main_action_active = 1;
    runtime.main_action_stage = kMainActionIdle;
    ++state.turn_action_count;

    if (selected.type == kOptionEnd) {
        runtime.main_action_stage = kMainActionTurnCycle;
        start_turn_end_full(state, runtime, rules);
        if (runtime.error_flags != 0 || runtime.turn_cycle_active) return;
        runtime.main_action_active = 0;
        runtime.main_action_stage = kMainActionIdle;
        if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
        return;
    }
    if (selected.type == kOptionAttack) {
        runtime.main_attack_id = selected.param0;
        runtime.main_src_attack_id = selected.param1;
        runtime.main_attack_bench_index = selected.param2;
        runtime.main_action_stage = kMainActionAttackReady;
        return;
    }
    if (selected.type == kOptionPlay) execute_main_play_full(state, runtime, rules, selected.param0);
    else if (selected.type == kOptionAttach) execute_main_attach_full(state, runtime, rules, selected);
    else if (selected.type == kOptionEvolve) execute_main_evolve_full(state, runtime, rules, selected);
    else if (selected.type == kOptionAbility) execute_main_ability_full(state, runtime, rules, selected);
    else if (selected.type == kOptionDiscard) execute_main_discard_full(state, runtime, rules, selected);
    else if (selected.type == kOptionRetreat) start_retreat_full(state, runtime, rules);
    else runtime.error_flags |= kRuntimeErrorInvalidSelection;
}

__device__ __forceinline__ void resume_main_action_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.main_action_active || runtime.error_flags != 0) return;
    const gc_u8 stage = runtime.main_action_stage;
    if (stage == kMainActionAttackReady) return;

    if (stage == kMainActionTurnCycle) {
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

    if (stage == kMainActionPostRefresh || stage == kMainActionRetreatPreRefresh) {
        if (!runtime.refresh_process_active) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        resume_refresh_full(state, runtime, rules);
        if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
        if (stage == kMainActionRetreatPreRefresh) {
            continue_retreat_after_pre_full(state, runtime, rules);
            return;
        }
        runtime.main_action_active = 0;
        runtime.main_action_stage = kMainActionIdle;
        if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
        return;
    }

    if (stage == kMainActionPlaySkill || stage == kMainActionAbility) {
        if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) {
            resume_effect_selection_full(state, runtime, rules, 0);
            if (runtime.error_flags != 0 || state.select_type != kSelectNone
                || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) return;
        } else if (runtime.effect_execution_active) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        if (stage == kMainActionPlaySkill) finish_playing_cards_full(state, runtime, rules);
        else clear_ability_full(state, runtime);
        if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
        return;
    }

    if (stage == kMainActionRetreatEnergy) {
        RuleEffect effect{};
        if (!validate_selected_response(state, runtime)) return;
        if (resume_energy_selection(state, runtime, rules, effect)) return;
        if (runtime.error_flags != 0) return;
        if (start_retreat_switch_full(state, runtime)) return;
        finish_main_refresh_full(state, runtime, rules);
        return;
    }

    if (stage == kMainActionRetreatSwitch) {
        if (runtime.pending_effect_kind != kPendingMainRetreatSwitch
            || !validate_selected_response(state, runtime)) return;
        const SelectOptionState* option = first_selected_option(runtime);
        if (option == nullptr || option->type != kOptionCard) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_i32 player = rule_active_player_index(state);
        const gc_u8 ref = option_card_ref(state, *option);
        const gc_i32 bench_index = ref == 0 ? -1 : current_area_index(state.players[player], kAreaBench, ref);
        clear_select_full(state, runtime);
        runtime.pending_effect_kind = kPendingNone;
        if (bench_index < 0) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        switch_pokemon_full(state, runtime, rules, player, bench_index);
        state.selected_list.count = 0;
        runtime.target_count = 0;
        if (runtime.error_flags == 0) finish_main_refresh_full(state, runtime, rules);
        return;
    }

    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
}

}  // namespace gpu_cabt
