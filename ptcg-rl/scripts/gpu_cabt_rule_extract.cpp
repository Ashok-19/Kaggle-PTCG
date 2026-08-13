// Runtime-only rule graph extractor for the local competition engine.
// This program writes transient binary tables to stdout; it contains no card rows.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "All.h"
#include "../src/ptcg_rl/gpu_cabt/native/state_core.h"
#include "../src/ptcg_rl/gpu_cabt/native/rule_static.h"

using namespace gpu_cabt;

static uint64_t hash8(const std::u8string& value) {
    uint64_t hash = 1469598103934665603ull;
    for (char8_t ch : value) {
        hash ^= static_cast<uint8_t>(ch);
        hash *= 1099511628211ull;
    }
    return hash;
}

static uint64_t card_flags(const CardMaster& card) {
    uint64_t flags = 0;
    if (card.tera) flags |= kCardFlagTera;
    if (card.trashMyTurnEnd) flags |= kCardFlagTrashMyTurnEnd;
    if (card.cannotToHandOrDeckInTrash) flags |= kCardFlagCannotToHandOrDeckInTrash;
    if (card.canPlayFirstTurn) flags |= kCardFlagCanPlayFirstTurn;
    if (card.transformOnly) flags |= kCardFlagTransformOnly;
    if (card.canTrash) flags |= kCardFlagCanTrash;
    if (card.toBench) flags |= kCardFlagToBench;
    if (card.toBattleFieldOnlySetup) flags |= kCardFlagToBattleFieldOnlySetup;
    if (card.toActiveOnlySetup) flags |= kCardFlagToActiveOnlySetup;
    if (card.noPrize) flags |= kCardFlagNoPrize;
    if (card.onlyTeamRocket) flags |= kCardFlagOnlyTeamRocket;
    if (card.ancient) flags |= kCardFlagAncient;
    if (card.future) flags |= kCardFlagFuture;
    if (card.hop) flags |= kCardFlagHop;
    if (card.lillie) flags |= kCardFlagLillie;
    if (card.iono) flags |= kCardFlagIono;
    if (card.n) flags |= kCardFlagN;
    if (card.ethan) flags |= kCardFlagEthan;
    if (card.cynthia) flags |= kCardFlagCynthia;
    if (card.misty) flags |= kCardFlagMisty;
    if (card.arven) flags |= kCardFlagArven;
    if (card.steven) flags |= kCardFlagSteven;
    if (card.marnie) flags |= kCardFlagMarnie;
    if (card.erika) flags |= kCardFlagErika;
    if (card.larry) flags |= kCardFlagLarry;
    if (card.teamRocket) flags |= kCardFlagTeamRocket;
    if (card.aceSpec) flags |= kCardFlagAceSpec;
    if (card.canUse) flags |= kCardFlagCanUse;
    return flags;
}

static uint32_t skill_flags(const Skill& skill) {
    uint32_t flags = 0;
    if (skill.mainAbility) flags |= kSkillFlagMainAbility;
    if (skill.onceTurn) flags |= kSkillFlagOnceTurn;
    if (skill.canSelectActivate) flags |= kSkillFlagCanSelectActivate;
    if (skill.notStack) flags |= kSkillFlagNotStack;
    if (skill.canActivateTrash) flags |= kSkillFlagCanActivateTrash;
    if (skill.attachBench) flags |= kSkillFlagAttachBench;
    if (skill.koMeAbility) flags |= kSkillFlagKoMeAbility;
    if (skill.luckyBonus) flags |= kSkillFlagLuckyBonus;
    return flags;
}

static uint32_t effect_flags(const Effect& effect) {
    uint32_t flags = 0;
    if (effect.isCondition) flags |= kEffectFlagIsCondition;
    if (effect.enemySelect) flags |= kEffectFlagEnemySelect;
    if (effect.randomSelect) flags |= kEffectFlagRandomSelect;
    if (effect.eachSelectedList) flags |= kEffectFlagEachSelectedList;
    if (effect.eachList) flags |= kEffectFlagEachList;
    if (effect.addCheckList) flags |= kEffectFlagAddCheckList;
    if (effect.notClearSelectedList) flags |= kEffectFlagNotClearSelectedList;
    if (effect.notPreTarget) flags |= kEffectFlagNotPreTarget;
    if (effect.notUpdateTarget) flags |= kEffectFlagNotUpdateTarget;
    if (effect.multiplyEffectValuePreTargetCount) flags |= kEffectFlagMultiplyPreTargetCount;
    if (effect.multiplyEffectValueCoinHeadCount) flags |= kEffectFlagMultiplyCoinHeadCount;
    if (effect.canNoSelect) flags |= kEffectFlagCanNoSelect;
    if (effect.canNoSelectIfExistPreTarget) flags |= kEffectFlagCanNoSelectIfExistPreTarget;
    if (effect.cannotNoSelect) flags |= kEffectFlagCannotNoSelect;
    if (effect.energyMaxSelect) flags |= kEffectFlagEnergyMaxSelect;
    if (effect.selectTargetCount) flags |= kEffectFlagSelectTargetCount;
    if (effect.selectCoinHeadCount) flags |= kEffectFlagSelectCoinHeadCount;
    if (effect.selectCoinHeadCount2) flags |= kEffectFlagSelectCoinHeadCount2;
    if (effect.selectEnemyEnergyCount) flags |= kEffectFlagSelectEnemyEnergyCount;
    if (effect.skipNoTarget) flags |= kEffectFlagSkipNoTarget;
    if (effect.open) flags |= kEffectFlagOpen;
    if (effect.setTargetSwitchBench) flags |= kEffectFlagSetTargetSwitchBench;
    if (effect.effectTargetActive) flags |= kEffectFlagEffectTargetActive;
    if (effect.effectTargetBench) flags |= kEffectFlagEffectTargetBench;
    if (effect.removeEffectedIfNoEffect) flags |= kEffectFlagRemoveEffectedIfNoEffect;
    if (effect.seeingDeck) flags |= kEffectFlagSeeingDeck;
    if (effect.separator) flags |= kEffectFlagSeparator;
    return flags;
}

static RuleTarget flatten_target(
    const Target& target,
    const std::map<std::u8string, int>& substring_ids
) {
    RuleTarget result{};
    result.target_player = static_cast<uint8_t>(target.targetPlayer);
    result.flags = static_cast<uint8_t>((target.notMe ? 1 : 0) | (target.skipEnemyTarget ? 2 : 0));
    result.area_count = static_cast<uint8_t>(target.areas.size());
    for (int index = 0; index < target.areas.size(); ++index) {
        result.areas[index] = static_cast<uint8_t>(target.areas[index]);
    }
    result.condition_count = static_cast<uint8_t>(target.conditions.size());
    for (int index = 0; index < static_cast<int>(target.conditions.size()); ++index) {
        const TargetCondition& source = target.conditions[index];
        RuleTargetCondition& dest = result.conditions[index];
        dest.target_type = static_cast<uint8_t>(source.targetType);
        dest.comparator_type = static_cast<uint8_t>(source.comparatorType);
        dest.value = source.val;
        dest.value2 = source.val2;
        dest.name_hash = hash8(source.name);
        dest.substring_mask_index = -1;
        if (source.targetType == TargetType::NameContains) {
            auto found = substring_ids.find(source.name);
            if (found != substring_ids.end()) dest.substring_mask_index = found->second;
        }
    }
    return result;
}

static RuleEffect flatten_effect(
    const Effect& effect,
    int parent_skill_id,
    int parent_attack_id,
    const std::map<std::u8string, int>& substring_ids
) {
    RuleEffect result{};
    result.flags = effect_flags(effect);
    result.effect_type = static_cast<uint8_t>(effect.effectType);
    result.effect_select_type = static_cast<uint8_t>(effect.effectSelectType);
    result.select_count = effect.selectCount;
    result.select_context = static_cast<uint8_t>(effect.selectContext);
    result.loop_count = effect.loopCount;
    result.fail_skip = effect.failSkip;
    result.priority = effect.priority;
    result.values[0] = effect.values[0];
    result.values[1] = effect.values[1];
    result.condition_type = static_cast<uint8_t>(effect.conditionType);
    result.comparator_type = static_cast<uint8_t>(effect.comparatorType);
    result.skill_id = effect.skillId;
    result.parent_skill_id = parent_skill_id;
    result.parent_attack_id = parent_attack_id;
    result.target = flatten_target(effect.target, substring_ids);
    return result;
}

int main() {
    InitializeAll();

    std::map<std::u8string, int> substring_ids;
    auto collect_target = [&](const Target& target) {
        for (const TargetCondition& condition : target.conditions) {
            if (condition.targetType == TargetType::NameContains) {
                substring_ids.emplace(condition.name, 0);
            }
        }
    };
    for (const auto& [id, skill] : SkillTable) {
        for (const Effect& effect : skill.effects) collect_target(effect.target);
        for (const Trigger& trigger : skill.triggers) collect_target(trigger.subject);
    }
    for (const auto& [id, attack] : AttackTable) {
        for (const Effect& effect : attack.preEffects) collect_target(effect.target);
        for (const Effect& effect : attack.postEffects) collect_target(effect.target);
    }
    int next_substring = 0;
    for (auto& [text, index] : substring_ids) index = next_substring++;

    std::vector<RuleCardMaster> cards(1268);
    std::vector<RuleSkill> skills(435);
    std::vector<RuleAttack> attacks(1557);
    std::vector<RuleEffect> effects;
    std::vector<RuleTrigger> triggers;
    effects.reserve(3067);
    triggers.reserve(77);

    for (const auto& [id, skill] : SkillTable) {
        RuleSkill row{};
        row.skill_id = id;
        row.card_id = skill.cardId;
        row.skill_type = static_cast<uint8_t>(skill.skillType);
        row.priority = skill.priority;
        row.first_condition_count = skill.firstConditionCount;
        row.second_effect_start_index = skill.secondEffectStartIndex;
        row.second_effect_start_index_enemy = skill.secondEffectStartIndexEnemy;
        row.trigger_start_index = skill.triggerStartIndex;
        row.area_count = static_cast<uint8_t>(skill.areas.size());
        for (int index = 0; index < skill.areas.size(); ++index) {
            row.areas[index] = static_cast<uint8_t>(skill.areas[index]);
        }
        row.flags = skill_flags(skill);
        row.trigger_offset = static_cast<int>(triggers.size());
        row.trigger_count = static_cast<int16_t>(skill.triggers.size());
        for (const Trigger& trigger : skill.triggers) {
            RuleTrigger trigger_row{};
            trigger_row.trigger_type = static_cast<uint8_t>(trigger.triggerType);
            trigger_row.subject = flatten_target(trigger.subject, substring_ids);
            triggers.push_back(trigger_row);
        }
        row.effect_offset = static_cast<int>(effects.size());
        row.effect_count = static_cast<int16_t>(skill.effects.size());
        for (const Effect& effect : skill.effects) {
            effects.push_back(flatten_effect(effect, id, -1, substring_ids));
        }
        row.name_hash = hash8(skill.name);
        skills[id] = row;
    }

    for (const auto& [id, attack] : AttackTable) {
        RuleAttack row{};
        row.attack_id = id;
        row.card_id = attack.cardId;
        row.damage = attack.damage;
        row.flags = attack.attackFlags;
        row.energy_count = static_cast<uint8_t>(attack.energies.size());
        for (int index = 0; index < attack.energies.size(); ++index) {
            row.energies[index] = static_cast<uint8_t>(attack.energies[index]);
        }
        row.pre_effect_offset = static_cast<int>(effects.size());
        row.pre_effect_count = static_cast<int16_t>(attack.preEffects.size());
        for (const Effect& effect : attack.preEffects) {
            effects.push_back(flatten_effect(effect, -1, id, substring_ids));
        }
        row.post_effect_offset = static_cast<int>(effects.size());
        row.post_effect_count = static_cast<int16_t>(attack.postEffects.size());
        for (const Effect& effect : attack.postEffects) {
            effects.push_back(flatten_effect(effect, -1, id, substring_ids));
        }
        row.last_cancel_fail_attack = attack.lastCancelFailAttack ? 1 : 0;
        row.name_hash = hash8(attack.name);
        attacks[id] = row;
    }

    for (const auto& [id, card] : CardTable) {
        RuleCardMaster row{};
        row.card_id = id;
        row.card_type = static_cast<uint8_t>(card.cardType);
        row.pokemon_type = static_cast<uint8_t>(card.pokemonType);
        row.evolution_type = static_cast<uint8_t>(card.evolutionType);
        row.retreat_cost = card.retreatCost;
        row.hp = card.hp;
        row.weakness = static_cast<uint8_t>(card.weakness);
        row.resistance = static_cast<uint8_t>(card.resistance);
        row.energy_type = static_cast<uint8_t>(card.energyType);
        row.energy_count = card.energyCount;
        row.flags = card_flags(card);
        row.ability_skill_id = card.ability ? static_cast<int16_t>(card.ability->skillId) : -1;
        row.play_skill_id = card.play ? static_cast<int16_t>(card.play->skillId) : -1;
        row.delay_skill_id = card.delay ? static_cast<int16_t>(card.delay->skillId) : -1;
        row.attack_ids[0] = -1;
        row.attack_ids[1] = -1;
        for (int index = 0; index < static_cast<int>(card.attacks.size()); ++index) {
            row.attack_ids[index] = static_cast<int16_t>(card.attacks[index]->attackId);
        }
        row.name_hash = hash8(card.name);
        row.evolves_from_hash = hash8(card.evolvesFrom);
        row.evolves_from2_hash = hash8(card.evolvesFrom2);
        cards[id] = row;
    }

    const int substring_words = (static_cast<int>(cards.size()) + 31) / 32;
    std::vector<uint32_t> substring_masks(substring_ids.size() * substring_words, 0);
    for (const auto& [needle, mask_index] : substring_ids) {
        for (const auto& [card_id, card] : CardTable) {
            if (card.name.find(needle) != std::u8string::npos) {
                substring_masks[mask_index * substring_words + card_id / 32] |=
                    1u << (card_id % 32);
            }
        }
    }

    const char magic[8] = {'G', 'C', 'R', 'U', 'L', 'E', '0', '1'};
    std::cout.write(magic, sizeof(magic));
    const uint32_t header[12] = {
        static_cast<uint32_t>(cards.size()),
        static_cast<uint32_t>(skills.size()),
        static_cast<uint32_t>(attacks.size()),
        static_cast<uint32_t>(effects.size()),
        static_cast<uint32_t>(triggers.size()),
        static_cast<uint32_t>(substring_ids.size()),
        static_cast<uint32_t>(substring_words),
        static_cast<uint32_t>(sizeof(RuleCardMaster)),
        static_cast<uint32_t>(sizeof(RuleSkill)),
        static_cast<uint32_t>(sizeof(RuleAttack)),
        static_cast<uint32_t>(sizeof(RuleEffect)),
        static_cast<uint32_t>(sizeof(RuleTrigger)),
    };
    std::cout.write(reinterpret_cast<const char*>(header), sizeof(header));
    std::cout.write(reinterpret_cast<const char*>(cards.data()), cards.size() * sizeof(cards[0]));
    std::cout.write(reinterpret_cast<const char*>(skills.data()), skills.size() * sizeof(skills[0]));
    std::cout.write(reinterpret_cast<const char*>(attacks.data()), attacks.size() * sizeof(attacks[0]));
    std::cout.write(reinterpret_cast<const char*>(effects.data()), effects.size() * sizeof(effects[0]));
    std::cout.write(reinterpret_cast<const char*>(triggers.data()), triggers.size() * sizeof(triggers[0]));
    std::cout.write(
        reinterpret_cast<const char*>(substring_masks.data()),
        substring_masks.size() * sizeof(substring_masks[0])
    );
    return 0;
}
