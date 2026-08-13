namespace gpu_cabt {

static constexpr gc_u8 kRefreshStageIdle = 0;
static constexpr gc_u8 kRefreshStageBench = 1;
static constexpr gc_u8 kRefreshStageTools = 2;
static constexpr gc_u8 kRefreshStageKo = 3;
static constexpr gc_u8 kRefreshStageActive = 4;
static constexpr gc_u8 kRefreshStageTriggers = 5;
static constexpr gc_u8 kRefreshStageDone = 6;

__device__ __forceinline__ bool finish_check_full(BattleCoreState& state, BattleRuntimeState& runtime) {
    if (state.game_result != 0) return true;
    gc_i32 score[2] = {0, 0};
    gc_u8 reason = 0;
    const gc_i32 first = state.first_player == 1 ? 1 : 0;
    for (gc_i32 order = 0; order < 2; ++order) {
        const gc_i32 p = order == 0 ? first : 1 - first;
        const PlayerState& player = state.players[p];
        if (player.prize.count == 0) {
            ++score[p];
            reason = 1;  // FinishReason::Prize0
        }
        if (player.active.count == 0 && player.bench.count == 0) {
            ++score[1 - p];
            reason = 3;  // FinishReason::NoActivePokemon
        }
    }
    if (reason == 0) return false;
    if (score[0] < score[1]) state.game_result = 2;
    else if (score[0] > score[1]) state.game_result = 1;
    else state.game_result = 3;
    state.finish_reason = reason;
    log_result(runtime, (gc_i32)state.game_result - 1, reason);
    return true;
}

__device__ __forceinline__ gc_i32 attached_tool_count_full(
    const BattleCoreState& state,
    gc_u8 pokemon_ref
) {
    if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return 0;
    const CardState& pokemon = state.all_card[pokemon_ref];
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return 0;
    const PlayerState& player = state.players[pokemon.player_index];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
        const gc_u8 ref = player.tool.values[i];
        if (state.all_card[ref].attach_move_counter == pokemon.move_counter) ++count;
    }
    return count;
}

__device__ __forceinline__ gc_i32 remaining_tool_capacity_full(
    const BattleCoreState& state,
    gc_u8 pokemon_ref
) {
    if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return 0;
    const CardState& pokemon = state.all_card[pokemon_ref];
    const CardContinualFields& fields = card_continual(pokemon);
    const gc_i32 capacity = fields.fields.tool4 ? 4 : (fields.fields.tool2 ? 2 : 1);
    return capacity - attached_tool_count_full(state, pokemon_ref);
}

__device__ __forceinline__ void reset_refresh_cycle(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    state.state_changed = 0;
    refresh_effect(state, runtime, rules, 0);
    if (runtime.error_flags != 0) return;
    runtime.refresh_process_stage = kRefreshStageBench;
    runtime.refresh_cursor = 0;
    runtime.refresh_tool_count = 0;
}

__device__ __forceinline__ bool begin_refresh_bench_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1) return false;
    const gc_i32 trash_count = -remaining_bench(state, player_index);
    if (trash_count <= 0) return false;
    const PlayerState& player = state.players[player_index];
    set_select_full(
        state, runtime, kSelectCard, kSelectContextDiscard,
        player_index, trash_count, trash_count
    );
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
        add_option_card(runtime, kAreaBench, i, player_index);
    runtime.pending_effect_kind = kPendingRefreshBenchTrash;
    runtime.pending_effect_arg0 = player_index;
    state.state_changed = 1;
    return true;
}

__device__ __forceinline__ void resume_refresh_bench_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingRefreshBenchTrash
        || !validate_selected_response(state, runtime)) return;
    collect_selected_card_targets(state, runtime);
    if (runtime.error_flags != 0) return;
    runtime.pending_effect_kind = kPendingNone;
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState ref = runtime.targets[i];
        if (!valid_area_ref(state, ref)) continue;
        move_ref_card_full(state, runtime, rules, ref.card, 3);
        if (runtime.error_flags != 0) return;
    }
    ++runtime.refresh_cursor;
}

__device__ __forceinline__ bool append_refresh_ref(
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    if (runtime.refresh_tool_count >= kAreaRefCapacity) {
        runtime.error_flags |= kRuntimeErrorTargetOverflow;
        return false;
    }
    runtime.refresh_refs[runtime.refresh_tool_count++] = ref;
    return true;
}

__device__ __forceinline__ void collect_refresh_tool_work(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    runtime.refresh_tool_count = 0;
    const gc_i32 first = state.first_player == 1 ? 1 : 0;
    for (gc_i32 order = 0; order < 2; ++order) {
        const gc_i32 p = order == 0 ? first : 1 - first;
        PlayerState& player = state.players[p];
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) {
            const gc_u8 ref = player.active.values[i];
            if (remaining_tool_capacity_full(state, ref) < 0 && !append_refresh_ref(runtime, ref)) return;
        }
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
            const gc_u8 ref = player.bench.values[i];
            if (remaining_tool_capacity_full(state, ref) < 0 && !append_refresh_ref(runtime, ref)) return;
        }
        for (gc_i32 i = (gc_i32)player.energy.count - 1; i >= 0; --i) {
            const gc_u8 energy_ref = player.energy.values[i];
            const CardState& energy = state.all_card[energy_ref];
            const RuleCardMaster* energy_master = rule_card(rules, energy.card_id);
            if (energy_master == nullptr || !card_flag(*energy_master, kCardFlagOnlyTeamRocket)) continue;
            const RefPositionState attached = attached_card_position(state, energy);
            if (attached.ref == 0 || attached.ref >= kAllCardCapacity) continue;
            const RuleCardMaster* pokemon_master = rule_card(rules, state.all_card[attached.ref].card_id);
            if (pokemon_master != nullptr && card_flag(*pokemon_master, kCardFlagTeamRocket)) continue;
            state.state_changed = 1;
            move_card_full(state, runtime, rules, p, 8, i, 3, 0, false, false, false);
            if (runtime.error_flags != 0) return;
        }
    }
    runtime.refresh_cursor = runtime.refresh_tool_count - 1;
}

__device__ __forceinline__ bool begin_refresh_tool_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    while (runtime.refresh_cursor >= 0) {
        const gc_u8 pokemon_ref = runtime.refresh_refs[runtime.refresh_cursor];
        if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) {
            --runtime.refresh_cursor;
            continue;
        }
        CardState& pokemon = state.all_card[pokemon_ref];
        if (pokemon.area != kAreaActive && pokemon.area != kAreaBench) {
            --runtime.refresh_cursor;
            continue;
        }
        const gc_i32 remain = remaining_tool_capacity_full(state, pokemon_ref);
        if (remain >= 0) {
            --runtime.refresh_cursor;
            continue;
        }
        gc_u8 area = 0;
        gc_i32 area_index = -1;
        gc_i32 player_index = -1;
        if (!card_position_for_ref(state, pokemon_ref, area, area_index, player_index)) {
            --runtime.refresh_cursor;
            continue;
        }
        const gc_i32 trash_count = -remain;
        set_select_full(
            state, runtime, kSelectAttachedCard, kSelectContextDiscardToolCard,
            player_index, trash_count, trash_count
        );
        const PlayerState& player = state.players[player_index];
        gc_i32 attached_index = 0;
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
            const gc_u8 tool_ref = player.tool.values[i];
            if (state.all_card[tool_ref].attach_move_counter != pokemon.move_counter) continue;
            add_option_tool_card(runtime, area, area_index, player_index, attached_index++);
        }
        runtime.pending_effect_kind = kPendingRefreshToolTrash;
        runtime.pending_effect_arg0 = pokemon_ref;
        state.state_changed = 1;
        return true;
    }
    return false;
}

__device__ __forceinline__ void resume_refresh_tool_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingRefreshToolTrash
        || !validate_selected_response(state, runtime)) return;
    collect_selected_attached_targets(state, runtime, false);
    if (runtime.error_flags != 0) return;
    runtime.pending_effect_kind = kPendingNone;
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState ref = runtime.targets[i];
        if (!valid_area_ref(state, ref)) continue;
        move_ref_card_full(state, runtime, rules, ref.card, 3);
        if (runtime.error_flags != 0) return;
    }
    refresh_effect(state, runtime, rules, 0);
    if (runtime.error_flags != 0) return;
    --runtime.refresh_cursor;
}

__device__ __forceinline__ bool begin_refresh_active_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1) return false;
    const PlayerState& player = state.players[player_index];
    if (player.active.count != 0 || player.bench.count == 0) return false;
    set_select_full(state, runtime, kSelectCard, kSelectContextToActive, player_index, 1, 1);
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
        add_option_card(runtime, kAreaBench, i, player_index);
    runtime.pending_effect_kind = kPendingRefreshActive;
    runtime.pending_effect_arg0 = player_index;
    state.state_changed = 1;
    return true;
}

__device__ __forceinline__ void resume_refresh_active_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.pending_effect_kind != kPendingRefreshActive
        || !validate_selected_response(state, runtime)) return;
    const gc_i32 player_index = runtime.pending_effect_arg0;
    const SelectOptionState* option = first_selected_option(runtime);
    if (option == nullptr || option->type != kOptionCard) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u8 ref = option_card_ref(state, *option);
    if (ref == 0 || player_index < 0 || player_index > 1
        || state.all_card[ref].player_index != player_index
        || state.all_card[ref].area != kAreaBench) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_i32 bench_index = current_area_index(state.players[player_index], kAreaBench, ref);
    clear_select_full(state, runtime);
    runtime.pending_effect_kind = kPendingNone;
    if (bench_index < 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    switch_pokemon_full(state, runtime, rules, player_index, bench_index);
    if (runtime.error_flags != 0) return;
    ++runtime.refresh_cursor;
}

__device__ __forceinline__ bool refresh_waiting(const BattleCoreState& state, const BattleRuntimeState& runtime) {
    return state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone
        || runtime.effect_execution_active
        || runtime.trigger_activation_waiting
        || runtime.trigger_resolution_active
        || runtime.ko_process_active;
}

__device__ __forceinline__ void continue_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 guard = 0; guard < 256; ++guard) {
        if (!runtime.refresh_process_active || runtime.error_flags != 0) return;
        if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone
            || runtime.effect_execution_active || runtime.trigger_activation_waiting) return;

        if (runtime.refresh_process_stage == kRefreshStageBench) {
            while (runtime.refresh_cursor < 2) {
                gc_i32 stadium_player = state.last_stadium_player;
                if (stadium_player < 0 || stadium_player > 1) stadium_player = 0;
                const gc_i32 p = runtime.refresh_cursor == 0 ? stadium_player : 1 - stadium_player;
                if (begin_refresh_bench_selection(state, runtime, p)) return;
                ++runtime.refresh_cursor;
            }
            if (state.phase == 2) {
                runtime.refresh_process_stage = kRefreshStageTriggers;
                resolve_trigger_stack_full(state, runtime, rules, 0);
                if (refresh_waiting(state, runtime)) return;
                continue;
            }
            collect_refresh_tool_work(state, runtime, rules);
            if (runtime.error_flags != 0) return;
            runtime.refresh_process_stage = kRefreshStageTools;
            continue;
        }

        if (runtime.refresh_process_stage == kRefreshStageTools) {
            if (begin_refresh_tool_selection(state, runtime)) return;
            runtime.refresh_process_stage = kRefreshStageKo;
            start_ko_process_full(state, runtime, rules);
            if (runtime.error_flags != 0 || runtime.ko_process_active
                || state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone
                || runtime.trigger_resolution_active || runtime.trigger_activation_waiting
                || runtime.effect_execution_active) return;
            continue;
        }

        if (runtime.refresh_process_stage == kRefreshStageKo) {
            if (runtime.ko_process_active) return;
            if (finish_check_full(state, runtime)) {
                runtime.refresh_process_stage = kRefreshStageDone;
                continue;
            }
            runtime.refresh_process_stage = kRefreshStageActive;
            runtime.refresh_cursor = 0;
            continue;
        }

        if (runtime.refresh_process_stage == kRefreshStageActive) {
            const gc_i32 active_player = rule_active_player_index(state);
            while (runtime.refresh_cursor < 2) {
                const gc_i32 p = runtime.refresh_cursor == 0 ? 1 - active_player : active_player;
                if (begin_refresh_active_selection(state, runtime, p)) return;
                ++runtime.refresh_cursor;
            }
            runtime.refresh_process_stage = kRefreshStageTriggers;
            resolve_trigger_stack_full(state, runtime, rules, 0);
            if (refresh_waiting(state, runtime)) return;
            continue;
        }

        if (runtime.refresh_process_stage == kRefreshStageTriggers) {
            if (runtime.trigger_resolution_active) return;
            if (state.state_changed) {
                if (++runtime.refresh_iteration > 32) {
                    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
                    return;
                }
                reset_refresh_cycle(state, runtime, rules);
                if (runtime.error_flags != 0) return;
                continue;
            }
            finish_check_full(state, runtime);
            runtime.refresh_process_stage = kRefreshStageDone;
            continue;
        }

        if (runtime.refresh_process_stage == kRefreshStageDone) {
            runtime.refresh_process_active = 0;
            runtime.refresh_process_stage = kRefreshStageIdle;
            runtime.refresh_cursor = 0;
            runtime.refresh_tool_count = 0;
            runtime.refresh_iteration = 0;
            return;
        }

        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ void start_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (runtime.refresh_process_active || state.select_type != kSelectNone
        || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.refresh_process_active = 1;
    runtime.refresh_process_stage = kRefreshStageBench;
    runtime.refresh_cursor = 0;
    runtime.refresh_tool_count = 0;
    runtime.refresh_iteration = 0;
    reset_refresh_cycle(state, runtime, rules);
    continue_refresh_full(state, runtime, rules);
}

__device__ __forceinline__ void resume_refresh_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.refresh_process_active || runtime.error_flags != 0) return;
    const gc_u16 kind = runtime.pending_effect_kind;
    if (kind == kPendingRefreshBenchTrash) {
        resume_refresh_bench_selection(state, runtime, rules);
    } else if (kind == kPendingRefreshToolTrash) {
        resume_refresh_tool_selection(state, runtime, rules);
    } else if (kind == kPendingRefreshActive) {
        resume_refresh_active_selection(state, runtime, rules);
    } else if (kind == kPendingTriggerOrder) {
        resume_trigger_order_full(state, runtime, rules);
        if (runtime.error_flags == 0 && !runtime.trigger_resolution_active)
            continue_refresh_full(state, runtime, rules);
        return;
    } else if (runtime.ko_process_active) {
        resume_ko_selection_full(state, runtime, rules);
        if (runtime.error_flags == 0 && !runtime.ko_process_active)
            continue_refresh_full(state, runtime, rules);
        return;
    } else if (runtime.trigger_resolution_active || runtime.trigger_activation_waiting
        || runtime.effect_execution_active) {
        resume_effect_selection_full(state, runtime, rules, runtime.trigger_resolution_depth);
        continue_trigger_activation_full(state, runtime, rules);
        if (runtime.error_flags == 0 && !runtime.trigger_resolution_active
            && !runtime.trigger_activation_waiting && !runtime.effect_execution_active)
            continue_refresh_full(state, runtime, rules);
        return;
    } else {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    if (runtime.error_flags == 0) continue_refresh_full(state, runtime, rules);
}

}  // namespace gpu_cabt
