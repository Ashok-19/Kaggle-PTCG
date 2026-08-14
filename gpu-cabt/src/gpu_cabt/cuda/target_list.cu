namespace gpu_cabt {

__device__ __forceinline__ AreaRefState trigger_area_ref(const AreaRef& ref) {
    AreaRefState result{};
    result.card = ref.card_index;
    result.move_counter = ref.move_counter;
    return result;
}

__device__ __forceinline__ bool on_skill(const BattleCoreState& state) {
    return state.effect_state.ability.skill_id > 0;
}

__device__ __noinline__ bool target_single(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    const RuleTargetCondition& target,
    const AreaRefState& effect_card
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    const RuleCardMaster* master_ptr = rule_card(rules, card.card_id);
    if (master_ptr == nullptr) return target.target_type == 0;
    const RuleCardMaster& master = *master_ptr;
    const gc_u8 comparator = target.comparator_type;
    switch (target.target_type) {
        case 0: return true;
        case 1: return compare_i32(get_hp(card, master), target.value, comparator);
        case 2: return compare_i32(master.hp, target.value, comparator);
        case 3: return compare_i32(retreat_cost(card, master), target.value, comparator);
        case 4: return bool_compare(match_energy(get_card_energy_type(card, master), (gc_u16)target.value), comparator);
        case 5: return bool_compare(
            match_energy(get_card_energy_type(card, master), (gc_u16)target.value)
                || match_energy(get_card_energy_type(card, master), (gc_u16)target.value2), comparator);
        case 6: return bool_compare(match_energy(master.resistance, (gc_u16)target.value), comparator);
        case 7: return bool_compare(master.card_type == 0, comparator);
        case 8: {
            const bool basic = master.evolution_type == 1
                && (card.area == kAreaActive || card.area == kAreaBench || master.card_type == 0);
            return bool_compare(basic, comparator);
        }
        case 9: return bool_compare(master.evolution_type == 2 || master.evolution_type == 3, comparator);
        case 10: return bool_compare(master.evolution_type == 2, comparator);
        case 11: return bool_compare(master.evolution_type == 3, comparator);
        case 12: return bool_compare(master.card_type == 5, comparator);
        case 13: return bool_compare(master.card_type == 6, comparator);
        case 14: return bool_compare(is_energy_card(master.card_type), comparator);
        case 15: return bool_compare(master.card_type == 1, comparator);
        case 16: return bool_compare(master.card_type == 2, comparator);
        case 17: return bool_compare(master.card_type == 3, comparator);
        case 18: return bool_compare(master.card_type == 4, comparator);
        case 19: return bool_compare(is_trainer(master.card_type), comparator);
        case 20: return bool_compare(master.card_id == target.value, comparator);
        case 21: return bool_compare(master.card_type == 0 || master.card_type == 5, comparator);
        case 22: {
            const bool result = master.card_type == 0
                ? master.evolution_type == 1
                : master.card_type == 5;
            return bool_compare(result, comparator);
        }
        case 23: return bool_compare(is_not_rule_pokemon_card(master) || master.card_type == 5, comparator);
        case 24: {
            bool match = false;
            if (master.card_type == 0) match = match_energy(get_card_energy_type(card, master), (gc_u16)target.value);
            else if (master.card_type == 4) match = true;
            return bool_compare(match, comparator);
        }
        case 25: return bool_compare(master.card_type == 1 || master.card_type == 2, comparator);
        case 26: {
            if (effect_card.card == 0 || effect_card.card >= kAllCardCapacity) return false;
            const CardState& source = state.all_card[effect_card.card];
            if (card.area == 9) return source.player_index != card.player_index;
            if (card.area == 8) return source.player_index != card.player_index && master.card_type == 6;
            return true;
        }
        case 27: return bool_compare(card_flag(master, kCardFlagEthan) || master.card_id == 2, comparator);
        case 28: return bool_compare(get_ability(rules, card, master) != nullptr, comparator);
        case 29: {
            const RuleSkill* ability = get_ability(rules, card, master);
            return bool_compare(ability != nullptr && ability->name_hash == target.name_hash, comparator);
        }
        case 30: {
            bool found = false;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const RuleAttack* attack = rule_attack(rules, master.attack_ids[i]);
                if (attack != nullptr && attack->name_hash == target.name_hash) { found = true; break; }
            }
            return bool_compare(found, comparator);
        }
        case 31: return bool_compare(is_rule_pokemon(master), comparator);
        case 32: return bool_compare(is_not_rule_pokemon(master), comparator);
        case 33: return bool_compare(is_ex(master), comparator);
        case 34: return bool_compare(master.pokemon_type == 4, comparator);
        case 35: return bool_compare(card_flag(master, kCardFlagTera), comparator);
        case 36: return bool_compare(card_flag(master, kCardFlagAncient), comparator);
        case 37: return bool_compare(card_flag(master, kCardFlagFuture), comparator);
        case 38: return bool_compare(card_flag(master, kCardFlagHop), comparator);
        case 39: return bool_compare(card_flag(master, kCardFlagLillie), comparator);
        case 40: return bool_compare(card_flag(master, kCardFlagIono), comparator);
        case 41: return bool_compare(card_flag(master, kCardFlagN), comparator);
        case 42: return bool_compare(card_flag(master, kCardFlagEthan), comparator);
        case 43: return bool_compare(card_flag(master, kCardFlagCynthia), comparator);
        case 44: return bool_compare(card_flag(master, kCardFlagMisty), comparator);
        case 45: return bool_compare(card_flag(master, kCardFlagArven), comparator);
        case 46: return bool_compare(card_flag(master, kCardFlagSteven), comparator);
        case 47: return bool_compare(card_flag(master, kCardFlagMarnie), comparator);
        case 48: return bool_compare(card_flag(master, kCardFlagErika), comparator);
        case 49: return bool_compare(card_flag(master, kCardFlagLarry), comparator);
        case 50: return bool_compare(card_flag(master, kCardFlagTeamRocket), comparator);
        case 51: return bool_compare(card_flag(master, kCardFlagSilcoonOrCascoon), comparator);
        case 52: return bool_compare(card_flag(master, kCardFlagKoffingOrWeezing), comparator);
        case 53: return bool_compare(card_flag(master, kCardFlagHonedgeOrDoubladeOrAegislash), comparator);
        case 54: return bool_compare(master.name_hash == target.name_hash, comparator);
        case 55: return bool_compare(substring_mask_match(rules, target.substring_mask_index, master.card_id), comparator);
        case 56: {
            if (master.evolution_type != 2 && master.evolution_type != 3) return false;
            if (card.player_index < 0 || card.player_index > 1) return false;
            const PlayerState& player = state.players[card.player_index];
            for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
                if (can_evolve_effect(state, rules, card, master, player.active.values[i])) return true;
            for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
                if (can_evolve_effect(state, rules, card, master, player.bench.values[i])) return true;
            return false;
        }
        case 57: {
            if (master.evolution_type != 3 || card.player_index < 0 || card.player_index > 1) return false;
            const PlayerState& player = state.players[card.player_index];
            for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
                if (can_evolve2(state, rules, card, master, player.active.values[i])) return true;
            for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
                if (can_evolve2(state, rules, card, master, player.bench.values[i])) return true;
            return false;
        }
        case 58:
            return effect_card.card != 0 && bool_compare(can_evolve_effect(state, rules, card, master, effect_card.card), comparator);
        case 59:
            return state.context_card != 0 && bool_compare(can_evolve_effect(state, rules, card, master, state.context_card), comparator);
        case 60: {
            if (state.context_card == 0) return false;
            const CardState& context = state.all_card[state.context_card];
            const RuleCardMaster* cm = rule_card(rules, context.card_id);
            return cm != nullptr && bool_compare(can_evolve_effect(state, rules, context, *cm, ref), comparator);
        }
        case 61: {
            if (card.player_index < 0 || card.player_index > 1) return false;
            const PlayerState& player = state.players[card.player_index];
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) found |= can_evolve_effect(state, rules, card, master, player.active.values[i]);
            for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) found |= can_evolve_effect(state, rules, card, master, player.bench.values[i]);
            return bool_compare(found, comparator);
        }
        case 62: {
            if (card.player_index < 0 || card.player_index > 1) return false;
            const PlayerState& player = state.players[card.player_index];
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) {
                const gc_u8 r = player.active.values[i];
                if (!card_turn(state.all_card[r]).fields.appear && can_evolve_effect(state, rules, card, master, r)) found = true;
            }
            for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
                const gc_u8 r = player.bench.values[i];
                if (!card_turn(state.all_card[r]).fields.appear && can_evolve_effect(state, rules, card, master, r)) found = true;
            }
            return bool_compare(found, comparator);
        }
        case 63: return bool_compare(is_evolved(state, ref), comparator);
        case 64: {
            for (gc_i32 i = 0; i < (gc_i32)runtime.turn_evolve_count; ++i) {
                const EvolveState& info = runtime.turn_evolve[i];
                if (info.ref != ref || info.pre_ref == 0) continue;
                const RuleCardMaster* pre = rule_card(rules, state.all_card[info.pre_ref].card_id);
                if (pre != nullptr && pre->name_hash == target.name_hash) return true;
            }
            return false;
        }
        case 65: return bool_compare(!card_turn(card).fields.appear, comparator);
        case 66: {
            for (gc_i32 i = 0; i < (gc_i32)runtime.turn_heal_count; ++i) if (runtime.turn_heal[i] == ref) return true;
            return false;
        }
        case 67:
            return effect_card.card != 0 && bool_compare(card.attach_move_counter == state.all_card[effect_card.card].move_counter, comparator);
        case 68: {
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)runtime.pre_target_count; ++i) {
                const AreaRefState& r = runtime.pre_targets[i];
                if (r.card != 0 && card.attach_move_counter == state.all_card[r.card].move_counter) { found = true; break; }
            }
            return bool_compare(found, comparator);
        }
        case 69: {
            if (!on_skill(state) || state.trigger_info.subject.card_index == 0) return false;
            return bool_compare(card.attach_move_counter == state.all_card[state.trigger_info.subject.card_index].move_counter, comparator);
        }
        case 70: {
            if (!on_skill(state) || state.trigger_info.object.card_index == 0) return false;
            return bool_compare(card.attach_move_counter == state.all_card[state.trigger_info.object.card_index].move_counter, comparator);
        }
        case 71:
            return state.context_card != 0 && bool_compare(card.attach_move_counter == state.all_card[state.context_card].move_counter, comparator);
        case 72: {
            if (card.player_index < 0 || card.player_index > 1) return false;
            const PlayerState& player = state.players[card.player_index];
            return player.active.count > 0 && bool_compare(card.attach_move_counter == state.all_card[player.active.values[0]].move_counter, comparator);
        }
        case 73: {
            if (card.player_index < 0 || card.player_index > 1) return false;
            bool found = false;
            const PlayerState& player = state.players[card.player_index];
            for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
                if (card.attach_move_counter == state.all_card[player.bench.values[i]].move_counter) { found = true; break; }
            return bool_compare(found, comparator);
        }
        case 74: return bool_compare(attached_energy_count(state, rules, card.player_index, ref) > 0, comparator);
        case 75: return compare_i32(attached_energy_count(state, rules, card.player_index, ref), target.value, comparator);
        case 76: return bool_compare(has_attached_special_energy(state, rules, ref), comparator);
        case 77: return bool_compare(attached_energy_type_count(state, rules, card.player_index, ref, (gc_u16)target.value) > 0, comparator);
        case 78: return bool_compare(attached_energy_type_count(state, rules, card.player_index, ref, (gc_u16)target.value) >= 2, comparator);
        case 79: return bool_compare(has_attached_energy_name(state, rules, ref, target.name_hash), comparator);
        case 80: return bool_compare(attached_tool_count(state, card) > 0, comparator);
        case 81: return bool_compare(has_attached_tool_name(state, rules, card, target.name_hash), comparator);
        case 82: return bool_compare(attached_tool_count(state, card) > 0 || has_attached_special_energy(state, rules, ref), comparator);
        case 83: {
            if (state.context_card == 0) return true;
            const CardState& context = state.all_card[state.context_card];
            return bool_compare(context.attach_move_counter != card.move_counter, comparator);
        }
        case 84: {
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)state.selected_list.count; ++i) {
                const CardState& selected = state.all_card[state.selected_list.values[i]];
                if (card.move_counter == selected.attach_move_counter) { found = true; break; }
            }
            return bool_compare(!found, comparator);
        }
        case 85: {
            const RefPositionState pos = attached_card_position(state, card);
            if (pos.ref == 0) return false;
            const EnergyInfoState info = get_energy_info(state, rules, card, pos.ref);
            return bool_compare(match_energy(info.type, (gc_u16)target.value), comparator);
        }
        case 86:
            if (card.area == kAreaHand) return true;
            return bool_compare(card.reverse != 0, comparator);
        case 87: return bool_compare((gc_i32)card.area == target.value, comparator);
        case 88: {
            const bool found = on_skill(state) && ref == state.trigger_info.subject.card_index;
            return bool_compare(found, comparator);
        }
        case 89: {
            const bool found = on_skill(state) && ref == state.trigger_info.object.card_index;
            return bool_compare(found, comparator);
        }
        case 90: return compare_i32(card.damage / 10, target.value, comparator);
        case 91: {
            gc_i32 min_hp = 10000000;
            for (gc_i32 p = 0; p < 2; ++p) {
                const PlayerState& player = state.players[p];
                for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) {
                    const gc_u8 r = player.active.values[i]; if (r == effect_card.card) continue;
                    const RuleCardMaster* m = rule_card(rules, state.all_card[r].card_id); if (m != nullptr) { const gc_i32 hp = get_hp(state.all_card[r], *m); if (hp < min_hp) min_hp = hp; }
                }
                for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
                    const gc_u8 r = player.bench.values[i]; if (r == effect_card.card) continue;
                    const RuleCardMaster* m = rule_card(rules, state.all_card[r].card_id); if (m != nullptr) { const gc_i32 hp = get_hp(state.all_card[r], *m); if (hp < min_hp) min_hp = hp; }
                }
            }
            return bool_compare(get_hp(card, master) == min_hp, comparator);
        }
        case 92: {
            if (card.player_index < 0 || card.player_index > 1) return false;
            gc_u16 enemy_types = 0; bool enemy_colorless = false;
            const PlayerState& enemy = state.players[1 - card.player_index];
            for (gc_i32 pass = 0; pass < 2; ++pass) {
                const gc_i32 n = pass == 0 ? enemy.active.count : enemy.bench.count;
                for (gc_i32 i = 0; i < n; ++i) {
                    const gc_u8 r = pass == 0 ? enemy.active.values[i] : enemy.bench.values[i];
                    const RuleCardMaster* m = rule_card(rules, state.all_card[r].card_id); if (m == nullptr) continue;
                    const gc_u16 t = get_card_energy_type(state.all_card[r], *m);
                    if (t == 0) enemy_colorless = true; else enemy_types |= t;
                }
            }
            bool found = false;
            const PlayerState& own = state.players[card.player_index];
            for (gc_i32 pass = 0; pass < 2 && !found; ++pass) {
                const gc_i32 n = pass == 0 ? own.active.count : own.bench.count;
                for (gc_i32 i = 0; i < n; ++i) {
                    const gc_u8 r = pass == 0 ? own.active.values[i] : own.bench.values[i];
                    const RuleCardMaster* m = rule_card(rules, state.all_card[r].card_id); if (m == nullptr) continue;
                    const gc_u16 t = get_card_energy_type(state.all_card[r], *m);
                    found |= t == 0 ? enemy_colorless : (enemy_types & t) != 0;
                }
            }
            return bool_compare(found, comparator);
        }
        case 93: return card.area == kAreaActive && bool_compare(is_special_condition(state.players[card.player_index]), comparator);
        case 94: return card.area == kAreaActive && bool_compare(is_special_condition(state.players[card.player_index]) || card.damage > 0, comparator);
        case 95: return card.area == kAreaActive && bool_compare(player_active_state(state.players[card.player_index]).fields.poison_damage_counter > 0, comparator);
        case 96: return card.area == kAreaActive && bool_compare(player_active_state(state.players[card.player_index]).fields.burned, comparator);
        case 97: return card.area == kAreaActive && bool_compare(player_active_state(state.players[card.player_index]).fields.bad_status == 3, comparator);
        case 98: return card.area == kAreaActive && bool_compare(
            player_active_state(state.players[card.player_index]).fields.poison_damage_counter > 0
                || player_active_state(state.players[card.player_index]).fields.burned, comparator);
        case 99: return bool_compare(card_turn(card).fields.bench_to_active, comparator);
        case 100: {
            if (effect_card.card == 0) return false;
            const gc_i32 enemy_player = 1 - state.all_card[effect_card.card].player_index;
            const PlayerState& enemy = state.players[enemy_player];
            bool found = false;
            for (gc_i32 pass = 0; pass < 2; ++pass) {
                const gc_i32 n = pass == 0 ? enemy.active.count : enemy.bench.count;
                for (gc_i32 i = 0; i < n; ++i) {
                    const gc_u8 r = pass == 0 ? enemy.active.values[i] : enemy.bench.values[i];
                    const RuleCardMaster* m = rule_card(rules, state.all_card[r].card_id);
                    if (m != nullptr && m->name_hash == master.name_hash) { found = true; break; }
                }
            }
            return bool_compare(found, comparator);
        }
        case 101: {
            bool found = false;
            for (gc_i32 i = 0; i < (gc_i32)state.check_list.count; ++i) {
                const gc_u8 r = state.check_list.values[i];
                if (r != 0 && state.all_card[r].card_id == card.card_id) { found = true; break; }
            }
            return bool_compare(!found, comparator);
        }
        default: return false;
    }
}

__device__ __noinline__ bool is_target(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    const RuleTarget& target,
    const AreaRefState& effect_card
) {
    for (gc_i32 i = 0; i < (gc_i32)target.condition_count; ++i) {
        if (!target_single(state, runtime, rules, ref, target.conditions[i], effect_card)) return false;
    }
    return true;
}

__device__ __forceinline__ bool append_area_ref(
    BattleRuntimeState& runtime,
    AreaRefState* output,
    gc_u16& count,
    const AreaRefState& ref,
    gc_u32 overflow_flag
) {
    if (count >= kAreaRefCapacity) { runtime.error_flags |= overflow_flag; return false; }
    output[count++] = ref;
    return true;
}

__device__ __forceinline__ void add_if_target(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    const RuleTarget& target,
    AreaRefState* output,
    gc_u16& count,
    const AreaRefState& effect_card,
    gc_u32 overflow_flag
) {
    if (is_target(state, runtime, rules, ref, target, effect_card)) {
        append_area_ref(runtime, output, count, make_area_ref(state, ref), overflow_flag);
    }
}

__device__ __noinline__ void target_list(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleTarget& target,
    AreaRefState* output,
    gc_u16& output_count,
    const AreaRefState& effect_card,
    gc_i32 effect_owner,
    bool output_is_runtime_target,
    gc_u32 overflow_flag
) {
    if (target.area_count == 0) { output_count = 0; return; }
    const gc_u8 first_area = target.areas[0];
    if (first_area == 15) {  // Me
        output_count = 0;
        if (not_moved(state, effect_card)) add_if_target(state, runtime, rules, effect_card.card, target, output, output_count, effect_card, overflow_flag);
        return;
    }
    if (first_area == 16) {  // Effected
        if (output_is_runtime_target) {
            gc_i32 write = 0;
            for (gc_i32 i = 0; i < (gc_i32)output_count; ++i) {
                if (is_target(state, runtime, rules, output[i].card, target, effect_card)) output[write++] = make_area_ref(state, output[i].card);
            }
            output_count = (gc_u16)write;
        } else {
            output_count = 0;
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i)
                add_if_target(state, runtime, rules, runtime.targets[i].card, target, output, output_count, effect_card, overflow_flag);
        }
    } else if (first_area == 17) {  // EffectedPreTarget
        output_count = 0;
        for (gc_i32 i = 0; i < (gc_i32)runtime.pre_target_count; ++i)
            add_if_target(state, runtime, rules, runtime.pre_targets[i].card, target, output, output_count, effect_card, overflow_flag);
    } else if (first_area == 18) {  // SelectedList
        output_count = 0;
        for (gc_i32 i = 0; i < (gc_i32)state.selected_list.count; ++i)
            add_if_target(state, runtime, rules, state.selected_list.values[i], target, output, output_count, effect_card, overflow_flag);
    } else if (first_area == 19) {  // TriggerSubject
        output_count = 0; const AreaRefState ref = trigger_area_ref(state.trigger_info.subject);
        if (not_moved(state, ref)) add_if_target(state, runtime, rules, ref.card, target, output, output_count, effect_card, overflow_flag);
        return;
    } else if (first_area == 20) {  // TriggerObject
        output_count = 0; const AreaRefState ref = trigger_area_ref(state.trigger_info.object);
        if (not_moved(state, ref)) add_if_target(state, runtime, rules, ref.card, target, output, output_count, effect_card, overflow_flag);
        return;
    } else if (first_area == 21) {  // Attach
        output_count = 0;
        if (effect_card.card != 0) {
            const RefPositionState pos = attached_card_position(state, state.all_card[effect_card.card]);
            if (pos.ref != 0) add_if_target(state, runtime, rules, pos.ref, target, output, output_count, effect_card, overflow_flag);
        }
        return;
    } else if (first_area == 22) {  // TurnPlay
        output_count = 0;
        for (gc_i32 i = 0; i < (gc_i32)runtime.turn_play_count; ++i)
            add_if_target(state, runtime, rules, runtime.turn_play[i], target, output, output_count, effect_card, overflow_flag);
    } else if (first_area == 23) {  // AttackPreMyTurn
        output_count = 0;
        if (effect_card.card != 0) {
            const CardState& card = state.all_card[effect_card.card];
            gc_i32 turn_index = rule_active_player_index(state) == card.player_index ? 2 : 1;
            const gc_u8 ref = state.turn_histories[turn_index].turn_attack_card;
            if (ref != 0) add_if_target(state, runtime, rules, ref, target, output, output_count, effect_card, overflow_flag);
        }
    } else {
        output_count = 0;
        for (gc_i32 order = 0; order < 2; ++order) {
            const gc_i32 player_index = order == 0 ? state.first_player : 1 - state.first_player;
            if (!is_target_player(effect_owner, player_index, target.target_player)) continue;
            const PlayerState& player = state.players[player_index];
            for (gc_i32 ai = 0; ai < (gc_i32)target.area_count; ++ai) {
                const gc_u8 area = target.areas[ai];
                if (area == 1 || area == 2 || area == 3 || area == 4 || area == 5 || area == 6 || area == 8 || area == 9 || area == 24) {
                    const gc_u8* values = nullptr; gc_i32 count = 0;
                    if (area == 1) { values = player.deck.values; count = player.deck.count; }
                    else if (area == 2) { values = player.hand.values; count = player.hand.count; }
                    else if (area == 3) { values = player.trash.values; count = player.trash.count; }
                    else if (area == 4) { values = player.active.values; count = player.active.count; }
                    else if (area == 5) { values = player.bench.values; count = player.bench.count; }
                    else if (area == 6) { values = player.prize.values; count = player.prize.count; }
                    else if (area == 8) { values = player.energy.values; count = player.energy.count; }
                    else if (area == 9) { values = player.tool.values; count = player.tool.count; }
                    else { values = player.temporary.values; count = player.temporary.count; }
                    for (gc_i32 i = 0; i < count; ++i) {
                        if (area == 2 && (target.flags & 2u) != 0 && effect_card.card != 0
                            && player_index != state.all_card[effect_card.card].player_index) {
                            append_area_ref(runtime, output, output_count, make_area_ref(state, values[i]), overflow_flag);
                        } else {
                            add_if_target(state, runtime, rules, values[i], target, output, output_count, effect_card, overflow_flag);
                        }
                    }
                } else if (area == 7) {
                    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i) {
                        const gc_u8 ref = state.stadium.values[i];
                        if (state.all_card[ref].player_index == player_index)
                            add_if_target(state, runtime, rules, ref, target, output, output_count, effect_card, overflow_flag);
                    }
                } else if (area == 11) {
                    append_area_ref(runtime, output, output_count, make_area_ref(state, (gc_u8)(1 + player_index)), overflow_flag);
                } else if (area == 12) {
                    for (gc_i32 i = 0; i < (gc_i32)state.looking.count; ++i) {
                        const gc_u8 ref = state.looking.values[i];
                        if (state.all_card[ref].player_index == player_index)
                            add_if_target(state, runtime, rules, ref, target, output, output_count, effect_card, overflow_flag);
                    }
                } else {
                    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
                    return;
                }
            }
        }
    }

    if ((target.flags & 1u) != 0) {
        for (gc_i32 i = 0; i < (gc_i32)output_count; ++i) {
            if (output[i].card == effect_card.card) {
                for (gc_i32 j = i + 1; j < (gc_i32)output_count; ++j) output[j - 1] = output[j];
                --output_count;
                break;
            }
        }
    }
}

}  // namespace gpu_cabt
