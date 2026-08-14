namespace gpu_cabt {

static constexpr gc_u64 kWutanBerryHash = 0xc9b33864f357fafeull;
static constexpr gc_u64 kHabanBerryHash = 0x4b701031847fa6dcull;

__device__ __forceinline__ gc_i32 taken_prize_count(const BattleCoreState& state, gc_i32 player_index) {
    if (player_index < 0 || player_index > 1) return 0;
    const gc_i32 count = 6 - (gc_i32)state.players[player_index].prize.count;
    return count > 0 ? count : 0;
}

__device__ __forceinline__ gc_u16 get_weakness_full(
    const CardState& card,
    const RuleCardMaster& master
) {
    if (card_next_enemy_turn_end(card).fields.no_weakness_next_enemy_turn) return kEnergyColorless;
    const gc_i32 index = (gc_i32)card_continual(card).fields.weakness_index;
    return index > 0 ? energy_type_from_index(index) : master.weakness;
}

__device__ __forceinline__ bool attack_flag(const RuleAttack* attack, gc_u32 bit) {
    return attack != nullptr && (attack->flags & (1u << bit)) != 0;
}

__device__ __noinline__ gc_i32 calc_damage_full(
    const BattleCoreState& state,
    const RuleTableView& rules,
    gc_i32 base_damage,
    gc_u8 target_ref,
    gc_u8 attacker_ref,
    bool calc_weakness,
    const RuleAttack* attack
) {
    gc_i32 damage = base_damage;
    if (damage <= 0 || target_ref == 0 || attacker_ref == 0
        || target_ref >= kAllCardCapacity || attacker_ref >= kAllCardCapacity) return 0;

    const CardState& target = state.all_card[target_ref];
    const CardState& attacker = state.all_card[attacker_ref];
    const RuleCardMaster* target_master = rule_card(rules, target.card_id);
    const RuleCardMaster* attacker_master = rule_card(rules, attacker.card_id);
    if (target_master == nullptr || attacker_master == nullptr) return 0;
    if (attacker.player_index < 0 || attacker.player_index > 1) return 0;

    const PlayerState& attacker_player = state.players[attacker.player_index];
    const CardNextTurnFields& attacker_turn = card_this_turn(attacker);
    const CardContinualFields& attacker_cont = card_continual(attacker);
    const CardTurnFields& attacker_history = card_turn(attacker);
    const PlayerTurnFields& attacker_player_turn = player_turn(attacker_player);
    const gc_u16 attacker_type = get_card_energy_type(attacker, *attacker_master);

    damage += attacker_turn.fields.damage_change;
    damage += attacker_cont.fields.damage_change;
    if (target.area == kAreaActive) damage += attacker_turn.fields.damage_change_active;
    if (target.area == kAreaActive && attacker.player_index != target.player_index) {
        damage += attacker_cont.fields.damage_change_active;
        damage += attacker_history.fields.damage_change_this_turn;
        damage += attacker_cont.fields.damage_change_enemy_taken_prize
            * taken_prize_count(state, 1 - attacker.player_index);
        damage += attacker_player_turn.fields.player_damage_change;
        if (is_ex(*target_master)) {
            damage += attacker_cont.fields.damage_change_ex;
            damage += attacker_history.fields.damage_change_ex_this_turn;
            damage += attacker_player_turn.fields.player_damage_change_ex;
        }
        if (contains_energy(attacker_type, kEnergyFighting)) {
            damage += attacker_player_turn.fields.player_damage_change_my_fighting;
        }
        if (attacker_cont.fields.damage_change_ability != 0
            && get_ability(rules, target, *target_master) != nullptr) {
            damage += attacker_cont.fields.damage_change_ability;
        }
        if (attacker_cont.fields.damage_change_evolved != 0
            && target_master->evolution_type != 1) {
            damage += attacker_cont.fields.damage_change_evolved;
        }
    }
    if (damage <= 0) return 0;

    bool calc_resistance = calc_weakness;
    bool calc_target_effect = true;
    if (attack != nullptr) {
        if (attack_flag(attack, 5)) calc_target_effect = false;
        if (attack_flag(attack, 6)) calc_weakness = false;
        if (attack_flag(attack, 7)) calc_resistance = false;
    }

    if (calc_weakness) {
        const gc_u16 weakness = get_weakness_full(target, *target_master);
        if (contains_energy(weakness, attacker_type)) damage *= 2;
    }
    if (calc_resistance && contains_energy(target_master->resistance, attacker_type)) {
        damage -= 30;
        if (damage <= 0) return 0;
    }

    if (calc_target_effect) {
        const CardContinualFields& target_cont = card_continual(target);
        const CardNextEnemyTurnEndFields& target_enemy_end = card_next_enemy_turn_end(target);
        damage += target_cont.fields.take_damage_change;
        damage += target_enemy_end.fields.take_damage_change_next_enemy_turn;
        damage += card_this_turn_enemy(target).fields.take_damage_change;

        const RuleSkill* attacker_ability = get_ability(rules, attacker, *attacker_master);
        if (attacker.player_index != target.player_index) {
            damage += target_cont.fields.take_enemy_attack_damage_change;
            if (contains_energy(attacker_type, (gc_u16)(kEnergyFire | kEnergyWater))) {
                damage += target_cont.fields.take_enemy_fire_or_water_pokemon_attack_damage_change;
            }
            if (contains_energy(attacker_type, (gc_u16)(kEnergyFire | kEnergyWater | kEnergyGrass | kEnergyLightning))) {
                damage += target_cont.fields.take_enemy4_type_pokemon_attack_damage_change;
            }
            if (attacker_ability != nullptr) damage += target_cont.fields.take_enemy_ability_pokemon_attack_damage_change;

            if (target_cont.fields.special_flag_tool) {
                if (contains_energy(attacker_type, kEnergyPsychic)
                    && has_attached_tool_name(state, rules, target, kWutanBerryHash)) damage -= 60;
                if (contains_energy(attacker_type, kEnergyDragon)
                    && has_attached_tool_name(state, rules, target, kHabanBerryHash)) damage -= 60;
            }

            const PlayerNextTurnFields& source_turn = player_this_turn(attacker_player);
            if (source_turn.fields.metal_damage_change != 0
                && contains_energy(get_card_energy_type(target, *target_master), kEnergyMetal)) {
                damage += source_turn.fields.metal_damage_change;
            }

            if (target_cont.fields.no_damage_enemy_ability_pokemon_attack && attacker_ability != nullptr) damage = 0;
            if (target_cont.fields.no_damage_enemy_ex_attack && is_ex(*attacker_master)) damage = 0;
            if (target_cont.fields.no_damage_enemy_basic_ex_attack
                && attacker_master->evolution_type == 1 && is_ex(*attacker_master)) damage = 0;
            if (target_cont.fields.no_damage_and_effect_enemy_terastal_attack
                && card_flag(*attacker_master, kCardFlagTera)) damage = 0;
            if (target_cont.fields.no_damage_and_effect_enemy_special_energy_attack
                && has_attached_special_energy(state, rules, attacker_ref)) damage = 0;
            if (card_next_enemy_battle_field(target).fields.no_damage_and_effect_enemy_ex_attack_next_enemy_turn
                && is_ex(*attacker_master)) damage = 0;
            if (target_cont.fields.no_damage_enemy_attack
                || target_enemy_end.fields.no_damage_and_effect_enemy_attack_next_enemy_turn) damage = 0;
        }
        if (target_enemy_end.fields.no_damage_attack_next_enemy_turn
            || target_enemy_end.fields.no_damage_and_effect_attack_next_enemy_turn) damage = 0;
        if (target_enemy_end.fields.no_damage_basic_attack_next_enemy_turn
            && attacker_master->evolution_type == 1) damage = 0;
        if (target_enemy_end.fields.no_damage_basic_color_attack_next_enemy_turn
            && attacker_master->evolution_type == 1 && attacker_type != kEnergyColorless) damage = 0;
        if (target_enemy_end.fields.no_damage_ability_attack_next_enemy_turn && attacker_ability != nullptr) damage = 0;
        if (damage <= (gc_i32)target_enemy_end.fields.no_damage_less_equal_attack_next_enemy_turn) damage = 0;
        if (target.area == kAreaBench && card_flag(*target_master, kCardFlagTera)) damage = 0;
        if (target_cont.fields.no_damage_greater_equal > 0
            && target_cont.fields.no_damage_greater_equal <= damage) damage = 0;
    }

    if (damage <= 0) return 0;
    return damage > 100000000 ? 100000000 : damage;
}

__device__ __noinline__ void after_damage_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 target_ref,
    gc_u8 cause_ref
) {
    if (target_ref == 0 || cause_ref == 0) return;
    CardState& target = state.all_card[target_ref];
    const CardState& cause = state.all_card[cause_ref];
    if (!card_continual(target).fields.special_flag_tool) return;
    const RuleCardMaster* cause_master = rule_card(rules, cause.card_id);
    if (cause_master == nullptr || target.player_index < 0 || target.player_index > 1) return;
    const gc_u16 attacker_type = get_card_energy_type(cause, *cause_master);
    PlayerState& player = state.players[target.player_index];
    for (gc_i32 i = (gc_i32)player.tool.count - 1; i >= 0; --i) {
        const gc_u8 tool_ref = player.tool.values[i];
        const CardState& tool = state.all_card[tool_ref];
        if (tool.attach_move_counter != target.move_counter) continue;
        const RuleCardMaster* tool_master = rule_card(rules, tool.card_id);
        if (tool_master == nullptr) continue;
        const bool consume = (tool_master->name_hash == kWutanBerryHash && contains_energy(attacker_type, kEnergyPsychic))
            || (tool_master->name_hash == kHabanBerryHash && contains_energy(attacker_type, kEnergyDragon));
        if (consume) move_card_full(state, runtime, rules, target.player_index, 9, i, 3, 0, false, false, false);
    }
}

__device__ __noinline__ void effect_attack_damage_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    gc_u8 target_ref,
    gc_i32 base_damage
) {
    if (target_ref == 0 || state.attacker == 0) return;
    const RuleAttack* attack = rule_attack(rules, state.current_attack_id);
    const bool calc_weakness = state.all_card[target_ref].area == kAreaActive;
    const gc_i32 damage = calc_damage_full(
        state, rules, base_damage, target_ref, state.attacker, calc_weakness, attack
    );
    state.changed = true;
    if (card_continual(state.all_card[target_ref]).fields.no_damage_coin && damage > 0) {
        select_coin_full(state, runtime, 1);
        if (state.coin_head_count != 0 && !attack_flag(attack, 5)) return;
    }
    add_damage_full(state, runtime, rules, target_ref, damage, true, state.attacker, false, attack);
    after_damage_full(state, runtime, rules, target_ref, state.attacker);
}

}  // namespace gpu_cabt
