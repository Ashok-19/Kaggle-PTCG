#pragma once

namespace gpu_cabt {

union CardNextTurnFields {
    gc_u32 value[4];
    struct {
        gc_i16 cannot_use_attack_id;
        gc_i16 cannot_use_attack_id2;
        gc_i16 damage_change;
        gc_i16 damage_change_active;
        gc_i16 damage_change_my_attack;
        gc_i8 attack_cost_change;
        gc_i8 retreat_cost_change;
        bool cannot_retreat : 1;
        bool cannot_hand_attach_energy : 1;
        bool cannot_attack : 1;
        bool cannot_attack_less_equal_energy2 : 1;
        bool attack_coin : 1;
        bool attack_coin2 : 1;
    } fields;
};

union CardNextMyTurnEnemyFields {
    gc_u32 value[1];
    struct {
        gc_i16 take_damage_change;
    } fields;
};

union CardNextEnemyTurnBattleFieldFields {
    gc_u16 value;
    struct {
        bool no_damage_and_effect_enemy_ex_attack_next_enemy_turn : 1;
    } fields;
};

union CardNextEnemyTurnEndFields {
    gc_u32 value;
    struct {
        gc_i16 take_damage_change_next_enemy_turn;
        gc_u8 no_damage_less_equal_attack_next_enemy_turn;
        bool no_damage_and_effect_attack_next_enemy_turn : 1;
        bool no_damage_and_effect_enemy_attack_next_enemy_turn : 1;
        bool no_damage_attack_next_enemy_turn : 1;
        bool no_damage_basic_attack_next_enemy_turn : 1;
        bool no_damage_basic_color_attack_next_enemy_turn : 1;
        bool no_damage_ability_attack_next_enemy_turn : 1;
        bool no_weakness_next_enemy_turn : 1;
    } fields;
};

union CardTurnFields {
    gc_u32 value[3];
    struct {
        gc_i16 damage_change_this_turn;
        gc_i16 damage_change_ex_this_turn;
        gc_u8 ko_cause_ref;
        gc_i8 ko_prize_change_always;
        gc_i8 ko_prize_change;
        bool appear : 1;
        bool evolved : 1;
        bool bench_to_active : 1;
        bool ko : 1;
        bool ko_attack_damage : 1;
        bool ko_enemy_attack_damage : 1;
        bool ko_enemy_attack_damage_active : 1;
        bool ko_enemy_ex_attack_damage : 1;
        bool ko_enemy_terastal_attack_damage : 1;
        bool ko_enemy_n_attack_damage : 1;
        bool ko_full : 1;
        bool ko_prize_plus1 : 1;
        bool ko_prize_decrease_once : 1;
        bool ko_prize_zero : 1;
        bool ko_no_damage_and_effect_attack_next_enemy_turn : 1;
    } fields;
};

union CardContinualFields {
    gc_u64 value[5];
    struct {
        gc_i16 hp_change;
        gc_i16 damage_change;
        gc_i16 damage_change_active;
        gc_i16 damage_change_ex;
        gc_i16 damage_change_ability;
        gc_i16 damage_change_evolved;
        gc_i16 damage_change_enemy_taken_prize;
        gc_i16 take_damage_change;
        gc_i16 take_enemy_attack_damage_change;
        gc_i16 take_enemy_ability_pokemon_attack_damage_change;
        gc_i16 take_enemy_fire_or_water_pokemon_attack_damage_change;
        gc_i16 take_enemy4_type_pokemon_attack_damage_change;
        gc_i16 no_damage_greater_equal;
        gc_i8 retreat_cost_change;
        gc_i8 attack_cost_change_colorless;
        gc_i8 attack_cost_down;
        gc_i8 attack_cost_down_colorless_own_attack;
        gc_i8 type_index;
        gc_i8 weakness_index;
        bool no_ability : 1;
        bool no_ko_me_ability : 1;
        bool no_damage_enemy_ability_pokemon_attack : 1;
        bool no_damage_enemy_ex_attack : 1;
        bool no_damage_enemy_basic_ex_attack : 1;
        bool no_damage_and_effect_enemy_terastal_attack : 1;
        bool no_damage_and_effect_enemy_special_energy_attack : 1;
        bool no_damage_enemy_attack : 1;
        bool no_effect_enemy_attack : 1;
        bool no_effect_enemy_item : 1;
        bool no_effect_enemy_supporter : 1;
        bool no_damage_counter_enemy_attack_ability : 1;
        bool no_enemy_ability : 1;
        bool no_special_condition : 1;
        bool no_sleep_paralyze_confuse : 1;
        bool no_sleep : 1;
        bool no_retreat_cost : 1;
        bool no_prize_ex : 1;
        bool not_recover_confuse_evolve : 1;
        bool can_use_pre_evolution_attack : 1;
        bool can_evolve_appear_turn : 1;
        bool can_evolve_grass_appear_turn : 1;
        bool can_attack_first : 1;
        bool cannot_retreat : 1;
        bool cannot_attack : 1;
        bool cannot_to_hand : 1;
        bool cannot_move_damage_counter : 1;
        bool attack_energy_colorless_one : 1;
        bool attack_energy_psychic_one : 1;
        bool double_grass_energy : 1;
        bool no_damage_coin : 1;
        bool ko_by_damage_to_hand : 1;
        bool basic_prize_plus1 : 1;
        bool double_attack : 1;
        bool tool2 : 1;
        bool tool4 : 1;
        bool technical_machine : 1;
        bool special_flag_tool : 1;
        bool rainbow_dna : 1;
        bool can_play : 1;
    } fields;
};

union PlayerNextTurnFields {
    gc_u32 value;
    struct {
        gc_i16 metal_damage_change;
        bool cannot_attack_less_equal_energy2 : 1;
        bool cannot_play_item : 1;
        bool cannot_play_supporter : 1;
        bool cannot_play_stadium : 1;
        bool cannot_play_special_energy : 1;
        bool cannot_evolve : 1;
        bool cannot_retreat_poison : 1;
    } fields;
};

union PlayerActiveFields {
    gc_u32 value;
    struct {
        gc_i8 poison_damage_counter;
        gc_u8 bad_status;
        bool burned;
    } fields;
};

union PlayerContinualFields {
    gc_u64 value;
    struct {
        gc_i16 poison_damage_change;
        gc_i16 burn_damage_change;
        gc_i8 poison_damage_change_not_darkness;
        gc_u8 bench_capacity : 4;
        bool cannot_play_item : 1;
        bool cannot_play_stadium : 1;
        bool cannot_play_tool : 1;
        bool cannot_play_ace_spec : 1;
        bool cannot_play_ability_pokemon_not_rocket : 1;
        bool cannot_trash_to_hand_ability_or_trainers : 1;
    } fields;
};

union PlayerTurnFields {
    gc_u64 value;
    struct {
        gc_i16 player_damage_change;
        gc_i16 player_damage_change_ex;
        gc_i16 player_damage_change_my_fighting;
        gc_i8 take_prize_count_change_terastal_attack_ko_active;
        gc_i8 take_prize_count_change_n_attack_ko_active;
    } fields;
};

union StateTurnFields {
    gc_u8 value;
    struct {
        bool supporter_played : 1;
        bool stadium_played : 1;
        bool energy_played : 1;
        bool retreated : 1;
        bool turn_end : 1;
    } fields;
};

union StateContinualFields {
    gc_u8 value;
    struct {
        bool no_tool_effect : 1;
    } fields;
};

__device__ __forceinline__ CardNextTurnFields& card_this_turn(CardState& card) {
    return *reinterpret_cast<CardNextTurnFields*>(card.this_turn);
}
__device__ __forceinline__ const CardNextTurnFields& card_this_turn(const CardState& card) {
    return *reinterpret_cast<const CardNextTurnFields*>(card.this_turn);
}
__device__ __forceinline__ CardNextTurnFields& card_next_turn(CardState& card) {
    return *reinterpret_cast<CardNextTurnFields*>(card.next_turn);
}
__device__ __forceinline__ CardNextMyTurnEnemyFields& card_this_turn_enemy(CardState& card) {
    return *reinterpret_cast<CardNextMyTurnEnemyFields*>(card.this_turn_enemy);
}
__device__ __forceinline__ const CardNextMyTurnEnemyFields& card_this_turn_enemy(const CardState& card) {
    return *reinterpret_cast<const CardNextMyTurnEnemyFields*>(card.this_turn_enemy);
}
__device__ __forceinline__ CardNextMyTurnEnemyFields& card_next_turn_enemy(CardState& card) {
    return *reinterpret_cast<CardNextMyTurnEnemyFields*>(card.next_turn_enemy);
}
__device__ __forceinline__ CardNextEnemyTurnBattleFieldFields& card_next_enemy_battle_field(CardState& card) {
    return *reinterpret_cast<CardNextEnemyTurnBattleFieldFields*>(&card.next_enemy_turn_end_state_battle_field);
}
__device__ __forceinline__ const CardNextEnemyTurnBattleFieldFields& card_next_enemy_battle_field(const CardState& card) {
    return *reinterpret_cast<const CardNextEnemyTurnBattleFieldFields*>(&card.next_enemy_turn_end_state_battle_field);
}
__device__ __forceinline__ CardNextEnemyTurnEndFields& card_next_enemy_turn_end(CardState& card) {
    return *reinterpret_cast<CardNextEnemyTurnEndFields*>(&card.next_enemy_turn_end_state);
}
__device__ __forceinline__ const CardNextEnemyTurnEndFields& card_next_enemy_turn_end(const CardState& card) {
    return *reinterpret_cast<const CardNextEnemyTurnEndFields*>(&card.next_enemy_turn_end_state);
}
__device__ __forceinline__ CardTurnFields& card_turn(CardState& card) {
    return *reinterpret_cast<CardTurnFields*>(card.turn_state);
}
__device__ __forceinline__ const CardTurnFields& card_turn(const CardState& card) {
    return *reinterpret_cast<const CardTurnFields*>(card.turn_state);
}
__device__ __forceinline__ CardContinualFields& card_continual(CardState& card) {
    return *reinterpret_cast<CardContinualFields*>(card.continual_state);
}
__device__ __forceinline__ const CardContinualFields& card_continual(const CardState& card) {
    return *reinterpret_cast<const CardContinualFields*>(card.continual_state);
}
__device__ __forceinline__ PlayerNextTurnFields& player_this_turn(PlayerState& player) {
    return *reinterpret_cast<PlayerNextTurnFields*>(&player.this_turn);
}
__device__ __forceinline__ const PlayerNextTurnFields& player_this_turn(const PlayerState& player) {
    return *reinterpret_cast<const PlayerNextTurnFields*>(&player.this_turn);
}
__device__ __forceinline__ PlayerNextTurnFields& player_next_turn(PlayerState& player) {
    return *reinterpret_cast<PlayerNextTurnFields*>(&player.next_turn);
}
__device__ __forceinline__ PlayerActiveFields& player_active_state(PlayerState& player) {
    return *reinterpret_cast<PlayerActiveFields*>(&player.active_state);
}
__device__ __forceinline__ const PlayerActiveFields& player_active_state(const PlayerState& player) {
    return *reinterpret_cast<const PlayerActiveFields*>(&player.active_state);
}
__device__ __forceinline__ PlayerContinualFields& player_continual(PlayerState& player) {
    return *reinterpret_cast<PlayerContinualFields*>(&player.continual_state);
}
__device__ __forceinline__ const PlayerContinualFields& player_continual(const PlayerState& player) {
    return *reinterpret_cast<const PlayerContinualFields*>(&player.continual_state);
}
__device__ __forceinline__ PlayerTurnFields& player_turn(PlayerState& player) {
    return *reinterpret_cast<PlayerTurnFields*>(&player.turn_state);
}
__device__ __forceinline__ const PlayerTurnFields& player_turn(const PlayerState& player) {
    return *reinterpret_cast<const PlayerTurnFields*>(&player.turn_state);
}
__device__ __forceinline__ StateTurnFields& state_turn(BattleCoreState& state) {
    return *reinterpret_cast<StateTurnFields*>(&state.turn_state);
}
__device__ __forceinline__ const StateTurnFields& state_turn(const BattleCoreState& state) {
    return *reinterpret_cast<const StateTurnFields*>(&state.turn_state);
}
__device__ __forceinline__ StateContinualFields& state_continual(BattleCoreState& state) {
    return *reinterpret_cast<StateContinualFields*>(&state.continual_state);
}
__device__ __forceinline__ const StateContinualFields& state_continual(const BattleCoreState& state) {
    return *reinterpret_cast<const StateContinualFields*>(&state.continual_state);
}

static_assert(sizeof(CardNextTurnFields) == 16, "CardNextTurnFields ABI");
static_assert(sizeof(CardNextMyTurnEnemyFields) == 4, "CardNextMyTurnEnemyFields ABI");
static_assert(sizeof(CardTurnFields) == 12, "CardTurnFields ABI");
static_assert(sizeof(CardContinualFields) == 40, "CardContinualFields ABI");
static_assert(sizeof(PlayerNextTurnFields) == 4, "PlayerNextTurnFields ABI");
static_assert(sizeof(PlayerActiveFields) == 4, "PlayerActiveFields ABI");
static_assert(sizeof(PlayerContinualFields) == 8, "PlayerContinualFields ABI");
static_assert(sizeof(PlayerTurnFields) == 8, "PlayerTurnFields ABI");
static_assert(sizeof(StateTurnFields) == 1, "StateTurnFields ABI");
static_assert(sizeof(StateContinualFields) == 1, "StateContinualFields ABI");

}  // namespace gpu_cabt
