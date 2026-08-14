namespace gpu_cabt {

__device__ __forceinline__ void condition_target_list(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleTarget& target,
    const AreaRefState& effect_card,
    gc_i32 effect_owner
) {
    runtime.scratch_target_count = 0;
    target_list(
        state, runtime, rules, target,
        runtime.scratch_targets, runtime.scratch_target_count,
        effect_card, effect_owner, false, kRuntimeErrorTargetOverflow
    );
}

__device__ __forceinline__ gc_i32 target_player_count(
    const RuleTarget& target,
    gc_i32 owner,
    gc_i32 slot
) {
    if (target.target_player == 3) return slot;
    if (target.target_player == 1) return slot == 0 ? owner : -1;
    if (target.target_player == 2) return slot == 0 ? 1 - owner : -1;
    return -1;
}

__device__ __forceinline__ void direct_count_append(
    BattleRuntimeState& runtime,
    gc_i32& count,
    bool& contains_effect,
    gc_u8 ref,
    gc_u8 effect_ref,
    bool track_effect
) {
    if (count >= kAreaRefCapacity) {
        runtime.error_flags |= kRuntimeErrorTargetOverflow;
        return;
    }
    if (track_effect && ref == effect_ref) contains_effect = true;
    ++count;
}

__device__ __forceinline__ gc_i32 count_target_unfiltered(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTarget& target,
    const AreaRefState& effect_card,
    gc_i32 effect_owner
) {
    if (target.area_count == 0) return 0;
    const gc_u8 first_area = target.areas[0];
    gc_i32 count = 0;
    bool contains_effect = false;
    const bool track_effect = (target.flags & 1u) != 0;

    if (first_area == 15) {  // Me; target_list returns before exclude-self post-pass.
        return not_moved(state, effect_card) ? 1 : 0;
    }
    if (first_area == 16) {  // Effected; condition_target_list uses output_is_runtime_target=false.
        for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i)
            direct_count_append(runtime, count, contains_effect, runtime.targets[i].card,
                                effect_card.card, track_effect);
    } else if (first_area == 17) {  // EffectedPreTarget
        for (gc_i32 i = 0; i < (gc_i32)runtime.pre_target_count; ++i)
            direct_count_append(runtime, count, contains_effect, runtime.pre_targets[i].card,
                                effect_card.card, track_effect);
    } else if (first_area == 18) {  // SelectedList
        for (gc_i32 i = 0; i < (gc_i32)state.selected_list.count; ++i)
            direct_count_append(runtime, count, contains_effect, state.selected_list.values[i],
                                effect_card.card, track_effect);
    } else if (first_area == 19) {  // TriggerSubject; early return in target_list.
        const AreaRefState ref = trigger_area_ref(state.trigger_info.subject);
        return not_moved(state, ref) ? 1 : 0;
    } else if (first_area == 20) {  // TriggerObject; early return in target_list.
        const AreaRefState ref = trigger_area_ref(state.trigger_info.object);
        return not_moved(state, ref) ? 1 : 0;
    } else if (first_area == 21) {  // Attach; early return in target_list.
        if (effect_card.card == 0) return 0;
        const RefPositionState pos = attached_card_position(state, state.all_card[effect_card.card]);
        return pos.ref != 0 ? 1 : 0;
    } else if (first_area == 22) {  // TurnPlay
        for (gc_i32 i = 0; i < (gc_i32)runtime.turn_play_count; ++i)
            direct_count_append(runtime, count, contains_effect, runtime.turn_play[i],
                                effect_card.card, track_effect);
    } else if (first_area == 23) {  // AttackPreMyTurn
        if (effect_card.card != 0) {
            const CardState& card = state.all_card[effect_card.card];
            const gc_i32 turn_index = rule_active_player_index(state) == card.player_index ? 2 : 1;
            const gc_u8 ref = state.turn_histories[turn_index].turn_attack_card;
            if (ref != 0)
                direct_count_append(runtime, count, contains_effect, ref,
                                    effect_card.card, track_effect);
        }
    } else {
        for (gc_i32 order = 0; order < 2; ++order) {
            const gc_i32 player_index = order == 0 ? state.first_player : 1 - state.first_player;
            if (!is_target_player(effect_owner, player_index, target.target_player)) continue;
            const PlayerState& player = state.players[player_index];
            for (gc_i32 ai = 0; ai < (gc_i32)target.area_count; ++ai) {
                const gc_u8 area = target.areas[ai];
                const gc_u8* values = nullptr;
                gc_i32 n = 0;
                if (area == 1) { values = player.deck.values; n = player.deck.count; }
                else if (area == 2) { values = player.hand.values; n = player.hand.count; }
                else if (area == 3) { values = player.trash.values; n = player.trash.count; }
                else if (area == 4) { values = player.active.values; n = player.active.count; }
                else if (area == 5) { values = player.bench.values; n = player.bench.count; }
                else if (area == 6) { values = player.prize.values; n = player.prize.count; }
                else if (area == 8) { values = player.energy.values; n = player.energy.count; }
                else if (area == 9) { values = player.tool.values; n = player.tool.count; }
                else if (area == 24) { values = player.temporary.values; n = player.temporary.count; }
                if (values != nullptr) {
                    if (!track_effect) {
                        if (count + n > kAreaRefCapacity) {
                            count = kAreaRefCapacity;
                            runtime.error_flags |= kRuntimeErrorTargetOverflow;
                        } else {
                            count += n;
                        }
                    } else {
                        for (gc_i32 i = 0; i < n; ++i)
                            direct_count_append(runtime, count, contains_effect, values[i],
                                                effect_card.card, true);
                    }
                    continue;
                }
                if (area == 7) {
                    for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i) {
                        const gc_u8 ref = state.stadium.values[i];
                        if (state.all_card[ref].player_index == player_index)
                            direct_count_append(runtime, count, contains_effect, ref,
                                                effect_card.card, track_effect);
                    }
                } else if (area == 11) {
                    direct_count_append(runtime, count, contains_effect,
                                        (gc_u8)(1 + player_index), effect_card.card, track_effect);
                } else if (area == 12) {
                    for (gc_i32 i = 0; i < (gc_i32)state.looking.count; ++i) {
                        const gc_u8 ref = state.looking.values[i];
                        if (state.all_card[ref].player_index == player_index)
                            direct_count_append(runtime, count, contains_effect, ref,
                                                effect_card.card, track_effect);
                    }
                } else {
                    runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
                    return count;
                }
            }
        }
    }
    if (track_effect && contains_effect && count > 0) --count;
    return count;
}

__device__ __noinline__ bool satisfy_condition(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect* effects,
    gc_i32 effect_count,
    gc_i32 effect_index,
    gc_u8 effect_card_ref,
    gc_i32 effect_owner
) {
    if (effect_index < 0 || effect_index >= effect_count) return false;
    const RuleEffect& effect = effects[effect_index];
    const AreaRefState effect_card = make_area_ref(state, effect_card_ref);
    const gc_u8 comparator = effect.comparator_type;
    switch (effect.condition_type) {
        case 0: return bool_compare(true, comparator);
        case 1: {  // AnyTargetAfterEffect
            bool found = false;
            for (gc_i32 i = effect_index + 1; i < effect_count; ++i) {
                const RuleEffect& later = effects[i];
                if ((later.flags & kEffectFlagIsCondition) != 0) continue;
                condition_target_list(state, runtime, rules, later.target, effect_card, effect_owner);
                if (runtime.scratch_target_count > 0) { found = true; break; }
            }
            return bool_compare(found, comparator);
        }
        case 2:  // CountTarget
            if (effect.target.condition_count == 0) {
                runtime.scratch_target_count = (gc_u16)count_target_unfiltered(
                    state, runtime, effect.target, effect_card, effect_owner
                );
                return compare_i32(runtime.scratch_target_count, effect.values[0], comparator);
            }
            condition_target_list(state, runtime, rules, effect.target, effect_card, effect_owner);
            return compare_i32(runtime.scratch_target_count, effect.values[0], comparator);
        case 3: {  // CountTarget2
            condition_target_list(state, runtime, rules, effect.target, effect_card, effect_owner);
            const gc_i32 count = runtime.scratch_target_count;
            return bool_compare(effect.values[0] == count || effect.values[1] == count, comparator);
        }
        case 4: {  // CountTargetMeOrEnemy
            RuleTarget target = effect.target;
            target.target_player = 1;
            condition_target_list(state, runtime, rules, target, effect_card, effect_owner);
            const gc_i32 me = runtime.scratch_target_count;
            target.target_player = 2;
            condition_target_list(state, runtime, rules, target, effect_card, effect_owner);
            const gc_i32 enemy = runtime.scratch_target_count;
            return compare_i32(me, effect.values[0], comparator)
                || compare_i32(enemy, effect.values[1], comparator);
        }
        case 5: {  // CompareCountTargetMeEnemy
            condition_target_list(state, runtime, rules, effect.target, effect_card, effect_owner);
            gc_i32 counts[2] = {};
            for (gc_i32 i = 0; i < (gc_i32)runtime.scratch_target_count; ++i) {
                const gc_u8 ref = runtime.scratch_targets[i].card;
                if (ref != 0 && state.all_card[ref].player_index >= 0 && state.all_card[ref].player_index <= 1)
                    ++counts[state.all_card[ref].player_index];
            }
            return compare_i32(counts[effect_owner], counts[1 - effect_owner], comparator);
        }
        case 6: {  // CountEnergy
            gc_i32 count = 0;
            for (gc_i32 slot = 0; slot < 2; ++slot) {
                const gc_i32 p = target_player_count(effect.target, effect_owner, slot);
                if (p < 0) continue;
                const PlayerState& player = state.players[p];
                for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
                    count += attached_energy_count(state, rules, p, player.active.values[i]);
                for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
                    count += attached_energy_count(state, rules, p, player.bench.values[i]);
            }
            return compare_i32(count, effect.values[0], comparator);
        }
        case 7: {  // CountEnergyType
            if (effect.target.condition_count == 0) return false;
            const gc_u16 type = (gc_u16)effect.target.conditions[0].value;
            gc_i32 count = 0;
            for (gc_i32 slot = 0; slot < 2; ++slot) {
                const gc_i32 p = target_player_count(effect.target, effect_owner, slot);
                if (p < 0) continue;
                const PlayerState& player = state.players[p];
                for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i)
                    count += attached_energy_type_count(state, rules, p, player.active.values[i], type);
                for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i)
                    count += attached_energy_type_count(state, rules, p, player.bench.values[i], type);
            }
            return compare_i32(count, effect.values[0], comparator);
        }
        case 8: {  // CompareCountEnergyMeEnemy
            condition_target_list(state, runtime, rules, effect.target, effect_card, effect_owner);
            gc_i32 counts[2] = {};
            for (gc_i32 i = 0; i < (gc_i32)runtime.scratch_target_count; ++i) {
                const gc_u8 ref = runtime.scratch_targets[i].card;
                if (ref == 0) continue;
                const CardState& energy = state.all_card[ref];
                const RefPositionState pos = attached_card_position(state, energy);
                if (pos.ref == 0 || energy.player_index < 0 || energy.player_index > 1) continue;
                counts[energy.player_index] += get_energy_info(state, rules, energy, pos.ref).count;
            }
            return compare_i32(counts[effect_owner], counts[1 - effect_owner], comparator);
        }
        case 9: {  // AttackEnergyExtra
            const RuleAttack* attack = rule_attack(rules, state.src_attack_id);
            if (attack == nullptr || state.attacker == 0) return false;
            const gc_i32 extra = insufficient_energy_count(state, rules, state.attacker, *attack, true);
            return compare_i32(-extra, effect.values[0], comparator);
        }
        case 10: {  // NotFullBench
            const gc_i32 player_index = effect.target.target_player == 1 ? effect_owner : 1 - effect_owner;
            return bool_compare(remaining_bench(state, player_index) >= 1, comparator);
        }
        case 11: {  // MyTurn
            if (state.phase != 1 || effect_card_ref == 0) return false;
            return bool_compare(state.all_card[effect_card_ref].player_index == rule_active_player_index(state), comparator);
        }
        case 12: return compare_i32(state.turn, effect.values[0], comparator);
        case 13: return bool_compare(state.turn_histories[1].ko != 0, comparator);
        case 14: return bool_compare(state.turn_histories[1].ko_team_rocket != 0, comparator);
        case 15: return bool_compare(state.turn_histories[1].ko_attack_damage != 0, comparator);
        case 16: return bool_compare(state.turn_histories[1].ko_attack_damage_ethan != 0, comparator);
        case 17: return bool_compare(state.turn_histories[1].ko_attack_damage_hop != 0, comparator);
        case 18: {  // NoSameNameSkillThisTurn
            bool not_used = true;
            for (gc_i32 i = 0; i < (gc_i32)runtime.turn_used_skill_count; ++i) {
                if (runtime.turn_used_skills[i] == effect.skill_id) { not_used = false; break; }
            }
            return bool_compare(not_used, comparator);
        }
        case 19:
            return bool_compare(
                state.turn_histories[2].turn_attack_id == state.current_attack_id
                    && state.turn_histories[2].turn_attack_card == state.attacker,
                comparator
            );
        case 20: return compare_i32(state.coin_head_count, effect.values[0], comparator);
        case 21: return bool_compare(state.attach_active != 0, comparator);
        case 22: {  // MysteryGarden
            const PlayerState& player = state.players[effect_owner];
            gc_i32 count = 0;
            for (gc_i32 pass = 0; pass < 2; ++pass) {
                const gc_i32 n = pass == 0 ? player.active.count : player.bench.count;
                for (gc_i32 i = 0; i < n; ++i) {
                    const gc_u8 ref = pass == 0 ? player.active.values[i] : player.bench.values[i];
                    const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
                    if (master != nullptr && contains_energy(get_card_energy_type(state.all_card[ref], *master), kEnergyPsychic)) ++count;
                }
            }
            return (gc_i32)player.hand.count <= count;
        }
        case 23: {  // LoveBall
            const PlayerState& own = state.players[effect_owner];
            const PlayerState& enemy = state.players[1 - effect_owner];
            for (gc_i32 pass = 0; pass < 2; ++pass) {
                const gc_i32 n = pass == 0 ? enemy.active.count : enemy.bench.count;
                for (gc_i32 i = 0; i < n; ++i) {
                    const gc_u8 enemy_ref = pass == 0 ? enemy.active.values[i] : enemy.bench.values[i];
                    const RuleCardMaster* enemy_master = rule_card(rules, state.all_card[enemy_ref].card_id);
                    if (enemy_master == nullptr || enemy_master->card_type != 0) continue;
                    gc_i32 count = 0;
                    for (gc_i32 zone = 0; zone < 3; ++zone) {
                        const gc_u8* values = zone == 0 ? own.active.values : zone == 1 ? own.bench.values : own.trash.values;
                        const gc_i32 size = zone == 0 ? own.active.count : zone == 1 ? own.bench.count : own.trash.count;
                        for (gc_i32 j = 0; j < size; ++j) {
                            const RuleCardMaster* m = rule_card(rules, state.all_card[values[j]].card_id);
                            if (m != nullptr && m->name_hash == enemy_master->name_hash) ++count;
                        }
                    }
                    if (count < 4) return true;
                }
            }
            return false;
        }
        default: return false;
    }
}

__device__ __noinline__ bool satisfy_skill_condition(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleSkill& skill,
    gc_u8 effect_card,
    gc_i32 effect_owner,
    gc_i32 start_index
) {
    if (skill.effect_offset < 0 || skill.effect_offset + skill.effect_count > rules.effect_count) return false;
    const RuleEffect* effects = rules.effects + skill.effect_offset;
    for (gc_i32 i = start_index; i < skill.effect_count; ++i) {
        const RuleEffect& effect = effects[i];
        if ((effect.flags & kEffectFlagIsCondition) == 0) break;
        if (!satisfy_condition(state, runtime, rules, effects, skill.effect_count, i, effect_card, effect_owner)) {
            if (effect.fail_skip) break;
            return false;
        }
    }
    if ((skill.flags & kSkillFlagOnceTurn) != 0 && effect_card != 0) {
        const CardState& card = state.all_card[effect_card];
        for (gc_i32 i = 0; i < (gc_i32)card.ability_used.count; ++i) {
            if (card.ability_used.values[i] == card.card_id) return false;
        }
    }
    return true;
}

}  // namespace gpu_cabt
