namespace gpu_cabt {

__device__ __forceinline__ bool card_flag(const RuleCardMaster& master, gc_u64 flag) {
    return (master.flags & flag) != 0;
}

static constexpr gc_u16 kEnergyColorless = 0;
static constexpr gc_u16 kEnergyGrass = 1;
static constexpr gc_u16 kEnergyFire = 2;
static constexpr gc_u16 kEnergyWater = 4;
static constexpr gc_u16 kEnergyLightning = 8;
static constexpr gc_u16 kEnergyPsychic = 16;
static constexpr gc_u16 kEnergyFighting = 32;
static constexpr gc_u16 kEnergyDarkness = 64;
static constexpr gc_u16 kEnergyMetal = 128;
static constexpr gc_u16 kEnergyDragon = 256;
static constexpr gc_u16 kEnergyAll = 511;
static constexpr gc_u64 kEeveeNameHash = 0x416d28ba135b132full;

struct RefPositionState {
    gc_u8 ref;
    gc_u8 area;
    gc_i16 index;
};

struct EnergyInfoState {
    gc_u16 type;
    gc_i16 count;
};

__device__ __forceinline__ gc_i32 rule_active_player_index(const BattleCoreState& state) {
    return ((state.turn + 1) ^ (gc_i32)state.first_player) & 1;
}

__device__ __forceinline__ bool compare_i32(gc_i32 value, gc_i32 expected, gc_u8 comparator) {
    switch (comparator) {
        case 0: return value == expected;
        case 1: return value >= expected;
        case 2: return value <= expected;
        case 3: return value != expected;
        case 4: return value > expected;
        case 5: return value < expected;
        default: return false;
    }
}

__device__ __forceinline__ bool bool_compare(bool value, gc_u8 comparator) {
    return comparator == 0 ? value : !value;
}

__device__ __forceinline__ bool is_target_player(
    gc_i32 owner,
    gc_i32 candidate,
    gc_u8 target_player
) {
    return ((1 + (owner ^ candidate)) & (gc_i32)target_player) != 0;
}

__device__ __forceinline__ bool contains_energy(gc_u16 left, gc_u16 right) {
    return (left & right) != 0;
}

__device__ __forceinline__ bool match_energy(gc_u16 left, gc_u16 right) {
    if (right == kEnergyColorless) return left == kEnergyColorless;
    return (left & right) != 0;
}

__device__ __forceinline__ gc_u16 energy_type_from_index(gc_i32 index) {
    switch (index) {
        case 0: return 0;
        case 1: return 1;
        case 2: return 2;
        case 3: return 4;
        case 4: return 8;
        case 5: return 16;
        case 6: return 32;
        case 7: return 64;
        case 8: return 128;
        case 9: return 256;
        case 10: return 511;
        case 11: return 80;
        default: return 0;
    }
}

__device__ __forceinline__ const RuleCardMaster* rule_card(
    const RuleTableView& rules,
    gc_i32 card_id
) {
    if (card_id <= 0 || card_id >= rules.card_count) return nullptr;
    const RuleCardMaster* card = &rules.cards[card_id];
    return card->card_id == card_id ? card : nullptr;
}

__device__ __forceinline__ const RuleSkill* rule_skill(
    const RuleTableView& rules,
    gc_i32 skill_id
) {
    if (skill_id <= 0 || skill_id >= rules.skill_count) return nullptr;
    const RuleSkill* skill = &rules.skills[skill_id];
    return skill->skill_id == skill_id ? skill : nullptr;
}

__device__ __forceinline__ const RuleAttack* rule_attack(
    const RuleTableView& rules,
    gc_i32 attack_id
) {
    if (attack_id <= 0 || attack_id >= rules.attack_count) return nullptr;
    const RuleAttack* attack = &rules.attacks[attack_id];
    return attack->attack_id == attack_id ? attack : nullptr;
}

__device__ __forceinline__ bool is_trainer(gc_u8 card_type) {
    return card_type >= 1 && card_type <= 4;
}

__device__ __forceinline__ bool is_energy_card(gc_u8 card_type) {
    return card_type == 5 || card_type == 6;
}

__device__ __forceinline__ bool is_rule_pokemon(const RuleCardMaster& master) {
    return master.pokemon_type == 3 || master.pokemon_type == 4;
}

__device__ __forceinline__ bool is_ex(const RuleCardMaster& master) {
    return is_rule_pokemon(master);
}

__device__ __forceinline__ bool is_not_rule_pokemon(const RuleCardMaster& master) {
    return !is_rule_pokemon(master) && master.pokemon_type != 0;
}

__device__ __forceinline__ bool is_not_rule_pokemon_card(const RuleCardMaster& master) {
    return master.pokemon_type == 1;
}

__device__ __forceinline__ bool not_moved(const BattleCoreState& state, const AreaRefState& ref) {
    if (ref.card == 0 || ref.card >= kAllCardCapacity) return false;
    return state.all_card[ref.card].move_counter == ref.move_counter;
}

__device__ __forceinline__ AreaRefState make_area_ref(
    const BattleCoreState& state,
    gc_u8 ref
) {
    AreaRefState result{};
    result.card = ref;
    if (ref > 0 && ref < kAllCardCapacity) result.move_counter = state.all_card[ref].move_counter;
    return result;
}

__device__ __forceinline__ gc_i32 current_area_index(
    const PlayerState& player,
    gc_u8 area,
    gc_u8 ref
) {
    if (area == kAreaDeck) {
        for (gc_i32 i = 0; i < (gc_i32)player.deck.count; ++i) if (player.deck.values[i] == ref) return i;
    } else if (area == kAreaHand) {
        for (gc_i32 i = 0; i < (gc_i32)player.hand.count; ++i) if (player.hand.values[i] == ref) return i;
    } else if (area == 3) {
        for (gc_i32 i = 0; i < (gc_i32)player.trash.count; ++i) if (player.trash.values[i] == ref) return i;
    } else if (area == kAreaActive) {
        for (gc_i32 i = 0; i < (gc_i32)player.active.count; ++i) if (player.active.values[i] == ref) return i;
    } else if (area == kAreaBench) {
        for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) if (player.bench.values[i] == ref) return i;
    } else if (area == kAreaPrize) {
        for (gc_i32 i = 0; i < (gc_i32)player.prize.count; ++i) if (player.prize.values[i] == ref) return i;
    } else if (area == 8) {
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) if (player.energy.values[i] == ref) return i;
    } else if (area == 9) {
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) if (player.tool.values[i] == ref) return i;
    } else if (area == 10) {
        for (gc_i32 i = 0; i < (gc_i32)player.pre_evolution.count; ++i) if (player.pre_evolution.values[i] == ref) return i;
    } else if (area == 24) {
        for (gc_i32 i = 0; i < (gc_i32)player.temporary.count; ++i) if (player.temporary.values[i] == ref) return i;
    }
    return -1;
}

__device__ __forceinline__ RefPositionState attached_card_position(
    const BattleCoreState& state,
    const CardState& attached
) {
    RefPositionState result{};
    result.index = -1;
    const gc_i32 player_index = attached.player_index;
    if (player_index < 0 || player_index > 1) return result;
    const PlayerState& player = state.players[player_index];
    if (player.active.count > 0) {
        const gc_u8 ref = player.active.values[0];
        if (state.all_card[ref].move_counter == attached.attach_move_counter) {
            result.ref = ref;
            result.area = kAreaActive;
            result.index = 0;
            return result;
        }
    }
    for (gc_i32 i = 0; i < (gc_i32)player.bench.count; ++i) {
        const gc_u8 ref = player.bench.values[i];
        if (state.all_card[ref].move_counter == attached.attach_move_counter) {
            result.ref = ref;
            result.area = kAreaBench;
            result.index = (gc_i16)i;
            return result;
        }
    }
    return result;
}

__device__ __forceinline__ gc_i32 get_max_hp(
    const CardState& card,
    const RuleCardMaster& master
) {
    return master.hp + (gc_i32)card_continual(card).fields.hp_change;
}

__device__ __forceinline__ gc_i32 get_hp(
    const CardState& card,
    const RuleCardMaster& master
) {
    return get_max_hp(card, master) - card.damage;
}

__device__ __forceinline__ gc_u16 get_card_energy_type(
    const CardState& card,
    const RuleCardMaster& master
) {
    const gc_i32 index = (gc_i32)card_continual(card).fields.type_index;
    return index > 0 ? energy_type_from_index(index) : master.energy_type;
}

__device__ __forceinline__ bool is_evolved(
    const BattleCoreState& state,
    gc_u8 pokemon_ref
) {
    if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[pokemon_ref];
    if (card.player_index < 0 || card.player_index > 1) return false;
    const PlayerState& player = state.players[card.player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.pre_evolution.count; ++i) {
        const CardState& pre = state.all_card[player.pre_evolution.values[i]];
        if (pre.attach_move_counter == card.move_counter) return true;
    }
    return false;
}

__device__ __forceinline__ const RuleSkill* get_ability(
    const RuleTableView& rules,
    const CardState& card,
    const RuleCardMaster& master
) {
    if (master.ability_skill_id <= 0) return nullptr;
    const CardContinualFields& fields = card_continual(card);
    if (fields.fields.no_ability) return nullptr;
    const RuleSkill* skill = rule_skill(rules, master.ability_skill_id);
    if (skill == nullptr) return nullptr;
    if (fields.fields.no_ko_me_ability && (skill->flags & kSkillFlagKoMeAbility) != 0) return nullptr;
    return skill;
}

__device__ __forceinline__ gc_i32 retreat_cost(
    const CardState& card,
    const RuleCardMaster& master
) {
    gc_i32 cost = (gc_i32)master.retreat_cost
        + (gc_i32)card_continual(card).fields.retreat_cost_change
        + (gc_i32)card_this_turn(card).fields.retreat_cost_change;
    if (card_continual(card).fields.no_retreat_cost || master.pokemon_type == 2) cost = 0;
    return cost < 0 ? 0 : cost;
}

__device__ __forceinline__ EnergyInfoState get_energy_info(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& energy,
    gc_u8 pokemon_ref
) {
    EnergyInfoState result{};
    const RuleCardMaster* master = rule_card(rules, energy.card_id);
    if (master == nullptr) return result;
    if (master->card_type == 6 && pokemon_ref > 0 && pokemon_ref < kAllCardCapacity) {
        const CardState& pokemon = state.all_card[pokemon_ref];
        const RuleCardMaster* pokemon_master = rule_card(rules, pokemon.card_id);
        if (pokemon_master != nullptr) {
            if (master->card_id == 10) {
                if (pokemon_master->evolution_type == 3) return {kEnergyAll, 2};
                return {kEnergyColorless, 1};
            }
            if (master->card_id == 16) {
                if (pokemon_master->evolution_type == 1) return {kEnergyAll, 1};
                return {kEnergyColorless, 1};
            }
            if (master->card_id == 17) {
                if (pokemon_master->evolution_type == 2 || pokemon_master->evolution_type == 3) {
                    return {kEnergyColorless, 3};
                }
                return {kEnergyColorless, 1};
            }
        }
    } else if (master->card_id == 1 && pokemon_ref > 0 && pokemon_ref < kAllCardCapacity) {
        if (card_continual(state.all_card[pokemon_ref]).fields.double_grass_energy) {
            return {kEnergyGrass, 2};
        }
    }
    result.type = master->energy_type;
    result.count = master->energy_count;
    return result;
}

__device__ __forceinline__ gc_i32 attached_energy_count(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_u8 pokemon_ref
) {
    if (player_index < 0 || player_index > 1 || pokemon_ref == 0) return 0;
    const gc_i32 move_counter = state.all_card[pokemon_ref].move_counter;
    gc_i32 count = 0;
    const PlayerState& player = state.players[player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const CardState& energy = state.all_card[player.energy.values[i]];
        if (energy.attach_move_counter == move_counter) count += get_energy_info(state, rules, energy, pokemon_ref).count;
    }
    return count;
}

__device__ __forceinline__ gc_i32 attached_energy_type_count(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 player_index,
    gc_u8 pokemon_ref,
    gc_u16 target_type
) {
    if (player_index < 0 || player_index > 1 || pokemon_ref == 0) return 0;
    const gc_i32 move_counter = state.all_card[pokemon_ref].move_counter;
    gc_i32 count = 0;
    const PlayerState& player = state.players[player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const CardState& energy = state.all_card[player.energy.values[i]];
        if (energy.attach_move_counter != move_counter) continue;
        const EnergyInfoState info = get_energy_info(state, rules, energy, pokemon_ref);
        if (contains_energy(info.type, target_type)) count += info.count;
    }
    return count;
}

__device__ __forceinline__ bool has_attached_special_energy(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 pokemon_ref
) {
    if (pokemon_ref == 0) return false;
    const CardState& pokemon = state.all_card[pokemon_ref];
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return false;
    const PlayerState& player = state.players[pokemon.player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const CardState& energy = state.all_card[player.energy.values[i]];
        const RuleCardMaster* master = rule_card(rules, energy.card_id);
        if (energy.attach_move_counter == pokemon.move_counter && master != nullptr && master->card_type == 6) return true;
    }
    return false;
}

__device__ __forceinline__ gc_i32 attached_tool_count(
    const BattleCoreState& state,
    const CardState& pokemon
) {
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return 0;
    const PlayerState& player = state.players[pokemon.player_index];
    gc_i32 count = 0;
    for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
        if (state.all_card[player.tool.values[i]].attach_move_counter == pokemon.move_counter) ++count;
    }
    return count;
}

__device__ __forceinline__ bool has_attached_tool_name(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& pokemon,
    gc_u64 name_hash
) {
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return false;
    const PlayerState& player = state.players[pokemon.player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
        const CardState& tool = state.all_card[player.tool.values[i]];
        const RuleCardMaster* master = rule_card(rules, tool.card_id);
        if (tool.attach_move_counter == pokemon.move_counter && master != nullptr && master->name_hash == name_hash) return true;
    }
    return false;
}

__device__ __forceinline__ bool has_attached_energy_name(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 pokemon_ref,
    gc_u64 name_hash
) {
    if (pokemon_ref == 0) return false;
    const CardState& pokemon = state.all_card[pokemon_ref];
    if (pokemon.player_index < 0 || pokemon.player_index > 1) return false;
    const PlayerState& player = state.players[pokemon.player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const CardState& energy = state.all_card[player.energy.values[i]];
        const RuleCardMaster* master = rule_card(rules, energy.card_id);
        if (energy.attach_move_counter == pokemon.move_counter && master != nullptr && master->name_hash == name_hash) return true;
    }
    return false;
}

__device__ __forceinline__ bool can_evolve_effect(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& hand_card,
    const RuleCardMaster& hand_master,
    gc_u8 pokemon_ref
) {
    if (hand_master.card_type != 0 || pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return false;
    const CardState& pokemon = state.all_card[pokemon_ref];
    if ((hand_master.flags & kCardFlagTransformOnly) != 0) return false;
    const RuleCardMaster* pokemon_master = rule_card(rules, pokemon.card_id);
    if (pokemon_master == nullptr) return false;
    if (card_continual(pokemon).fields.rainbow_dna) {
        if (state.turn > 2 && !card_turn(pokemon).fields.appear && hand_card.area == kAreaHand
            && is_ex(hand_master) && hand_master.evolves_from_hash == kEeveeNameHash) {
            return true;
        }
    }
    return hand_master.evolves_from_hash != 0 && hand_master.evolves_from_hash == pokemon_master->name_hash;
}

__device__ __forceinline__ bool can_evolve2(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const CardState& hand_card,
    const RuleCardMaster& hand_master,
    gc_u8 pokemon_ref
) {
    if (hand_master.card_type != 0 || hand_master.evolution_type != 3 || pokemon_ref == 0) return false;
    const CardState& pokemon = state.all_card[pokemon_ref];
    if (card_turn(pokemon).fields.appear || (hand_master.flags & kCardFlagTransformOnly) != 0) return false;
    const RuleCardMaster* pokemon_master = rule_card(rules, pokemon.card_id);
    return pokemon_master != nullptr && hand_master.evolves_from2_hash != 0
        && hand_master.evolves_from2_hash == pokemon_master->name_hash;
}

__device__ __forceinline__ gc_i32 bench_capacity(const PlayerState& player) {
    const gc_i32 capacity = (gc_i32)player_continual(player).fields.bench_capacity;
    return capacity == 0 ? 5 : capacity;
}

__device__ __forceinline__ gc_i32 remaining_bench(const BattleCoreState& state, gc_i32 player_index) {
    return bench_capacity(state.players[player_index]) - (gc_i32)state.players[player_index].bench.count;
}

__device__ __forceinline__ bool is_special_condition(const PlayerState& player) {
    const PlayerActiveFields& active = player_active_state(player);
    return active.fields.bad_status != 0 || active.fields.poison_damage_counter > 0 || active.fields.burned;
}

__device__ __forceinline__ bool substring_mask_match(
    const RuleTableView& rules,
    gc_i32 mask_index,
    gc_i32 card_id
) {
    if (mask_index < 0 || mask_index >= rules.substring_mask_count || card_id < 0 || card_id >= rules.card_count) return false;
    const gc_i32 word = card_id >> 5;
    const gc_i32 bit = card_id & 31;
    return (rules.substring_masks[mask_index * rules.substring_mask_words + word] & (1u << bit)) != 0;
}


__device__ __forceinline__ gc_i32 energy_type_index(gc_u16 type) {
    switch (type) {
        case 0: return 0; case 1: return 1; case 2: return 2; case 4: return 3;
        case 8: return 4; case 16: return 5; case 32: return 6; case 64: return 7;
        case 128: return 8; case 256: return 9; case 511: return 10; case 80: return 11;
        default: return 0;
    }
}

__device__ __forceinline__ bool master_has_attack(
    const RuleCardMaster& master,
    gc_i32 attack_id
) {
    return master.attack_ids[0] == attack_id || master.attack_ids[1] == attack_id;
}

__device__ __noinline__ gc_i32 insufficient_energy_count(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 pokemon_ref,
    const RuleAttack& attack,
    bool return_extra
) {
    if (pokemon_ref == 0 || pokemon_ref >= kAllCardCapacity) return 999;
    const CardState& card = state.all_card[pokemon_ref];
    const RuleCardMaster* master = rule_card(rules, card.card_id);
    if (master == nullptr || card.player_index < 0 || card.player_index > 1) return 999;
    gc_i32 required[10] = {};
    gc_i32 required_colorless = 0;
    gc_i32 required_sum = 0;
    bool fix_energy = false;
    const gc_u32 flags = attack.flags;
    if ((flags & (1u << 13)) != 0 && is_special_condition(state.players[card.player_index])) {
        fix_energy = true;
    } else if ((card_continual(card).fields.attack_energy_colorless_one
                || card_continual(card).fields.attack_energy_psychic_one)
               && master_has_attack(*master, attack.attack_id)) {
        fix_energy = true;
        if (card_continual(card).fields.attack_energy_colorless_one) ++required_colorless;
        else ++required[energy_type_index(kEnergyPsychic)];
        ++required_sum;
    } else if ((flags & (1u << 14)) != 0 && card.damage > 0) {
        fix_energy = true;
        ++required[energy_type_index(kEnergyDarkness)];
        ++required_sum;
    } else {
        for (gc_i32 i = 0; i < (gc_i32)attack.energy_count; ++i) {
            const gc_u16 type = attack.energies[i];
            if (type == kEnergyColorless) ++required_colorless;
            else ++required[energy_type_index(type)];
            ++required_sum;
        }
    }

    gc_i32 all_count = 0;
    gc_i32 pd_count = 0;
    gc_i32 colorless_count = 0;
    const PlayerState& player = state.players[card.player_index];
    for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
        const CardState& energy = state.all_card[player.energy.values[i]];
        if (energy.attach_move_counter != card.move_counter) continue;
        const EnergyInfoState info = get_energy_info(state, rules, energy, pokemon_ref);
        for (gc_i32 unit = 0; unit < info.count; ++unit) {
            const gc_u16 type = info.type;
            if (type == kEnergyAll) ++all_count;
            else if (type == kEnergyColorless) ++colorless_count;
            else if (type == (kEnergyPsychic | kEnergyDarkness)) ++pd_count;
            else {
                gc_i32& number = required[energy_type_index(type)];
                if (number > 0) { --number; --required_sum; }
                else ++colorless_count;
            }
        }
    }

    if (!fix_energy) {
        all_count += card_continual(card).fields.attack_cost_down;
        const gc_i32 change = (gc_i32)card_continual(card).fields.attack_cost_change_colorless
            + (gc_i32)card_this_turn(card).fields.attack_cost_change;
        if (change < 0) colorless_count -= change;
        else { required_colorless += change; required_sum += change; }
        if (card_continual(card).fields.attack_cost_down_colorless_own_attack > 0
            && master_has_attack(*master, attack.attack_id)) {
            colorless_count += card_continual(card).fields.attack_cost_down_colorless_own_attack;
        }
    }

    for (gc_i32 i = 0; i < pd_count; ++i) {
        gc_i32& psychic = required[energy_type_index(kEnergyPsychic)];
        if (psychic > 0) { --psychic; --required_sum; continue; }
        gc_i32& darkness = required[energy_type_index(kEnergyDarkness)];
        if (darkness > 0) { --darkness; --required_sum; continue; }
        ++colorless_count;
    }
    if (return_extra) return required_sum - all_count - colorless_count;
    gc_i32 used_colorless = colorless_count < required_colorless ? colorless_count : required_colorless;
    gc_i32 need = required_sum - all_count - used_colorless;
    return need > 0 ? need : 0;
}

__device__ __forceinline__ bool enough_energy(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 pokemon_ref,
    const RuleAttack& attack
) {
    return insufficient_energy_count(state, rules, pokemon_ref, attack, false) <= 0;
}


__device__ __forceinline__ gc_i32 effect_value(
    const BattleCoreState& state,
    const BattleRuntimeState& runtime,
    const RuleEffect& effect,
    gc_i32 index
) {
    if (index < 0 || index > 1) return 0;
    gc_i32 value = effect.values[index];
    if ((effect.flags & kEffectFlagMultiplyPreTargetCount) != 0) value *= runtime.pre_target_count;
    if ((effect.flags & kEffectFlagMultiplyCoinHeadCount) != 0) value *= state.coin_head_count;
    return value;
}

__device__ __forceinline__ gc_i16 clamp_i16_add(gc_i16 current, gc_i32 delta) {
    gc_i32 value = (gc_i32)current + delta;
    if (value < -32768) value = -32768;
    if (value > 32767) value = 32767;
    return (gc_i16)value;
}

__device__ __forceinline__ gc_i8 clamp_i8(gc_i32 value, gc_i32 low, gc_i32 high) {
    if (value < low) value = low;
    if (value > high) value = high;
    return (gc_i8)value;
}


__device__ __forceinline__ bool on_effect(const BattleCoreState& state) {
    return state.effect_state.on_effect != 0;
}

__device__ __forceinline__ bool on_attack(const BattleCoreState& state) {
    return state.current_attack_id > 0;
}

__device__ __forceinline__ bool on_attack_effect(const BattleCoreState& state) {
    if (!on_attack(state)) return false;
    if (on_effect(state)) {
        const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
        if (effect_ref != state.attacker) return false;
    }
    return true;
}

__device__ __forceinline__ bool is_prevent_effect(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 source_ref
) {
    if (source_ref == 0 || source_ref >= kAllCardCapacity) return false;
    const CardState* target = &state.all_card[source_ref];
    if (target->area == 8 || target->area == 9) {
        const RefPositionState pos = attached_card_position(state, *target);
        if (pos.ref != 0) target = &state.all_card[pos.ref];
    }
    const CardContinualFields& continual = card_continual(*target);
    const CardNextEnemyTurnEndFields& next_end = card_next_enemy_turn_end(*target);
    if (on_attack_effect(state)) {
        if (state.attacker == 0) return false;
        const CardState& attacker = state.all_card[state.attacker];
        const RuleCardMaster* attacker_master = rule_card(rules, attacker.card_id);
        if (attacker.player_index != target->player_index) {
            if (continual.fields.no_damage_and_effect_enemy_terastal_attack
                && attacker_master != nullptr
                && card_flag(*attacker_master, kCardFlagTera)) return true;
            if (continual.fields.no_damage_and_effect_enemy_special_energy_attack
                && has_attached_special_energy(state, rules, state.attacker)) return true;
            if (continual.fields.no_effect_enemy_attack
                || next_end.fields.no_damage_and_effect_enemy_attack_next_enemy_turn) return true;
            if (card_next_enemy_battle_field(*target).fields.no_damage_and_effect_enemy_ex_attack_next_enemy_turn
                && attacker_master != nullptr && is_ex(*attacker_master)) return true;
        }
        if (next_end.fields.no_damage_and_effect_attack_next_enemy_turn) return true;
    } else if (on_effect(state)) {
        const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
        if (effect_ref != 0 && effect_ref < kAllCardCapacity) {
            const CardState& effect_card = state.all_card[effect_ref];
            if (effect_card.player_index != target->player_index) {
                const RuleCardMaster* effect_master = rule_card(rules, effect_card.card_id);
                if (effect_master != nullptr) {
                    if (continual.fields.no_effect_enemy_item && effect_master->card_type == 1) return true;
                    if (continual.fields.no_effect_enemy_supporter && effect_master->card_type == 3) return true;
                }
                if (continual.fields.no_enemy_ability
                    && (effect_card.area == kAreaActive || effect_card.area == kAreaBench)) return true;
            }
        }
    }
    return false;
}

__device__ __forceinline__ bool valid_area_ref(
    const BattleCoreState& state,
    const AreaRefState& ref
) {
    return ref.card != 0 && ref.card < kAllCardCapacity
        && state.all_card[ref.card].move_counter == ref.move_counter;
}

__device__ __forceinline__ bool valid_area_ref_not_prevented(
    const BattleCoreState& state,
    const RuleTableView& rules,
    const AreaRefState& ref
) {
    return valid_area_ref(state, ref) && !is_prevent_effect(state, rules, ref.card);
}

__device__ __forceinline__ bool is_prevent_damage_counter(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_u8 target_ref
) {
    if (target_ref == 0 || target_ref >= kAllCardCapacity) return false;
    const CardState& target = state.all_card[target_ref];
    if (!card_continual(target).fields.no_damage_counter_enemy_attack_ability) return false;
    const gc_u8 effect_ref = state.effect_state.ability.effect_card.card_index;
    if (effect_ref == 0 || effect_ref >= kAllCardCapacity) return false;
    const CardState& effect_card = state.all_card[effect_ref];
    const RuleCardMaster* master = rule_card(rules, effect_card.card_id);
    return master != nullptr && master->card_type == 0
        && target.player_index != effect_card.player_index;
}


__device__ __forceinline__ gc_i32 effect_player_index(const BattleCoreState& state) {
    const gc_i32 player = state.effect_state.ability.use_player_index;
    if (player >= 0 && player <= 1) return player;
    const gc_u8 ref = state.effect_state.ability.effect_card.card_index;
    return ref != 0 && ref < kAllCardCapacity ? state.all_card[ref].player_index : 0;
}

__device__ __forceinline__ gc_i32 effect_target_player_index(
    const BattleCoreState& state,
    const RuleEffect& effect
) {
    const gc_i32 player = effect_player_index(state);
    return effect.target.target_player == 1 ? player : 1 - player;
}

__device__ __forceinline__ gc_i32 effect_looking_player_index(
    const BattleCoreState& state,
    const RuleEffect& effect
) {
    if ((effect.flags & kEffectFlagOpen) != 0) return 2;
    return effect_player_index(state);
}

__device__ __forceinline__ gc_i32 looking_open_type(const BattleCoreState& state) {
    if (state.looking_player == 2) return 0;
    if (state.looking_player < 0 || state.looking_player > 1) return 0;
    return 3 + state.looking_player;
}

__device__ __forceinline__ void shuffle_player_deck(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1) return;
    auto& deck = state.players[player_index].deck;
    for (gc_i32 index = (gc_i32)deck.count - 1; index > 0; --index) {
        const gc_u32 swap_index = bounded_u32(
            runtime.rng_seed,
            runtime.rng_stream,
            &runtime.rng_draw_index,
            (gc_u32)(index + 1)
        );
        const gc_u8 tmp = deck.values[index];
        deck.values[index] = deck.values[swap_index];
        deck.values[swap_index] = tmp;
    }
}

__device__ __forceinline__ void shuffle_u8_list(
    gc_u8* values,
    gc_i32 count,
    BattleRuntimeState& runtime
) {
    for (gc_i32 index = count - 1; index > 0; --index) {
        const gc_u32 swap_index = bounded_u32(
            runtime.rng_seed,
            runtime.rng_stream,
            &runtime.rng_draw_index,
            (gc_u32)(index + 1)
        );
        const gc_u8 tmp = values[index]; values[index] = values[swap_index]; values[swap_index] = tmp;
    }
}

}  // namespace gpu_cabt
