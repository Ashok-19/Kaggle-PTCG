namespace gpu_cabt {

static constexpr gc_u8 kEffectSelectAll = 0;
static constexpr gc_u8 kEffectSelectCardCount = 1;
static constexpr gc_u8 kEffectSelectMaxCardCount = 2;
static constexpr gc_u8 kEffectSelectCardUntil = 3;
static constexpr gc_u8 kEffectSelectMaxCardUntil = 4;
static constexpr gc_u8 kEffectSelectEnergy = 5;
static constexpr gc_u8 kEffectSelectMaxEnergyCard = 6;
static constexpr gc_u8 kEffectSelectToolCard = 7;
static constexpr gc_u8 kEffectSelectCardOrAttachedCardCount = 8;
static constexpr gc_u8 kEffectSelectEvolve = 9;
static constexpr gc_u8 kEffectSelectEvolve2 = 10;

static constexpr gc_u8 kEffectRepeatSingle = 0;
static constexpr gc_u8 kEffectRepeatSelected = 1;
static constexpr gc_u8 kEffectRepeatEach = 2;
static constexpr gc_u8 kEffectRepeatLoop = 3;

static constexpr gc_u16 kPendingSubstepAbilityActivate = 100;
static constexpr gc_u16 kPendingSubstepAbilityFirstEffect = 101;
static constexpr gc_u16 kPendingSubstepAbilityEnemyEffect = 102;
static constexpr gc_u16 kPendingSubstepGenericCard = 200;
static constexpr gc_u16 kPendingSubstepGenericAttached = 201;
static constexpr gc_u16 kPendingSubstepGenericEvolve = 202;
static constexpr gc_u16 kPendingSubstepGenericCardOrAttached = 203;

struct EffectSpanState {
    const RuleEffect* effects;
    gc_i32 count;
    gc_i32 first_condition_count;
    const RuleSkill* skill;
};

__device__ __forceinline__ bool current_effect_span(
    const BattleCoreState& state,
    const RuleTableView& rules,
    EffectSpanState& span
) {
    span = {};
    const gc_i32 skill_id = state.effect_state.ability.skill_id;
    if (skill_id > 0) {
        const RuleSkill* skill = rule_skill(rules, skill_id);
        if (skill == nullptr || skill->effect_offset < 0
            || skill->effect_offset + skill->effect_count > rules.effect_count) return false;
        span.effects = rules.effects + skill->effect_offset;
        span.count = skill->effect_count;
        span.first_condition_count = skill->first_condition_count;
        span.skill = skill;
        return true;
    }
    const RuleAttack* attack = rule_attack(rules, state.current_attack_id);
    if (attack == nullptr) return false;
    const bool post = state.post_attack_effect != 0;
    const gc_i32 offset = post ? attack->post_effect_offset : attack->pre_effect_offset;
    const gc_i32 count = post ? attack->post_effect_count : attack->pre_effect_count;
    if (offset < 0 || offset + count > rules.effect_count) return false;
    span.effects = rules.effects + offset;
    span.count = count;
    span.first_condition_count = -1;
    span.skill = nullptr;
    return true;
}

__device__ __forceinline__ bool rule_target_has_area(const RuleTarget& target, gc_u8 area) {
    for (gc_i32 i = 0; i < (gc_i32)target.area_count; ++i) if (target.areas[i] == area) return true;
    return false;
}

__device__ __forceinline__ void copy_effect_targets_to_pre(BattleRuntimeState& runtime) {
    runtime.pre_target_count = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        if (runtime.pre_target_count >= kAreaRefCapacity) {
            runtime.error_flags |= kRuntimeErrorPreTargetOverflow;
            return;
        }
        runtime.pre_targets[runtime.pre_target_count++] = runtime.targets[i];
    }
}

__device__ __forceinline__ void remove_pre_targets(BattleRuntimeState& runtime) {
    gc_i32 write = 0;
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        bool found = false;
        for (gc_i32 j = 0; j < (gc_i32)runtime.pre_target_count; ++j) {
            if (runtime.targets[i].card == runtime.pre_targets[j].card) { found = true; break; }
        }
        if (!found) runtime.targets[write++] = runtime.targets[i];
    }
    runtime.target_count = (gc_u16)write;
}

__device__ __forceinline__ gc_i32 total_enemy_in_play_energy(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 owner
) {
    const gc_i32 player_index = 1 - owner;
    const PlayerState& player = state.players[player_index];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
        count += attached_energy_count(state, rules, player_index, player.active.values[i]);
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
        count += attached_energy_count(state, rules, player_index, player.bench.values[i]);
    return count;
}

__device__ __forceinline__ gc_i32 effect_select_count(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    gc_i32 count = effect.select_count;
    if ((effect.flags & kEffectFlagSelectTargetCount) != 0) count = runtime.target_count;
    else if ((effect.flags & kEffectFlagSelectCoinHeadCount) != 0) count = state.coin_head_count;
    else if ((effect.flags & kEffectFlagSelectCoinHeadCount2) != 0) count = state.coin_head_count * 2;
    else if ((effect.flags & kEffectFlagSelectEnemyEnergyCount) != 0)
        count = total_enemy_in_play_energy(state, rules, effect_player_index(state));
    return count;
}

__device__ __forceinline__ gc_u8 option_card_ref(
    const BattleCoreState& state,
    const SelectOptionState& option
) {
    const gc_i32 player_index = option.param2;
    if (player_index < 0 || player_index > 1) return 0;
    return area_ref_at(state, player_index, (gc_u8)option.param0, option.param1);
}

__device__ __forceinline__ gc_u8 option_attached_ref(
    const BattleCoreState& state,
    const SelectOptionState& option,
    bool energy
) {
    const gc_i32 player_index = option.param2;
    if (player_index < 0 || player_index > 1) return 0;
    const gc_u8 pokemon_ref = area_ref_at(state, player_index, (gc_u8)option.param0, option.param1);
    if (pokemon_ref == 0) return 0;
    const gc_i32 move_counter = state.all_card[pokemon_ref].move_counter;
    const PlayerState& player = state.players[player_index];
    gc_i32 attached_index = 0;
    if (energy) {
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
            const gc_u8 ref = player.energy.values[i];
            if (state.all_card[ref].attach_move_counter != move_counter) continue;
            if (attached_index++ == option.param3) return ref;
        }
    } else {
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
            const gc_u8 ref = player.tool.values[i];
            if (state.all_card[ref].attach_move_counter != move_counter) continue;
            if (attached_index++ == option.param3) return ref;
        }
    }
    return 0;
}

__device__ __forceinline__ gc_i32 attached_ordinal(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 attached_ref,
    bool energy
) {
    if (attached_ref == 0 || player_index < 0 || player_index > 1) return -1;
    const CardState& attached = state.all_card[attached_ref];
    const PlayerState& player = state.players[player_index];
    gc_i32 ordinal = 0;
    if (energy) {
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
            const gc_u8 ref = player.energy.values[i];
            if (state.all_card[ref].attach_move_counter != attached.attach_move_counter) continue;
            if (ref == attached_ref) return ordinal;
            ++ordinal;
        }
    } else {
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
            const gc_u8 ref = player.tool.values[i];
            if (state.all_card[ref].attach_move_counter != attached.attach_move_counter) continue;
            if (ref == attached_ref) return ordinal;
            ++ordinal;
        }
    }
    return -1;
}

__device__ __forceinline__ void add_attached_target_option(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref,
    bool energy,
    bool energy_unit
) {
    if (ref == 0 || ref >= kAllCardCapacity) return;
    const CardState& attached = state.all_card[ref];
    const RefPositionState pos = attached_card_position(state, attached);
    if (pos.ref == 0 || attached.player_index < 0 || attached.player_index > 1) return;
    const gc_i32 ordinal = attached_ordinal(state, attached.player_index, ref, energy);
    if (ordinal < 0) return;
    if (energy_unit) {
        const RuleCardMaster* master = nullptr;
        (void)master;
        add_option_energy(runtime, pos.area, pos.index, attached.player_index, ordinal, 1);
    } else if (energy) {
        add_option_energy_card(runtime, pos.area, pos.index, attached.player_index, ordinal);
    } else {
        add_option_tool_card(runtime, pos.area, pos.index, attached.player_index, ordinal);
    }
}

__device__ __forceinline__ bool effect_is_not_open_select_no_condition(const RuleEffect& effect) {
    if (effect.target.area_count != 1 || effect.target.condition_count == 0) return false;
    const gc_u8 area = effect.target.areas[0];
    return area == 1 || area == 12;
}

__device__ __forceinline__ bool effect_instant_dispatch(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    if (effect.effect_type <= 29) return effect_instant_0_29(state, runtime, rules, effect, depth);
    if (effect.effect_type <= 47) return effect_instant_30_47(state, runtime, rules, effect, depth);
    if (effect.effect_type <= 55) return effect_instant_48_55(state, runtime, rules, effect);
    if (effect.effect_type <= 71) return effect_instant_56_71(state, runtime, rules, effect);
    if (effect.effect_type <= 95) return effect_instant_72_95(state, runtime, rules, effect);
    if (effect.effect_type <= 110) return effect_instant_96_110(state, runtime, rules, effect);
    if (effect.effect_type <= 135) return effect_instant_111_135(state, runtime, rules, effect);
    if (effect.effect_type <= 158) return effect_instant_136_158(state, runtime, rules, effect);
    if (effect.effect_type <= 170) return effect_instant_159_170(state, runtime, rules, effect);
    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
    return false;
}

__device__ __forceinline__ void begin_generic_card_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleEffect& effect,
    gc_i32 player_index,
    gc_i32 minimum,
    gc_i32 maximum
) {
    set_select_full(state, runtime, kSelectCard, effect.select_context, player_index, minimum, maximum);
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        const AreaRefState ref = runtime.targets[i];
        if (!valid_area_ref(state, ref)) continue;
        gc_u8 area = 0; gc_i32 index = -1; gc_i32 owner = -1;
        if (card_position_for_ref(state, ref.card, area, index, owner)) add_option_card(runtime, area, index, owner);
    }
    runtime.pending_effect_kind = kPendingEffectSelection;
    runtime.pending_effect_substep = kPendingSubstepGenericCard;
}

__device__ __forceinline__ bool begin_effect_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 select_count,
    gc_i32 select_player
) {
    const gc_u8 select_type = effect.effect_select_type;
    if (select_type == kEffectSelectEvolve || select_type == kEffectSelectEvolve2) {
        set_select_full(state, runtime, kSelectEvolve, kSelectContextEvolve, select_player);
        const PlayerState& player = state.players[select_player];
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
            const AreaRefState source = runtime.targets[i];
            if (!valid_area_ref(state, source)) continue;
            const CardState& evolve = state.all_card[source.card];
            const RuleCardMaster* master = rule_card(rules, evolve.card_id);
            if (master == nullptr) continue;
            const gc_i32 source_index = current_area_index(player, evolve.area, source.card);
            if (source_index < 0) continue;
            if (player.active.count > 0) {
                const gc_u8 target = player.active.values[0];
                const bool can = select_type == kEffectSelectEvolve
                    ? can_evolve_effect(state, rules, evolve, *master, target)
                    : can_evolve2(state, rules, evolve, *master, target);
                if (can) add_option_evolve(runtime, evolve.area, source_index, kAreaActive, 0);
            }
            for (gc_i32 j = 0; j < (gc_i32)player.bench.count; ++j) {
                const gc_u8 target = player.bench.values[j];
                const bool can = select_type == kEffectSelectEvolve
                    ? can_evolve_effect(state, rules, evolve, *master, target)
                    : can_evolve2(state, rules, evolve, *master, target);
                if (can) add_option_evolve(runtime, evolve.area, source_index, kAreaBench, j);
            }
        }
        runtime.pending_effect_kind = kPendingEffectSelection;
        runtime.pending_effect_substep = kPendingSubstepGenericEvolve;
        return runtime.option_count != 0;
    }

    if (select_type == kEffectSelectMaxEnergyCard || select_type == kEffectSelectToolCard) {
        gc_u8 context = effect.select_context;
        if (select_type == kEffectSelectMaxEnergyCard && context == kSelectContextDiscard)
            context = kSelectContextDiscardEnergyCard;
        if (select_type == kEffectSelectToolCard && context == kSelectContextDiscard)
            context = kSelectContextDiscardToolCard;
        gc_i32 maximum = runtime.target_count < select_count ? runtime.target_count : select_count;
        gc_i32 minimum = 1;
        if (select_type == kEffectSelectMaxEnergyCard && on_attack_effect(state)) minimum = 0;
        if ((effect.flags & kEffectFlagCanNoSelect) != 0) minimum = 0;
        if ((effect.flags & kEffectFlagCannotNoSelect) != 0) minimum = 1;
        set_select_full(state, runtime, kSelectAttachedCard, context, select_player, minimum, maximum);
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
            const gc_u8 ref = runtime.targets[i].card;
            if (!valid_area_ref(state, runtime.targets[i])) continue;
            add_attached_target_option(state, runtime, ref, select_type == kEffectSelectMaxEnergyCard, false);
        }
        runtime.pending_effect_kind = kPendingEffectSelection;
        runtime.pending_effect_substep = kPendingSubstepGenericAttached;
        return runtime.option_count != 0;
    }

    if (select_type == kEffectSelectCardOrAttachedCardCount) {
        gc_u8 context = effect.select_context == kSelectContextDiscard
            ? kSelectContextDiscardCardOrAttachedCard : effect.select_context;
        gc_i32 maximum = runtime.target_count < select_count ? runtime.target_count : select_count;
        set_select_full(state, runtime, kSelectCardOrAttachedCard, context, select_player, 1, maximum);
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
            const AreaRefState ref = runtime.targets[i];
            if (!valid_area_ref(state, ref)) continue;
            const CardState& card = state.all_card[ref.card];
            if (card.area == 8) add_attached_target_option(state, runtime, ref.card, true, false);
            else if (card.area == 9) add_attached_target_option(state, runtime, ref.card, false, false);
            else {
                gc_u8 area = 0; gc_i32 index = -1; gc_i32 owner = -1;
                if (card_position_for_ref(state, ref.card, area, index, owner)) add_option_card(runtime, area, index, owner);
            }
        }
        runtime.pending_effect_kind = kPendingEffectSelection;
        runtime.pending_effect_substep = kPendingSubstepGenericCardOrAttached;
        return runtime.option_count != 0;
    }

    if (select_type == kEffectSelectEnergy) {
        gc_u8 context = effect.select_context;
        if (context == kSelectContextDiscard) context = kSelectContextDiscardEnergy;
        else if (context == kSelectContextToDeck) context = kSelectContextToDeckEnergy;
        else if (context == kSelectContextToHand) context = kSelectContextToHandEnergy;
        state.energy_cost = select_count;
        state.remain_energy_cost = select_count;
        state.selected_energy_card_count = 0;
        state.selected_list.count = 0;
        if (runtime.target_count > 0) state.changed = 1;
        gc_i32 sum = 0;
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
            const AreaRefState r = runtime.targets[i];
            if (!valid_area_ref(state, r)) continue;
            const CardState& energy = state.all_card[r.card];
            const RefPositionState pos = attached_card_position(state, energy);
            if (pos.ref == 0) continue;
            sum += get_energy_info(state, rules, energy, pos.ref).count;
        }
        if (state.energy_cost > sum) state.energy_cost = state.remain_energy_cost = sum;
        gc_i32 minimum = state.remain_energy_cost <= 0 ? 0 : 1;
        if ((effect.flags & kEffectFlagEnergyMaxSelect) != 0 && on_attack_effect(state)) minimum = 0;
        set_select_full(state, runtime, kSelectEnergy, context, select_player, minimum, 1);
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
            const AreaRefState r = runtime.targets[i];
            if (!valid_area_ref(state, r) || is_prevent_effect(state, rules, r.card)) continue;
            const CardState& energy = state.all_card[r.card];
            const RefPositionState pos = attached_card_position(state, energy);
            if (pos.ref == 0) continue;
            const gc_i32 ordinal = attached_ordinal(state, energy.player_index, r.card, true);
            if (ordinal < 0) continue;
            const gc_i32 units = get_energy_info(state, rules, energy, pos.ref).count;
            add_option_energy(runtime, pos.area, pos.index, energy.player_index, ordinal, units);
        }
        runtime.pending_effect_kind = kPendingEnergyMove;
        runtime.pending_effect_substep = 0;
        return runtime.option_count != 0;
    }

    gc_i32 count = select_count;
    if (select_type == kEffectSelectCardUntil) {
        count = (gc_i32)runtime.target_count - effect.select_count;
        if (count <= 0) return false;
    } else if (select_type == kEffectSelectMaxCardUntil) {
        count = (gc_i32)runtime.target_count - effect.select_count;
        if (count < 0) count = 0;
    }
    gc_i32 maximum = runtime.target_count < count ? runtime.target_count : count;
    if (effect.effect_type == 19) {
        const gc_i32 target_player = effect_target_player_index(state, effect);
        const gc_i32 remain = remaining_bench(state, target_player);
        if (remain <= 0) return false;
        if (maximum > remain) maximum = remain;
    } else if ((effect.effect_type == 64 || effect.effect_type == 65) && state.selected_list.count == 0) {
        return false;
    }
    gc_i32 minimum = maximum;
    if (select_type == kEffectSelectMaxCardCount) {
        minimum = on_attack_effect(state) ? 0 : (maximum > 0 ? 1 : 0);
    } else if (select_type == kEffectSelectMaxCardUntil) {
        maximum = runtime.target_count;
    }
    if ((effect.flags & kEffectFlagCanNoSelect) != 0) minimum = 0;
    if ((effect.flags & kEffectFlagCanNoSelectIfExistPreTarget) != 0 && runtime.pre_target_count > 0) minimum = 0;
    if (effect_is_not_open_select_no_condition(effect)) minimum = 0;
    if (maximum >= 1 && minimum == 0 && (effect.flags & kEffectFlagCannotNoSelect) != 0
        && (!on_attack_effect(state) || effect.skill_id == 0)) minimum = 1;

    if ((effect.flags & kEffectFlagRandomSelect) != 0) {
        shuffle_target_refs(runtime);
        if (runtime.target_count > maximum) runtime.target_count = (gc_u16)maximum;
        return false;
    }
    begin_generic_card_selection(state, runtime, effect, select_player, minimum, maximum);
    return runtime.option_count != 0 || minimum == 0;
}

__device__ __forceinline__ bool switch_effect_selection_blocked(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 select_player
) {
    if (effect.effect_type != 23) return false;
    const gc_i32 owner = effect_player_index(state);
    gc_i32 target_player = -1;
    if (effect.target.target_player == 1) target_player = owner;
    else if (effect.target.target_player == 2) target_player = 1 - owner;
    else return false;
    if ((effect.flags & kEffectFlagEffectTargetActive) == 0
        && (owner == target_player || select_player == target_player)) return false;
    if ((effect.flags & kEffectFlagEffectTargetBench) != 0) return false;
    const PlayerState& player = state.players[target_player];
    if (player.active.count == 0) return true;
    return is_prevent_effect(state, rules, player.active.values[0]);
}

__device__ __forceinline__ void append_effect_check_list(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
        if (state.check_list.count >= (gc_i32)(sizeof(state.check_list.values) / sizeof(state.check_list.values[0]))) {
            runtime.error_flags |= kRuntimeErrorZoneOverflow;
            return;
        }
        state.check_list.values[state.check_list.count++] = runtime.targets[i].card;
    }
}

__device__ __forceinline__ bool dispatch_effect_after_selection(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    gc_i32 depth
) {
    if (effect.loop_count > 0 && runtime.target_count == 0) {
        state.effect_loop_stop = 1;
        state.effect_state.on_effect = 0;
        return false;
    }
    if ((effect.flags & kEffectFlagAddCheckList) != 0) {
        append_effect_check_list(state, runtime);
        if (runtime.error_flags != 0) return false;
    }
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_substep = 0;
    effect_instant_dispatch(state, runtime, rules, effect, depth);
    if (runtime.error_flags != 0) return false;
    if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone) return true;
    state.effect_state.on_effect = 0;
    return false;
}

__device__ __forceinline__ bool activate_effect_instance(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const EffectSpanState& span,
    gc_i32 effect_index,
    gc_i32 depth
) {
    if (effect_index < 0 || effect_index >= span.count) return false;
    const RuleEffect& effect = span.effects[effect_index];
    state.effect_state.effect_index = (gc_i8)effect_index;
    state.effect_state.on_effect = 1;

    if ((effect.flags & kEffectFlagIsCondition) != 0) {
        if (effect_index >= span.first_condition_count) {
            if (!satisfy_condition(state, runtime, rules, span.effects, span.count, effect_index,
                                   state.effect_state.ability.effect_card.card_index, effect_player_index(state))) {
                if (effect.fail_skip) state.effect_jump = (gc_u8)effect.fail_skip;
                else state.is_break = 1;
            }
            state.effect_state.on_effect = 0;
        }
        return false;
    }

    gc_i32 select_count = effect_select_count(state, runtime, rules, effect);
    if (((effect.flags & kEffectFlagSelectCoinHeadCount) != 0
         || (effect.flags & kEffectFlagSelectCoinHeadCount2) != 0
         || (effect.flags & kEffectFlagSelectEnemyEnergyCount) != 0) && select_count == 0) {
        state.effect_state.on_effect = 0;
        return false;
    }

    if ((effect.flags & kEffectFlagNotUpdateTarget) == 0) {
        if (effect.target.area_count == 0 || effect.target.areas[0] != 17) copy_effect_targets_to_pre(runtime);
        target_list(state, runtime, rules, effect.target,
                    runtime.targets, runtime.target_count,
                    activate_effect_ref(state.effect_state.ability), effect_player_index(state),
                    true, kRuntimeErrorTargetOverflow);
        if (runtime.error_flags != 0) return false;
        if (runtime.target_count == 0) {
            if (effect.loop_count > 0) { state.effect_loop_stop = 1; state.effect_state.on_effect = 0; return false; }
            if (effect.target.area_count == 1
                && (effect.target.areas[0] == 19 || effect.target.areas[0] == 20)) {
                state.effect_state.on_effect = 0;
                return false;
            }
        }
    }
    if ((effect.flags & kEffectFlagNotPreTarget) != 0) remove_pre_targets(runtime);
    if ((effect.flags & kEffectFlagSkipNoTarget) != 0 && runtime.target_count == 0) {
        state.effect_state.on_effect = 0;
        return false;
    }
    if (effect.effect_select_type != kEffectSelectAll && rule_target_has_area(effect.target, 1)) state.select_deck = 1;
    if ((effect.flags & kEffectFlagSeeingDeck) != 0) state.select_deck = 1;

    gc_i32 select_player = state.effect_state.ability.use_player_index;
    if (select_player < 0 || select_player > 1) select_player = effect_player_index(state);
    if ((effect.flags & kEffectFlagEnemySelect) != 0) select_player = 1 - select_player;
    if (switch_effect_selection_blocked(state, rules, effect, select_player)) {
        state.effect_state.on_effect = 0;
        return false;
    }

    if (effect.effect_select_type != kEffectSelectAll) {
        if (begin_effect_selection(state, runtime, rules, effect, select_count, select_player)) return true;
        if ((effect.flags & kEffectFlagRandomSelect) == 0 || effect.effect_select_type == kEffectSelectEnergy) {
            state.effect_state.on_effect = 0;
            return false;
        }
    }

    return dispatch_effect_after_selection(state, runtime, rules, effect, depth);
}

__device__ __forceinline__ void reset_effect_repeat(BattleRuntimeState& runtime) {
    runtime.effect_repeat_index = 0;
    runtime.effect_repeat_count = 0;
    runtime.effect_repeat_mode = kEffectRepeatSingle;
}

__device__ __forceinline__ bool prepare_effect_repeat(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleEffect& effect
) {
    reset_effect_repeat(runtime);
    if ((effect.flags & kEffectFlagEachSelectedList) != 0) {
        runtime.effect_repeat_mode = kEffectRepeatSelected;
        runtime.effect_repeat_count = state.selected_list.count;
    } else if ((effect.flags & kEffectFlagEachList) != 0) {
        runtime.effect_repeat_mode = kEffectRepeatEach;
        runtime.effect_repeat_count = state.each_list.count;
    } else if (effect.loop_count > 0) {
        runtime.effect_repeat_mode = kEffectRepeatLoop;
        runtime.effect_repeat_count = effect.loop_count;
        state.effect_loop_stop = 0;
    } else {
        runtime.effect_repeat_count = 1;
    }
    return runtime.effect_repeat_count > 0;
}

__device__ __forceinline__ void bind_effect_repeat_context(
    BattleCoreState& state,
    const BattleRuntimeState& runtime
) {
    if (runtime.effect_repeat_mode == kEffectRepeatSelected) {
        state.effect_state.selected_list_index = (gc_i8)runtime.effect_repeat_index;
        state.context_card = state.selected_list.values[runtime.effect_repeat_index];
    } else if (runtime.effect_repeat_mode == kEffectRepeatEach) {
        state.effect_state.each_list_index = (gc_i8)runtime.effect_repeat_index;
        state.context_card = state.each_list.values[runtime.effect_repeat_index];
    } else if (runtime.effect_repeat_mode == kEffectRepeatLoop) {
        state.effect_state.selected_list_index = (gc_i8)runtime.effect_repeat_index;
    }
}

__device__ __forceinline__ void finish_effect_instance(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleEffect& effect
) {
    state.effect_state.on_effect = 0;
    runtime.effect_instance_waiting = 0;
    if ((effect.flags & kEffectFlagSeparator) != 0 && !state.changed) state.effect_jump = 99;
    ++runtime.effect_repeat_index;
    if (runtime.effect_repeat_index >= runtime.effect_repeat_count || state.is_break) {
        ++runtime.effect_cursor;
        reset_effect_repeat(runtime);
    }
}

__device__ __noinline__ void run_effect_execution(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    if (!runtime.effect_execution_active || runtime.error_flags != 0) return;
    EffectSpanState span{};
    if (!current_effect_span(state, rules, span)) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        runtime.effect_execution_active = 0;
        return;
    }
    for (gc_i32 steps = 0; steps < 10000; ++steps) {
        if (runtime.effect_instance_waiting || state.select_type != kSelectNone
            || runtime.pending_effect_kind != kPendingNone) return;
        if (state.is_break || runtime.effect_cursor >= span.count) {
            runtime.effect_execution_active = 0;
            state.effect_state.on_effect = 0;
            return;
        }
        if (state.effect_jump > 0) {
            --state.effect_jump;
            ++runtime.effect_cursor;
            reset_effect_repeat(runtime);
            continue;
        }
        const RuleEffect& effect = span.effects[runtime.effect_cursor];
        if (runtime.effect_repeat_count == 0 && !prepare_effect_repeat(state, runtime, effect)) {
            ++runtime.effect_cursor;
            continue;
        }
        if (runtime.effect_repeat_mode == kEffectRepeatLoop && state.effect_loop_stop) {
            state.effect_loop_stop = 0;
            ++runtime.effect_cursor;
            reset_effect_repeat(runtime);
            continue;
        }
        bind_effect_repeat_context(state, runtime);
        const bool waiting = activate_effect_instance(state, runtime, rules, span, runtime.effect_cursor, depth);
        if (waiting) {
            runtime.effect_instance_waiting = 1;
            return;
        }
        finish_effect_instance(state, runtime, effect);
        if (runtime.error_flags != 0) return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

__device__ __forceinline__ void start_effect_execution(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 start_index,
    gc_i32 depth
) {
    runtime.effect_cursor = (gc_i16)start_index;
    reset_effect_repeat(runtime);
    runtime.effect_execution_active = 1;
    runtime.effect_instance_waiting = 0;
    runtime.pending_effect_kind = kPendingNone;
    runtime.pending_effect_substep = 0;
    state.is_break = 0;
    state.effect_jump = 0;
    run_effect_execution(state, runtime, rules, depth);
}

__device__ __forceinline__ bool append_turn_used_skill(BattleRuntimeState& runtime, gc_i32 skill_id) {
    if (runtime.turn_used_skill_count >= kTurnSkillCapacity) {
        runtime.error_flags |= kRuntimeErrorTurnHistoryOverflow;
        return false;
    }
    runtime.turn_used_skills[runtime.turn_used_skill_count++] = (gc_i16)skill_id;
    return true;
}

__device__ __forceinline__ bool mark_once_turn_skill(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleSkill& skill
) {
    if ((skill.flags & kSkillFlagOnceTurn) == 0) return true;
    const gc_u8 ref = state.effect_state.ability.effect_card.card_index;
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    CardState& card = state.all_card[ref];
    for (gc_i32 i = 0; i < (gc_i32)card.ability_used.count; ++i)
        if (card.ability_used.values[i] == card.card_id) return false;
    if (card.ability_used.count >= 8) {
        for (gc_i32 i = 1; i < 8; ++i) card.ability_used.values[i - 1] = card.ability_used.values[i];
        card.ability_used.count = 7;
    }
    card.ability_used.values[card.ability_used.count++] = (gc_i16)card.card_id;
    return true;
}

__device__ __forceinline__ void activate_ability_body(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleSkill& skill,
    gc_i32 start_index,
    gc_i32 depth
) {
    if (!mark_once_turn_skill(state, runtime, skill)) return;
    if (!append_turn_used_skill(runtime, skill.skill_id)) return;
    start_effect_execution(state, runtime, rules, start_index, depth);
}

__device__ __noinline__ void activate_ability_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 depth
) {
    runtime.target_count = 0;
    state.changed = 0;
    const RuleSkill* skill = rule_skill(rules, state.effect_state.ability.skill_id);
    if (skill == nullptr) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_u8 ref = state.effect_state.ability.effect_card.card_index;
    const gc_i32 owner = state.effect_state.ability.use_player_index;
    if ((skill->flags & kSkillFlagCanSelectActivate) != 0) {
        state.context_card = ref;
        set_select_full(state, runtime, kSelectYesNo, kSelectContextActivate, owner);
        add_option_yes_no(runtime);
        runtime.pending_effect_kind = kPendingSelectActivate;
        runtime.pending_effect_substep = kPendingSubstepAbilityActivate;
        return;
    }
    if (skill->second_effect_start_index > 0) {
        if (!satisfy_skill_condition(state, runtime, rules, *skill, ref, owner, 0)) {
            activate_ability_body(state, runtime, rules, *skill, skill->second_effect_start_index, depth);
            return;
        }
        state.context_card = ref;
        set_select_full(state, runtime, kSelectYesNo, kSelectContextFirstEffect, owner);
        add_option_yes_no(runtime);
        runtime.pending_effect_kind = kPendingSelectEffect;
        runtime.pending_effect_substep = kPendingSubstepAbilityFirstEffect;
        runtime.pending_effect_arg0 = skill->second_effect_start_index;
        return;
    }
    if (skill->second_effect_start_index_enemy > 0) {
        state.context_card = ref;
        set_select_full(state, runtime, kSelectYesNo, kSelectContextActivate, 1 - owner);
        add_option_yes_no(runtime);
        runtime.pending_effect_kind = kPendingSelectEffect;
        runtime.pending_effect_substep = kPendingSubstepAbilityEnemyEffect;
        runtime.pending_effect_arg0 = skill->second_effect_start_index_enemy;
        return;
    }
    const gc_i32 default_start = skill->trigger_start_index > 0 ? skill->trigger_start_index : 0;
    activate_ability_body(state, runtime, rules, *skill, default_start, depth);
}

}  // namespace gpu_cabt
