#include <cstdint>
#include <iostream>
#include "All.h"

static void emit(uint64_t value) { std::cout.write(reinterpret_cast<const char*>(&value), 8); }

int main() {
    CardNextTurnState next{};
    next.cannotUseAttackId = 0x1234;
    next.cannotUseAttackId2 = 0x2345;
    next.damageChange = -333;
    next.damageChangeActive = 444;
    next.damageChangeMyAttack = -555;
    next.attackCostChange = -7;
    next.retreatCostChange = 9;
    next.cannotRetreat = true;
    next.cannotHandAttachEnergy = false;
    next.cannotAttack = true;
    next.cannotAttackLessEqualEnergy2 = true;
    next.attackCoin = false;
    next.attackCoin2 = true;
    for (uint32_t value : next.value) emit(value);

    CardNextMyTurnEnemyState enemy{};
    enemy.takeDamageChange = -771;
    emit(enemy.value[0]);

    Card card{};
    card.damageChangeThisTurn = -101;
    card.damageChangeExThisTurn = 202;
    card.koCauseRef = 77;
    card.koPrizeChangeAlways = -3;
    card.koPrizeChange = 4;
    card.appear = true;
    card.evolved = false;
    card.benchToActive = true;
    card.ko = true;
    card.koAttackDamage = false;
    card.koEnemyAttackDamage = true;
    card.koEnemyAttackDamageActive = false;
    card.koEnemyExAttackDamage = true;
    card.koEnemyTerastalAttackDamage = true;
    card.koEnemyNAttackDamage = false;
    card.koFull = true;
    card.koPrizePlus1 = false;
    card.koPrizeDecreaseOnce = true;
    card.koPrizeZero = true;
    card.koNoDamageAndEffectAttackNextEnemyTurn = true;
    for (uint32_t value : card.turnState) emit(value);

    Card c{};
    c.hpChange = 11;
    c.damageChange = -12;
    c.damageChangeActive = 13;
    c.damageChangeEx = -14;
    c.damageChangeAbility = 15;
    c.damageChangeEvolved = -16;
    c.damageChangeEnemyTakenPrize = 17;
    c.takeDamageChange = -18;
    c.takeEnemyAttackDamageChange = 19;
    c.takeEnemyAbilityPokemonAttackDamageChange = -20;
    c.takeEnemyFireOrWaterPokemonAttackDamageChange = 21;
    c.takeEnemy4TypePokemonAttackDamageChange = -22;
    c.noDamageGreaterEqual = 230;
    c.retreatCostChange = -4;
    c.attackCostChangeColorless = 5;
    c.attackCostDown = -6;
    c.attackCostDownColorlessOwnAttack = 7;
    c.typeIndex = 8;
    c.weaknessIndex = 9;
    c.noAbility = true;
    c.noKoMeAbility = false;
    c.noDamageEnemyAbilityPokemonAttack = true;
    c.noDamageEnemyExAttack = false;
    c.noDamageEnemyBasicExAttack = true;
    c.noDamageAndEffectEnemyTerastalAttack = false;
    c.noDamageAndEffectEnemySpecialEnergyAttack = true;
    c.noDamageEnemyAttack = true;
    c.noEffectEnemyAttack = false;
    c.noEffectEnemyItem = true;
    c.noEffectEnemySupporter = false;
    c.noDamageCounterEnemyAttackAbility = true;
    c.noEnemyAbility = true;
    c.noSpecialCondition = false;
    c.noSleepParalyzeConfuse = true;
    c.noSleep = false;
    c.noRetreatCost = true;
    c.noPrizeEx = false;
    c.notRecoverConfuseEvolve = true;
    c.canUsePreEvolutionAttack = true;
    c.canEvolveAppearTurn = false;
    c.canEvolveGrassAppearTurn = true;
    c.canAttackFirst = false;
    c.cannotRetreat = true;
    c.cannotAttack = true;
    c.cannotToHand = false;
    c.cannotMoveDamageCounter = true;
    c.attackEnergyColoressOne = false;
    c.attackEnergyPsychicOne = true;
    c.doubleGrassEnergy = true;
    c.noDamageCoin = false;
    c.koByDamageToHand = true;
    c.basicPrizePlus1 = false;
    c.doubleAttack = true;
    c.tool2 = false;
    c.tool4 = true;
    c.technicalMachine = true;
    c.specialFlagTool = false;
    c.rainbowDna = true;
    c.canPlay = true;
    for (uint64_t value : c.continualState) emit(value);

    PlayerNextTurnState pn{};
    pn.metalDamageChange = -321;
    pn.cannotAttackLessEqualEnergy2 = true;
    pn.cannotPlayItem = false;
    pn.cannotPlaySupporter = true;
    pn.cannotPlayStadium = true;
    pn.cannotPlaySpecialEnergy = false;
    pn.cannotEvolve = true;
    pn.cannotRetreatPoison = false;
    emit(pn.value);

    PlayerState player{};
    player.poisonDamageCounter = 12;
    player.badStatus = BadStatusType::Confused;
    player.burned = true;
    emit(player.activeState);

    PlayerState pc{};
    pc.poisonDamageChange = -111;
    pc.burnDamageChange = 222;
    pc.poisonDamageChangeNotDarkness = -7;
    pc.benchCapacity = 8;
    pc.cannotPlayItem = true;
    pc.cannotPlayStadium = false;
    pc.cannotPlayTool = true;
    pc.cannotPlayAceSpec = true;
    pc.cannotPlayAbilityPokemonNotRocket = false;
    pc.cannotTrashToHandAbilityOrTrainers = true;
    emit(pc.continualState);

    PlayerState pt{};
    pt.playerDamageChange = -100;
    pt.playerDamageChangeEx = 200;
    pt.playerDamageChangeMyFighting = -300;
    pt.takePrizeCountChangeTerastalAttackKoActive = 5;
    pt.takePrizeCountChangeNAttackKoActive = -6;
    emit(pt.turnState);

    State s{};
    s.supporterPlayed = true;
    s.stadiumPlayed = false;
    s.energyPlayed = true;
    s.retreated = true;
    s.turnEnd = false;
    emit(s.turnState);

    State sc{};
    sc.noToolEffect = true;
    emit(sc.continualState);
    return 0;
}
