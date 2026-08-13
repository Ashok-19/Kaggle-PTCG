#pragma once

// Fixed-capacity runtime buffers kept separate from the stable battle core.
// The native engine's dynamic vectors are bounded here by physical-card or
// continuation limits. Every overflow fails closed through error_flags.

namespace gpu_cabt {

static constexpr int kOptionCapacity = 128;
static constexpr int kSelectedCapacity = 128;
static constexpr int kContinuationCapacity = 256;
static constexpr int kAreaRefCapacity = 128;
static constexpr int kTriggerCapacity = 128;
static constexpr int kTurnSkillCapacity = 128;
static constexpr int kTurnCardCapacity = 128;
static constexpr int kTurnEvolveCapacity = 64;
static constexpr int kCardEffectCapacity = 128;
static constexpr int kAbilitySetWordCount = 14;  // 448 skill ids / 32.

static constexpr gc_u32 kRuntimeErrorOptionOverflow = 1u << 0;
static constexpr gc_u32 kRuntimeErrorSelectedOverflow = 1u << 1;
static constexpr gc_u32 kRuntimeErrorContinuationOverflow = 1u << 2;
static constexpr gc_u32 kRuntimeErrorZoneOverflow = 1u << 3;
static constexpr gc_u32 kRuntimeErrorUnsupportedTransition = 1u << 4;
static constexpr gc_u32 kRuntimeErrorInvalidSelection = 1u << 5;
static constexpr gc_u32 kRuntimeErrorNoBasicPokemon = 1u << 6;
static constexpr gc_u32 kRuntimeErrorMulliganLoopLimit = 1u << 7;
static constexpr gc_u32 kRuntimeErrorTargetOverflow = 1u << 8;
static constexpr gc_u32 kRuntimeErrorPreTargetOverflow = 1u << 9;
static constexpr gc_u32 kRuntimeErrorKoOverflow = 1u << 10;
static constexpr gc_u32 kRuntimeErrorTriggerOverflow = 1u << 11;
static constexpr gc_u32 kRuntimeErrorTurnHistoryOverflow = 1u << 12;
static constexpr gc_u32 kRuntimeErrorCardEffectOverflow = 1u << 13;
static constexpr gc_u32 kRuntimeErrorRefreshDepth = 1u << 14;
static constexpr gc_u32 kRuntimeErrorInterpreterLimit = 1u << 15;

static constexpr gc_u16 kContinuationNone = 0;
static constexpr gc_u16 kContinuationSelectedIsFirst = 1;
static constexpr gc_u16 kContinuationAfterOpeningDraw = 2;
static constexpr gc_u16 kContinuationSelectedMulligan = 3;
static constexpr gc_u16 kContinuationSelectedSetupActivePokemon = 4;
static constexpr gc_u16 kContinuationAfterResetupActivePokemon = 5;
static constexpr gc_u16 kContinuationSetupActivePokemon = 6;
static constexpr gc_u16 kContinuationSelectedSetupBenchPokemon = 7;

static constexpr gc_u16 kPendingNone = 0;
static constexpr gc_u16 kPendingPrizeLuckyBonus = 1;
static constexpr gc_u16 kPendingPrizeLuckyBonusCoin = 2;
static constexpr gc_u16 kPendingSwitchPokemon = 3;
static constexpr gc_u16 kPendingDevolveAny = 4;
static constexpr gc_u16 kPendingSwapHp = 5;
static constexpr gc_u16 kPendingCoin = 6;
static constexpr gc_u16 kPendingDisableAttack = 7;
static constexpr gc_u16 kPendingSelectActivate = 8;
static constexpr gc_u16 kPendingSelectEffect = 9;
static constexpr gc_u16 kPendingSpecialCondition = 10;
static constexpr gc_u16 kPendingEnergyMove = 11;
static constexpr gc_u16 kPendingEnergySwitch = 12;
static constexpr gc_u16 kPendingSelectPile = 13;
static constexpr gc_u16 kPendingCustom = 14;
static constexpr gc_u16 kPendingDamageCounterAny = 15;
static constexpr gc_u16 kPendingDamageCounterSwitchAny = 16;
static constexpr gc_u16 kPendingRemoveDamageCounter = 17;
static constexpr gc_u16 kPendingAttackDamageTargets = 18;
static constexpr gc_u16 kPendingAttackDamageMulti = 19;
static constexpr gc_u16 kPendingAttackDamageCoinTargets = 20;
static constexpr gc_u16 kPendingRecoverSpecialCondition = 21;
static constexpr gc_u16 kPendingMoreDevolve = 22;
static constexpr gc_u16 kPendingEffectSelection = 23;
static constexpr gc_u16 kPendingAttackDamagePutCounter = 24;
static constexpr gc_u16 kPendingTriggerOrder = 25;

struct SelectOptionState {
    gc_u8 type;
    gc_u8 reserved;
    gc_i16 param0;
    gc_i16 param1;
    gc_i16 param2;
    gc_i16 param3;
    gc_i16 param4;
};

struct ContinuationState {
    gc_u16 opcode;
    gc_u8 arg_type;
    gc_u8 call_count;
    gc_u8 called_count;
    gc_u8 reserved0;
    gc_u16 reserved1;
    gc_i32 arg0;
    gc_i32 arg1;
    gc_i32 arg2;
};

struct AreaRefState {
    gc_u8 card;
    gc_u8 reserved0;
    gc_u16 reserved1;
    gc_i32 move_counter;
};

struct TriggeredAbilityState {
    ActivateAbilityInfo activate;
    TriggerInfo trigger;
};

struct EvolveState {
    gc_u8 pre_ref;
    gc_u8 ref;
    gc_u16 reserved;
};

struct CardEffectOrderState {
    gc_u8 ref;
    gc_i8 priority;
    gc_u16 reserved;
    gc_i32 skill_order;
    gc_i32 move_counter;
};

struct BattleRuntimeState {
    gc_u32 error_flags;
    gc_u16 option_count;
    gc_u16 selected_count;
    gc_u16 continuation_count;
    gc_u16 target_count;
    gc_u16 pre_target_count;
    gc_u16 ko_count;
    gc_u16 delay_trigger_count;
    gc_u16 temporary_trigger_count;
    gc_u16 trigger_count;
    gc_u16 turn_used_skill_count;
    gc_u16 turn_play_count;
    gc_u16 turn_heal_count;
    gc_u16 turn_evolve_count;
    gc_u16 card_effect_count;
    gc_u16 scratch_target_count;
    gc_i16 effect_cursor;
    gc_i16 effect_repeat_index;
    gc_i16 effect_repeat_count;
    gc_u8 effect_repeat_mode;
    gc_u8 effect_execution_active;
    gc_u8 effect_instance_waiting;
    gc_u8 trigger_resolution_active;
    gc_i8 trigger_resolution_depth;
    gc_u8 trigger_activation_waiting;
    gc_u16 pending_effect_kind;
    gc_u16 pending_effect_substep;
    gc_i32 pending_effect_arg0;
    gc_i32 pending_effect_arg1;
    gc_i32 pending_effect_arg2;
    gc_i32 pending_effect_arg3;
    gc_u64 rng_seed;
    gc_u64 rng_stream;
    gc_u64 rng_draw_index;

    SelectOptionState options[kOptionCapacity];
    gc_i32 selected[kSelectedCapacity];
    ContinuationState continuations[kContinuationCapacity];
    AreaRefState targets[kAreaRefCapacity];
    AreaRefState pre_targets[kAreaRefCapacity];
    AreaRefState ko_list[kAreaRefCapacity];
    AreaRefState scratch_targets[kAreaRefCapacity];
    TriggeredAbilityState delay_triggers[kTriggerCapacity];
    TriggeredAbilityState temporary_triggers[kTriggerCapacity];
    TriggeredAbilityState triggers[kTriggerCapacity];
    gc_i16 turn_used_skills[kTurnSkillCapacity];
    gc_u8 turn_play[kTurnCardCapacity];
    gc_u8 turn_heal[kTurnCardCapacity];
    EvolveState turn_evolve[kTurnEvolveCapacity];
    gc_u32 ability_set[2][kAbilitySetWordCount];
    CardEffectOrderState card_effects[kCardEffectCapacity];
};

static_assert(sizeof(SelectOptionState) == 12, "SelectOptionState ABI");
static_assert(sizeof(ContinuationState) == 20, "ContinuationState ABI");
static_assert(sizeof(AreaRefState) == 8, "AreaRefState ABI");
static_assert(sizeof(EvolveState) == 4, "EvolveState ABI");
static_assert(sizeof(CardEffectOrderState) == 12, "CardEffectOrderState ABI");
static_assert(sizeof(BattleRuntimeState) <= 32 * 1024, "runtime buffer must stay compact");

}  // namespace gpu_cabt
