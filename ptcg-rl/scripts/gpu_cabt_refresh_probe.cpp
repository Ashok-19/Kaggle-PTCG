#include <cstdint>
#include <iostream>
#include "All.h"

static void emit(uint64_t value) { std::cout.write(reinterpret_cast<const char*>(&value), 8); }

template <class L>
static void push(L& list, CardRef ref) { list.push_back(ref); }

static void forceSynthetic(State& s, int mode) {
    s.stadium.clear();
    for (int p = 0; p < 2; ++p) {
        PlayerState& ps = s.players[p];
        ps.active.clear(); ps.bench.clear(); ps.prize.clear(); ps.hand.clear(); ps.deck.clear();
        ps.trash.clear(); ps.energy.clear(); ps.tool.clear(); ps.preEvolution.clear(); ps.temporary.clear();
        const int base = p == 0 ? 3 : 63;
        int order[60];
        const int shift = (mode * 10 + p * 3) % 60;
        for (int i = 0; i < 60; ++i) order[i] = (i + shift) % 60;
        int cursor = 0;
        auto take = [&](AreaType area, int count) {
            for (int n = 0; n < count; ++n) {
                CardRef ref(base + order[cursor++]);
                Card& card = s.getCard(ref);
                card.area = area; card.preArea = area; card.reverse = false; card.skillOrder = order[cursor - 1] % 7;
                if (area == AreaType::Active) push(ps.active, ref);
                else if (area == AreaType::Bench) push(ps.bench, ref);
                else if (area == AreaType::Hand) push(ps.hand, ref);
                else if (area == AreaType::Energy) push(ps.energy, ref);
                else if (area == AreaType::Tool) push(ps.tool, ref);
                else if (area == AreaType::Trash) push(ps.trash, ref);
                else if (area == AreaType::Deck) push(ps.deck, ref);
            }
        };
        take(AreaType::Active, 1);
        take(AreaType::Bench, 8);
        take(AreaType::Hand, 15);
        take(AreaType::Energy, 10);
        take(AreaType::Tool, 8);
        take(AreaType::Trash, 10);
        take(AreaType::Deck, p == 0 ? 7 : 8);
        if (p == 0) {
            CardRef ref(base + order[cursor++]);
            Card& card = s.getCard(ref); card.area = AreaType::Stadium; card.preArea = AreaType::Stadium;
            s.stadium.push_back(ref);
        }
        CardRef field[9]; field[0] = ps.active[0]; for (int i = 0; i < 8; ++i) field[i + 1] = ps.bench[i];
        for (int i = 0; i < ps.energy.size(); ++i) s.getCard(ps.energy[i]).attachMoveCounter = s.getCard(field[(i + mode) % 9]).moveCounter;
        for (int i = 0; i < ps.tool.size(); ++i) s.getCard(ps.tool[i]).attachMoveCounter = s.getCard(field[(i * 2 + mode) % 9]).moveCounter;
        ps.poisonDamageCounter = 2 + p; ps.badStatus = BadStatusType::Confused; ps.burned = true;
    }
    s.continualState = 0;
    s.currentSkillOrder = 100 + mode;
    s.currentCardEffectIndex = 0;
    s.updateOrder = false;
}

static void snapshot(const State& s) {
    emit((uint64_t)(uint32_t)s.continualState);
    emit((uint64_t)(uint32_t)s.currentSkillOrder);
    emit((uint64_t)(uint32_t)s.currentCardEffectIndex);
    emit((uint64_t)(uint32_t)s.updateOrder);
    for (int p = 0; p < 2; ++p) {
        emit(s.players[p].continualState);
        emit((uint64_t)(uint32_t)s.players[p].activeState);
    }
    for (int ref = 3; ref < 123; ++ref) {
        const Card& card = s.getCard(CardRef(ref));
        emit((uint64_t)(uint32_t)card.skillOrder);
        emit((uint64_t)(uint32_t)card.area);
        for (uint64_t word : card.continualState) emit(word);
    }
}

int main() {
    InitializeAll();
    int decks[120]; for (int& value : decks) if (!(std::cin >> value)) return 2;
    GameConfig config{}; config.recordLog = false; config.deviceRand = false; config.seed = 1;
    for (int p = 0; p < 2; ++p) for (int i = 0; i < 60; ++i) config.decks[p].cards[i] = decks[p * 60 + i];
    for (int mode = 0; mode < 6; ++mode) {
        BattleData battle; battle.init(config); State& s = battle.state; forceSynthetic(s, mode); RefreshEffect(s, 0); snapshot(s);
    }
    return 0;
}
