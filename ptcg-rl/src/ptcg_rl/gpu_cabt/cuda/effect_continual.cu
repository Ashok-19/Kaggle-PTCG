namespace gpu_cabt {

__device__ __forceinline__ bool no_effect_active(
    const BattleCoreState& state,
    gc_i32 player_index,
    gc_u8 effect_card_ref
) {
    const PlayerState& player = state.players[player_index];
    if (player.active.count > 0 && effect_card_ref != 0) {
        if (state.all_card[effect_card_ref].area != 7) {
            if (card_continual(state.all_card[player.active.values[0]]).fields.no_enemy_ability) return true;
        }
    }
    return false;
}

__device__ __noinline__ void effect_continual(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    const RuleEffect& effect,
    const AreaRefState* target_list_ref,
    gc_i32 target_count,
    gc_i32 effect_player,
    gc_u8 effect_card_ref
) {
    const gc_i32 value = effect_value(state, runtime, effect, 0);
    switch (effect.effect_type) {
        case 171: break;
        case 172:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.hp_change=clamp_i16_add(f.hp_change,value); }
            break;
        case 173:
            for (gc_i32 i=0;i<target_count;++i) { gc_u8 r=target_list_ref[i].card; auto& f=card_continual(state.all_card[r]).fields; gc_i32 n=attached_energy_type_count(state,rules,state.all_card[r].player_index,r,kEnergyFighting); f.hp_change=clamp_i16_add(f.hp_change,n*value); }
            break;
        case 174:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change=clamp_i16_add(f.damage_change,value); }
            break;
        case 175:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change_active=clamp_i16_add(f.damage_change_active,value); }
            break;
        case 176:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change_ex=clamp_i16_add(f.damage_change_ex,value); }
            break;
        case 177:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change_ability=clamp_i16_add(f.damage_change_ability,value); }
            break;
        case 178:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change_evolved=clamp_i16_add(f.damage_change_evolved,value); }
            break;
        case 179:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.damage_change_enemy_taken_prize=clamp_i16_add(f.damage_change_enemy_taken_prize,value); }
            break;
        case 180:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.take_damage_change=clamp_i16_add(f.take_damage_change,value); }
            break;
        case 181:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.take_enemy_attack_damage_change=clamp_i16_add(f.take_enemy_attack_damage_change,value); }
            break;
        case 182:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.take_enemy_ability_pokemon_attack_damage_change=clamp_i16_add(f.take_enemy_ability_pokemon_attack_damage_change,value); }
            break;
        case 183:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.take_enemy_fire_or_water_pokemon_attack_damage_change=clamp_i16_add(f.take_enemy_fire_or_water_pokemon_attack_damage_change,value); }
            break;
        case 184:
            for (gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.take_enemy4_type_pokemon_attack_damage_change=clamp_i16_add(f.take_enemy4_type_pokemon_attack_damage_change,value); }
            break;
        case 185:
            for (gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_greater_equal=(gc_i16)value;
            break;
        case 186:
            for (gc_i32 i=0;i<target_count;++i) { auto& x=card_continual(state.all_card[target_list_ref[i].card]).fields.retreat_cost_change; x=clamp_i8((gc_i32)x+value,-100,100); }
            break;
        case 187:
            for (gc_i32 i=0;i<target_count;++i) { auto& x=card_continual(state.all_card[target_list_ref[i].card]).fields.attack_cost_change_colorless; x=clamp_i8((gc_i32)x+value,-100,100); }
            break;
        case 188:
            for (gc_i32 i=0;i<target_count;++i) { auto& x=card_continual(state.all_card[target_list_ref[i].card]).fields.attack_cost_down; x=clamp_i8((gc_i32)x+value,0,100); }
            break;
        case 189:
            if (effect_card_ref!=0) { auto& x=card_continual(state.all_card[effect_card_ref]).fields.attack_cost_change_colorless; x=clamp_i8((gc_i32)x-target_count,-100,100); }
            break;
        case 190:
            for (gc_i32 i=0;i<target_count;++i) { auto& x=card_continual(state.all_card[target_list_ref[i].card]).fields.attack_cost_down_colorless_own_attack; x=clamp_i8((gc_i32)x+6-state.players[1-effect_player].prize.count,0,100); }
            break;
        case 191:
            for (gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.type_index=(gc_i8)value;
            break;
        case 192:
            for (gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.weakness_index=(gc_i8)value;
            break;
        case 193:
            for (gc_i32 i=0;i<target_count;++i) {
                gc_u8 r=target_list_ref[i].card; CardState& card=state.all_card[r]; card_continual(card).fields.no_ability=true;
                for (gc_i32 j=0;j<state.current_card_effect_index && j<(gc_i32)runtime.card_effect_count;++j) {
                    if (runtime.card_effects[j].ref==r && state.current_card_effect_index<(gc_i32)runtime.card_effect_count) {
                        gc_u8 current=runtime.card_effects[state.current_card_effect_index].ref;
                        card.skill_order=state.all_card[current].skill_order+1; state.update_order=true;
                    }
                }
            }
            break;
        case 194: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_ko_me_ability=true; break;
        case 195: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_enemy_attack=true; break;
        case 196: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_enemy_ability_pokemon_attack=true; break;
        case 197: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_enemy_ex_attack=true; break;
        case 198: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_enemy_basic_ex_attack=true; break;
        case 199: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_and_effect_enemy_terastal_attack=true; break;
        case 200: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_and_effect_enemy_special_energy_attack=true; break;
        case 201: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_effect_enemy_attack=true; break;
        case 202: for(gc_i32 i=0;i<target_count;++i) { auto& f=card_continual(state.all_card[target_list_ref[i].card]).fields; f.no_damage_enemy_attack=true; f.no_effect_enemy_attack=true; } break;
        case 203: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_effect_enemy_item=true; break;
        case 204: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_effect_enemy_supporter=true; break;
        case 205: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_counter_enemy_attack_ability=true; break;
        case 206: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_enemy_ability=true; break;
        case 207: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_special_condition=true; break;
        case 208: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_sleep_paralyze_confuse=true; break;
        case 209: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_sleep=true; break;
        case 210: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_retreat_cost=true; break;
        case 211: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_prize_ex=true; break;
        case 212: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.not_recover_confuse_evolve=true; break;
        case 213: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.can_use_pre_evolution_attack=true; break;
        case 214: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.can_evolve_appear_turn=true; break;
        case 215: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.can_evolve_grass_appear_turn=true; break;
        case 216: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.can_attack_first=true; break;
        case 217: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.cannot_retreat=true; break;
        case 218: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.cannot_attack=true; break;
        case 219: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.cannot_to_hand=true; break;
        case 220: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.cannot_move_damage_counter=true; break;
        case 221: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.attack_energy_colorless_one=true; break;
        case 222: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.attack_energy_psychic_one=true; break;
        case 223: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.double_grass_energy=true; break;
        case 224: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.no_damage_coin=true; break;
        case 225: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.ko_by_damage_to_hand=true; break;
        case 226: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.basic_prize_plus1=true; break;
        case 227: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.double_attack=true; break;
        case 228: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.tool2=true; break;
        case 229: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.tool4=true; break;
        case 230: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.technical_machine=true; break;
        case 231: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.special_flag_tool=true; break;
        case 232: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.rainbow_dna=true; break;
        case 233: for(gc_i32 i=0;i<target_count;++i) card_continual(state.all_card[target_list_ref[i].card]).fields.can_play=true; break;
        case 234:
        case 235:
        case 236:
        case 237:
        case 238:
        case 239:
        case 240:
        case 241:
        case 242:
        case 243: {
            for (gc_i32 slot=0;slot<2;++slot) {
                const gc_i32 p=target_player_count(effect.target,effect_player,slot); if(p<0) continue;
                if ((effect.effect_type==234 || effect.effect_type==235 || effect.effect_type==236) && no_effect_active(state,p,effect_card_ref)) continue;
                auto& f=player_continual(state.players[p]).fields;
                switch(effect.effect_type) {
                    case 234: f.poison_damage_change=(gc_i16)((gc_i32)f.poison_damage_change+value); break;
                    case 235: f.burn_damage_change=(gc_i16)((gc_i32)f.burn_damage_change+value); break;
                    case 236: f.poison_damage_change_not_darkness=(gc_i8)((gc_i32)f.poison_damage_change_not_darkness+value); break;
                    case 237: if(f.bench_capacity==0 || f.bench_capacity>value) f.bench_capacity=(gc_u8)value; break;
                    case 238: f.cannot_play_item=true; break;
                    case 239: f.cannot_play_stadium=true; break;
                    case 240: f.cannot_play_tool=true; break;
                    case 241: f.cannot_play_ace_spec=true; break;
                    case 242: f.cannot_play_ability_pokemon_not_rocket=true; break;
                    case 243: f.cannot_trash_to_hand_ability_or_trainers=true; break;
                }
            }
            break;
        }
        case 244: state_continual(state).fields.no_tool_effect=true; break;
        default: runtime.error_flags |= kRuntimeErrorUnsupportedTransition; break;
    }
}

}  // namespace gpu_cabt
