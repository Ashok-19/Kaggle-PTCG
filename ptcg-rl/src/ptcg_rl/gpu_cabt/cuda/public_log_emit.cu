namespace gpu_cabt {

__device__ __forceinline__ void log_shuffle(BattleRuntimeState& runtime, gc_i32 player) {
    append_public_log(runtime, kLogShuffle, 1, player);
}
__device__ __forceinline__ void log_has_basic(BattleRuntimeState& runtime, gc_i32 player, bool has_basic) {
    append_public_log(runtime, kLogHasBasicPokemon, 2, player, has_basic ? 1 : 0);
}
__device__ __forceinline__ void log_turn_start(BattleRuntimeState& runtime, gc_i32 player) {
    append_public_log(runtime, kLogTurnStart, 1, player);
}
__device__ __forceinline__ void log_turn_end(BattleRuntimeState& runtime, gc_i32 player) {
    append_public_log(runtime, kLogTurnEnd, 1, player);
}
__device__ __forceinline__ void log_draw(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player, gc_u8 ref
) {
    append_public_log(runtime, kLogDraw, 3, player, state.all_card[ref].card_id, ref);
}
__device__ __forceinline__ void log_move_card(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_i32 from_area, gc_i32 to_area, gc_i32 open_type
) {
    append_public_log(runtime, kLogMoveCard, 6, player, state.all_card[ref].card_id, ref,
        from_area, to_area, open_type);
}
__device__ __forceinline__ void log_switch(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 active, gc_u8 bench
) {
    append_public_log(runtime, kLogSwitch, 5, player, state.all_card[active].card_id, active,
        state.all_card[bench].card_id, bench);
}
__device__ __forceinline__ void log_change(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 before, gc_u8 after
) {
    append_public_log(runtime, kLogChange, 5, player, state.all_card[before].card_id, before,
        state.all_card[after].card_id, after);
}
__device__ __forceinline__ void log_play(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player, gc_u8 ref
) {
    append_public_log(runtime, kLogPlay, 3, player, state.all_card[ref].card_id, ref);
}
__device__ __forceinline__ void log_attach(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_u8 target
) {
    append_public_log(runtime, kLogAttach, 5, player, state.all_card[ref].card_id, ref,
        state.all_card[target].card_id, target);
}
__device__ __forceinline__ void log_evolve(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_u8 target
) {
    append_public_log(runtime, kLogEvolve, 5, player, state.all_card[ref].card_id, ref,
        state.all_card[target].card_id, target);
}
__device__ __forceinline__ void log_devolve(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_u8 target
) {
    append_public_log(runtime, kLogDevolve, 5, player, state.all_card[ref].card_id, ref,
        state.all_card[target].card_id, target);
}
__device__ __forceinline__ void log_move_attached(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_u8 before, gc_u8 after
) {
    append_public_log(runtime, kLogMoveAttached, 7, player, state.all_card[ref].card_id, ref,
        state.all_card[before].card_id, before, state.all_card[after].card_id, after);
}
__device__ __forceinline__ void log_attack(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_i32 attack_id
) {
    append_public_log(runtime, kLogAttack, 4, player, state.all_card[ref].card_id, ref, attack_id);
}
__device__ __forceinline__ void log_hp_change(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player,
    gc_u8 ref, gc_i32 value, bool counter
) {
    append_public_log(runtime, kLogHpChange, 5, player, state.all_card[ref].card_id, ref,
        value, counter ? 1 : 0);
}
__device__ __forceinline__ void log_condition(
    const BattleCoreState& state, BattleRuntimeState& runtime, gc_u8 type,
    gc_i32 player, bool recover, gc_u8 ref
) {
    append_public_log(runtime, type, 4, player, recover ? 1 : 0,
        state.all_card[ref].card_id, ref);
}
__device__ __forceinline__ void log_coin(BattleRuntimeState& runtime, gc_i32 player, bool head) {
    append_public_log(runtime, kLogCoin, 2, player, head ? 1 : 0);
}
__device__ __forceinline__ void log_result(BattleRuntimeState& runtime, gc_i32 result, gc_i32 reason) {
    append_public_log(runtime, kLogResult, 2, result, reason);
}

__device__ __forceinline__ void clear_sleep_paralyze_confuse_logged(
    BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1) return;
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0) { player_active_state(player).fields.bad_status = 0; return; }
    const gc_u8 ref = player.active.values[0];
    const gc_u8 status = player_active_state(player).fields.bad_status;
    if (status == 1) log_condition(state, runtime, kLogAsleep, player_index, true, ref);
    else if (status == 2) log_condition(state, runtime, kLogParalyzed, player_index, true, ref);
    else if (status == 3) log_condition(state, runtime, kLogConfused, player_index, true, ref);
    player_active_state(player).fields.bad_status = 0;
}

__device__ __forceinline__ void clear_special_condition_logged(
    BattleCoreState& state, BattleRuntimeState& runtime, gc_i32 player_index
) {
    if (player_index < 0 || player_index > 1) return;
    PlayerState& player = state.players[player_index];
    if (player.active.count == 0) { player.active_state = 0; return; }
    const gc_u8 ref = player.active.values[0];
    clear_sleep_paralyze_confuse_logged(state, runtime, player_index);
    auto& active = player_active_state(player).fields;
    if (active.poison_damage_counter != 0) log_condition(state, runtime, kLogPoisoned, player_index, true, ref);
    if (active.burned) log_condition(state, runtime, kLogBurned, player_index, true, ref);
    active.poison_damage_counter = 0;
    active.burned = false;
}

}  // namespace gpu_cabt
