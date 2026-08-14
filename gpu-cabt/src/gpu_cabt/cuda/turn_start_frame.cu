namespace gpu_cabt {

__device__ __forceinline__ gc_i32 active_player_index(const BattleCoreState* state) {
    return ((state->turn + 1) ^ (gc_i32)state->first_player) & 1;
}

__device__ __forceinline__ void player_turn_start(PlayerState* player, gc_i32 active_player) {
    if ((gc_i32)player->player_index == active_player) {
        player->this_turn = player->next_turn;
        player->next_turn = 0;
    }
}

__device__ __forceinline__ void card_turn_start(CardState* card, gc_i32 active_player) {
    card->take_attack_damage_pre_turn = card->take_attack_damage_this_turn;
    card->take_attack_damage_this_turn = 0;
    if ((gc_i32)card->player_index == active_player) {
        #pragma unroll
        for (gc_i32 index = 0; index < 4; ++index) {
            card->this_turn[index] = card->next_turn[index];
            card->next_turn[index] = 0;
        }
    } else {
        card->this_turn_enemy[0] = card->next_turn_enemy[0];
        card->next_turn_enemy[0] = 0;
    }
}

__device__ __forceinline__ bool turn_start_frame(
    BattleCoreState* state,
    BattleRuntimeState* runtime
) {
    if (state->game_result != 0) return false;
    state->turn += 1;
    state->turn_action_count = 0;
    const gc_i32 active_player = active_player_index(state);
    state->phase = 1;  // GamePhase::Main in the current CABT engine.

    runtime->turn_used_skill_count = 0;
    runtime->turn_play_count = 0;
    runtime->turn_heal_count = 0;
    runtime->turn_evolve_count = 0;

    state->turn_histories[2] = state->turn_histories[1];
    state->turn_histories[1] = state->turn_histories[0];
    state->turn_histories[0] = {};

    for (gc_i32 index = 0; index < (gc_i32)state->stadium.count; ++index) {
        const gc_u8 ref = state->stadium.values[index];
        if (ref == 0 || ref >= kAllCardCapacity) {
            runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
            return false;
        }
        card_turn_start(&state->all_card[ref], active_player);
    }
    for (gc_i32 player_index = 0; player_index < 2; ++player_index) {
        PlayerState* player = &state->players[player_index];
        player_turn_start(player, active_player);
        for (gc_i32 index = 0; index < (gc_i32)player->active.count; ++index) {
            const gc_u8 ref = player->active.values[index];
            if (ref == 0 || ref >= kAllCardCapacity) {
                runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
                return false;
            }
            card_turn_start(&state->all_card[ref], active_player);
        }
        for (gc_i32 index = 0; index < (gc_i32)player->bench.count; ++index) {
            const gc_u8 ref = player->bench.values[index];
            if (ref == 0 || ref >= kAllCardCapacity) {
                runtime->error_flags |= kRuntimeErrorUnsupportedTransition;
                return false;
            }
            card_turn_start(&state->all_card[ref], active_player);
        }
    }
    return true;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_force_turn_start_case(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    auto* runtime = reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    state->turn = env_index % 5;
    state->turn_action_count = 70 + env_index;
    state->first_player = (gc_i8)(env_index & 1);
    state->phase = 0;
    for (gc_i32 player_index = 0; player_index < 2; ++player_index) {
        auto& player = state->players[player_index];
        if (player.active.count == 0) {
            const gc_u8 ref = (gc_u8)(player_index == 0 ? 3 : 63);
            player.active.count = 1;
            player.active.values[0] = ref;
            state->all_card[ref].area = gpu_cabt::kAreaActive;
        }
    }
    runtime->turn_used_skill_count = 3;
    runtime->turn_play_count = 4;
    runtime->turn_heal_count = 5;
    runtime->turn_evolve_count = 6;

    for (gc_i32 history = 0; history < 3; ++history) {
        state->turn_histories[history].turn_attack_id = 1000 + history * 100 + env_index;
        state->turn_histories[history].take_prize_count_turn_player = (gc_i8)(history + 1);
    }
    for (gc_i32 player_index = 0; player_index < 2; ++player_index) {
        auto& player = state->players[player_index];
        player.this_turn = 0x11110000u + (gc_u32)(player_index * 0x100 + env_index);
        player.next_turn = 0x22220000u + (gc_u32)(player_index * 0x100 + env_index);
        if (player.active.count > 0) {
            auto& card = state->all_card[player.active.values[0]];
            card.take_attack_damage_this_turn = 300 + player_index * 10 + env_index;
            card.take_attack_damage_pre_turn = -1;
            for (gc_i32 word = 0; word < 4; ++word) {
                card.this_turn[word] = 0x10000000u + player_index * 0x10000u + word * 0x100u + env_index;
                card.next_turn[word] = 0x20000000u + player_index * 0x10000u + word * 0x100u + env_index;
            }
            card.this_turn_enemy[0] = 0x30000000u + player_index * 0x10000u + env_index;
            card.next_turn_enemy[0] = 0x40000000u + player_index * 0x10000u + env_index;
        }
    }
}

extern "C" __global__ void gpu_cabt_turn_start_frame(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    auto* runtime = reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    if (runtime->error_flags != 0) return;
    gpu_cabt::turn_start_frame(state, runtime);
}

static constexpr gc_i32 kTurnStartFrameSnapshotSize = 46;

extern "C" __global__ void gpu_cabt_turn_start_frame_snapshot(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    gc_i32* output,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto* state = reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const auto* runtime = reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    gc_i32* row = output + (gc_i64)env_index * kTurnStartFrameSnapshotSize;
    gc_i32 c = 0;
    row[c++] = state->turn;
    row[c++] = state->turn_action_count;
    row[c++] = state->phase;
    row[c++] = gpu_cabt::active_player_index(state);
    row[c++] = runtime->error_flags;
    row[c++] = runtime->turn_used_skill_count;
    row[c++] = runtime->turn_play_count;
    row[c++] = runtime->turn_heal_count;
    row[c++] = runtime->turn_evolve_count;
    for (gc_i32 h = 0; h < 3; ++h) {
        row[c++] = state->turn_histories[h].turn_attack_id;
        row[c++] = state->turn_histories[h].take_prize_count_turn_player;
    }
    for (gc_i32 p = 0; p < 2; ++p) {
        const auto& player = state->players[p];
        row[c++] = (gc_i32)player.this_turn;
        row[c++] = (gc_i32)player.next_turn;
        const auto& card = state->all_card[player.active.values[0]];
        row[c++] = card.take_attack_damage_this_turn;
        row[c++] = card.take_attack_damage_pre_turn;
        for (gc_i32 word = 0; word < 4; ++word) row[c++] = (gc_i32)card.this_turn[word];
        for (gc_i32 word = 0; word < 4; ++word) row[c++] = (gc_i32)card.next_turn[word];
        row[c++] = (gc_i32)card.this_turn_enemy[0];
        row[c++] = (gc_i32)card.next_turn_enemy[0];
    }
    while (c < kTurnStartFrameSnapshotSize) row[c++] = 0;
}
