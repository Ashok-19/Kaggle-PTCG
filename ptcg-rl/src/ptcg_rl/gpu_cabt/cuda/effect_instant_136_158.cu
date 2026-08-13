namespace gpu_cabt {

__device__ __noinline__ bool effect_instant_136_158(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect
) {
    if (effect.effect_type < 136 || effect.effect_type > 158) return false;
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    const gc_i32 owner = effect_player_index(state);
    switch (effect.effect_type) {
        case 136:  // CannotUseThisAttackNextTurn
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                card_next_turn(state.all_card[r.card]).fields.cannot_use_attack_id = (gc_i16)state.current_attack_id;
            }
            return true;
        case 137: case 138: case 139: case 140: case 141:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                auto& f = card_next_turn(state.all_card[r.card]).fields;
                if (effect.effect_type == 137) f.damage_change_my_attack = clamp_i16_add(f.damage_change_my_attack, value);
                else if (effect.effect_type == 138) f.damage_change_active = clamp_i16_add(f.damage_change_active, value);
                else if (effect.effect_type == 139) f.damage_change = clamp_i16_add(f.damage_change, value);
                else if (effect.effect_type == 140) f.attack_cost_change = clamp_i8((gc_i32)f.attack_cost_change + value, -100, 100);
                else f.retreat_cost_change = clamp_i8((gc_i32)f.retreat_cost_change + value, -100, 100);
            }
            return true;
        case 142: case 143: case 144: case 145: case 146: case 147:
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                auto& f = card_next_turn(state.all_card[r.card]).fields;
                if (effect.effect_type == 142) f.cannot_retreat = true;
                else if (effect.effect_type == 143) f.cannot_hand_attach_energy = true;
                else if (effect.effect_type == 144) f.cannot_attack = true;
                else if (effect.effect_type == 145) f.cannot_attack_less_equal_energy2 = true;
                else if (effect.effect_type == 146) f.attack_coin = true;
                else f.attack_coin2 = true;
            }
            return true;
        case 148:  // CannotUseSelectedAttack
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                const RuleCardMaster* master = rule_card(rules, state.all_card[r.card].card_id);
                if (master == nullptr) continue;
                clear_select_full(state, runtime);
                set_select_full(state, runtime, kSelectAttack, kSelectContextDisableAttack, owner);
                for (gc_i32 j = 0; j < kRuleCardAttackCapacity; ++j) {
                    const gc_i32 attack_id = master->attack_ids[j];
                    if (attack_id > 0) add_option_attack(runtime, attack_id, attack_id);
                }
                if (runtime.option_count != 0) {
                    runtime.pending_effect_kind = kPendingDisableAttack;
                    runtime.pending_effect_arg0 = r.card;
                    runtime.pending_effect_arg1 = i;
                    return true;
                }
            }
            return true;
        case 149: case 150: case 151: case 152: case 153: case 154: case 155: case 156:
            for (gc_i32 p = 0; p < 2; ++p) {
                if (!is_target_player(owner, p, effect.target.target_player)) continue;
                auto& f = player_next_turn(state.players[p]).fields;
                if (effect.effect_type == 149) f.metal_damage_change = clamp_i16_add(f.metal_damage_change, value);
                else if (effect.effect_type == 150) f.cannot_attack_less_equal_energy2 = true;
                else if (effect.effect_type == 151) f.cannot_play_item = true;
                else if (effect.effect_type == 152) f.cannot_play_supporter = true;
                else if (effect.effect_type == 153) f.cannot_play_stadium = true;
                else if (effect.effect_type == 154) f.cannot_play_special_energy = true;
                else if (effect.effect_type == 155) f.cannot_evolve = true;
                else f.cannot_retreat_poison = true;
            }
            return true;
        case 157:  // TakeDamageChangeNextMyTurnEnemy
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                card_next_turn_enemy(state.all_card[r.card]).fields.take_damage_change = (gc_i16)value;
            }
            return true;
        case 158:  // CannotUseThisAttackNonActive
            for (gc_i32 i = 0; i < (gc_i32)runtime.target_count; ++i) {
                const AreaRefState r = runtime.targets[i];
                if (!valid_area_ref_not_prevented(state, rules, r)) continue;
                state.all_card[r.card].cannot_use_attack_id_non_active = (gc_i16)state.current_attack_id;
            }
            return true;
    }
    return true;
}

}  // namespace gpu_cabt
