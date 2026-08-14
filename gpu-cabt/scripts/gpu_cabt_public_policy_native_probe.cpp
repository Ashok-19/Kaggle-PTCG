#include <iostream>
#include "All.h"
#include "ToJson.h"

static void clear_zones(State& state) {
    state.stadium.clear();
    state.looking.clear();
    for (int p = 0; p < 2; ++p) {
        auto& ps = state.players[p];
        ps.active.clear(); ps.bench.clear(); ps.prize.clear(); ps.hand.clear();
        ps.deck.clear(); ps.trash.clear(); ps.energy.clear(); ps.tool.clear();
        ps.preEvolution.clear(); ps.temporary.clear();
    }
}

static void place(State& state, int ref, AreaType area, bool reverse = false) {
    auto& card = state.getCard(CardRef(ref));
    card.preArea = card.area;
    card.area = area;
    card.reverse = reverse;
}

static void push(State& state, int player, AreaType area, int ref, bool reverse = false) {
    place(state, ref, area, reverse);
    state.pushCardRef(area, player, CardRef(ref));
}

static void build_fixture(State& state, int actor, int mode) {
    clear_zones(state);
    state.options.clear(); state.selected.clear(); state.logs.clear(); state.logIndex = {};
    push(state, 0, AreaType::Active, 47); push(state, 0, AreaType::Bench, 44);
    push(state, 0, AreaType::Hand, 20); push(state, 0, AreaType::Hand, 21);
    push(state, 0, AreaType::Deck, 22); push(state, 0, AreaType::Deck, 23);
    push(state, 0, AreaType::Trash, 24);
    push(state, 0, AreaType::Prize, 25, true); push(state, 0, AreaType::Prize, 26);
    push(state, 1, AreaType::Active, 63); push(state, 1, AreaType::Bench, 64, true);
    push(state, 1, AreaType::Hand, 65); push(state, 1, AreaType::Hand, 66);
    push(state, 1, AreaType::Deck, 67); push(state, 1, AreaType::Deck, 68);
    push(state, 1, AreaType::Trash, 69);
    push(state, 1, AreaType::Prize, 70, true); push(state, 1, AreaType::Prize, 71);
    place(state, 29, AreaType::Stadium); state.stadium.push_back(CardRef(29));
    place(state, 27, AreaType::Looking); place(state, 28, AreaType::Looking);
    state.looking.push_back(CardRef(27)); state.looking.push_back(CardRef(28));
    state.lookingPlayer = mode == 0 ? actor : mode == 1 ? 2 : mode == 2 ? actor + 3 : 1 - actor;
    state.lookingReverse = true;
    state.turn = 7; state.turnActionCount = 13; state.firstPlayer = 1;
    state.supporterPlayed = true; state.stadiumPlayed = true; state.energyPlayed = true; state.retreated = true;
    state.selectType = SelectType::Main; state.selectContext = SelectContext::Main;
    state.selectPlayer = actor; state.selectMin = 0; state.selectMax = 1;
    state.remainDamageCounter = 40; state.remainEnergyCost = 2; state.selectDeck = true;
    const int active_ref = actor == 0 ? 47 : 63;
    const int hand_ref = actor == 0 ? 20 : 65;
    state.contextCard = CardRef(hand_ref);
    state.effectState = {}; state.effectState.onEffect = true;
    state.effectState.ability.effectCard = state.makeAreaRef(CardRef(active_ref));
    state.effectState.ability.usePlayerIndex = actor;
    { auto& o = state.addOption(SelectOptionType::Number); o.param0 = 3; }
    { auto& o = state.addOption(SelectOptionType::Card); o.param0 = (short)AreaType::Hand; o.param1 = 1; o.param2 = (short)actor; }
    { auto& o = state.addOption(SelectOptionType::Play); o.param0 = 0; }
    state.addOption(SelectOptionType::Retreat);
    state.addOption(SelectOptionType::End);
    { auto& o = state.addOption(SelectOptionType::Skill); o.param0 = (short)state.getCard(CardRef(active_ref)).cardId; o.param1 = (short)active_ref; }
}

int main() {
    InitializeAll();
    GameConfig config = {};
    config.seed = 1; config.recordLog = false; config.deviceRand = false; config.sendDeck = false;
    for (int p = 0; p < 2; ++p) for (int i = 0; i < DECK_SIZE; ++i) {
        int id = 0; if (!(std::cin >> id)) return 2; config.decks[p].cards[i] = id;
    }
    for (int actor = 0; actor < 2; ++actor) for (int mode = 0; mode < 4; ++mode) {
        BattleData battle; battle.init(config); build_fixture(battle.state, actor, mode);
        JsonBuilder json; ToJsonApi(battle.state, json, 0);
        std::cout.write(reinterpret_cast<const char*>(json.buf.data()), (std::streamsize)json.buf.size());
        std::cout << '\n';
    }
    return 0;
}
