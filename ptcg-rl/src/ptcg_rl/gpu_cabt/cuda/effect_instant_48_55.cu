namespace gpu_cabt {

__device__ __forceinline__ bool is_evolved_full(const BattleCoreState& state, gc_u8 ref) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    if (card.player_index < 0 || card.player_index > 1) return false;
    const PlayerState& p = state.players[card.player_index];
    for (gc_i32 i = 0; i < (gc_i32)p.pre_evolution.count; ++i)
        if (state.all_card[p.pre_evolution.values[i]].attach_move_counter == card.move_counter) return true;
    return false;
}

__device__ __forceinline__ void exchange_selected_full(BattleCoreState& state, BattleRuntimeState& runtime) {
    if (state.check_list.count == 0 || runtime.target_count == 0) return;
    const gc_u8 prize_ref = state.check_list.values[0];
    const AreaRefState hand_target = runtime.targets[0];
    if (prize_ref == 0 || prize_ref >= kAllCardCapacity || !valid_area_ref(state, hand_target)) return;
    const gc_u8 hand_ref = hand_target.card;
    CardState& prize_card = state.all_card[prize_ref];
    CardState& hand_card = state.all_card[hand_ref];
    if (prize_card.player_index < 0 || prize_card.player_index > 1
        || hand_card.player_index < 0 || hand_card.player_index > 1) return;
    const gc_i32 prize_index = current_area_index(state.players[prize_card.player_index], prize_card.area, prize_ref);
    const gc_i32 hand_index = current_area_index(state.players[hand_card.player_index], hand_card.area, hand_ref);
    if (prize_card.area != 6 || hand_card.area != 2 || prize_index < 0 || hand_index < 0) return;
    const gc_i32 pp = prize_card.player_index;
    const gc_i32 hp = hand_card.player_index;
    card_moved_full(state, runtime, prize_ref, 2, false);
    card_moved_full(state, runtime, hand_ref, 6, false);
    state.players[pp].prize.values[prize_index] = hand_ref;
    state.players[hp].hand.values[hand_index] = prize_ref;
    state.all_card[prize_ref].reverse = 0;
    state.all_card[hand_ref].reverse = 0;
}

__device__ __noinline__ bool effect_instant_48_55(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    if (effect.effect_type < 48 || effect.effect_type > 55) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    switch (effect.effect_type) {
        case 48:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i)
                if (valid_area_ref_not_prevented(state, rules, runtime.targets[i]))
                    devolve_ref_full(state, runtime, rules, runtime.targets[i].card, (gc_u8)value);
            return true;
        case 49: {
            if (runtime.target_count == 0 || !valid_area_ref_not_prevented(state, rules, runtime.targets[0])) return true;
            const gc_u8 old = runtime.targets[0].card;
            const CardState before = state.all_card[old];
            const gc_i32 p = before.player_index;
            const gc_u8 area = before.area;
            const gc_i32 index = p >= 0 && p <= 1 ? current_area_index(state.players[p], area, old) : -1;
            devolve_ref_full(state, runtime, rules, old, 2);
            if (p >= 0 && p <= 1 && index >= 0) {
                const gc_u8 current = area_ref_at(state, p, area, index);
                if (current && is_evolved_full(state, current)) {
                    state.context_card = current;
                    set_select_full(state, runtime, kSelectYesNo, kSelectContextMoreDevolve, effect_player_index(state));
                    add_option_yes_no(runtime);
                    runtime.pending_effect_kind = kPendingMoreDevolve;
                    runtime.pending_effect_arg0 = current;
                }
            }
            return true;
        }
        case 50:
        case 51:
            if (state.selected_list.count > 0) {
                const gc_u8 replacement = state.selected_list.values[0];
                for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                    if (!valid_area_ref(state, runtime.targets[i])) continue;
                    transform_proc_full(state, runtime, rules, runtime.targets[i].card, replacement, effect.effect_type == 50);
                    break;
                }
            }
            return true;
        case 52:
            exchange_selected_full(state, runtime);
            return true;
        case 53:
        case 54:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                CardTurnFields& f = card_turn(state.all_card[runtime.targets[i].card]);
                if (effect.effect_type == 53)
                    f.fields.ko_prize_change_always = clamp_i8((gc_i32)f.fields.ko_prize_change_always + value, -128, 127);
                else
                    f.fields.ko_prize_change = clamp_i8((gc_i32)f.fields.ko_prize_change + value, -128, 127);
            }
            return true;
        case 55:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                if (!valid_area_ref(state, runtime.targets[i])) continue;
                CardState& c = state.all_card[runtime.targets[i].card];
                if (c.player_index < 0 || c.player_index > 1) continue;
                PlayerState& p = state.players[c.player_index];
                if (!p.ko_prize_once_changed) {
                    p.ko_prize_once_changed = 1;
                    card_turn(c).fields.ko_prize_decrease_once = true;
                }
            }
            return true;
    }
    return true;
}

}  // namespace gpu_cabt
