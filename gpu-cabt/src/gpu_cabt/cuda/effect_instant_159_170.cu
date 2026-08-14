namespace gpu_cabt {

__device__ __noinline__ bool effect_instant_159_170(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    if (effect.effect_type < 159 || effect.effect_type > 170) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    const gc_i32 value2 = effect_value(state, runtime, effect, 1);
    const gc_i32 owner = effect_player_index(state);
    switch (effect.effect_type) {
        case 159:  // SelectActivate
            set_select_full(state, runtime, kSelectYesNo, kSelectContextActivate, owner);
            add_option_yes_no(runtime);
            runtime.pending_effect_kind = kPendingSelectActivate;
            return true;
        case 160:  // SelectEffect
            set_select_full(state, runtime, kSelectYesNo, kSelectContextFirstEffect, owner);
            add_option_yes_no(runtime);
            runtime.pending_effect_kind = kPendingSelectEffect;
            runtime.pending_effect_arg0 = value;
            return true;
        case 161: state.fail_attack = 1; return true;
        case 162: state.fail_attack = 0; return true;
        case 163:
            select_coin_full(state, runtime, 1);
            if (state.coin_head_count != 0) state.effect_jump = 99;
            return true;
        case 164:
            select_coin_full(state, runtime, 1);
            if (state.coin_head_count == 0) state.effect_jump = 99;
            return true;
        case 165:
            select_coin_full(state, runtime, value);
            if (state.coin_head_count < value) state.effect_jump = 99;
            return true;
        case 166:
            select_coin_full(state, runtime, 1);
            if (state.coin_head_count == 0) state.effect_jump = (gc_u8)value;
            (void)value2;
            return true;
        case 167: state.post_effect_activate = 1; return true;
        case 168:
            if (!state.post_effect_activate) state.effect_jump = 99;
            return true;
        case 169:
            set_select_full(state, runtime, kSelectSpecialCondition, kSelectContextAffectSpecialCondition, owner);
            add_option_special_condition(runtime, 0);
            add_option_special_condition(runtime, 1);
            add_option_special_condition(runtime, 4);
            runtime.pending_effect_kind = kPendingSpecialCondition;
            runtime.pending_effect_arg0 = 1 - owner;
            return true;
        case 170:
            set_select_full(state, runtime, kSelectSpecialCondition, kSelectContextAffectSpecialCondition, owner);
            for (gc_i32 c = 0; c < 5; ++c) add_option_special_condition(runtime, c);
            runtime.pending_effect_kind = kPendingSpecialCondition;
            runtime.pending_effect_arg0 = 1 - owner;
            return true;
    }
    (void)rules;
    return true;
}

}  // namespace gpu_cabt
