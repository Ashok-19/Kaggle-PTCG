#include <array>
#include <cstdint>
#include <iostream>
#include <vector>

#include "state_core.h"
#include "runtime_state.h"

using namespace gpu_cabt;

static void init_cards(BattleCoreState& state, const std::array<int, 120>& ids) {
    state = {};
    state.move_counter = 1;
    state.first_player = -1;
    for (int p = 0; p < 2; ++p) {
        const int player_ref = 1 + p;
        state.all_card[player_ref].card_id = 0;
        state.all_card[player_ref].move_counter = state.move_counter++;
        state.all_card[player_ref].player_index = (gc_i8)p;
        state.all_card[player_ref].area = kAreaPlayer;
        state.players[p].player_index = (gc_i8)p;
    }
    int ref = 3;
    for (int p = 0; p < 2; ++p) {
        for (int i = 0; i < kDeckSize; ++i, ++ref) {
            auto& card = state.all_card[ref];
            card.card_id = ids[p * kDeckSize + i];
            card.move_counter = state.move_counter++;
            card.player_index = (gc_i8)p;
            card.area = kAreaDeck;
        }
    }
}

static void place(BattleCoreState& state, int ref, int player, gc_u8 area, bool reverse = false) {
    auto& card = state.all_card[ref];
    card.player_index = (gc_i8)player;
    card.pre_area = card.area;
    card.area = area;
    card.reverse = reverse ? 1 : 0;
}

template <typename List>
static void push(BattleCoreState& state, List& list, int ref, int player, gc_u8 area, bool reverse = false) {
    place(state, ref, player, area, reverse);
    list.values[list.count++] = (gc_u8)ref;
}

static void build_fixture(BattleCoreState& state, BattleRuntimeState& runtime, int actor, int mode) {
    runtime = {};
    for (int p = 0; p < 2; ++p) {
        auto& ps = state.players[p];
        ps.active.count = 0; ps.bench.count = 0; ps.prize.count = 0;
        ps.hand.count = 0; ps.deck.count = 0; ps.trash.count = 0;
        ps.energy.count = 0; ps.tool.count = 0; ps.pre_evolution.count = 0;
        ps.temporary.count = 0; ps.active_state = 0; ps.continual_state = 0;
        ps.turn_state = 0; ps.this_turn = 0; ps.next_turn = 0;
    }
    state.stadium.count = 0; state.looking.count = 0;
    state.selected_list.count = 0; state.each_list.count = 0;
    state.playing.count = 0; state.check_list.count = 0;

    push(state, state.players[0].active, 47, 0, 4);
    push(state, state.players[0].bench, 44, 0, 5);
    push(state, state.players[0].hand, 20, 0, 2);
    push(state, state.players[0].hand, 21, 0, 2);
    push(state, state.players[0].deck, 22, 0, 1);
    push(state, state.players[0].deck, 23, 0, 1);
    push(state, state.players[0].trash, 24, 0, 3);
    push(state, state.players[0].prize, 25, 0, 6, true);
    push(state, state.players[0].prize, 26, 0, 6);
    push(state, state.players[1].active, 63, 1, 4);
    push(state, state.players[1].bench, 64, 1, 5, true);
    push(state, state.players[1].hand, 65, 1, 2);
    push(state, state.players[1].hand, 66, 1, 2);
    push(state, state.players[1].deck, 67, 1, 1);
    push(state, state.players[1].deck, 68, 1, 1);
    push(state, state.players[1].trash, 69, 1, 3);
    push(state, state.players[1].prize, 70, 1, 6, true);
    push(state, state.players[1].prize, 71, 1, 6);

    place(state, 29, 0, 7); state.stadium.values[0] = 29; state.stadium.count = 1;
    place(state, 27, 0, 12); place(state, 28, 0, 12);
    state.looking.values[0] = 27; state.looking.values[1] = 28; state.looking.count = 2;
    state.looking_player = mode == 0 ? (gc_i8)actor : mode == 1 ? 2 : mode == 2 ? (gc_i8)(actor + 3) : (gc_i8)(1 - actor);
    state.looking_reverse = 1;

    state.turn = 7; state.turn_action_count = 13; state.phase = 3;
    state.game_result = 0; state.finish_reason = 0; state.first_player = 1;
    state.turn_state = 0x0f;
    state.select_type = 1; state.select_context = 1; state.select_player = (gc_i8)actor;
    state.select_min = 0; state.select_max = 1;
    state.remain_damage_counter = 40; state.remain_energy_cost = 2; state.select_deck = 1;
    const gc_u8 active_ref = actor == 0 ? 47 : 63;
    const gc_u8 hand_ref = actor == 0 ? 20 : 65;
    state.context_card = hand_ref;
    state.effect_state = {};
    state.effect_state.on_effect = 1;
    state.effect_state.ability.effect_card.card_index = active_ref;
    state.effect_state.ability.effect_card.move_counter = state.all_card[active_ref].move_counter;
    state.effect_state.ability.use_player_index = (gc_i8)actor;

    runtime.option_count = 6;
    runtime.options[0] = {0, 0, 3, 0, 0, 0, 0};
    runtime.options[1] = {3, 0, 2, 1, (gc_i16)actor, 0, 0};
    runtime.options[2] = {7, 0, 0, 0, 0, 0, 0};
    runtime.options[3] = {12, 0, 0, 0, 0, 0, 0};
    runtime.options[4] = {14, 0, 0, 0, 0, 0, 0};
    runtime.options[5] = {15, 0, (gc_i16)state.all_card[active_ref].card_id, (gc_i16)active_ref, 0, 0, 0};
}

int main() {
    std::array<int, 120> ids{};
    for (int& id : ids) if (!(std::cin >> id)) return 2;
    constexpr std::uint32_t count = 8;
    std::vector<BattleCoreState> states(count);
    std::vector<BattleRuntimeState> runtimes(count);
    for (std::uint32_t env = 0; env < count; ++env) {
        init_cards(states[env], ids);
        build_fixture(states[env], runtimes[env], env / 4, env & 3);
    }
    const std::uint32_t state_size = sizeof(BattleCoreState);
    const std::uint32_t runtime_size = sizeof(BattleRuntimeState);
    std::cout.write(reinterpret_cast<const char*>(&state_size), sizeof(state_size));
    std::cout.write(reinterpret_cast<const char*>(&runtime_size), sizeof(runtime_size));
    std::cout.write(reinterpret_cast<const char*>(&count), sizeof(count));
    std::cout.write(reinterpret_cast<const char*>(states.data()), (std::streamsize)(states.size() * sizeof(BattleCoreState)));
    std::cout.write(reinterpret_cast<const char*>(runtimes.data()), (std::streamsize)(runtimes.size() * sizeof(BattleRuntimeState)));
    return 0;
}
