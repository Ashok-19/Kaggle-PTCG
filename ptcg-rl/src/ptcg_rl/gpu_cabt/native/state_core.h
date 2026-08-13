#pragma once

// Portable, pointer-free battle-state ABI for host/CUDA differential testing.
// This file intentionally uses no standard-library headers so NVRTC can compile
// it with the minimal CUDA runtime/header package used by local qualification.

using gc_u8 = unsigned char;
using gc_i8 = signed char;
using gc_u16 = unsigned short;
using gc_i16 = short;
using gc_u32 = unsigned int;
using gc_i32 = int;
using gc_u64 = unsigned long long;
using gc_i64 = long long;

static_assert(sizeof(gc_u8) == 1, "gc_u8 width");
static_assert(sizeof(gc_u16) == 2, "gc_u16 width");
static_assert(sizeof(gc_u32) == 4, "gc_u32 width");
static_assert(sizeof(gc_u64) == 8, "gc_u64 width");

namespace gpu_cabt {

static constexpr int kDeckSize = 60;
static constexpr int kBenchSizeMax = 8;
static constexpr int kCardListCapacity = kDeckSize + 1;
static constexpr int kAllCardCapacity = 128;
static constexpr int kSelectCountCapacity = kBenchSizeMax + 1;
static constexpr gc_u8 kAreaDeck = 1;
static constexpr gc_u8 kAreaHand = 2;
static constexpr gc_u8 kAreaActive = 4;
static constexpr gc_u8 kAreaPlayer = 11;

template <typename T, int Capacity>
struct FixedListU8 {
    gc_u8 count;
    T values[Capacity];
};

struct AreaRef {
    gc_u8 card_index;
    gc_i32 move_counter;
};

struct ActivateAbilityInfo {
    gc_i32 skill_id;
    AreaRef effect_card;
    gc_i8 use_player_index;
    gc_u8 is_effect_stack;
    gc_i8 effect_stack_index;
    gc_u8 is_special_condition;
};

struct TriggerInfo {
    gc_u8 type;
    gc_i8 depth;
    gc_i32 value;
    AreaRef subject;
    AreaRef object;
};

struct EffectState {
    ActivateAbilityInfo ability;
    gc_i8 effect_index;
    gc_u8 on_effect;
    gc_i8 selected_list_index;
    gc_i8 each_list_index;
    gc_i16 effect_rate;
    gc_i32 damage_change;
};

struct TurnHistory {
    gc_u8 ko;
    gc_u8 ko_team_rocket;
    gc_u8 ko_attack_damage;
    gc_u8 ko_attack_damage_ethan;
    gc_u8 ko_attack_damage_hop;
    gc_u8 turn_attack_card;
    gc_i8 take_prize_count_turn_player;
    gc_i32 turn_attack_id;
};

struct CardState {
    gc_i32 card_id;
    gc_i32 move_counter;
    gc_i32 attach_move_counter;
    gc_i32 skill_order;
    gc_i32 damage;

    gc_u32 this_turn[4];
    gc_u32 next_turn[4];
    gc_u32 this_turn_enemy[1];
    gc_u32 next_turn_enemy[1];

    gc_i32 take_attack_damage_this_turn;
    gc_i32 take_attack_damage_pre_turn;

    gc_i8 player_index;
    gc_u8 area;
    gc_u8 pre_area;
    gc_u8 reverse;

    gc_i16 cannot_use_attack_id_non_active;
    FixedListU8<gc_i16, 8> ability_used;

    gc_u16 next_enemy_turn_end_state_battle_field;
    gc_u32 next_enemy_turn_end_state;
    gc_u32 turn_state[3];
    gc_u64 continual_state[5];
};

struct PlayerState {
    FixedListU8<gc_u8, 1> active;
    FixedListU8<gc_u8, kBenchSizeMax> bench;
    FixedListU8<gc_u8, kCardListCapacity> prize;
    FixedListU8<gc_u8, kCardListCapacity> hand;
    FixedListU8<gc_u8, kCardListCapacity> deck;
    FixedListU8<gc_u8, kCardListCapacity> trash;
    FixedListU8<gc_u8, kCardListCapacity> energy;
    FixedListU8<gc_u8, kCardListCapacity> tool;
    FixedListU8<gc_u8, kCardListCapacity> pre_evolution;
    FixedListU8<gc_u8, kCardListCapacity> temporary;

    gc_i8 player_index;
    gc_u8 ko_prize_once_changed;
    gc_u32 this_turn;
    gc_u32 next_turn;
    gc_u32 active_state;
    gc_u32 reserved;
    gc_u64 continual_state;
    gc_u64 turn_state;
};

struct BattleCoreState {
    gc_i32 turn;
    gc_i32 turn_action_count;
    gc_i32 effect_action_count;
    gc_i32 turn_attack_count;

    gc_u8 phase;
    gc_u8 game_result;
    gc_u8 finish_reason;
    gc_u8 setup_done[2];
    gc_u8 mulligan[2];
    gc_i32 mulligan_count[2];
    gc_i8 first_player;
    gc_i8 looking_player;
    gc_u8 looking_reverse;
    gc_u8 is_break;
    gc_u8 effect_loop_stop;
    gc_u8 changed;
    gc_u8 state_changed;
    gc_u8 update_order;
    gc_u8 turn_state;
    gc_u8 continual_state;
    gc_u32 reserved;

    gc_i32 current_card_effect_index;
    gc_i32 coin_head_count;
    gc_i8 last_stadium_player;
    gc_u8 fail_retreat;

    gc_u8 select_type;
    gc_u8 select_context;
    gc_u8 context_card;
    gc_u8 select_deck;
    gc_i8 select_player;
    gc_i32 select_min;
    gc_i32 select_max;
    gc_i32 remain_damage_counter;
    gc_i32 energy_cost;
    gc_i32 remain_energy_cost;
    gc_i32 selected_energy_card_count;
    gc_i32 removed_damage_counter;
    gc_i32 select_counts[kSelectCountCapacity];
    gc_u8 selecting_energy_pokemon_ref;

    EffectState effect_state;
    TriggerInfo trigger_info;
    gc_u8 effect_jump;
    gc_u8 attach_active;

    gc_i32 current_attack_id;
    gc_i32 src_attack_id;
    gc_i32 attack_damage_change;
    gc_i32 last_attack_damage;
    gc_u8 attacker;
    gc_u8 post_attack_effect;
    gc_u8 post_effect_activate;
    gc_u8 fail_attack;
    gc_u8 second_attack;

    gc_i32 move_counter;
    gc_i32 current_skill_order;
    TurnHistory turn_histories[3];

    FixedListU8<gc_u8, 1> stadium;
    FixedListU8<gc_u8, kCardListCapacity> looking;
    FixedListU8<gc_u8, kCardListCapacity> selected_list;
    FixedListU8<gc_u8, kCardListCapacity> each_list;
    FixedListU8<gc_u8, 2> playing;
    FixedListU8<gc_u8, 9> check_list;
    PlayerState players[2];
    gc_i32 log_index[2];
    CardState all_card[kAllCardCapacity];
};

}  // namespace gpu_cabt
