namespace gpu_cabt {

__device__ __forceinline__ void deck_to_trash_full(
    BattleCoreState& state, BattleRuntimeState& runtime, const RuleTableView& rules,
    const RuleEffect& effect, gc_i32 count, bool bottom
) {
    runtime.target_count=0; const gc_i32 owner=effect_player_index(state);
    for(gc_i32 p=0;p<2;++p){if(!is_target_player(owner,p,effect.target.target_player))continue;for(gc_i32 n=0;n<count;++n){PlayerState& ps=state.players[p];if(ps.deck.count==0)break;const gc_i32 index=bottom?0:(gc_i32)ps.deck.count-1;state.changed=true;gc_u8 ref=move_card_full(state,runtime,rules,p,1,index,3,0,false,false,false);if(ref&&runtime.target_count<kAreaRefCapacity)runtime.targets[runtime.target_count++]=make_area_ref(state,ref);else if(runtime.target_count>=kAreaRefCapacity)runtime.error_flags|=kRuntimeErrorTargetOverflow;}}
}

__device__ __noinline__ bool effect_instant_111_135(
    BattleCoreState& state, BattleRuntimeState& runtime, const RuleTableView& rules, const RuleEffect& effect
) {
    if(effect.effect_type<111||effect.effect_type>135)return false;
    const gc_i32 v=effect_value(state,runtime,effect,0), owner=effect_player_index(state);
    switch(effect.effect_type){
        case 111: deck_to_trash_full(state,runtime,rules,effect,v,false); return true;
        case 112: select_coin_until_tail_full(state,runtime); deck_to_trash_full(state,runtime,rules,effect,state.coin_head_count,false); return true;
        case 113: deck_to_trash_full(state,runtime,rules,effect,v,true); return true;
        case 114: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)){state.changed=true;for(gc_i32 n=0;n<v&&state.players[p].deck.count;++n){gc_u8 r=move_card_full(state,runtime,rules,p,1,(gc_i32)state.players[p].deck.count-1,6,0,false,false,false);if(r)state.all_card[r].reverse=1;}}return true;
        case 115: for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player))shuffle_player_deck(state,runtime,p);return true;
        case 116:
            for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)){
                state.changed=true;
                state.game_result=(gc_u8)(p+1);
                state.finish_reason=4;
                log_result(runtime,(gc_i32)state.game_result-1,4);
                break;
            }
            return true;
        case 117: state.fail_retreat=1; return true;
        case 118: state.changed=true;state_turn(state).fields.turn_end=true;return true;
        case 119: case 120:
            for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(!valid_area_ref_not_prevented(state,rules,r))continue;auto& f=card_turn(state.all_card[r.card]).fields;if(effect.effect_type==119)f.damage_change_this_turn=clamp_i16_add(f.damage_change_this_turn,v);else f.damage_change_ex_this_turn=clamp_i16_add(f.damage_change_ex_this_turn,v);}return true;
        case 121: case 122: case 123: case 124: case 125:
            for(gc_i32 p=0;p<2;++p)if(is_target_player(owner,p,effect.target.target_player)){auto& f=player_turn(state.players[p]).fields;if(effect.effect_type==121)f.player_damage_change=clamp_i16_add(f.player_damage_change,v);else if(effect.effect_type==122)f.player_damage_change_ex=clamp_i16_add(f.player_damage_change_ex,v);else if(effect.effect_type==123)f.player_damage_change_my_fighting=clamp_i16_add(f.player_damage_change_my_fighting,v);else if(effect.effect_type==124)f.take_prize_count_change_terastal_attack_ko_active=clamp_i8((gc_i32)f.take_prize_count_change_terastal_attack_ko_active+v,-128,127);else f.take_prize_count_change_n_attack_ko_active=clamp_i8((gc_i32)f.take_prize_count_change_n_attack_ko_active+v,-128,127);}return true;
        case 126:
            for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(valid_area_ref_not_prevented(state,rules,r)){auto& f=card_next_enemy_turn_end(state.all_card[r.card]).fields;f.take_damage_change_next_enemy_turn=clamp_i16_add(f.take_damage_change_next_enemy_turn,v);}}return true;
        case 127:
            for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(valid_area_ref_not_prevented(state,rules,r)){auto& x=card_next_enemy_turn_end(state.all_card[r.card]).fields.no_damage_less_equal_attack_next_enemy_turn;if(x<v)x=(gc_u8)v;}}return true;
        case 128: case 129: case 131: case 132: case 133: case 134: case 135:
            for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(!valid_area_ref_not_prevented(state,rules,r))continue;auto& f=card_next_enemy_turn_end(state.all_card[r.card]).fields;if(effect.effect_type==128)f.no_damage_and_effect_attack_next_enemy_turn=true;else if(effect.effect_type==129)f.no_damage_and_effect_enemy_attack_next_enemy_turn=true;else if(effect.effect_type==131)f.no_damage_attack_next_enemy_turn=true;else if(effect.effect_type==132)f.no_damage_basic_attack_next_enemy_turn=true;else if(effect.effect_type==133)f.no_damage_basic_color_attack_next_enemy_turn=true;else if(effect.effect_type==134)f.no_damage_ability_attack_next_enemy_turn=true;else f.no_weakness_next_enemy_turn=true;}return true;
        case 130:
            for(gc_i32 i=0;i<(gc_i32)runtime.target_count;++i){const AreaRefState r=runtime.targets[i];if(valid_area_ref_not_prevented(state,rules,r))card_next_enemy_battle_field(state.all_card[r.card]).fields.no_damage_and_effect_enemy_ex_attack_next_enemy_turn=true;}return true;
    }
    return true;
}

}  // namespace gpu_cabt
