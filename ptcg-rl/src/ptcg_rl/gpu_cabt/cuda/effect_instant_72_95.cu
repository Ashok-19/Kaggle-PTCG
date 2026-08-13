namespace gpu_cabt {

__device__ __forceinline__ gc_i32 target_energy_count_full(
    const BattleCoreState& state, const BattleRuntimeState& runtime, const RuleTableView& rules
) {
    gc_i32 count = 0;
    for (gc_i32 i=0;i<(gc_i32)runtime.target_count;++i) {
        const AreaRefState r=runtime.targets[i]; if(!valid_area_ref(state,r))continue;
        const CardState& c=state.all_card[r.card];
        count += attached_energy_count(state,rules,c.player_index,r.card);
    }
    return count;
}

__device__ __forceinline__ gc_i32 target_type_energy_count_full(
    const BattleCoreState& state, const BattleRuntimeState& runtime, const RuleTableView& rules, gc_u16 type
) {
    gc_i32 count=0;
    for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(!valid_area_ref(state,r))continue;const CardState& c=state.all_card[r.card];count+=attached_energy_type_count(state,rules,c.player_index,r.card,type);}
    return count;
}

__device__ __noinline__ bool effect_instant_72_95(
    BattleCoreState& state, BattleRuntimeState& runtime, const RuleTableView& rules, const RuleEffect& effect
) {
    if(effect.effect_type<72||effect.effect_type>95)return false;
    const gc_i32 v=effect_value(state,runtime,effect,0), v2=effect_value(state,runtime,effect,1);
    switch(effect.effect_type){
        case 72: select_coin_until_tail_full(state,runtime); if(v==1&&state.coin_head_count==0)state.effect_jump=99; return true;
        case 73: state.attack_damage_change=v; return true;
        case 74: state.attack_damage_change=v*(gc_i32)runtime.target_count; return true;
        case 75: state.effect_state.damage_change=v*(gc_i32)runtime.target_count; return true;
        case 76: state.attack_damage_change=v*target_energy_count_full(state,runtime,rules); return true;
        case 77: state.effect_state.damage_change=v*target_energy_count_full(state,runtime,rules); return true;
        case 78: state.attack_damage_change=v2*target_type_energy_count_full(state,runtime,rules,(gc_u16)v); return true;
        case 79: state.effect_state.damage_change=v2*target_type_energy_count_full(state,runtime,rules,(gc_u16)v); return true;
        case 80: select_coin_full(state,runtime,target_energy_count_full(state,runtime,rules)); state.attack_damage_change=v*state.coin_head_count; return true;
        case 81: select_coin_full(state,runtime,target_type_energy_count_full(state,runtime,rules,(gc_u16)v)); state.attack_damage_change=v2*state.coin_head_count; return true;
        case 82: select_coin_full(state,runtime,v); state.attack_damage_change=v2*state.coin_head_count; return true;
        case 83: select_coin_until_tail_full(state,runtime); state.attack_damage_change=v*state.coin_head_count; return true;
        case 84: select_coin_full(state,runtime,(gc_i32)runtime.target_count); state.attack_damage_change=v*state.coin_head_count; return true;
        case 85: select_coin_full(state,runtime,(gc_i32)runtime.target_count); state.attack_damage_change=v*((gc_i32)runtime.target_count-state.coin_head_count); return true;
        case 86: case 87: {gc_i32 n=0,o=effect_player_index(state);for(gc_i32 p=0;p<2;++p)if(is_target_player(o,p,effect.target.target_player))n+=taken_prize_count(state,p);if(effect.effect_type==86)state.attack_damage_change=v*n;else state.effect_state.damage_change=v*n;return true;}
        case 88: case 89: {gc_i32 n=0;for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i)if(valid_area_ref(state,runtime.targets[i]))n+=v*state.all_card[runtime.targets[i].card].damage/10;if(effect.effect_type==88)state.attack_damage_change=n;else state.effect_state.damage_change=n;return true;}
        case 90:
            set_select_full(state,runtime,kSelectCount,kSelectContextDamageCounterCount,effect_player_index(state));for(gc_i32 i=0;i<=v;++i)add_option_number(runtime,i);runtime.pending_effect_kind=kPendingAttackDamagePutCounter;runtime.pending_effect_arg0=v2;return true;
        case 91: {gc_i32 n=0;for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(!valid_area_ref(state,r))continue;const CardState& c=state.all_card[r.card];const RuleCardMaster* m=rule_card(rules,c.card_id);if(m)n+=v*retreat_cost(c,*m);}state.attack_damage_change=n;return true;}
        case 92: {gc_u32 types=0;for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i)if(valid_area_ref(state,runtime.targets[i])){const RuleCardMaster* m=rule_card(rules,state.all_card[runtime.targets[i].card].card_id);if(m)types|=m->energy_type;}state.attack_damage_change=v*(gc_i32)__popc(types);return true;}
        case 93: {gc_i32 n=0,o=effect_player_index(state);for(gc_i32 p=0;p<2;++p)if(is_target_player(o,p,effect.target.target_player)){const auto& a=player_active_state(state.players[p]).fields;if(a.poison_damage_counter)n++;if(a.burned)n++;if(a.bad_status)n++;}state.attack_damage_change=v*n;return true;}
        case 94: {gc_i32 n=0;for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i)if(valid_area_ref(state,runtime.targets[i]))n+=state.all_card[runtime.targets[i].card].take_attack_damage_pre_turn;state.attack_damage_change=n;return true;}
        case 95: state.attack_damage_change=v*state.turn_histories[1].take_prize_count_turn_player; return true;
    }
    return true;
}

}  // namespace gpu_cabt
