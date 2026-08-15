namespace gpu_cabt {

static constexpr gc_i32 kPolicyGlobalWidth = 24;
static constexpr gc_i32 kPolicyPlayerWidth = 12;
static constexpr gc_i32 kPolicyEntityWidth = 19;
static constexpr gc_i32 kPolicyEntityCapacity = kAllCardCapacity;
static constexpr gc_i32 kPolicyOptionWidth = 20;
static constexpr gc_i32 kPolicyOptionCapacity = kOptionCapacity;

static constexpr gc_u32 kPolicyProjectionNoSelection = 1u << 0;
static constexpr gc_u32 kPolicyProjectionBadActor = 1u << 1;
static constexpr gc_u32 kPolicyProjectionEntityOverflow = 1u << 2;
static constexpr gc_u32 kPolicyProjectionOptionOverflow = 1u << 3;
static constexpr gc_u32 kPolicyProjectionBadReference = 1u << 4;

__device__ __forceinline__ gc_i32 policy_relative_player(gc_i32 player, gc_i32 actor) {
    if (player < 0 || player > 1 || actor < 0 || actor > 1) return -1;
    return player == actor ? 0 : 1;
}

__device__ __forceinline__ gc_i32 policy_role(gc_u8 area, gc_i32 index) {
    if (area == kAreaActive) return 1;
    if (area == kAreaBench) return index >= 0 ? index + 2 : 0;
    return index >= 0 ? index + 1 : 0;
}

__device__ __forceinline__ gc_u8 policy_ref_at(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 area,
    gc_i32 index
) {
    if (index < 0) return 0;
    if (player_index >= 0 && player_index <= 1) {
        const PlayerState& player = state.players[player_index];
        if (area == kAreaDeck && index < (gc_i32)player.deck.count) return player.deck.values[index];
        if (area == kAreaHand && index < (gc_i32)player.hand.count) return player.hand.values[index];
        if (area == 3 && index < (gc_i32)player.trash.count) return player.trash.values[index];
        if (area == kAreaActive && index < (gc_i32)player.active.count) return player.active.values[index];
        if (area == kAreaBench && index < (gc_i32)player.bench.count) return player.bench.values[index];
        if (area == kAreaPrize && index < (gc_i32)player.prize.count) return player.prize.values[index];
        if (area == 8 && index < (gc_i32)player.energy.count) return player.energy.values[index];
        if (area == 9 && index < (gc_i32)player.tool.count) return player.tool.values[index];
        if (area == 10 && index < (gc_i32)player.pre_evolution.count) return player.pre_evolution.values[index];
        if (area == 24 && index < (gc_i32)player.temporary.count) return player.temporary.values[index];
    }
    if (area == 7 && index < (gc_i32)state.stadium.count) return state.stadium.values[index];
    if (area == 12 && index < (gc_i32)state.looking.count) return state.looking.values[index];
    if (area == 13 && index < (gc_i32)state.playing.count) return state.playing.values[index];
    return 0;
}

__device__ __forceinline__ bool policy_parent_visible(
    const BattleCoreState& state,
    const CardState& attached
) {
    const RefPositionState parent = attached_card_position(state, attached);
    return parent.ref != 0 && !state.all_card[parent.ref].reverse;
}

__device__ __forceinline__ bool policy_card_visible(
    const BattleCoreState& state,
    gc_i32 actor,
    gc_u8 ref
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    if (state.context_card == ref) return true;
    if (state.effect_state.on_effect && state.effect_state.ability.effect_card.card_index == ref) return true;
    const CardState& card = state.all_card[ref];
    const gc_i32 owner = card.player_index;
    switch (card.area) {
        case kAreaDeck: return owner == actor && state.select_deck != 0;
        case kAreaHand: return owner == actor;
        case 3: return true;
        case kAreaActive:
        case kAreaBench: return card.reverse == 0;
        case kAreaPrize: return card.reverse == 0;
        case 7: return true;
        case 8:
        case 9:
        case 10: return policy_parent_visible(state, card);
        case 12:
            return state.looking_player == actor || state.looking_player == 2;
        case 13:
            return state.context_card == ref
                || (state.effect_state.on_effect && state.effect_state.ability.effect_card.card_index == ref);
        default: return false;
    }
}

__device__ __forceinline__ gc_i32 policy_visible_prize_count(
    const BattleCoreState& state,
    gc_i32 player_index
) {
    gc_i32 count = 0;
    const auto& prize = state.players[player_index].prize;
    for (gc_i32 i = 0; i < (gc_i32)prize.count; ++i)
        if (!state.all_card[prize.values[i]].reverse) ++count;
    return count;
}

__device__ __forceinline__ gc_i32 policy_public_looking_mode(
    const BattleCoreState& state,
    gc_i32 actor
) {
    if (state.looking.count == 0 || actor < 0 || actor > 1) return 0;
    if (state.looking_player == actor || state.looking_player == 2) return 1;
    if (state.looking_player == actor + 3) return 2;
    return 0;
}

__device__ __forceinline__ gc_i32 policy_pre_evolution_count(
    const BattleCoreState& state,
    const CardState& pokemon
) {
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return 0;
    gc_i32 count = 0;
    const auto& list = state.players[pokemon.player_index].pre_evolution;
    for (gc_i32 i = 0; i < (gc_i32)list.count; ++i)
        if (state.all_card[list.values[i]].attach_move_counter == pokemon.move_counter) ++count;
    return count;
}

__device__ __forceinline__ gc_i32 policy_energy_index_mask(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& pokemon,
    gc_u8 pokemon_ref
) {
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return 0;
    gc_u16 mask = 0;
    const auto& list = state.players[pokemon.player_index].energy;
    for (gc_i32 i = 0; i < (gc_i32)list.count; ++i) {
        const CardState& energy = state.all_card[list.values[i]];
        if (energy.attach_move_counter != pokemon.move_counter) continue;
        const gc_i32 index = energy_type_index(
            get_energy_info(state, rules, energy, pokemon_ref).type
        );
        if (index >= 0 && index < 12) mask |= (gc_u16)(1u << index);
    }
    return (gc_i32)mask;
}

__device__ __forceinline__ void policy_emit_entity(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 actor,
    gc_u8 ref,
    gc_u8 area,
    gc_i32 zone_index,
    gc_i32 parent_role,
    bool visible,
    gc_i32* rows,
    gc_i32& count,
    gc_u32& status
) {
    if (count >= kPolicyEntityCapacity) {
        status |= kPolicyProjectionEntityOverflow;
        return;
    }
    gc_i32* row = rows + (gc_i64)count * kPolicyEntityWidth;
    for (gc_i32 i = 0; i < kPolicyEntityWidth; ++i) row[i] = 0;
    if (ref == 0 || ref >= kAllCardCapacity) {
        status |= kPolicyProjectionBadReference;
        ++count;
        return;
    }
    const CardState& card = state.all_card[ref];
    row[1] = policy_relative_player(card.player_index, actor);
    row[2] = area;
    row[3] = policy_role(area, zone_index);
    row[4] = visible ? 1 : 0;
    row[15] = parent_role;
    // Bridge-only transport identity. Raw ref magnitude never enters model features.
    row[18] = visible ? (gc_i32)ref : 0;
    if (visible) {
        row[0] = card.card_id;
        const RuleCardMaster* master = rule_card(rules, card.card_id);
        if (master == nullptr) {
            status |= kPolicyProjectionBadReference;
        } else {
            row[17] = master->card_type;
            if (area == kAreaActive || area == kAreaBench) {
                row[5] = get_hp(card, *master);
                row[6] = get_max_hp(card, *master);
                row[7] = card.damage;
                row[8] = card_turn(card).fields.appear ? 1 : 0;
                row[9] = attached_energy_count(state, rules, card.player_index, ref);
                row[10] = attached_tool_count(state, card);
                row[11] = policy_pre_evolution_count(state, card);
                if (area == kAreaActive && card.player_index >= 0 && card.player_index <= 1) {
                    const auto& active = player_active_state(state.players[card.player_index]).fields;
                    row[12] = active.poison_damage_counter != 0 ? 1 : 0;
                    row[13] = active.burned ? 1 : 0;
                    row[14] = active.bad_status;
                }
                row[16] = policy_energy_index_mask(state, rules, card, ref);
            }
        }
    }
    ++count;
}

__device__ __forceinline__ void policy_emit_player_entities(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 actor,
    gc_i32 player_index,
    gc_i32* rows,
    gc_i32& count,
    gc_u32& status
) {
    const PlayerState& player = state.players[player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) {
        const gc_u8 ref = player.active.values[i];
        policy_emit_entity(state, rules, actor, ref, kAreaActive, i, 0,
            policy_card_visible(state, actor, ref), rows, count, status);
    }
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
        const gc_u8 ref = player.bench.values[i];
        policy_emit_entity(state, rules, actor, ref, kAreaBench, i, 0,
            policy_card_visible(state, actor, ref), rows, count, status);
    }
    if (player_index == actor) {
        for (gc_i32 i = 0; i < (gc_i32)player.hand.count; ++i)
            policy_emit_entity(state, rules, actor, player.hand.values[i], kAreaHand, i, 0,
                true, rows, count, status);
        if (state.select_deck) {
            for (gc_i32 i = 0; i < (gc_i32)player.deck.count; ++i)
                policy_emit_entity(state, rules, actor, player.deck.values[i], kAreaDeck, i, 0,
                    true, rows, count, status);
        }
    }
    for (gc_i32 i = 0; i < (gc_i32)player.trash.count; ++i)
        policy_emit_entity(state, rules, actor, player.trash.values[i], 3, i, 0,
            true, rows, count, status);
    for (gc_i32 i = 0; i < (gc_i32)player.prize.count; ++i) {
        const gc_u8 ref = player.prize.values[i];
        policy_emit_entity(state, rules, actor, ref, kAreaPrize, i, 0,
            policy_card_visible(state, actor, ref), rows, count, status);
    }
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const gc_u8 ref = player.energy.values[i];
        const RefPositionState parent = attached_card_position(state, state.all_card[ref]);
        if (parent.ref == 0 || !policy_card_visible(state, actor, parent.ref)) continue;
        policy_emit_entity(state, rules, actor, ref, 8, i,
            policy_role(parent.area, parent.index), true, rows, count, status);
    }
    for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
        const gc_u8 ref = player.tool.values[i];
        const RefPositionState parent = attached_card_position(state, state.all_card[ref]);
        if (parent.ref == 0 || !policy_card_visible(state, actor, parent.ref)) continue;
        policy_emit_entity(state, rules, actor, ref, 9, i,
            policy_role(parent.area, parent.index), true, rows, count, status);
    }
    for (gc_i32 i = 0; i < (gc_i32)player.pre_evolution.count; ++i) {
        const gc_u8 ref = player.pre_evolution.values[i];
        const RefPositionState parent = attached_card_position(state, state.all_card[ref]);
        if (parent.ref == 0 || !policy_card_visible(state, actor, parent.ref)) continue;
        policy_emit_entity(state, rules, actor, ref, 10, i,
            policy_role(parent.area, parent.index), true, rows, count, status);
    }
}

__device__ __forceinline__ gc_u8 policy_nth_attached_ref(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 parent_ref,
    gc_i32 ordinal,
    bool energy
) {
    if (player_index < 0 || player_index > 1 || parent_ref == 0 || ordinal < 0) return 0;
    const gc_i32 move_counter = state.all_card[parent_ref].move_counter;
    const auto& list = energy ? state.players[player_index].energy : state.players[player_index].tool;
    gc_i32 seen = 0;
    for (gc_i32 i = 0; i < (gc_i32)list.count; ++i) {
        const gc_u8 ref = list.values[i];
        if (state.all_card[ref].attach_move_counter != move_counter) continue;
        if (seen++ == ordinal) return ref;
    }
    return 0;
}

__device__ __forceinline__ void policy_emit_public_option_params(
    const SelectOptionState& option,
    gc_i32* row
) {
    // Mirror the agent-visible SelectOptionJson fields. Internal execution
    // parameters must not be promoted into learner features.
    if (option.type == kOptionNumber || option.type == kOptionPlay
        || option.type == kOptionSpecialCondition || option.type == kOptionSkill) {
        row[3] = option.param0;
    } else if (option.type == kOptionCard) {
        row[3] = option.param0;
        row[4] = option.param1;
        row[5] = option.param2;
    } else if (option.type == kOptionToolCard || option.type == kOptionEnergyCard) {
        row[3] = option.param0;
        row[4] = option.param1;
        row[5] = option.param2;
        row[6] = option.param3;
    } else if (option.type == kOptionEnergy) {
        row[3] = option.param0;
        row[4] = option.param1;
        row[5] = option.param2;
        row[6] = option.param3;
        row[7] = option.param4;
    } else if (option.type == kOptionAttach || option.type == kOptionEvolve) {
        row[3] = option.param0;
        row[4] = option.param1;
        row[5] = option.param2;
        row[6] = option.param3;
    } else if (option.type == kOptionAbility || option.type == kOptionDiscard) {
        row[3] = option.param0;
        row[4] = option.param1;
    } else if (option.type == kOptionAttack) {
        row[3] = option.param0;
    }
    // Skill serial is intentionally excluded from the semantic actor schema;
    // row[8] carries the public card id.
}

__device__ __forceinline__ void policy_option_source(
    const BattleCoreState& state,
    gc_i32 actor,
    const SelectOptionState& option,
    gc_u8& source_ref,
    gc_u8& target_ref,
    gc_u8& source_area,
    gc_i32& source_index,
    gc_i32& source_player,
    gc_u8& target_area,
    gc_i32& target_index,
    gc_i32& target_player
) {
    source_ref = target_ref = 0;
    source_area = target_area = 0;
    source_index = target_index = -1;
    source_player = target_player = -1;
    if (option.type == kOptionCard) {
        source_area = (gc_u8)option.param0; source_index = option.param1; source_player = option.param2;
        source_ref = policy_ref_at(state, source_player, source_area, source_index);
    } else if (option.type == kOptionToolCard || option.type == kOptionEnergyCard || option.type == kOptionEnergy) {
        target_area = (gc_u8)option.param0; target_index = option.param1; target_player = option.param2;
        target_ref = policy_ref_at(state, target_player, target_area, target_index);
        const bool energy = option.type != kOptionToolCard;
        source_ref = policy_nth_attached_ref(state, target_player, target_ref, option.param3, energy);
        source_area = energy ? 8 : 9; source_index = option.param3; source_player = target_player;
    } else if (option.type == kOptionPlay) {
        source_area = kAreaHand; source_index = option.param0; source_player = actor;
        source_ref = policy_ref_at(state, actor, source_area, source_index);
    } else if (option.type == kOptionAttach || option.type == kOptionEvolve) {
        source_area = (gc_u8)option.param0; source_index = option.param1; source_player = actor;
        source_ref = policy_ref_at(state, actor, source_area, source_index);
        target_area = (gc_u8)option.param2; target_index = option.param3; target_player = actor;
        target_ref = policy_ref_at(state, actor, target_area, target_index);
    } else if (option.type == kOptionAbility || option.type == kOptionDiscard) {
        source_area = (gc_u8)option.param0; source_index = option.param1; source_player = actor;
        source_ref = policy_ref_at(state, actor, source_area, source_index);
    } else if (option.type == kOptionRetreat) {
        target_area = kAreaActive; target_index = 0; target_player = actor;
        target_ref = policy_ref_at(state, actor, target_area, 0);
    } else if (option.type == kOptionAttack) {
        // Native CABT exposes only attackId for an Attack option. Do not derive
        // a source-card feature from execution-only source/bench parameters.
    } else if (option.type == kOptionSkill) {
        source_ref = option.param1 > 0 && option.param1 < kAllCardCapacity ? (gc_u8)option.param1 : 0;
        if (source_ref) {
            const CardState& card = state.all_card[source_ref];
            source_player = card.player_index;
            source_area = card.area;
            source_index = current_area_index(state.players[source_player], source_area, source_ref);
        }
    }
}

__device__ __forceinline__ void policy_emit_options(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    gc_i32 actor,
    gc_i32* rows,
    gc_i32& count,
    gc_u32& status
) {
    if (runtime.option_count > kPolicyOptionCapacity) {
        status |= kPolicyProjectionOptionOverflow;
        return;
    }
    count = runtime.option_count;
    for (gc_i32 i = 0; i < count; ++i) {
        gc_i32* row = rows + (gc_i64)i * kPolicyOptionWidth;
        for (gc_i32 j = 0; j < kPolicyOptionWidth; ++j) row[j] = 0;
        const SelectOptionState& option = runtime.options[i];
        row[0] = option.type;
        row[1] = state.select_type;
        row[2] = state.select_context;
        policy_emit_public_option_params(option, row);
        gc_u8 src = 0, dst = 0, src_area = 0, dst_area = 0;
        gc_i32 src_index = -1, dst_index = -1, src_player = -1, dst_player = -1;
        policy_option_source(state, actor, option, src, dst, src_area, src_index, src_player,
            dst_area, dst_index, dst_player);
        if (option.type == kOptionSkill) row[8] = option.param0;
        else if (src && policy_card_visible(state, actor, src)) row[8] = state.all_card[src].card_id;
        if (dst && policy_card_visible(state, actor, dst)) row[9] = state.all_card[dst].card_id;
        row[10] = src_area;
        row[11] = policy_role(src_area, src_index);
        row[12] = policy_relative_player(src_player, actor);
        row[13] = dst_area;
        row[14] = policy_role(dst_area, dst_index);
        row[15] = policy_relative_player(dst_player, actor);
        row[16] = option.type == kOptionAttack ? option.param0 : 0;
        if (option.type == kOptionNumber || option.type == kOptionSpecialCondition) row[18] = option.param0;
        else if (option.type == kOptionEnergy) row[18] = option.param4;
        row[19] = 1;
    }
}

__device__ __forceinline__ void project_policy_full(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_i32* globals,
    gc_i32* players,
    gc_i32* entities,
    gc_i32& entity_count,
    gc_i32* options,
    gc_i32& option_count,
    gc_u32& status
) {
    for (gc_i32 i = 0; i < kPolicyGlobalWidth; ++i) globals[i] = 0;
    for (gc_i32 i = 0; i < 2 * kPolicyPlayerWidth; ++i) players[i] = 0;
    entity_count = 0;
    option_count = 0;
    status = 0;
    if (state.select_type == kSelectNone) {
        status |= kPolicyProjectionNoSelection;
        return;
    }
    const gc_i32 actor = state.select_player;
    if (actor < 0 || actor > 1) {
        status |= kPolicyProjectionBadActor;
        return;
    }
    globals[0] = state.turn;
    globals[1] = state.turn_action_count;
    globals[2] = state.first_player < 0 ? -1 : policy_relative_player(state.first_player, actor);
    globals[3] = state.first_player < 0 ? -1 : policy_relative_player(rule_active_player_index(state), actor);
    // globals[4] is reserved. Native ToJsonApi does not expose the internal
    // phase state, so it must not cross the learner-facing firewall.
    if (state.game_result != 0) globals[5] = (state.game_result - 1) == actor ? 1 : 2;
    globals[6] = state.select_type;
    globals[7] = state.select_context;
    globals[8] = state.select_min;
    globals[9] = state.select_max;
    globals[10] = state.remain_damage_counter;
    globals[11] = state.remain_energy_cost;
    const auto& turn = state_turn(state).fields;
    globals[12] = turn.supporter_played ? 1 : 0;
    globals[13] = turn.stadium_played ? 1 : 0;
    globals[14] = turn.energy_played ? 1 : 0;
    globals[15] = turn.retreated ? 1 : 0;
    if (state.context_card > 0 && state.context_card < kAllCardCapacity)
        globals[16] = state.all_card[state.context_card].card_id;
    const gc_u8 effect_ref = state.effect_state.on_effect
        ? state.effect_state.ability.effect_card.card_index : 0;
    if (effect_ref > 0 && effect_ref < kAllCardCapacity) globals[17] = state.all_card[effect_ref].card_id;
    globals[18] = state.select_deck ? 1 : 0;
    globals[19] = policy_public_looking_mode(state, actor);
    if (globals[19] != 0) globals[20] = state.looking.count;
    if (state.stadium.count > 0) globals[21] = state.all_card[state.stadium.values[0]].card_id;
    globals[22] = runtime.option_count;

    for (gc_i32 rel = 0; rel < 2; ++rel) {
        const gc_i32 p = rel == 0 ? actor : 1 - actor;
        const PlayerState& player = state.players[p];
        gc_i32* row = players + rel * kPolicyPlayerWidth;
        row[0] = player.deck.count;
        row[1] = player.hand.count;
        row[2] = player.prize.count;
        row[3] = policy_visible_prize_count(state, p);
        row[4] = player.bench.count;
        const gc_i32 override_capacity = player_continual(player).fields.bench_capacity;
        row[5] = override_capacity == 0 ? 5 : override_capacity;
        row[6] = player.active.count > 0 && state.all_card[player.active.values[0]].reverse ? 1 : 0;
        const auto& active = player_active_state(player).fields;
        row[7] = active.poison_damage_counter != 0 ? 1 : 0;
        row[8] = active.burned ? 1 : 0;
        row[9] = active.bad_status == 1 ? 1 : 0;
        row[10] = active.bad_status == 2 ? 1 : 0;
        row[11] = active.bad_status == 3 ? 1 : 0;
        policy_emit_player_entities(state, rules, actor, p, entities, entity_count, status);
    }
    if (state.stadium.count > 0) {
        const gc_u8 ref = state.stadium.values[0];
        policy_emit_entity(state, rules, actor, ref, 7, 0, 0, true,
            entities, entity_count, status);
    }
    if (state.looking.count > 0) {
        const bool full = state.looking_player == actor || state.looking_player == 2;
        const bool facedown = state.looking_player == actor + 3;
        if (full || facedown) {
            for (gc_i32 i = 0; i < (gc_i32)state.looking.count; ++i)
                policy_emit_entity(state, rules, actor, state.looking.values[i], 12, i, 0,
                    full, entities, entity_count, status);
        }
    }
    policy_emit_options(state, runtime, actor, options, option_count, status);
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_project_policy(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    const gpu_cabt::RuleCardMaster* cards,
    const gpu_cabt::RuleSkill* skills,
    const gpu_cabt::RuleAttack* attacks,
    const gpu_cabt::RuleEffect* effects,
    const gpu_cabt::RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words,
    gc_i32* globals,
    gc_i32* players,
    gc_i32* entities,
    gc_i32* entity_counts,
    gc_i32* options,
    gc_i32* option_counts,
    gc_u32* projection_status,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto& state = *reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    const auto& runtime = *reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    const auto rules = gpu_cabt::make_game_rule_view(
        cards, skills, attacks, effects, triggers, masks,
        card_count, skill_count, attack_count, effect_count, trigger_count, mask_count, mask_words);
    gpu_cabt::project_policy_full(
        state, runtime, rules,
        globals + (gc_i64)env_index * gpu_cabt::kPolicyGlobalWidth,
        players + (gc_i64)env_index * 2 * gpu_cabt::kPolicyPlayerWidth,
        entities + (gc_i64)env_index * gpu_cabt::kPolicyEntityCapacity * gpu_cabt::kPolicyEntityWidth,
        entity_counts[env_index],
        options + (gc_i64)env_index * gpu_cabt::kPolicyOptionCapacity * gpu_cabt::kPolicyOptionWidth,
        option_counts[env_index],
        projection_status[env_index]);
}
