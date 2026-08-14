namespace gpu_cabt {

static constexpr gc_u8 kTurnCycleIdle = 0;
static constexpr gc_u8 kTurnCycleAfterEndRefresh = 1;
static constexpr gc_u8 kTurnCycleAfterEnd2Refresh = 2;
static constexpr gc_u8 kTurnCycleAfterCheckupRefresh = 3;
static constexpr gc_u8 kTurnCycleAfterCheckupEndRefresh = 4;
static constexpr gc_u8 kTurnCycleAfterStartRefresh = 5;
static constexpr gc_u8 kTurnCycleDone = 6;

__device__ __forceinline__ bool push_temp_trigger_turn_cycle(
    BattleRuntimeState& runtime,
    const TriggeredAbilityState& trigger
) {
    if (runtime.temporary_trigger_count >= kTriggerCapacity) {
        runtime.error_flags |= kRuntimeErrorTriggerOverflow;
        return false;
    }
    runtime.temporary_triggers[runtime.temporary_trigger_count++] = trigger;
    return true;
}

__device__ __forceinline__ void remove_delay_trigger_at(
    BattleRuntimeState& runtime,
    gc_i32 index
) {
    if (index < 0 || index >= (gc_i32)runtime.delay_trigger_count) return;
    for (gc_i32 i = index + 1; i < (gc_i32)runtime.delay_trigger_count; ++i)
        runtime.delay_triggers[i - 1] = runtime.delay_triggers[i];
    --runtime.delay_trigger_count;
}

__device__ __forceinline__ void collect_turn_end_delayed_triggers(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    const gc_u8 player_ref = (gc_u8)(1 + player_index);
    for (gc_i32 i = (gc_i32)runtime.delay_trigger_count - 1; i >= 0; --i) {
        const TriggeredAbilityState trigger = runtime.delay_triggers[i];
        const gc_u8 effect_ref = trigger.activate.effect_card.card_index;
        if (effect_ref == 0 || effect_ref >= kAllCardCapacity) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }
        const gc_i32 effect_player = state.all_card[effect_ref].player_index;
        if (effect_player != player_index) {
            if (trigger.trigger.type == 1 && !push_temp_trigger_turn_cycle(runtime, trigger)) return;
            remove_delay_trigger_at(runtime, i);
        } else if (trigger.trigger.type == 1
            && trigger.trigger.subject.card_index == player_ref) {
            if (!push_temp_trigger_turn_cycle(runtime, trigger)) return;
            remove_delay_trigger_at(runtime, i);
        }
    }
}

__device__ __forceinline__ void card_turn_end_full(
    CardState& card,
    gc_i32 active_player
) {
    for (gc_i32 i = 0; i < 3; ++i) card.turn_state[i] = 0;
    card.ability_used.count = 0;
    for (gc_i32 i = 0; i < 4; ++i) card.this_turn[i] = 0;
    card.this_turn_enemy[0] = 0;
    if (card.player_index != active_player) {
        card.next_enemy_turn_end_state = 0;
        card.next_enemy_turn_end_state_battle_field = 0;
    }
}

__device__ __forceinline__ void player_turn_end_full(PlayerState& player) {
    player.turn_state = 0;
    player.this_turn = 0;
}

__device__ __forceinline__ void turn_end_state_roll_full(
    BattleCoreState& state,
    gc_i32 active_player
) {
    state.turn_state = 0;
    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i)
        card_turn_end_full(state.all_card[state.stadium.values[i]], active_player);
    const gc_i32 first = state.first_player == 1 ? 1 : 0;
    for (gc_i32 order = 0; order < 2; ++order) {
        const gc_i32 p = order == 0 ? first : 1 - first;
        PlayerState& player = state.players[p];
        player_turn_end_full(player);
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
            card_turn_end_full(state.all_card[player.active.values[i]], active_player);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
            card_turn_end_full(state.all_card[player.bench.values[i]], active_player);
    }
}

__device__ __forceinline__ void trash_turn_end_attached_cards(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    if (!state_continual(state).fields.no_tool_effect) {
        for (gc_i32 i = (gc_i32)player.tool.count - 1; i >= 0; --i) {
            const gc_u8 ref = player.tool.values[i];
            const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
            if (master != nullptr && card_flag(*master, kCardFlagTrashMyTurnEnd)) {
                move_card_full(state, runtime, rules, player_index, 9, i, 3, 0, false, false, false);
                if (runtime.error_flags != 0) return;
            }
        }
    }
    for (gc_i32 i = (gc_i32)player.energy.count - 1; i >= 0; --i) {
        const gc_u8 ref = player.energy.values[i];
        const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
        if (master != nullptr && card_flag(*master, kCardFlagTrashMyTurnEnd)) {
            move_card_full(state, runtime, rules, player_index, 8, i, 3, 0, false, false, false);
            if (runtime.error_flags != 0) return;
        }
    }
}

__device__ __forceinline__ void card_turn_start_full(
    CardState& card,
    gc_i32 active_player
) {
    card.take_attack_damage_pre_turn = card.take_attack_damage_this_turn;
    card.take_attack_damage_this_turn = 0;
    if (card.player_index == active_player) {
        for (gc_i32 i = 0; i < 4; ++i) {
            card.this_turn[i] = card.next_turn[i];
            card.next_turn[i] = 0;
        }
    } else {
        card.this_turn_enemy[0] = card.next_turn_enemy[0];
        card.next_turn_enemy[0] = 0;
    }
}

__device__ __forceinline__ void player_turn_start_full(
    PlayerState& player,
    gc_i32 active_player
) {
    if (player.player_index == active_player) {
        player.this_turn = player.next_turn;
        player.next_turn = 0;
    }
}

__device__ __forceinline__ void turn_start_state_roll_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    ++state.turn;
    state.turn_action_count = 0;
    const gc_i32 active_player = rule_active_player_index(state);
    state.phase = 1;
    runtime.turn_used_skill_count = 0;
    runtime.turn_play_count = 0;
    runtime.turn_heal_count = 0;
    runtime.turn_evolve_count = 0;
    state.turn_histories[2] = state.turn_histories[1];
    state.turn_histories[1] = state.turn_histories[0];
    state.turn_histories[0] = {};
    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i)
        card_turn_start_full(state.all_card[state.stadium.values[i]], active_player);
    const gc_i32 first = state.first_player == 1 ? 1 : 0;
    for (gc_i32 order = 0; order < 2; ++order) {
        const gc_i32 p = order == 0 ? first : 1 - first;
        PlayerState& player = state.players[p];
        player_turn_start_full(player, active_player);
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
            card_turn_start_full(state.all_card[player.active.values[i]], active_player);
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
            card_turn_start_full(state.all_card[player.bench.values[i]], active_player);
    }
}

__device__ __forceinline__ bool any_checkup_condition(const BattleCoreState& state) {
    for (gc_i32 p = 0; p < 2; ++p)
        if (player_has_checkup_condition(state.players[p])) return true;
    return false;
}

__device__ __forceinline__ void start_embedded_refresh(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 next_stage
) {
    runtime.turn_cycle_stage = next_stage;
    start_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ bool turn_cycle_waiting(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime
) {
    return runtime.refresh_process_active || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active
        || runtime.trigger_resolution_active || runtime.trigger_activation_waiting
        || runtime.ko_process_active;
}

__device__ __forceinline__ void continue_turn_cycle_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 guard = 0; guard < 64; ++guard) {
        if (!runtime.turn_cycle_active || runtime.error_flags != 0) return;
        if (turn_cycle_waiting(state, runtime)) return;

        if (runtime.turn_cycle_stage == kTurnCycleAfterEndRefresh) {
            if (finish_check_full(state, runtime)) {
                runtime.turn_cycle_stage = kTurnCycleDone;
                continue;
            }
            const gc_i32 active_player = rule_active_player_index(state);
            turn_end_state_roll_full(state, active_player);
            trash_turn_end_attached_cards(state, runtime, rules, active_player);
            if (runtime.error_flags != 0) return;
            start_embedded_refresh(state, runtime, rules, kTurnCycleAfterEnd2Refresh);
            if (turn_cycle_waiting(state, runtime)) return;
            continue;
        }

        if (runtime.turn_cycle_stage == kTurnCycleAfterEnd2Refresh) {
            if (finish_check_full(state, runtime)) {
                runtime.turn_cycle_stage = kTurnCycleDone;
                continue;
            }
            state.phase = 2;
            pull_trigger(state, runtime, rules, 2, 0, 0, 0);
            if (runtime.error_flags != 0) return;
            if (any_checkup_condition(state) && !append_special_condition_trigger(runtime)) return;
            start_embedded_refresh(state, runtime, rules, kTurnCycleAfterCheckupRefresh);
            if (turn_cycle_waiting(state, runtime)) return;
            continue;
        }

        if (runtime.turn_cycle_stage == kTurnCycleAfterCheckupRefresh) {
            if (finish_check_full(state, runtime)) {
                runtime.turn_cycle_stage = kTurnCycleDone;
                continue;
            }
            state.phase = 3;
            start_embedded_refresh(state, runtime, rules, kTurnCycleAfterCheckupEndRefresh);
            if (turn_cycle_waiting(state, runtime)) return;
            continue;
        }

        if (runtime.turn_cycle_stage == kTurnCycleAfterCheckupEndRefresh) {
            if (finish_check_full(state, runtime)) {
                runtime.turn_cycle_stage = kTurnCycleDone;
                continue;
            }
            turn_start_state_roll_full(state, runtime);
            const gc_i32 active_player = rule_active_player_index(state);
            log_turn_start(runtime, active_player);
            if (runtime.error_flags != 0) return;
            if (state.players[active_player].deck.count == 0) {
                state.game_result = active_player == 0 ? 2 : 1;
                state.finish_reason = 2;
                log_result(runtime, (gc_i32)state.game_result - 1, 2);
                runtime.turn_cycle_stage = kTurnCycleDone;
                continue;
            }
            draw_cards(&state, &runtime, active_player, 1);
            if (runtime.error_flags != 0) return;
            start_embedded_refresh(state, runtime, rules, kTurnCycleAfterStartRefresh);
            if (turn_cycle_waiting(state, runtime)) return;
            continue;
        }

        if (runtime.turn_cycle_stage == kTurnCycleAfterStartRefresh) {
            runtime.turn_cycle_stage = kTurnCycleDone;
            continue;
        }

        if (runtime.turn_cycle_stage == kTurnCycleDone) {
            runtime.turn_cycle_active = 0;
            runtime.turn_cycle_stage = kTurnCycleIdle;
            return;
        }

        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ void start_turn_end_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.turn_cycle_active || finish_check_full(state, runtime)) return;
    runtime.turn_cycle_active = 1;
    const gc_i32 active_player = rule_active_player_index(state);
    log_turn_end(runtime, active_player);
    if (runtime.error_flags != 0) return;
    collect_turn_end_delayed_triggers(state, runtime, active_player);
    if (runtime.error_flags != 0) return;
    pull_trigger(state, runtime, rules, 1, (gc_u8)(1 + active_player), 0, 0);
    if (runtime.error_flags != 0) return;
    start_embedded_refresh(state, runtime, rules, kTurnCycleAfterEndRefresh);
    if (!turn_cycle_waiting(state, runtime))
        continue_turn_cycle_full(state, runtime, rules);
}

__device__ __forceinline__ void resume_turn_cycle_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.turn_cycle_active || runtime.error_flags != 0) return;
    if (runtime.refresh_process_active) {
        resume_refresh_full(state, runtime, rules);
        if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
    } else {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    continue_turn_cycle_full(state, runtime, rules);
}

}  // namespace gpu_cabt
