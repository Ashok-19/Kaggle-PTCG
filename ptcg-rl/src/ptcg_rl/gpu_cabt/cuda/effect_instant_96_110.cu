namespace gpu_cabt {

__device__ __forceinline__ void effect_targets_status(
    BattleCoreState& state, BattleRuntimeState& runtime, const RuleTableView& rules,
    const RuleEffect& effect, gc_i32 kind, gc_i32 poison_count = 1
) {
    if (runtime.target_count > 0) {
        const AreaRefState r = runtime.targets[0];
        if (valid_area_ref(state,r) && state.all_card[r.card].area == kAreaActive) {
            const gc_i32 p=state.all_card[r.card].player_index;
            if(kind==0)effect_burn(state,runtime,rules,p);else if(kind==1)effect_poison(state,runtime,rules,p,poison_count);else if(kind==2)effect_sleep(state,runtime,rules,p);
        }
        return;
    }
    const gc_i32 owner=effect_player_index(state);
    for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)){
        if(kind==0)effect_burn(state,runtime,rules,p);else if(kind==1)effect_poison(state,runtime,rules,p,poison_count);else if(kind==2)effect_sleep(state,runtime,rules,p);
    }
}

__device__ __noinline__ bool effect_instant_96_110(
    BattleCoreState& state, BattleRuntimeState& runtime, const RuleTableView& rules, const RuleEffect& effect
) {
    if(effect.effect_type<96||effect.effect_type>110)return false;
    const gc_i32 v=effect_value(state,runtime,effect,0); const gc_i32 owner=effect_player_index(state);
    switch(effect.effect_type){
        case 96: effect_targets_status(state,runtime,rules,effect,0); return true;
        case 97: effect_targets_status(state,runtime,rules,effect,1,1); return true;
        case 98: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))effect_poison(state,runtime,rules,p,8);return true;
        case 99: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))effect_poison(state,runtime,rules,p,16);return true;
        case 100: effect_targets_status(state,runtime,rules,effect,2); return true;
        case 101: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))effect_confuse(state,runtime,rules,p);return true;
        case 102: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))effect_paralyze(state,runtime,rules,p);return true;
        case 103:
            for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)&&!prevent_effect_active(state,rules,p)){state.changed=true;state.players[p].active_state=0;}return true;
        case 104:
            for(gc_i32 p=0;p<2;++p){if(!is_target_player(owner,p,effect.target.target_player)||prevent_effect_active(state,rules,p))continue;auto& a=player_active_state(state.players[p]).fields;state.changed=true;set_select_full(state,runtime,kSelectSpecialCondition,kSelectContextRecoverSpecialCondition,owner);if(a.poison_damage_counter)add_option_special_condition(runtime,0);if(a.burned)add_option_special_condition(runtime,1);if(a.bad_status==1)add_option_special_condition(runtime,2);else if(a.bad_status==2)add_option_special_condition(runtime,3);else if(a.bad_status==3)add_option_special_condition(runtime,4);if(runtime.option_count){runtime.pending_effect_kind=kPendingRecoverSpecialCondition;runtime.pending_effect_arg0=p;}else clear_select_full(state,runtime);break;}return true;
        case 105: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))draw_cards(&state,&runtime,p,v);return true;
        case 106: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))draw_cards(&state,&runtime,p,(gc_i32)runtime.target_count);return true;
        case 107: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))draw_cards(&state,&runtime,p,state.players[p].prize.count);return true;
        case 108: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))draw_cards(&state,&runtime,p,v-(gc_i32)state.players[p].hand.count);return true;
        case 109:
            for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)){gc_i32 n=0;const PlayerState& ps=state.players[p];if(ps.active.count){const gc_u8 r=ps.active.values[0];const RuleCardMaster* m=rule_card(rules,state.all_card[r].card_id);if(m&&contains_energy(get_card_energy_type(state.all_card[r],*m),kEnergyPsychic))++n;}for(gc_i32 i=0;i<(gc_i32)ps.bench.count;++i){const gc_u8 r=ps.bench.values[i];const RuleCardMaster* m=rule_card(rules,state.all_card[r].card_id);if(m&&contains_energy(get_card_energy_type(state.all_card[r],*m),kEnergyPsychic))++n;}draw_cards(&state,&runtime,p,n-(gc_i32)ps.hand.count);}return true;
        case 110: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))draw_cards(&state,&runtime,p,(gc_i32)state.players[1-p].hand.count-(gc_i32)state.players[p].hand.count);return true;
    }
    return true;
}

}  // namespace gpu_cabt
