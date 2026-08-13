static constexpr gc_i32 kRefreshProbeSnapshotWords = 848;

namespace gpu_cabt {

__device__ __forceinline__ void clear_u8_list(gc_u8& count) { count = 0; }

template <typename T, int Capacity>
__device__ __forceinline__ bool probe_push(
    FixedListU8<T, Capacity>& list,
    T value,
    BattleRuntimeState& runtime
) {
    if ((gc_i32)list.count >= Capacity) {
        runtime.error_flags |= kRuntimeErrorZoneOverflow;
        return false;
    }
    list.values[list.count++] = value;
    return true;
}

__device__ __forceinline__ void force_refresh_synthetic(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 mode
) {
    runtime = {};
    state.stadium.count = 0;
    for (gc_i32 p = 0; p < 2; ++p) {
        PlayerState& player = state.players[p];
        player.active.count = 0;
        player.bench.count = 0;
        player.prize.count = 0;
        player.hand.count = 0;
        player.deck.count = 0;
        player.trash.count = 0;
        player.energy.count = 0;
        player.tool.count = 0;
        player.pre_evolution.count = 0;
        player.temporary.count = 0;
        const gc_i32 base = p == 0 ? 3 : 63;
        const gc_i32 shift = (mode * 10 + p * 3) % 60;
        gc_i32 order[60];
        #pragma unroll 1
        for (gc_i32 i = 0; i < 60; ++i) order[i] = (i + shift) % 60;
        gc_i32 cursor = 0;
        for (gc_i32 zone = 0; zone < 7; ++zone) {
            gc_i32 count = 0;
            gc_u8 area = 0;
            if (zone == 0) { count = 1; area = kAreaActive; }
            else if (zone == 1) { count = 8; area = kAreaBench; }
            else if (zone == 2) { count = 15; area = kAreaHand; }
            else if (zone == 3) { count = 10; area = 8; }
            else if (zone == 4) { count = 8; area = 9; }
            else if (zone == 5) { count = 10; area = 3; }
            else { count = p == 0 ? 7 : 8; area = kAreaDeck; }
            for (gc_i32 n = 0; n < count; ++n) {
                const gc_u8 ref = (gc_u8)(base + order[cursor++]);
                CardState& card = state.all_card[ref];
                card.area = area;
                card.pre_area = area;
                card.reverse = 0;
                card.skill_order = order[cursor - 1] % 7;
                if (area == kAreaActive) probe_push(player.active, ref, runtime);
                else if (area == kAreaBench) probe_push(player.bench, ref, runtime);
                else if (area == kAreaHand) probe_push(player.hand, ref, runtime);
                else if (area == 8) probe_push(player.energy, ref, runtime);
                else if (area == 9) probe_push(player.tool, ref, runtime);
                else if (area == 3) probe_push(player.trash, ref, runtime);
                else if (area == kAreaDeck) probe_push(player.deck, ref, runtime);
            }
        }
        if (p == 0) {
            const gc_u8 ref = (gc_u8)(base + order[cursor++]);
            CardState& card = state.all_card[ref];
            card.area = 7;
            card.pre_area = 7;
            probe_push(state.stadium, ref, runtime);
        }
        gc_u8 field[9];
        field[0] = player.active.values[0];
        for (gc_i32 i = 0; i < 8; ++i) field[i + 1] = player.bench.values[i];
        for (gc_i32 i = 0; i < (gc_i32)player.energy.count; ++i) {
            state.all_card[player.energy.values[i]].attach_move_counter =
                state.all_card[field[(i + mode) % 9]].move_counter;
        }
        for (gc_i32 i = 0; i < (gc_i32)player.tool.count; ++i) {
            state.all_card[player.tool.values[i]].attach_move_counter =
                state.all_card[field[(i * 2 + mode) % 9]].move_counter;
        }
        PlayerActiveFields& active = player_active_state(player);
        active.fields.poison_damage_counter = (gc_i8)(2 + p);
        active.fields.bad_status = 3;
        active.fields.burned = true;
    }
    state.continual_state = 0;
    state.current_skill_order = 100 + mode;
    state.current_card_effect_index = 0;
    state.update_order = false;
}

__device__ __forceinline__ RuleTableView make_rule_view(
    const RuleCardMaster* cards,
    const RuleSkill* skills,
    const RuleAttack* attacks,
    const RuleEffect* effects,
    const RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words
) {
    RuleTableView view{};
    view.cards = cards;
    view.skills = skills;
    view.attacks = attacks;
    view.effects = effects;
    view.triggers = triggers;
    view.substring_masks = masks;
    view.card_count = card_count;
    view.skill_count = skill_count;
    view.attack_count = attack_count;
    view.effect_count = effect_count;
    view.trigger_count = trigger_count;
    view.substring_mask_count = mask_count;
    view.substring_mask_words = mask_words;
    return view;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_force_refresh_synthetic(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gc_i32* modes,
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
    gpu_cabt::force_refresh_synthetic(*state, *runtime, modes[env_index]);
}

extern "C" __global__ void gpu_cabt_refresh_effect_kernel(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gpu_cabt::RuleCardMaster* cards,
    const gpu_cabt::RuleSkill* skills,
    const gpu_cabt::RuleAttack* attacks,
    const gpu_cabt::RuleEffect* effects,
    const gpu_cabt::RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words,
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
    const gpu_cabt::RuleTableView rules = gpu_cabt::make_rule_view(
        cards, skills, attacks, effects, triggers, masks,
        card_count, skill_count, attack_count, effect_count, trigger_count,
        mask_count, mask_words
    );
    gpu_cabt::refresh_effect(*state, *runtime, rules, 0);
}

extern "C" __global__ void gpu_cabt_refresh_probe_snapshot(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    unsigned long long* output,
    gc_u32* errors,
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
    errors[env_index] = runtime->error_flags;
    unsigned long long* row = output + (gc_i64)env_index * kRefreshProbeSnapshotWords;
    gc_i32 cursor = 0;
    row[cursor++] = (gc_u64)(gc_u32)state->continual_state;
    row[cursor++] = (gc_u64)(gc_u32)state->current_skill_order;
    row[cursor++] = (gc_u64)(gc_u32)state->current_card_effect_index;
    row[cursor++] = (gc_u64)(gc_u32)state->update_order;
    for (gc_i32 p = 0; p < 2; ++p) {
        row[cursor++] = state->players[p].continual_state;
        row[cursor++] = (gc_u64)(gc_u32)state->players[p].active_state;
    }
    for (gc_i32 ref = 3; ref < 123; ++ref) {
        const auto& card = state->all_card[ref];
        row[cursor++] = (gc_u64)(gc_u32)card.skill_order;
        row[cursor++] = (gc_u64)(gc_u32)card.area;
        for (gc_i32 word = 0; word < 5; ++word) row[cursor++] = card.continual_state[word];
    }
}
