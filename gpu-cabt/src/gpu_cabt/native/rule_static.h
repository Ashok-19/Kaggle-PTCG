#pragma once

// Pointer-free flattened CABT rule graph.  The official card/rule rows are
// extracted at runtime from the local competition engine and are never stored
// in the repository.  This header defines only our GPU transport schema.

namespace gpu_cabt {

static constexpr int kRuleTargetAreaCapacity = 4;
static constexpr int kRuleTargetConditionCapacity = 3;
static constexpr int kRuleSkillAreaCapacity = 2;
static constexpr int kRuleAttackEnergyCapacity = 7;
static constexpr int kRuleCardAttackCapacity = 2;

static constexpr gc_u64 kCardFlagTera = 1ull << 0;
static constexpr gc_u64 kCardFlagTrashMyTurnEnd = 1ull << 1;
static constexpr gc_u64 kCardFlagCannotToHandOrDeckInTrash = 1ull << 2;
static constexpr gc_u64 kCardFlagCanPlayFirstTurn = 1ull << 3;
static constexpr gc_u64 kCardFlagTransformOnly = 1ull << 4;
static constexpr gc_u64 kCardFlagCanTrash = 1ull << 5;
static constexpr gc_u64 kCardFlagToBench = 1ull << 6;
static constexpr gc_u64 kCardFlagToBattleFieldOnlySetup = 1ull << 7;
static constexpr gc_u64 kCardFlagToActiveOnlySetup = 1ull << 8;
static constexpr gc_u64 kCardFlagNoPrize = 1ull << 9;
static constexpr gc_u64 kCardFlagOnlyTeamRocket = 1ull << 10;
static constexpr gc_u64 kCardFlagAncient = 1ull << 11;
static constexpr gc_u64 kCardFlagFuture = 1ull << 12;
static constexpr gc_u64 kCardFlagHop = 1ull << 13;
static constexpr gc_u64 kCardFlagLillie = 1ull << 14;
static constexpr gc_u64 kCardFlagIono = 1ull << 15;
static constexpr gc_u64 kCardFlagN = 1ull << 16;
static constexpr gc_u64 kCardFlagEthan = 1ull << 17;
static constexpr gc_u64 kCardFlagCynthia = 1ull << 18;
static constexpr gc_u64 kCardFlagMisty = 1ull << 19;
static constexpr gc_u64 kCardFlagArven = 1ull << 20;
static constexpr gc_u64 kCardFlagSteven = 1ull << 21;
static constexpr gc_u64 kCardFlagMarnie = 1ull << 22;
static constexpr gc_u64 kCardFlagErika = 1ull << 23;
static constexpr gc_u64 kCardFlagLarry = 1ull << 24;
static constexpr gc_u64 kCardFlagTeamRocket = 1ull << 25;
static constexpr gc_u64 kCardFlagAceSpec = 1ull << 26;
static constexpr gc_u64 kCardFlagCanUse = 1ull << 27;
static constexpr gc_u64 kCardFlagSilcoonOrCascoon = 1ull << 28;
static constexpr gc_u64 kCardFlagKoffingOrWeezing = 1ull << 29;
static constexpr gc_u64 kCardFlagHonedgeOrDoubladeOrAegislash = 1ull << 30;

static constexpr gc_u32 kSkillFlagMainAbility = 1u << 0;
static constexpr gc_u32 kSkillFlagOnceTurn = 1u << 1;
static constexpr gc_u32 kSkillFlagCanSelectActivate = 1u << 2;
static constexpr gc_u32 kSkillFlagNotStack = 1u << 3;
static constexpr gc_u32 kSkillFlagCanActivateTrash = 1u << 4;
static constexpr gc_u32 kSkillFlagAttachBench = 1u << 5;
static constexpr gc_u32 kSkillFlagKoMeAbility = 1u << 6;
static constexpr gc_u32 kSkillFlagLuckyBonus = 1u << 7;

static constexpr gc_u32 kEffectFlagIsCondition = 1u << 0;
static constexpr gc_u32 kEffectFlagEnemySelect = 1u << 1;
static constexpr gc_u32 kEffectFlagRandomSelect = 1u << 2;
static constexpr gc_u32 kEffectFlagEachSelectedList = 1u << 3;
static constexpr gc_u32 kEffectFlagEachList = 1u << 4;
static constexpr gc_u32 kEffectFlagAddCheckList = 1u << 5;
static constexpr gc_u32 kEffectFlagNotClearSelectedList = 1u << 6;
static constexpr gc_u32 kEffectFlagNotPreTarget = 1u << 7;
static constexpr gc_u32 kEffectFlagNotUpdateTarget = 1u << 8;
static constexpr gc_u32 kEffectFlagMultiplyPreTargetCount = 1u << 9;
static constexpr gc_u32 kEffectFlagMultiplyCoinHeadCount = 1u << 10;
static constexpr gc_u32 kEffectFlagCanNoSelect = 1u << 11;
static constexpr gc_u32 kEffectFlagCanNoSelectIfExistPreTarget = 1u << 12;
static constexpr gc_u32 kEffectFlagCannotNoSelect = 1u << 13;
static constexpr gc_u32 kEffectFlagEnergyMaxSelect = 1u << 14;
static constexpr gc_u32 kEffectFlagSelectTargetCount = 1u << 15;
static constexpr gc_u32 kEffectFlagSelectCoinHeadCount = 1u << 16;
static constexpr gc_u32 kEffectFlagSelectCoinHeadCount2 = 1u << 17;
static constexpr gc_u32 kEffectFlagSelectEnemyEnergyCount = 1u << 18;
static constexpr gc_u32 kEffectFlagSkipNoTarget = 1u << 19;
static constexpr gc_u32 kEffectFlagOpen = 1u << 20;
static constexpr gc_u32 kEffectFlagSetTargetSwitchBench = 1u << 21;
static constexpr gc_u32 kEffectFlagEffectTargetActive = 1u << 22;
static constexpr gc_u32 kEffectFlagEffectTargetBench = 1u << 23;
static constexpr gc_u32 kEffectFlagRemoveEffectedIfNoEffect = 1u << 24;
static constexpr gc_u32 kEffectFlagSeeingDeck = 1u << 25;
static constexpr gc_u32 kEffectFlagSeparator = 1u << 26;

struct RuleTargetCondition {
    gc_u8 target_type;
    gc_u8 comparator_type;
    gc_i16 reserved;
    gc_i32 value;
    gc_i32 value2;
    gc_u64 name_hash;
    gc_i32 substring_mask_index;
    gc_i32 reserved2;
};

struct RuleTarget {
    gc_u8 target_player;
    gc_u8 flags;  // bit0=not_me, bit1=skip_enemy_target
    gc_u8 area_count;
    gc_u8 condition_count;
    gc_u8 areas[kRuleTargetAreaCapacity];
    RuleTargetCondition conditions[kRuleTargetConditionCapacity];
};

struct RuleEffect {
    gc_u32 flags;
    gc_u8 effect_type;
    gc_u8 effect_select_type;
    gc_i8 select_count;
    gc_u8 select_context;
    gc_i8 loop_count;
    gc_i8 fail_skip;
    gc_i16 priority;
    gc_i32 values[2];
    gc_u8 condition_type;
    gc_u8 comparator_type;
    gc_u16 reserved;
    gc_i32 skill_id;
    gc_i32 parent_skill_id;
    gc_i32 parent_attack_id;
    RuleTarget target;
};

struct RuleTrigger {
    gc_u8 trigger_type;
    gc_u8 reserved[3];
    RuleTarget subject;
};

struct RuleSkill {
    gc_i32 skill_id;
    gc_i32 card_id;
    gc_u8 skill_type;
    gc_i8 priority;
    gc_i8 first_condition_count;
    gc_i8 second_effect_start_index;
    gc_i8 second_effect_start_index_enemy;
    gc_i8 trigger_start_index;
    gc_u8 area_count;
    gc_u8 areas[kRuleSkillAreaCapacity];
    gc_u8 reserved0;
    gc_u32 flags;
    gc_i32 trigger_offset;
    gc_i16 trigger_count;
    gc_i16 reserved1;
    gc_i32 effect_offset;
    gc_i16 effect_count;
    gc_i16 reserved2;
    gc_u64 name_hash;
};

struct RuleAttack {
    gc_i32 attack_id;
    gc_i32 card_id;
    gc_i32 damage;
    gc_u32 flags;
    gc_u8 energy_count;
    gc_u16 energies[kRuleAttackEnergyCapacity];
    gc_i32 pre_effect_offset;
    gc_i16 pre_effect_count;
    gc_i16 reserved0;
    gc_i32 post_effect_offset;
    gc_i16 post_effect_count;
    gc_u8 last_cancel_fail_attack;
    gc_u8 reserved1;
    gc_u64 name_hash;
};

struct RuleCardMaster {
    gc_i32 card_id;
    gc_u8 card_type;
    gc_u8 pokemon_type;
    gc_u8 evolution_type;
    gc_i8 retreat_cost;
    gc_i32 hp;
    gc_u16 weakness;
    gc_u16 resistance;
    gc_u16 energy_type;
    gc_i8 energy_count;
    gc_u64 flags;
    gc_i16 ability_skill_id;
    gc_i16 play_skill_id;
    gc_i16 delay_skill_id;
    gc_i16 attack_ids[kRuleCardAttackCapacity];
    gc_u64 name_hash;
    gc_u64 evolves_from_hash;
    gc_u64 evolves_from2_hash;
};

struct RuleTableView {
    const RuleCardMaster* cards;
    const RuleSkill* skills;
    const RuleAttack* attacks;
    const RuleEffect* effects;
    const RuleTrigger* triggers;
    const gc_u32* substring_masks;
    gc_i32 card_count;
    gc_i32 skill_count;
    gc_i32 attack_count;
    gc_i32 effect_count;
    gc_i32 trigger_count;
    gc_i32 substring_mask_count;
    gc_i32 substring_mask_words;
};

}  // namespace gpu_cabt

static_assert(sizeof(gpu_cabt::RuleCardMaster) == 72, "RuleCardMaster ABI");
static_assert(sizeof(gpu_cabt::RuleSkill) == 48, "RuleSkill ABI");
static_assert(sizeof(gpu_cabt::RuleAttack) == 56, "RuleAttack ABI");
static_assert(sizeof(gpu_cabt::RuleEffect) == 144, "RuleEffect ABI");
static_assert(sizeof(gpu_cabt::RuleTrigger) == 112, "RuleTrigger ABI");
