namespace gpu_cabt {

static constexpr gc_u8 kKoStageAfterPreTriggers = 1;
static constexpr gc_u8 kKoStageAfterKoTriggers = 2;
static constexpr gc_u8 kKoStagePrizeSelection = 3;

__device__ __forceinline__ bool card_is_ko_full(
    const CardState& card,
    const RuleCardMaster& master
) {
    return card.damage >= get_max_hp(card, master);
}

__device__ __forceinline__ gc_i32 ko_prize_count_full(
    const BattleCoreState& state,
    const RuleCardMaster& master,
    const CardState& card
) {
    const CardTurnFields& turn = card_turn(card);
    if (turn.fields.ko_prize_zero) return 0;
    gc_i32 count = 1;
    if (master.pokemon_type == 3) count = 2;
    else if (master.pokemon_type == 4) count = 3;
    count += turn.fields.ko_prize_change_always;
    if (turn.fields.ko_enemy_attack_damage) {
        count += turn.fields.ko_prize_change;
        if (turn.fields.ko_prize_decrease_once) --count;
    }
    if (turn.fields.ko_enemy_terastal_attack_damage && card.area == kAreaActive)
        count += player_turn(state.players[1 - card.player_index]).fields.take_prize_count_change_terastal_attack_ko_active;
    if (turn.fields.ko_enemy_n_attack_damage && card.area == kAreaActive)
        count += player_turn(state.players[1 - card.player_index]).fields.take_prize_count_change_n_attack_ko_active;
    if (turn.fields.ko_prize_plus1) ++count;
    return count > 0 ? count : 0;
}

__device__ __forceinline__ bool append_ko_ref(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    if (runtime.ko_count >= kAreaRefCapacity) {
        runtime.error_flags |= kRuntimeErrorKoOverflow;
        return false;
    }
    runtime.ko_list[runtime.ko_count++] = make_area_ref(state, ref);
    return true;
}

__device__ __forceinline__ void mark_pre_ko_player(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    for (gc_i32 i = (gc_i32)player.bench.count - 1; i >= 0; --i) {
        const gc_u8 ref = player.bench.values[i];
        CardState& card = state.all_card[ref];
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        if (master == nullptr) continue;
        if (card_is_ko_full(card, *master)) card_turn(card).fields.ko = true;
        const CardTurnFields& turn = card_turn(card);
        if (turn.fields.ko_attack_damage) {
            pull_trigger(state, runtime, rules, 12, ref, 0, 1);
            if (turn.fields.ko_full) {
                pull_trigger(state, runtime, rules, 13, ref, 0, 1);
                if (turn.fields.ko_enemy_attack_damage) pull_trigger(state, runtime, rules, 14, ref, 0, 1);
            }
        }
    }
    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        CardState& card = state.all_card[ref];
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        if (master != nullptr) {
            if (card_is_ko_full(card, *master)) card_turn(card).fields.ko = true;
            const CardTurnFields& turn = card_turn(card);
            if (turn.fields.ko_attack_damage) {
                pull_trigger(state, runtime, rules, 12, ref, 0, 1);
                if (turn.fields.ko_full) {
                    pull_trigger(state, runtime, rules, 13, ref, 0, 1);
                    if (turn.fields.ko_enemy_attack_damage) pull_trigger(state, runtime, rules, 14, ref, 0, 1);
                }
            }
        }
    }
}

__device__ __forceinline__ void collect_ko_player_reverse_in_play(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    PlayerState& player = state.players[player_index];
    for (gc_i32 i = (gc_i32)player.bench.count - 1; i >= 0; --i) {
        const gc_u8 ref = player.bench.values[i];
        if (card_turn(state.all_card[ref]).fields.ko && !append_ko_ref(state, runtime, ref)) return;
    }
    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        if (card_turn(state.all_card[ref]).fields.ko) append_ko_ref(state, runtime, ref);
    }
}

__device__ __forceinline__ void pull_ko_triggers_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 i = 0; i < (gc_i32)runtime.ko_count; ++i) {
        const AreaRefState r = runtime.ko_list[i];
        if (!valid_area_ref(state, r)) continue;
        CardState& card = state.all_card[r.card];
        const CardTurnFields& turn = card_turn(card);
        const gc_u8 cause = turn.fields.ko_cause_ref;
        pull_trigger(state, runtime, rules, 15, r.card, cause, 1);
        if (turn.fields.ko_enemy_attack_damage) pull_trigger(state, runtime, rules, 16, r.card, cause, 1);
        if (turn.fields.ko_enemy_ex_attack_damage) pull_trigger(state, runtime, rules, 17, r.card, cause, 1);
        if (turn.fields.ko_enemy_attack_damage_active) pull_trigger(state, runtime, rules, 18, r.card, cause, 1);
        if (turn.fields.ko_no_damage_and_effect_attack_next_enemy_turn
            && cause != 0 && cause < kAllCardCapacity && state.all_card[cause].area == kAreaActive)
            card_next_enemy_turn_end(state.all_card[cause]).fields.no_damage_and_effect_attack_next_enemy_turn = true;
        if (runtime.error_flags != 0) return;
    }
}

__device__ __forceinline__ bool append_ko_prize_obligation(
    BattleRuntimeState& runtime,
    gc_i32 player_index,
    gc_i32 count
) {
    if (count <= 0) return true;
    if (runtime.ko_prize_obligation_count >= kAreaRefCapacity) {
        runtime.error_flags |= kRuntimeErrorKoOverflow;
        return false;
    }
    const gc_i32 index = runtime.ko_prize_obligation_count++;
    runtime.ko_prize_player[index] = (gc_u8)player_index;
    runtime.ko_prize_count[index] = (gc_u8)(count > 255 ? 255 : count);
    return true;
}

__device__ __forceinline__ void record_ko_history_full(
    BattleCoreState& state,
    const RuleCardMaster& master,
    const CardState& card
) {
    if (state.phase != 1 || rule_active_player_index(state) == card.player_index) return;
    TurnHistory& history = state.turn_histories[0];
    history.ko = 1;
    if (card_flag(master, kCardFlagTeamRocket)) history.ko_team_rocket = 1;
    if (card_turn(card).fields.ko_enemy_attack_damage) {
        history.ko_attack_damage = 1;
        if (card_flag(master, kCardFlagEthan)) history.ko_attack_damage_ethan = 1;
        if (card_flag(master, kCardFlagHop)) history.ko_attack_damage_hop = 1;
    }
}

__device__ __forceinline__ void snapshot_prizes_and_move_kos(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    runtime.ko_prize_obligation_count = 0;
    runtime.ko_prize_obligation_index = -1;
    for (gc_i32 i = 0; i < (gc_i32)runtime.ko_count; ++i) {
        const AreaRefState r = runtime.ko_list[i];
        if (!valid_area_ref(state, r)) continue;
        const CardState& card = state.all_card[r.card];
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        if (master == nullptr) continue;
        if (!card_flag(*master, kCardFlagNoPrize)) {
            const gc_i32 prize = ko_prize_count_full(state, *master, card);
            if (!append_ko_prize_obligation(runtime, 1 - card.player_index, prize)) return;
        }
        record_ko_history_full(state, *master, card);
    }
    for (gc_i32 i = (gc_i32)runtime.ko_count - 1; i >= 0; --i) {
        const AreaRefState r = runtime.ko_list[i];
        if (!valid_area_ref(state, r)) continue;
        CardState& card = state.all_card[r.card];
        const gc_i32 player_index = card.player_index;
        const gc_i32 area_index = current_area_index(state.players[player_index], card.area, r.card);
        if (area_index < 0) continue;
        gc_u8 to_area = 3;
        if (card_continual(card).fields.ko_by_damage_to_hand
            && card_turn(card).fields.ko_enemy_attack_damage) to_area = kAreaHand;
        move_card_full(state, runtime, rules, player_index, card.area, area_index, to_area, 0, false, false, true);
        if (runtime.error_flags != 0) return;
    }
    runtime.ko_count = 0;
    runtime.ko_prize_obligation_index = runtime.ko_prize_obligation_count - 1;
}

__device__ __forceinline__ bool begin_ko_prize_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    while (runtime.ko_prize_obligation_index >= 0) {
        const gc_i32 index = runtime.ko_prize_obligation_index;
        const gc_i32 player_index = runtime.ko_prize_player[index];
        gc_i32 count = runtime.ko_prize_count[index];
        if (player_index < 0 || player_index > 1 || state.players[player_index].prize.count == 0 || count <= 0) {
            --runtime.ko_prize_obligation_index;
            continue;
        }
        if (count > (gc_i32)state.players[player_index].prize.count) count = state.players[player_index].prize.count;
        set_select_full(state, runtime, kSelectCard, kSelectContextToHand, player_index, count, count);
        for (gc_i32 i = 0; i < (gc_i32)state.players[player_index].prize.count; ++i)
            add_option_card(runtime, kAreaPrize, i, player_index);
        runtime.pending_effect_kind = kPendingPrizeSelect;
        return true;
    }
    runtime.ko_process_active = 0;
    runtime.ko_process_stage = 0;
    return false;
}

__device__ __forceinline__ void continue_ko_process_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.ko_process_active || runtime.error_flags != 0) return;
    if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone
        || runtime.effect_execution_active || runtime.trigger_resolution_active
        || runtime.trigger_activation_waiting) return;

    for (gc_i32 guard = 0; guard < 8; ++guard) {
        if (runtime.ko_process_stage == kKoStageAfterPreTriggers) {
            runtime.ko_count = 0;
            const gc_i32 first = state.first_player;
            collect_ko_player_reverse_in_play(state, runtime, 1 - first);
            collect_ko_player_reverse_in_play(state, runtime, first);
            if (runtime.error_flags != 0) return;
            if (runtime.ko_count == 0) {
                runtime.ko_process_active = 0;
                runtime.ko_process_stage = 0;
                return;
            }
            state.state_changed = 1;
            pull_ko_triggers_full(state, runtime, rules);
            if (runtime.error_flags != 0) return;
            runtime.ko_process_stage = kKoStageAfterKoTriggers;
            resolve_trigger_stack_full(state, runtime, rules, 1);
            if (runtime.trigger_resolution_active || state.select_type != kSelectNone
                || runtime.pending_effect_kind != kPendingNone || runtime.effect_execution_active) return;
            continue;
        }
        if (runtime.ko_process_stage == kKoStageAfterKoTriggers) {
            snapshot_prizes_and_move_kos(state, runtime, rules);
            if (runtime.error_flags != 0) return;
            runtime.ko_process_stage = kKoStagePrizeSelection;
            if (begin_ko_prize_selection(state, runtime)) return;
            return;
        }
        if (runtime.ko_process_stage == kKoStagePrizeSelection) {
            if (begin_ko_prize_selection(state, runtime)) return;
            return;
        }
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ void start_ko_process_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    runtime.ko_process_active = 1;
    runtime.ko_process_stage = kKoStageAfterPreTriggers;
    runtime.ko_prize_obligation_count = 0;
    runtime.ko_prize_obligation_index = -1;
    runtime.ko_count = 0;
    const gc_i32 first = state.first_player;
    mark_pre_ko_player(state, runtime, rules, first);
    mark_pre_ko_player(state, runtime, rules, 1 - first);
    if (runtime.error_flags != 0) return;
    resolve_trigger_stack_full(state, runtime, rules, 1);
    if (!runtime.trigger_resolution_active && state.select_type == kSelectNone
        && runtime.pending_effect_kind == kPendingNone && !runtime.effect_execution_active)
        continue_ko_process_full(state, runtime, rules);
}

__device__ __forceinline__ void finish_current_ko_prize_obligation(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    --runtime.ko_prize_obligation_index;
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_substep = 0;
    if (!begin_ko_prize_selection(state, runtime))
        continue_ko_process_full(state, runtime, rules);
}

__device__ __forceinline__ void resume_ko_selection_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.ko_process_active) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return;
    }
    const gc_u16 kind = runtime.pending_effect_kind;
    if (kind == kPendingPrizeSelect) {
        if (!validate_selected_response(state, runtime)) return;
        collect_selected_card_targets(state, runtime);
        if (runtime.error_flags != 0) return;
        runtime.pending_effect_kind = kPendingNone;
        runtime.pending_effect_substep = 0;
        prize_to_hand_full(state, runtime, rules);
        if (runtime.error_flags != 0) return;
        if (runtime.pending_effect_kind != kPendingNone || state.select_type != kSelectNone) return;
        finish_current_ko_prize_obligation(state, runtime, rules);
        return;
    }
    if (kind == kPendingPrizeLuckyBonus) {
        if (!validate_selected_response(state, runtime)) return;
        if (resume_lucky_bonus(state, runtime, rules)) return;
        if (runtime.error_flags != 0) return;
        finish_current_ko_prize_obligation(state, runtime, rules);
        return;
    }
    if (kind == kPendingPrizeLuckyBonusCoin) {
        if (!validate_selected_response(state, runtime)) return;
        if (resume_lucky_bonus_prize(state, runtime, rules)) return;
        if (runtime.error_flags != 0) return;
        finish_current_ko_prize_obligation(state, runtime, rules);
        return;
    }
    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
}

}  // namespace gpu_cabt
