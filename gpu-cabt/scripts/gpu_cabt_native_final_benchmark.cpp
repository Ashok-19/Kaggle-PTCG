#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "All.h"
#include "ToJson.h"

using Clock = std::chrono::steady_clock;

static double percentile(std::vector<double> values, double q) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const double position = q * (values.size() - 1);
    const std::size_t lo = static_cast<std::size_t>(position);
    const std::size_t hi = std::min(lo + 1, values.size() - 1);
    const double fraction = position - static_cast<double>(lo);
    return values[lo] + (values[hi] - values[lo]) * fraction;
}

struct Metrics {
    std::string mode;
    std::uint64_t games = 0;
    std::uint64_t decisions = 0;
    std::uint64_t failures = 0;
    std::uint64_t json_bytes = 0;
    int max_turn = 0;
    double seconds = 0.0;
    std::vector<double> game_ms;
};

static Metrics run_mode(
    const std::array<std::array<int, DECK_SIZE>, 7>& decks,
    int repeats,
    bool public_observation
) {
    Metrics metrics;
    metrics.mode = public_observation ? "public" : "core";
    const auto run_start = Clock::now();
    for (int repeat = 0; repeat < repeats; ++repeat) {
        for (int opponent = 1; opponent < 7; ++opponent) {
            for (int lucario_seat = 0; lucario_seat < 2; ++lucario_seat) {
                const auto game_start = Clock::now();
                try {
                    GameConfig config{};
                    config.recordLog = public_observation;
                    config.deviceRand = true;
                    config.seed = 0;
                    config.timeLimit = 0;
                    const auto& deck0 = lucario_seat == 0 ? decks[0] : decks[opponent];
                    const auto& deck1 = lucario_seat == 0 ? decks[opponent] : decks[0];
                    for (int i = 0; i < DECK_SIZE; ++i) {
                        config.decks[0].cards[i] = deck0[i];
                        config.decks[1].cards[i] = deck1[i];
                    }

                    BattleData battle;
                    battle.init(config);
                    battle.start();
                    JsonBuilder json;
                    int game_decisions = 0;
                    bool failed = false;
                    while (true) {
                        const bool continued = battle.next();
                        if (public_observation) {
                            json.clear();
                            ToJsonApi(battle.state, json, battle.state.nextLogStart());
                            metrics.json_bytes += json.buf.size();
                        }
                        if (!continued) break;
                        if (++game_decisions > 5000) {
                            failed = true;
                            break;
                        }
                        battle.state.selected.clear();
                        for (int i = 0; i < battle.state.selectMin; ++i) {
                            battle.state.selected.push_back(i);
                        }
                    }
                    if (failed || !battle.state.isFinish()) {
                        ++metrics.failures;
                    } else {
                        ++metrics.games;
                        metrics.decisions += static_cast<std::uint64_t>(game_decisions);
                        metrics.max_turn = std::max(metrics.max_turn, battle.state.turn);
                    }
                } catch (...) {
                    ++metrics.failures;
                }
                const double elapsed_ms = std::chrono::duration<double, std::milli>(
                    Clock::now() - game_start
                ).count();
                metrics.game_ms.push_back(elapsed_ms);
            }
        }
    }
    metrics.seconds = std::chrono::duration<double>(Clock::now() - run_start).count();
    return metrics;
}

static void print_metrics(const Metrics& metrics) {
    const double games_per_second = metrics.seconds > 0.0 ? metrics.games / metrics.seconds : 0.0;
    const double decisions_per_second = metrics.seconds > 0.0 ? metrics.decisions / metrics.seconds : 0.0;
    std::cout << std::fixed << std::setprecision(6)
              << "{\"mode\":\"" << metrics.mode << "\""
              << ",\"games\":" << metrics.games
              << ",\"decisions\":" << metrics.decisions
              << ",\"failures\":" << metrics.failures
              << ",\"seconds\":" << metrics.seconds
              << ",\"games_per_second\":" << games_per_second
              << ",\"decisions_per_second\":" << decisions_per_second
              << ",\"game_latency_p50_ms\":" << percentile(metrics.game_ms, 0.50)
              << ",\"game_latency_p95_ms\":" << percentile(metrics.game_ms, 0.95)
              << ",\"game_latency_p99_ms\":" << percentile(metrics.game_ms, 0.99)
              << ",\"max_turn\":" << metrics.max_turn
              << ",\"json_bytes\":" << metrics.json_bytes
              << "}\n";
}

int main(int argc, char** argv) {
    int repeats = 10;
    if (argc == 2) repeats = std::max(1, std::stoi(argv[1]));
    if (argc > 2) return 2;

    InitializeAll();
    std::array<std::array<int, DECK_SIZE>, 7> decks{};
    for (auto& deck : decks) {
        for (int& card : deck) {
            if (!(std::cin >> card)) return 3;
        }
    }

    print_metrics(run_mode(decks, repeats, false));
    print_metrics(run_mode(decks, repeats, true));
    return 0;
}
