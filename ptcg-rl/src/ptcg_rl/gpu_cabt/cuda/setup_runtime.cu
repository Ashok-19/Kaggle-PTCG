namespace gpu_cabt {

static constexpr gc_u8 kSetupStageIdle = 0;
static constexpr gc_u8 kSetupStageWaitIsFirst = 1;
static constexpr gc_u8 kSetupStagePreFirst = 2;
static constexpr gc_u8 kSetupStageWaitPreFirst = 3;
static constexpr gc_u8 kSetupStagePreSecond = 4;
static constexpr gc_u8 kSetupStageWaitPreSecond = 5;
static constexpr gc_u8 kSetupStageActiveFirst = 6;
static constexpr gc_u8 kSetupStageWaitActiveFirst = 7;
static constexpr gc_u8 kSetupStageActiveSecond = 8;
static constexpr gc_u8 kSetupStageWaitActiveSecond = 9;
static constexpr gc_u8 kSetupStageEvaluate = 10;
static constexpr gc_u8 kSetupStageResetLoop = 11;
static constexpr gc_u8 kSetupStageWaitResetMulligan = 12;
static constexpr gc_u8 kSetupStageWaitResetActive = 13;
static constexpr gc_u8 kSetupStageCompensation = 14;
static constexpr gc_u8 kSetupStageWaitCompensation = 15;
static constexpr gc_u8 kSetupStageBenchFirst = 16;
static constexpr gc_u8 kSetupStageWaitBenchFirst = 17;
static constexpr gc_u8 kSetupStageBenchSecond = 18;
static constexpr gc_u8 kSetupStageWaitBenchSecond = 19;
static constexpr gc_u8 kSetupStageTurnStart = 20;
static constexpr gc_u8 kSetupStageAfterTurnRefresh = 21;

struct SetupRuleFlagsFull {
    bool has_basic;
    bool has_doll;
};

__device__ __forceinline__ void zero_setup_runtime_full(BattleRuntimeState& runtime) {
    gc_u8* bytes = reinterpret_cast<gc_u8*>(&runtime);
    for (gc_i32 i = 0; i < (gc_i32)sizeof(BattleRuntimeState); ++i) bytes[i] = 0;
}

__device__ __forceinline__ void shuffle_setup_deck_full(
    FixedListU8<gc_u8, kCardListCapacity>& deck,
    BattleRuntimeState& runtime
) {
    for (gc_i32 i = (gc_i32)deck.count - 1; i > 0; --i) {
        const gc_u32 j = bounded_u32(
            runtime.rng_seed, runtime.rng_stream, &runtime.rng_draw_index, (gc_u32)(i + 1)
        );
        const gc_u8 temp = deck.values[i];
        deck.values[i] = deck.values[j];
        deck.values[j] = temp;
    }
}

__device__ __forceinline__ const RuleCardMaster* setup_card_master_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return nullptr;
    }
    const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
    if (master == nullptr) runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
    return master;
}

__device__ __forceinline__ bool setup_master_basic_full(const RuleCardMaster& master) {
    return master.card_type == 0 && master.evolution_type == 1;
}

__device__ __forceinline__ bool setup_master_doll_full(const RuleCardMaster& master) {
    return card_flag(master, kCardFlagToBattleFieldOnlySetup)
        || card_flag(master, kCardFlagToActiveOnlySetup);
}

__device__ __forceinline__ bool setup_master_can_bench_full(const RuleCardMaster& master) {
    return setup_master_basic_full(master) || card_flag(master, kCardFlagToBattleFieldOnlySetup);
}

__device__ __forceinline__ bool setup_master_can_active_full(const RuleCardMaster& master) {
    return setup_master_can_bench_full(master) || card_flag(master, kCardFlagToActiveOnlySetup);
}

__device__ __forceinline__ SetupRuleFlagsFull setup_hand_flags_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    SetupRuleFlagsFull result{false, false};
    const auto& hand = state.players[player_index].hand;
    for (gc_i32 i = 0; i < (gc_i32)hand.count; ++i) {
        const RuleCardMaster* master = setup_card_master_full(state, runtime, rules, hand.values[i]);
        if (master == nullptr) return result;
        result.has_basic = result.has_basic || setup_master_basic_full(*master);
        result.has_doll = result.has_doll || setup_master_doll_full(*master);
    }
    return result;
}

__device__ __forceinline__ bool setup_deck_has_basic_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    const auto& deck = state.players[player_index].deck;
    for (gc_i32 i = 0; i < (gc_i32)deck.count; ++i) {
        const RuleCardMaster* master = setup_card_master_full(state, runtime, rules, deck.values[i]);
        if (master == nullptr) return false;
        if (setup_master_basic_full(*master)) return true;
    }
    return false;
}

__device__ __forceinline__ void setup_open_return_shuffle_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    auto& player = state.players[player_index];
    while (player.hand.count > 0) {
        if (player.deck.count >= kCardListCapacity) {
            runtime.error_flags |= kRuntimeErrorZoneOverflow;
            return;
        }
        const gc_u8 ref = player.hand.values[(gc_i32)player.hand.count - 1];
        --player.hand.count;
        player.deck.values[player.deck.count++] = ref;
        card_moved_non_field(&state, &runtime, ref, kAreaDeck, 0);
        if (runtime.error_flags != 0) return;
    }
    if (player.deck.count > 0) {
        state.changed = 1;
        shuffle_setup_deck_full(player.deck, runtime);
    }
}

__device__ __forceinline__ void setup_make_mulligan_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    set_select_full(state, runtime, kSelectYesNo, kSelectContextMulligan, player_index);
    add_option_yes_no(runtime);
}

__device__ __forceinline__ bool setup_prepare_pre_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    const SetupRuleFlagsFull flags = setup_hand_flags_full(state, runtime, rules, player_index);
    if (runtime.error_flags != 0) return false;
    if (flags.has_basic) {
        state.mulligan[player_index] = 0;
        return false;
    }
    if (flags.has_doll) {
        setup_make_mulligan_select_full(state, runtime, player_index);
        return true;
    }
    state.mulligan[player_index] = 1;
    return false;
}

__device__ __forceinline__ void setup_make_active_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    set_select_full(state, runtime, kSelectCard, kSelectContextSetupActivePokemon, player_index);
    const auto& hand = state.players[player_index].hand;
    for (gc_i32 i = 0; i < (gc_i32)hand.count; ++i) {
        const RuleCardMaster* master = setup_card_master_full(state, runtime, rules, hand.values[i]);
        if (master == nullptr) return;
        if (setup_master_can_active_full(*master)) add_option_card(runtime, kAreaHand, i, player_index);
        if (runtime.error_flags != 0) return;
    }
    if (runtime.option_count == 0) runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
}

__device__ __forceinline__ bool setup_prepare_active_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    if (state.mulligan[player_index]) {
        const SetupRuleFlagsFull flags = setup_hand_flags_full(state, runtime, rules, player_index);
        if (runtime.error_flags != 0) return false;
        if (!setup_deck_has_basic_full(state, runtime, rules, player_index) && !flags.has_basic) {
            if (runtime.error_flags == 0) runtime.error_flags |= kRuntimeErrorNoBasicPokemon;
        }
        return false;
    }
    setup_make_active_select_full(state, runtime, rules, player_index);
    return runtime.error_flags == 0;
}

__device__ __forceinline__ gc_u8 setup_move_selected_active_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    if (runtime.selected_count != 1) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    const gc_i32 selected_index = runtime.selected[0];
    if (selected_index < 0 || selected_index >= (gc_i32)runtime.option_count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    const SelectOptionState option = runtime.options[selected_index];
    if (option.type != kOptionCard || option.param0 != (gc_i16)kAreaHand
        || option.param2 != (gc_i16)player_index) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    auto& player = state.players[player_index];
    const gc_i32 hand_index = option.param1;
    if (hand_index < 0 || hand_index >= (gc_i32)player.hand.count || player.active.count != 0) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return 0;
    }
    const gc_u8 ref = player.hand.values[hand_index];
    for (gc_i32 i = hand_index; i + 1 < (gc_i32)player.hand.count; ++i)
        player.hand.values[i] = player.hand.values[i + 1];
    --player.hand.count;
    player.active.values[0] = ref;
    player.active.count = 1;
    CardState& card = state.all_card[ref];
    if (card.area != kAreaHand) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return 0;
    }
    const gc_u8 pre_area = card.area;
    clear_card_state(&card);
    card.move_counter = state.move_counter++;
    card.turn_state[1] |= (1u << 24);
    card.area = kAreaActive;
    card.pre_area = pre_area;
    card.reverse = 1;
    card.attach_move_counter = 0;
    state.setup_done[player_index] = 1;
    clear_select_full(state, runtime);
    return ref;
}

__device__ __forceinline__ void setup_prize_player_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    auto& player = state.players[player_index];
    for (gc_i32 i = 0; i < 6 && player.deck.count > 0; ++i) {
        if (player.prize.count >= kCardListCapacity) {
            runtime.error_flags |= kRuntimeErrorZoneOverflow;
            return;
        }
        const gc_u8 ref = player.deck.values[(gc_i32)player.deck.count - 1];
        --player.deck.count;
        player.prize.values[player.prize.count++] = ref;
        card_moved_non_field(&state, &runtime, ref, kAreaPrize, 1);
        if (runtime.error_flags != 0) return;
    }
}

__device__ __forceinline__ gc_i32 setup_bench_capacity_full(const PlayerState& player) {
    const gc_i32 override_capacity = (gc_i32)((player.continual_state >> 40) & 0xfu);
    return override_capacity == 0 ? 5 : override_capacity;
}

__device__ __forceinline__ void setup_make_bench_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    set_select_full(state, runtime, kSelectCard, kSelectContextSetupBenchPokemon, player_index, 0, 0);
    const auto& hand = state.players[player_index].hand;
    for (gc_i32 i = 0; i < (gc_i32)hand.count; ++i) {
        const RuleCardMaster* master = setup_card_master_full(state, runtime, rules, hand.values[i]);
        if (master == nullptr) return;
        if (setup_master_can_bench_full(*master)) add_option_card(runtime, kAreaHand, i, player_index);
        if (runtime.error_flags != 0) return;
    }
    gc_i32 remaining = setup_bench_capacity_full(state.players[player_index])
        - (gc_i32)state.players[player_index].bench.count;
    if (remaining < 0) remaining = 0;
    state.select_max = (gc_i32)runtime.option_count < remaining ? runtime.option_count : remaining;
}

__device__ __forceinline__ void setup_capture_bench_targets_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    runtime.target_count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.selected_count; ++i) {
        const gc_i32 option_index = runtime.selected[i];
        if (option_index < 0 || option_index >= (gc_i32)runtime.option_count
            || runtime.target_count >= kAreaRefCapacity) {
            runtime.error_flags |= option_index < 0 || option_index >= (gc_i32)runtime.option_count
                ? kRuntimeErrorInvalidSelection : kRuntimeErrorTargetOverflow;
            return;
        }
        const SelectOptionState& option = runtime.options[option_index];
        if (option.type != kOptionCard || option.param0 != (gc_i16)kAreaHand
            || option.param2 != (gc_i16)player_index) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_i32 hand_index = option.param1;
        const auto& hand = state.players[player_index].hand;
        if (hand_index < 0 || hand_index >= (gc_i32)hand.count) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_u8 ref = hand.values[hand_index];
        AreaRefState& target = runtime.targets[runtime.target_count++];
        target.card = ref;
        target.reserved0 = 0;
        target.reserved1 = 0;
        target.move_counter = state.all_card[ref].move_counter;
    }
    clear_select_full(state, runtime);
}

__device__ __forceinline__ gc_i32 setup_hand_index_for_ref_full(
    const PlayerState& player,
    gc_u8 ref
) {
    for (gc_i32 i = 0; i < (gc_i32)player.hand.count; ++i)
        if (player.hand.values[i] == ref) return i;
    return -1;
}

__device__ __forceinline__ void setup_move_saved_bench_targets_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    auto& player = state.players[player_index];
    for (gc_i32 target_index = 0; target_index < (gc_i32)runtime.target_count; ++target_index) {
        const gc_u8 ref = runtime.targets[target_index].card;
        const gc_i32 hand_index = setup_hand_index_for_ref_full(player, ref);
        if (hand_index < 0 || player.bench.count >= kBenchSizeMax) {
            runtime.error_flags |= hand_index < 0 ? kRuntimeErrorInvalidSelection : kRuntimeErrorZoneOverflow;
            return;
        }
        for (gc_i32 i = hand_index; i + 1 < (gc_i32)player.hand.count; ++i)
            player.hand.values[i] = player.hand.values[i + 1];
        --player.hand.count;
        player.bench.values[player.bench.count++] = ref;
        CardState& card = state.all_card[ref];
        if (card.area != kAreaHand) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }
        const gc_u8 pre_area = card.area;
        clear_card_state(&card);
        card.move_counter = state.move_counter++;
        card.turn_state[1] |= (1u << 24);
        card.area = kAreaBench;
        card.pre_area = pre_area;
        card.reverse = 1;
        card.attach_move_counter = 0;
    }
}

__device__ __forceinline__ void setup_reveal_and_normalize_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    for (gc_i32 p = 0; p < 2; ++p) {
        auto& player = state.players[p];
        if (player.active.count != 1) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }
        state.all_card[player.active.values[0]].reverse = 0;
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
            state.all_card[player.bench.values[i]].reverse = 0;
    }
    CardState& first = state.all_card[state.players[state.first_player].active.values[0]];
    CardState& second = state.all_card[state.players[1 - state.first_player].active.values[0]];
    if (first.move_counter > second.move_counter) {
        const gc_i32 temp = first.move_counter;
        first.move_counter = second.move_counter;
        second.move_counter = temp;
    }
}

__device__ __forceinline__ void setup_make_compensation_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 mulligan_player
) {
    const gc_i32 select_player = 1 - mulligan_player;
    set_select_full(state, runtime, kSelectCount, kSelectContextDrawCount, select_player);
    const gc_i32 count = state.mulligan_count[mulligan_player];
    for (gc_i32 i = 0; i <= count; ++i) add_option_number(runtime, i);
}

__device__ __forceinline__ bool setup_waiting_on_other_process_full(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime
) {
    return runtime.refresh_process_active || runtime.ko_process_active
        || runtime.trigger_resolution_active || runtime.trigger_activation_waiting
        || runtime.effect_execution_active || runtime.pending_effect_kind != kPendingNone
        || state.game_result != 0;
}

__device__ __forceinline__ void continue_setup_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    for (gc_i32 guard = 0; guard < 256; ++guard) {
        if (!runtime.setup_process_active || runtime.error_flags != 0) return;
        if (state.select_type != kSelectNone || setup_waiting_on_other_process_full(state, runtime)) return;
        const gc_i32 first = state.first_player;
        if (runtime.setup_process_stage != kSetupStageWaitIsFirst && (first < 0 || first > 1)) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }
        const gc_i32 second = 1 - first;

        if (runtime.setup_process_stage == kSetupStagePreFirst) {
            if (setup_prepare_pre_full(state, runtime, rules, first)) {
                runtime.setup_process_stage = kSetupStageWaitPreFirst;
                return;
            }
            runtime.setup_process_stage = kSetupStagePreSecond;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStagePreSecond) {
            if (setup_prepare_pre_full(state, runtime, rules, second)) {
                runtime.setup_process_stage = kSetupStageWaitPreSecond;
                return;
            }
            runtime.setup_process_stage = kSetupStageActiveFirst;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageActiveFirst) {
            if (setup_prepare_active_full(state, runtime, rules, first)) {
                runtime.setup_process_stage = kSetupStageWaitActiveFirst;
                return;
            }
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStageActiveSecond;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageActiveSecond) {
            if (setup_prepare_active_full(state, runtime, rules, second)) {
                runtime.setup_process_stage = kSetupStageWaitActiveSecond;
                return;
            }
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStageEvaluate;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageEvaluate) {
            const bool done0 = state.setup_done[0] != 0;
            const bool done1 = state.setup_done[1] != 0;
            if (done0 && done1) {
                if (state.players[first].prize.count == 0) setup_prize_player_full(state, runtime, first);
                if (runtime.error_flags != 0) return;
                if (state.players[second].prize.count == 0) setup_prize_player_full(state, runtime, second);
                if (runtime.error_flags != 0) return;
                runtime.setup_comp_cursor = 0;
                runtime.setup_process_stage = kSetupStageCompensation;
                continue;
            }
            if (done0 != done1) {
                const gc_i32 done_player = done0 ? 0 : 1;
                const gc_i32 reset_player = 1 - done_player;
                if (state.players[done_player].prize.count == 0)
                    setup_prize_player_full(state, runtime, done_player);
                if (runtime.error_flags != 0) return;
                runtime.setup_player = (gc_i8)reset_player;
                runtime.setup_process_stage = kSetupStageResetLoop;
                continue;
            }
            setup_open_return_shuffle_full(state, runtime, first);
            if (runtime.error_flags != 0) return;
            draw_cards(&state, &runtime, first, 7);
            if (runtime.error_flags != 0) return;
            setup_open_return_shuffle_full(state, runtime, second);
            if (runtime.error_flags != 0) return;
            draw_cards(&state, &runtime, second, 7);
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStagePreFirst;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageResetLoop) {
            const gc_i32 p = runtime.setup_player;
            if (p < 0 || p > 1) {
                runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
                return;
            }
            bool found_boundary = false;
            for (gc_i32 attempt = 0; attempt < 64; ++attempt) {
                if (state.mulligan_count[p] < kDeckSize - 7 - 6) ++state.mulligan_count[p];
                setup_open_return_shuffle_full(state, runtime, p);
                if (runtime.error_flags != 0) return;
                draw_cards(&state, &runtime, p, 7);
                if (runtime.error_flags != 0) return;
                const SetupRuleFlagsFull flags = setup_hand_flags_full(state, runtime, rules, p);
                if (runtime.error_flags != 0) return;
                if (flags.has_basic) {
                    state.mulligan[p] = 0;
                    setup_make_active_select_full(state, runtime, rules, p);
                    if (runtime.error_flags != 0) return;
                    runtime.setup_process_stage = kSetupStageWaitResetActive;
                    found_boundary = true;
                    break;
                }
                if (flags.has_doll) {
                    setup_make_mulligan_select_full(state, runtime, p);
                    runtime.setup_process_stage = kSetupStageWaitResetMulligan;
                    found_boundary = true;
                    break;
                }
                state.mulligan[p] = 1;
                if (!setup_deck_has_basic_full(state, runtime, rules, p)) {
                    if (runtime.error_flags == 0) runtime.error_flags |= kRuntimeErrorNoBasicPokemon;
                    return;
                }
            }
            if (found_boundary) return;
            runtime.error_flags |= kRuntimeErrorMulliganLoopLimit;
            return;
        }
        if (runtime.setup_process_stage == kSetupStageCompensation) {
            while (runtime.setup_comp_cursor < 2) {
                const gc_i32 p = runtime.setup_comp_cursor == 0 ? first : second;
                if (state.mulligan_count[p] > 0) {
                    setup_make_compensation_select_full(state, runtime, p);
                    runtime.setup_process_stage = kSetupStageWaitCompensation;
                    return;
                }
                ++runtime.setup_comp_cursor;
            }
            runtime.setup_process_stage = kSetupStageBenchFirst;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageBenchFirst) {
            setup_make_bench_select_full(state, runtime, rules, first);
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStageWaitBenchFirst;
            return;
        }
        if (runtime.setup_process_stage == kSetupStageBenchSecond) {
            setup_make_bench_select_full(state, runtime, rules, second);
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStageWaitBenchSecond;
            return;
        }
        if (runtime.setup_process_stage == kSetupStageTurnStart) {
            if (finish_check_full(state)) {
                runtime.setup_process_active = 0;
                runtime.setup_process_stage = kSetupStageIdle;
                return;
            }
            turn_start_state_roll_full(state, runtime);
            const gc_i32 active_player = rule_active_player_index(state);
            if (state.players[active_player].deck.count == 0) {
                state.game_result = active_player == 0 ? 2 : 1;
                state.finish_reason = 2;
                runtime.setup_process_active = 0;
                runtime.setup_process_stage = kSetupStageIdle;
                return;
            }
            draw_cards(&state, &runtime, active_player, 1);
            if (runtime.error_flags != 0) return;
            runtime.setup_process_stage = kSetupStageAfterTurnRefresh;
            start_refresh_full(state, runtime, rules);
            if (runtime.error_flags != 0 || runtime.refresh_process_active) return;
            continue;
        }
        if (runtime.setup_process_stage == kSetupStageAfterTurnRefresh) {
            if (state.game_result == 0) begin_main_select_full(state, runtime, rules);
            runtime.setup_process_active = 0;
            runtime.setup_process_stage = kSetupStageIdle;
            return;
        }
        if (runtime.setup_process_stage == kSetupStageWaitIsFirst
            || runtime.setup_process_stage == kSetupStageWaitPreFirst
            || runtime.setup_process_stage == kSetupStageWaitPreSecond
            || runtime.setup_process_stage == kSetupStageWaitActiveFirst
            || runtime.setup_process_stage == kSetupStageWaitActiveSecond
            || runtime.setup_process_stage == kSetupStageWaitResetMulligan
            || runtime.setup_process_stage == kSetupStageWaitResetActive
            || runtime.setup_process_stage == kSetupStageWaitCompensation
            || runtime.setup_process_stage == kSetupStageWaitBenchFirst
            || runtime.setup_process_stage == kSetupStageWaitBenchSecond) return;
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ bool setup_selected_yes_full(
    BattleRuntimeState& runtime,
    bool& yes
) {
    if (runtime.selected_count != 1) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    const gc_i32 selected_index = runtime.selected[0];
    if (selected_index < 0 || selected_index >= (gc_i32)runtime.option_count) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    const gc_u8 type = runtime.options[selected_index].type;
    if (type != kOptionYes && type != kOptionNo) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    yes = type == kOptionYes;
    return true;
}

__device__ __forceinline__ void resume_setup_selection_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (!runtime.setup_process_active || runtime.error_flags != 0) return;
    const gc_u8 stage = runtime.setup_process_stage;
    const gc_i32 first = state.first_player;

    if (stage == kSetupStageWaitIsFirst) {
        bool yes = false;
        if (!setup_selected_yes_full(runtime, yes)) return;
        const gc_i32 select_player = state.select_player;
        state.first_player = (gc_i8)(yes ? select_player : 1 - select_player);
        clear_select_full(state, runtime);
        draw_cards(&state, &runtime, state.first_player, 7);
        if (runtime.error_flags != 0) return;
        draw_cards(&state, &runtime, 1 - state.first_player, 7);
        if (runtime.error_flags != 0) return;
        runtime.setup_process_stage = kSetupStagePreFirst;
        continue_setup_full(state, runtime, rules);
        return;
    }
    if (first < 0 || first > 1) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 second = 1 - first;
    if (stage == kSetupStageWaitPreFirst || stage == kSetupStageWaitPreSecond
        || stage == kSetupStageWaitResetMulligan) {
        bool yes = false;
        if (!setup_selected_yes_full(runtime, yes)) return;
        const gc_i32 p = stage == kSetupStageWaitPreFirst ? first
            : stage == kSetupStageWaitPreSecond ? second : runtime.setup_player;
        state.mulligan[p] = yes ? 1 : 0;
        clear_select_full(state, runtime);
        if (stage == kSetupStageWaitPreFirst) runtime.setup_process_stage = kSetupStagePreSecond;
        else if (stage == kSetupStageWaitPreSecond) runtime.setup_process_stage = kSetupStageActiveFirst;
        else {
            if (yes) {
                const SetupRuleFlagsFull flags = setup_hand_flags_full(state, runtime, rules, p);
                if (runtime.error_flags != 0) return;
                if (!setup_deck_has_basic_full(state, runtime, rules, p) && !flags.has_basic) {
                    if (runtime.error_flags == 0) runtime.error_flags |= kRuntimeErrorNoBasicPokemon;
                    return;
                }
                runtime.setup_process_stage = kSetupStageResetLoop;
            } else {
                setup_make_active_select_full(state, runtime, rules, p);
                if (runtime.error_flags != 0) return;
                runtime.setup_process_stage = kSetupStageWaitResetActive;
                return;
            }
        }
        continue_setup_full(state, runtime, rules);
        return;
    }
    if (stage == kSetupStageWaitActiveFirst || stage == kSetupStageWaitActiveSecond
        || stage == kSetupStageWaitResetActive) {
        const gc_i32 p = stage == kSetupStageWaitActiveFirst ? first
            : stage == kSetupStageWaitActiveSecond ? second : runtime.setup_player;
        if (setup_move_selected_active_full(state, runtime, p) == 0) return;
        if (stage == kSetupStageWaitActiveFirst) runtime.setup_process_stage = kSetupStageActiveSecond;
        else if (stage == kSetupStageWaitActiveSecond) runtime.setup_process_stage = kSetupStageEvaluate;
        else {
            if (state.players[p].prize.count == 0) setup_prize_player_full(state, runtime, p);
            if (runtime.error_flags != 0) return;
            runtime.setup_comp_cursor = 0;
            runtime.setup_process_stage = kSetupStageCompensation;
        }
        continue_setup_full(state, runtime, rules);
        return;
    }
    if (stage == kSetupStageWaitCompensation) {
        if (runtime.selected_count != 1) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_i32 selected_index = runtime.selected[0];
        if (selected_index < 0 || selected_index >= (gc_i32)runtime.option_count
            || runtime.options[selected_index].type != kOptionNumber) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_i32 count = runtime.options[selected_index].param0;
        const gc_i32 select_player = state.select_player;
        clear_select_full(state, runtime);
        draw_cards(&state, &runtime, select_player, count);
        if (runtime.error_flags != 0) return;
        ++runtime.setup_comp_cursor;
        runtime.setup_process_stage = kSetupStageCompensation;
        continue_setup_full(state, runtime, rules);
        return;
    }
    if (stage == kSetupStageWaitBenchFirst) {
        setup_capture_bench_targets_full(state, runtime, first);
        if (runtime.error_flags != 0) return;
        runtime.setup_process_stage = kSetupStageBenchSecond;
        continue_setup_full(state, runtime, rules);
        return;
    }
    if (stage == kSetupStageWaitBenchSecond) {
        setup_move_saved_bench_targets_full(state, runtime, first);
        if (runtime.error_flags != 0) return;
        setup_capture_bench_targets_full(state, runtime, second);
        if (runtime.error_flags != 0) return;
        setup_move_saved_bench_targets_full(state, runtime, second);
        if (runtime.error_flags != 0) return;
        state.setup_done[0] = 0;
        state.setup_done[1] = 0;
        setup_reveal_and_normalize_full(state, runtime);
        if (runtime.error_flags != 0) return;
        runtime.setup_process_stage = kSetupStageTurnStart;
        continue_setup_full(state, runtime, rules);
        return;
    }
    runtime.error_flags |= kRuntimeErrorInvalidSelection;
}

__device__ __forceinline__ void reset_game_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const gc_i32* decks,
    gc_u64 seed,
    gc_u64 stream
) {
    gc_u8* state_bytes = reinterpret_cast<gc_u8*>(&state);
    for (gc_i32 i = 0; i < (gc_i32)sizeof(BattleCoreState); ++i) state_bytes[i] = 0;
    zero_setup_runtime_full(runtime);
    state.move_counter = 1;
    state.first_player = -1;
    for (gc_i32 p = 0; p < 2; ++p) {
        const gc_i32 ref = 1 + p;
        state.all_card[ref].card_id = 0;
        state.all_card[ref].move_counter = state.move_counter++;
        state.all_card[ref].player_index = (gc_i8)p;
        state.all_card[ref].area = kAreaPlayer;
        state.players[p].player_index = (gc_i8)p;
    }
    gc_i32 ref = 3;
    for (gc_i32 p = 0; p < 2; ++p) {
        auto& deck = state.players[p].deck;
        deck.count = kDeckSize;
        for (gc_i32 input_index = 0; input_index < kDeckSize; ++input_index) {
            CardState& card = state.all_card[ref];
            card.card_id = decks[p * kDeckSize + input_index];
            card.move_counter = state.move_counter++;
            card.player_index = (gc_i8)p;
            card.area = kAreaDeck;
            deck.values[kDeckSize - input_index - 1] = (gc_u8)ref;
            ++ref;
        }
    }
    runtime.rng_seed = seed;
    runtime.rng_stream = stream;
    for (gc_i32 p = 0; p < 2; ++p) {
        shuffle_setup_deck_full(state.players[p].deck, runtime);
        state.changed = 1;
    }
    set_select_full(state, runtime, kSelectYesNo, kSelectContextIsFirst, 0);
    add_option_yes_no(runtime);
    runtime.setup_process_active = 1;
    runtime.setup_process_stage = kSetupStageWaitIsFirst;
    runtime.setup_player = -1;
    runtime.setup_comp_cursor = 0;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_game_reset(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* decks,
    gc_u64 seed,
    gc_u64 stream_base,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    gpu_cabt::reset_game_full(
        state, runtime, decks + (gc_i64)env_index * 2 * gpu_cabt::kDeckSize,
        seed, stream_base + (gc_u64)env_index);
}
