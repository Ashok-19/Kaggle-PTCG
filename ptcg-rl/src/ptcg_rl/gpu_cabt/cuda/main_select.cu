namespace gpu_cabt {

static constexpr gc_u64 kPrismTowerHash = 0x77576423c9a3dce0ull;
static constexpr gc_u64 kCoreMemoryHash = 0x8b75aab384250f71ull;
static constexpr gc_u64 kMegaZygardeExHash = 0xa0f2a4bcd44dfb22ull;

__device__ __forceinline__ bool can_play_common_full(
    const PlayerState& player,
    const CardState& card,
    const RuleCardMaster& master
) {
    return !(player_continual(player).fields.cannot_play_ace_spec
        && card.area == kAreaHand && card_flag(master, kCardFlagAceSpec));
}

__device__ __forceinline__ bool can_play_skill_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    const CardState& card,
    const RuleCardMaster& master
) {
    if (master.play_skill_id <= 0) return false;
    const RuleSkill* skill = rule_skill(rules, master.play_skill_id);
    if (skill == nullptr) return false;
    if (skill->second_effect_start_index > 0) return true;
    return satisfy_skill_condition(state, runtime, rules, *skill, ref, card.player_index, 0);
}

__device__ __forceinline__ bool can_activate_main_ability_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 ref,
    gc_i32 use_player
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return false;
    const RuleSkill* skill = get_ability(rules, card, *master);
    if (skill == nullptr || (skill->flags & kSkillFlagMainAbility) == 0) return false;
    if (!skill_area_match(*skill, card.area)) return false;
    return satisfy_skill_condition(state, runtime, rules, *skill, ref, use_player, 0);
}

__device__ __forceinline__ bool can_evolve_main_full(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& hand_card,
    const RuleCardMaster& hand_master,
    gc_u8 pokemon_ref
) {
    if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return false;
    const CardState& pokemon = state.all_card[pokemon_ref];
    const bool cannot_evolve_appear = !card_continual(pokemon).fields.can_evolve_appear_turn;
    if (state.turn <= 2 && cannot_evolve_appear) return false;
    if (card_turn(pokemon).fields.appear && cannot_evolve_appear) {
        if (!card_continual(pokemon).fields.can_evolve_grass_appear_turn
            || !contains_energy(hand_master.energy_type, kEnergyGrass)) return false;
    }
    return can_evolve_effect(state, rules, hand_card, hand_master, pokemon_ref);
}

__device__ __forceinline__ bool can_attack_card_full(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    if (card_continual(card).fields.cannot_attack || card_this_turn(card).fields.cannot_attack) return false;
    if (card_this_turn(card).fields.cannot_attack_less_equal_energy2
        && attached_energy_count(state, rules, card.player_index, ref) <= 2) return false;
    return true;
}

__device__ __forceinline__ bool satisfy_attack_state_condition_full(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& card,
    const RuleAttack& attack,
    gc_i32 src_attack_id
) {
    const CardNextTurnFields& turn = card_this_turn(card);
    if (turn.fields.cannot_use_attack_id == attack.attack_id
        || turn.fields.cannot_use_attack_id2 == attack.attack_id
        || card.cannot_use_attack_id_non_active == attack.attack_id) {
        if (src_attack_id == 0 || src_attack_id == attack.attack_id) return false;
    }
    if ((attack.flags & (1u << 8)) != 0 && state.turn <= 2) return false;
    if ((attack.flags & (1u << 9)) != 0) {
        const gc_i32 previous_id = state.turn_histories[2].turn_attack_id;
        if (previous_id > 0) {
            const RuleAttack* previous = rule_attack(rules, previous_id);
            if (previous != nullptr && previous->name_hash == attack.name_hash) return false;
        }
    }
    if ((attack.flags & (1u << 10)) != 0
        && state.players[1 - card.player_index].prize.count != 1) return false;
    return true;
}

__device__ __forceinline__ bool satisfy_attack_effect_condition_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 attacker_ref,
    const RuleAttack& attack
) {
    if (attack.pre_effect_count > 0 && attack.post_effect_count > 0) return true;
    if (attack.post_effect_offset < 0
        || attack.post_effect_offset + attack.post_effect_count > rules.effect_count) return false;
    const RuleEffect* effects = rules.effects + attack.post_effect_offset;
    for (gc_i32 i = 0; i < attack.post_effect_count; ++i) {
        const RuleEffect& effect = effects[i];
        if ((effect.flags & kEffectFlagIsCondition) == 0 || effect.fail_skip) break;
        if (!satisfy_condition(state, runtime, rules, effects, attack.post_effect_count,
                               i, attacker_ref, state.all_card[attacker_ref].player_index)) return false;
    }
    return true;
}

__device__ __forceinline__ bool can_use_attack_option_full(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 attacker_ref,
    const RuleAttack& attack,
    gc_i32 src_attack_id
) {
    if (!can_attack_card_full(state, rules, attacker_ref)) return false;
    if (attack.damage == 0 && (attack.flags & (1u << 19)) == 0
        && !satisfy_attack_effect_condition_full(state, runtime, rules, attacker_ref, attack)) return false;
    if (src_attack_id == 0 || src_attack_id == attack.attack_id) {
        if (!satisfy_attack_state_condition_full(state, rules, state.all_card[attacker_ref], attack, src_attack_id)) return false;
    } else {
        const RuleAttack* source = rule_attack(rules, src_attack_id);
        if (source == nullptr || !satisfy_attack_state_condition_full(
                state, rules, state.all_card[attacker_ref], *source, src_attack_id)) return false;
    }
    return state.turn >= 2 || (attack.flags & (1u << 18)) != 0
        || card_continual(state.all_card[attacker_ref]).fields.can_attack_first;
}

__device__ __forceinline__ void add_main_attack_candidate(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 attacker_ref,
    gc_i32 attack_id,
    gc_i32 src_attack_id,
    gc_i32 bench_index
) {
    const RuleAttack* attack = rule_attack(rules, attack_id);
    if (attack == nullptr) return;
    if (!can_use_attack_option_full(state, runtime, rules, attacker_ref, *attack, src_attack_id)) return;
    add_option_attack(runtime, attack_id, src_attack_id, bench_index);
}

__device__ __forceinline__ void add_extracted_printed_attack(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 attacker_ref,
    const RuleAttack& source
) {
    const gc_i32 player = state.all_card[attacker_ref].player_index;
    if ((source.flags & (1u << 0)) != 0 || (source.flags & (1u << 1)) != 0) {
        const PlayerState& enemy = state.players[1 - player];
        if (enemy.active.count == 0) return;
        const RuleCardMaster* master = rule_card(rules, state.all_card[enemy.active.values[0]].card_id);
        if (master == nullptr) return;
        if ((source.flags & (1u << 1)) != 0 && !card_flag(*master, kCardFlagTera)) return;
        for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i)
            if (master->attack_ids[i] > 0)
                add_main_attack_candidate(state, runtime, rules, attacker_ref,
                                          master->attack_ids[i], source.attack_id, -1);
        return;
    }
    if ((source.flags & (1u << 3)) != 0) {
        const PlayerState& own = state.players[player];
        for (gc_i32 bi = 0; bi < (gc_i32)own.bench.count; ++bi) {
            const RuleCardMaster* master = rule_card(rules, state.all_card[own.bench.values[bi]].card_id);
            if (master == nullptr || !card_flag(*master, kCardFlagN)) continue;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i)
                if (master->attack_ids[i] > 0)
                    add_main_attack_candidate(state, runtime, rules, attacker_ref,
                                              master->attack_ids[i], source.attack_id, -1);
        }
        return;
    }
    add_main_attack_candidate(state, runtime, rules, attacker_ref, source.attack_id, 0, -1);
}

__device__ __forceinline__ void add_active_attack_options_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 active_ref
) {
    const CardState& card = state.all_card[active_ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return;
    for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
        const gc_i32 attack_id = master->attack_ids[i];
        if (attack_id <= 0) continue;
        const RuleAttack* attack = rule_attack(rules, attack_id);
        if (attack != nullptr && enough_energy(state, rules, active_ref, *attack))
            add_extracted_printed_attack(state, runtime, rules, active_ref, *attack);
    }
    if (card_continual(card).fields.can_use_pre_evolution_attack) {
        const PlayerState& player = state.players[card.player_index];
        for (gc_i32 pi = 0; pi < (gc_i32)player.pre_evolution.count; ++pi) {
            const gc_u8 pre_ref = player.pre_evolution.values[pi];
            if (state.all_card[pre_ref].attach_move_counter != card.move_counter) continue;
            const RuleCardMaster* pre_master = rule_card(rules, state.all_card[pre_ref].card_id);
            if (pre_master == nullptr) continue;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const gc_i32 attack_id = pre_master->attack_ids[i];
                const RuleAttack* attack = attack_id > 0 ? rule_attack(rules, attack_id) : nullptr;
                if (attack != nullptr && enough_energy(state, rules, active_ref, *attack))
                    add_main_attack_candidate(state, runtime, rules, active_ref, attack_id, 0, -1);
            }
        }
    }
    if (card_continual(card).fields.technical_machine) {
        const PlayerState& player = state.players[card.player_index];
        for (gc_i32 ti = 0; ti < (gc_i32)player.tool.count; ++ti) {
            const gc_u8 tool_ref = player.tool.values[ti];
            const CardState& tool = state.all_card[tool_ref];
            if (tool.attach_move_counter != card.move_counter) continue;
            const RuleCardMaster* tool_master = rule_card(rules, tool.card_id);
            if (tool_master == nullptr) continue;
            if (tool_master->name_hash == kCoreMemoryHash && master->name_hash != kMegaZygardeExHash) continue;
            for (gc_i32 i = 0; i < kRuleCardAttackCapacity; ++i) {
                const gc_i32 attack_id = tool_master->attack_ids[i];
                const RuleAttack* attack = attack_id > 0 ? rule_attack(rules, attack_id) : nullptr;
                if (attack != nullptr && enough_energy(state, rules, active_ref, *attack))
                    add_main_attack_candidate(state, runtime, rules, active_ref, attack_id, 0, -1);
            }
        }
    }
}

__device__ __forceinline__ bool can_retreat_full(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index
) {
    if (state_turn(state).fields.retreated || player_index < 0 || player_index > 1) return false;
    const PlayerState& player = state.players[player_index];
    if (player.active.count == 0 || player.bench.count == 0) return false;
    const gc_u8 active_ref = player.active.values[0];
    const CardState& card = state.all_card[active_ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr) return false;
    if (attached_energy_count(state, rules, player_index, active_ref) < retreat_cost(card, *master)) return false;
    const gc_u8 status = player_active_state(player).fields.bad_status;
    if (status == 1 || status == 2) return false;
    if (card_this_turn(card).fields.cannot_retreat || card_continual(card).fields.cannot_retreat) return false;
    if (master->pokemon_type == 2) return false;
    if (player_this_turn(player).fields.cannot_retreat_poison
        && player_active_state(player).fields.poison_damage_counter > 0
        && !card_continual(card).fields.no_effect_enemy_supporter) return false;
    return true;
}

__device__ __forceinline__ void add_in_play_evolve_options(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 hand_index,
    const CardState& hand_card,
    const RuleCardMaster& hand_master,
    gc_i32 player_index
) {
    const PlayerState& player = state.players[player_index];
    if (player.active.count > 0 && can_evolve_main_full(state, rules, hand_card, hand_master, player.active.values[0]))
        add_option_evolve(runtime, kAreaHand, hand_index, kAreaActive, 0);
    for (gc_i32 bi = 0; bi < (gc_i32)player.bench.count; ++bi)
        if (can_evolve_main_full(state, rules, hand_card, hand_master, player.bench.values[bi]))
            add_option_evolve(runtime, kAreaHand, hand_index, kAreaBench, bi);
}

__device__ __forceinline__ void add_in_play_attach_options(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32 hand_index,
    const RuleCardMaster& source_master,
    gc_i32 player_index,
    bool energy
) {
    const PlayerState& player = state.players[player_index];
    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        const CardState& target = state.all_card[ref];
        const RuleCardMaster* target_master = rule_card(rules, target.card_id);
        if (target_master != nullptr) {
            const bool ok = energy
                ? (!card_this_turn(target).fields.cannot_hand_attach_energy
                   && can_attach_energy_full(source_master, *target_master))
                : remaining_tool_capacity_full(state, target) > 0;
            if (ok) add_option_attach(runtime, kAreaHand, hand_index, kAreaActive, 0);
        }
    }
    for (gc_i32 bi = 0; bi < (gc_i32)player.bench.count; ++bi) {
        const gc_u8 ref = player.bench.values[bi];
        const CardState& target = state.all_card[ref];
        const RuleCardMaster* target_master = rule_card(rules, target.card_id);
        if (target_master == nullptr) continue;
        const bool ok = energy
            ? (!card_this_turn(target).fields.cannot_hand_attach_energy
               && can_attach_energy_full(source_master, *target_master))
            : remaining_tool_capacity_full(state, target) > 0;
        if (ok) add_option_attach(runtime, kAreaHand, hand_index, kAreaBench, bi);
    }
}

__device__ __forceinline__ void begin_main_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules
) {
    if (finish_check_full(state, runtime)) return;
    if (state.phase != 1 || state.select_type != kSelectNone) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    const gc_i32 player_index = rule_active_player_index(state);
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0) {
        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    set_select_full(state, runtime, kSelectMain, kSelectContextMain, player_index, 1, 1);

    for (gc_i32 hi = 0; hi < (gc_i32)player.hand.count; ++hi) {
        const gc_u8 ref = player.hand.values[hi];
        const CardState& card = state.all_card[ref];
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        if (master == nullptr) continue;

        if (master->card_type == 0) {
            const RuleSkill* ability = get_ability(rules, card, *master);
            if (player_continual(player).fields.cannot_play_ability_pokemon_not_rocket
                && ability != nullptr && !card_flag(*master, kCardFlagTeamRocket)) continue;
            if (master->evolution_type != 1) {
                if (player_this_turn(player).fields.cannot_evolve) continue;
                add_in_play_evolve_options(state, runtime, rules, hi, card, *master, player_index);
                if (!card_continual(card).fields.can_play) continue;
            }
            if (remaining_bench(state, player_index) <= 0) continue;
            add_option_play(runtime, hi);
            continue;
        }

        if (is_energy_card(master->card_type)) {
            if (state_turn(state).fields.energy_played || !can_play_common_full(player, card, *master)) continue;
            if (player_this_turn(player).fields.cannot_play_special_energy && master->card_type == 6) continue;
            add_in_play_attach_options(state, runtime, rules, hi, *master, player_index, true);
            continue;
        }

        if (!can_play_common_full(player, card, *master)) continue;
        if (master->card_type == 3) {
            if (state.turn <= 1 && !card_flag(*master, kCardFlagCanPlayFirstTurn)) continue;
            if (state_turn(state).fields.supporter_played
                || player_this_turn(player).fields.cannot_play_supporter) continue;
            if (!can_play_skill_full(state, runtime, rules, ref, card, *master)) continue;
        } else if (master->card_type == 4) {
            if (master->card_id == 1429) {
                if (state.stadium.count == 0) continue;
                const RuleCardMaster* current = rule_card(rules, state.all_card[state.stadium.values[0]].card_id);
                if (current == nullptr || current->name_hash != kPrismTowerHash) continue;
            } else if (state_turn(state).fields.stadium_played) continue;
            if (player_continual(player).fields.cannot_play_stadium
                || player_this_turn(player).fields.cannot_play_stadium) continue;
            if (state.stadium.count > 0) {
                const RuleCardMaster* current = rule_card(rules, state.all_card[state.stadium.values[0]].card_id);
                if (current != nullptr && current->name_hash == master->name_hash) continue;
            }
        } else if (master->card_type == 2) {
            if (player_continual(player).fields.cannot_play_tool) continue;
            add_in_play_attach_options(state, runtime, rules, hi, *master, player_index, false);
            continue;
        } else if (master->card_type == 1) {
            if (player_this_turn(player).fields.cannot_play_item
                || player_continual(player).fields.cannot_play_item) continue;
            if (!can_play_skill_full(state, runtime, rules, ref, card, *master)) continue;
        }
        add_option_play(runtime, hi);
    }

    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        if (can_activate_main_ability_full(state, runtime, rules, ref, player_index))
            add_option_ability(runtime, kAreaActive, 0);
        const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
        if (master != nullptr && card_flag(*master, kCardFlagCanTrash)) add_option_discard(runtime, kAreaActive, 0);
    }
    for (gc_i32 bi = 0; bi < (gc_i32)player.bench.count; ++bi) {
        const gc_u8 ref = player.bench.values[bi];
        if (can_activate_main_ability_full(state, runtime, rules, ref, player_index))
            add_option_ability(runtime, kAreaBench, bi);
        const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
        if (master != nullptr && card_flag(*master, kCardFlagCanTrash)) add_option_discard(runtime, kAreaBench, bi);
    }
    for (gc_i32 si = 0; si < (gc_i32)state.stadium.count; ++si)
        if (can_activate_main_ability_full(state, runtime, rules, state.stadium.values[si], player_index))
            add_option_ability(runtime, 7, si);

    const gc_u8 active_ref = player.active.values[0];
    const gc_u8 status = player_active_state(player).fields.bad_status;
    if (status != 1 && status != 2 && can_attack_card_full(state, rules, active_ref))
        add_active_attack_options_full(state, runtime, rules, active_ref);

    if (state.turn >= 2) {
        for (gc_i32 bi = 0; bi < (gc_i32)player.bench.count; ++bi) {
            const gc_u8 ref = player.bench.values[bi];
            const RuleCardMaster* master = rule_card(rules, state.all_card[ref].card_id);
            if (master == nullptr) continue;
            for (gc_i32 ai = 0; ai < kRuleCardAttackCapacity; ++ai) {
                const gc_i32 attack_id = master->attack_ids[ai];
                const RuleAttack* attack = attack_id > 0 ? rule_attack(rules, attack_id) : nullptr;
                if (attack != nullptr && (attack->flags & (1u << 17)) != 0
                    && enough_energy(state, rules, ref, *attack))
                    add_option_attack(runtime, attack_id, attack_id, bi);
            }
        }
    }
    if (can_retreat_full(state, rules, player_index)) add_option_retreat(runtime);
    add_option_end(runtime);
}

}  // namespace gpu_cabt
