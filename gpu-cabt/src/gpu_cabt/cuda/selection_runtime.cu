namespace gpu_cabt {

static constexpr gc_u8 kSelectNone = 0;
static constexpr gc_u8 kSelectMain = 1;
static constexpr gc_u8 kSelectCard = 2;
static constexpr gc_u8 kSelectAttachedCard = 3;
static constexpr gc_u8 kSelectCardOrAttachedCard = 4;
static constexpr gc_u8 kSelectEnergy = 5;
static constexpr gc_u8 kSelectSkill = 6;
static constexpr gc_u8 kSelectAttack = 7;
static constexpr gc_u8 kSelectEvolve = 8;
static constexpr gc_u8 kSelectCount = 9;
static constexpr gc_u8 kSelectYesNo = 10;
static constexpr gc_u8 kSelectSpecialCondition = 11;

static constexpr gc_u8 kSelectContextNone = 0;
static constexpr gc_u8 kSelectContextMain = 1;
static constexpr gc_u8 kSelectContextSetupActivePokemon = 2;
static constexpr gc_u8 kSelectContextSetupBenchPokemon = 3;
static constexpr gc_u8 kSelectContextSwitch = 4;
static constexpr gc_u8 kSelectContextToActive = 5;
static constexpr gc_u8 kSelectContextToBench = 6;
static constexpr gc_u8 kSelectContextToField = 7;
static constexpr gc_u8 kSelectContextToHand = 8;
static constexpr gc_u8 kSelectContextDiscard = 9;
static constexpr gc_u8 kSelectContextToDeck = 10;
static constexpr gc_u8 kSelectContextToDeckBottom = 11;
static constexpr gc_u8 kSelectContextToPrize = 12;
static constexpr gc_u8 kSelectContextNotMove = 13;
static constexpr gc_u8 kSelectContextDamageCounter = 14;
static constexpr gc_u8 kSelectContextDamageCounterAny = 15;
static constexpr gc_u8 kSelectContextDamage = 16;
static constexpr gc_u8 kSelectContextRemoveDamageCounter = 17;
static constexpr gc_u8 kSelectContextHeal = 18;
static constexpr gc_u8 kSelectContextEvolvesFrom = 19;
static constexpr gc_u8 kSelectContextEvolvesTo = 20;
static constexpr gc_u8 kSelectContextDevolve = 21;
static constexpr gc_u8 kSelectContextAttachFrom = 22;
static constexpr gc_u8 kSelectContextAttachTo = 23;
static constexpr gc_u8 kSelectContextDetachFrom = 24;
static constexpr gc_u8 kSelectContextLook = 25;
static constexpr gc_u8 kSelectContextEffectTarget = 26;
static constexpr gc_u8 kSelectContextDiscardEnergyCard = 27;
static constexpr gc_u8 kSelectContextDiscardToolCard = 28;
static constexpr gc_u8 kSelectContextSwitchEnergyCard = 29;
static constexpr gc_u8 kSelectContextDiscardCardOrAttachedCard = 30;
static constexpr gc_u8 kSelectContextDiscardEnergy = 31;
static constexpr gc_u8 kSelectContextToHandEnergy = 32;
static constexpr gc_u8 kSelectContextToDeckEnergy = 33;
static constexpr gc_u8 kSelectContextSwitchEnergy = 34;
static constexpr gc_u8 kSelectContextSkillOrder = 35;
static constexpr gc_u8 kSelectContextAttack = 36;
static constexpr gc_u8 kSelectContextDisableAttack = 37;
static constexpr gc_u8 kSelectContextEvolve = 38;
static constexpr gc_u8 kSelectContextDrawCount = 39;
static constexpr gc_u8 kSelectContextDamageCounterCount = 40;
static constexpr gc_u8 kSelectContextRemoveDamageCounterCount = 41;
static constexpr gc_u8 kSelectContextIsFirst = 42;
static constexpr gc_u8 kSelectContextMulligan = 43;
static constexpr gc_u8 kSelectContextActivate = 44;
static constexpr gc_u8 kSelectContextFirstEffect = 45;
static constexpr gc_u8 kSelectContextMoreDevolve = 46;
static constexpr gc_u8 kSelectContextCoinHead = 47;
static constexpr gc_u8 kSelectContextAffectSpecialCondition = 48;
static constexpr gc_u8 kSelectContextRecoverSpecialCondition = 49;

static constexpr gc_u8 kOptionNumber = 0;
static constexpr gc_u8 kOptionYes = 1;
static constexpr gc_u8 kOptionNo = 2;
static constexpr gc_u8 kOptionCard = 3;
static constexpr gc_u8 kOptionToolCard = 4;
static constexpr gc_u8 kOptionEnergyCard = 5;
static constexpr gc_u8 kOptionEnergy = 6;
static constexpr gc_u8 kOptionPlay = 7;
static constexpr gc_u8 kOptionAttach = 8;
static constexpr gc_u8 kOptionEvolve = 9;
static constexpr gc_u8 kOptionAbility = 10;
static constexpr gc_u8 kOptionDiscard = 11;
static constexpr gc_u8 kOptionRetreat = 12;
static constexpr gc_u8 kOptionAttack = 13;
static constexpr gc_u8 kOptionEnd = 14;
static constexpr gc_u8 kOptionSkill = 15;
static constexpr gc_u8 kOptionSpecialCondition = 16;

__device__ __forceinline__ void clear_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime
) {
    state.select_type = kSelectNone;
    state.select_deck = 0;
    state.context_card = 0;
    runtime.option_count = 0;
    runtime.selected_count = 0;
}

__device__ __forceinline__ void set_select_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 type,
    gc_u8 context,
    gc_i32 player_index,
    gc_i32 minimum = 1,
    gc_i32 maximum = 1
) {
    runtime.option_count = 0;
    runtime.selected_count = 0;
    state.select_type = type;
    state.select_context = context;
    state.select_player = (gc_i8)player_index;
    state.select_min = minimum;
    state.select_max = maximum;
}

__device__ __forceinline__ SelectOptionState* add_option_full(
    BattleRuntimeState& runtime,
    gc_u8 type
) {
    if (runtime.option_count >= kOptionCapacity) {
        runtime.error_flags |= kRuntimeErrorOptionOverflow;
        return nullptr;
    }
    SelectOptionState* option = &runtime.options[runtime.option_count++];
    *option = {};
    option->type = type;
    return option;
}

__device__ __forceinline__ void add_option_yes_no(BattleRuntimeState& runtime) {
    add_option_full(runtime, kOptionYes);
    add_option_full(runtime, kOptionNo);
}

__device__ __forceinline__ void add_option_number(BattleRuntimeState& runtime, gc_i32 number) {
    SelectOptionState* option = add_option_full(runtime, kOptionNumber);
    if (option != nullptr) option->param0 = (gc_i16)number;
}

__device__ __forceinline__ void add_option_card(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_i32 player_index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionCard);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)player_index;
}

__device__ __forceinline__ void add_option_tool_card(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_i32 player_index,
    gc_i32 tool_index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionToolCard);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)player_index;
    option->param3 = (gc_i16)tool_index;
}

__device__ __forceinline__ void add_option_energy_card(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_i32 player_index,
    gc_i32 energy_index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionEnergyCard);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)player_index;
    option->param3 = (gc_i16)energy_index;
}

__device__ __forceinline__ void add_option_energy(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_i32 player_index,
    gc_i32 energy_index,
    gc_i32 count
) {
    SelectOptionState* option = add_option_full(runtime, kOptionEnergy);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)player_index;
    option->param3 = (gc_i16)energy_index;
    option->param4 = (gc_i16)count;
}

__device__ __forceinline__ void add_option_play(BattleRuntimeState& runtime, gc_i32 index) {
    SelectOptionState* option = add_option_full(runtime, kOptionPlay);
    if (option != nullptr) option->param0 = (gc_i16)index;
}

__device__ __forceinline__ void add_option_attach(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_u8 in_play_area,
    gc_i32 in_play_index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionAttach);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)in_play_area;
    option->param3 = (gc_i16)in_play_index;
}

__device__ __forceinline__ void add_option_evolve(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index,
    gc_u8 in_play_area,
    gc_i32 in_play_index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionEvolve);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
    option->param2 = (gc_i16)in_play_area;
    option->param3 = (gc_i16)in_play_index;
}

__device__ __forceinline__ void add_option_ability(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionAbility);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
}

__device__ __forceinline__ void add_option_discard(
    BattleRuntimeState& runtime,
    gc_u8 area,
    gc_i32 index
) {
    SelectOptionState* option = add_option_full(runtime, kOptionDiscard);
    if (option == nullptr) return;
    option->param0 = (gc_i16)area;
    option->param1 = (gc_i16)index;
}

__device__ __forceinline__ void add_option_retreat(BattleRuntimeState& runtime) {
    add_option_full(runtime, kOptionRetreat);
}

__device__ __forceinline__ void add_option_attack(
    BattleRuntimeState& runtime,
    gc_i32 attack_id,
    gc_i32 src_attack_id,
    gc_i32 bench_index = -1
) {
    SelectOptionState* option = add_option_full(runtime, kOptionAttack);
    if (option == nullptr) return;
    option->param0 = (gc_i16)attack_id;
    option->param1 = (gc_i16)src_attack_id;
    option->param2 = (gc_i16)bench_index;
}

__device__ __forceinline__ void add_option_end(BattleRuntimeState& runtime) {
    add_option_full(runtime, kOptionEnd);
}

__device__ __forceinline__ void add_option_special_condition(
    BattleRuntimeState& runtime,
    gc_i32 condition
) {
    SelectOptionState* option = add_option_full(runtime, kOptionSpecialCondition);
    if (option != nullptr) option->param0 = (gc_i16)condition;
}

__device__ __forceinline__ void add_option_skill_order(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_u8 ref
) {
    SelectOptionState* option = add_option_full(runtime, kOptionSkill);
    if (option == nullptr || ref == 0) return;
    option->param0 = (gc_i16)state.all_card[ref].card_id;
    option->param1 = (gc_i16)ref;
}

__device__ __forceinline__ bool card_position_for_ref(
    const BattleCoreState& state,
    gc_u8 ref,
    gc_u8& area,
    gc_i32& index,
    gc_i32& player_index
) {
    if (ref == 0 || ref >= kAllCardCapacity) return false;
    const CardState& card = state.all_card[ref];
    player_index = card.player_index;
    area = card.area;
    if (player_index >= 0 && player_index <= 1) {
        index = current_area_index(state.players[player_index], area, ref);
        if (index >= 0) return true;
    }
    if (area == 7) {
        for (gc_i32 i = 0; i < (gc_i32)state.stadium.count; ++i) {
            if (state.stadium.values[i] == ref) { index = i; return true; }
        }
    } else if (area == 12) {
        for (gc_i32 i = 0; i < (gc_i32)state.looking.count; ++i) {
            if (state.looking.values[i] == ref) { index = i; return true; }
        }
    } else if (area == 13) {
        for (gc_i32 i = 0; i < (gc_i32)state.playing.count; ++i) {
            if (state.playing.values[i] == ref) { index = i; return true; }
        }
    }
    index = -1;
    return false;
}

__device__ __forceinline__ bool selected_index_valid(
    const BattleRuntimeState& runtime,
    gc_i32 selected_index
) {
    return selected_index >= 0 && selected_index < (gc_i32)runtime.option_count;
}

__device__ __forceinline__ SelectOptionState selected_option(
    const BattleRuntimeState& runtime,
    gc_i32 selected_slot
) {
    if (selected_slot < 0 || selected_slot >= (gc_i32)runtime.selected_count) return {};
    const gc_i32 option_index = runtime.selected[selected_slot];
    if (!selected_index_valid(runtime, option_index)) return {};
    return runtime.options[option_index];
}

__device__ __forceinline__ bool selected_yes(const BattleRuntimeState& runtime) {
    return runtime.selected_count > 0 && selected_option(runtime, 0).type == kOptionYes;
}

__device__ __forceinline__ gc_i32 selected_number(const BattleRuntimeState& runtime) {
    return runtime.selected_count > 0 ? selected_option(runtime, 0).param0 : 0;
}

}  // namespace gpu_cabt
