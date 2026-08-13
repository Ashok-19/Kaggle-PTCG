extern "C" __global__ void gpu_cabt_state_layout_probe(gc_u64* output) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;

    output[0] = sizeof(gpu_cabt::AreaRef);
    output[1] = sizeof(gpu_cabt::ActivateAbilityInfo);
    output[2] = sizeof(gpu_cabt::TriggerInfo);
    output[3] = sizeof(gpu_cabt::EffectState);
    output[4] = sizeof(gpu_cabt::TurnHistory);
    output[5] = sizeof(gpu_cabt::CardState);
    output[6] = sizeof(gpu_cabt::PlayerState);
    output[7] = sizeof(gpu_cabt::BattleCoreState);

    output[8] = (gc_u64)(&(((gpu_cabt::BattleCoreState*)0)->players));
    output[9] = (gc_u64)(&(((gpu_cabt::BattleCoreState*)0)->all_card));
    output[10] = (gc_u64)(&(((gpu_cabt::BattleCoreState*)0)->effect_state));
    output[11] = (gc_u64)(&(((gpu_cabt::BattleCoreState*)0)->select_counts));
    output[12] = (gc_u64)(&(((gpu_cabt::CardState*)0)->continual_state));
    output[13] = (gc_u64)(&(((gpu_cabt::PlayerState*)0)->deck));
}

extern "C" __global__ void gpu_cabt_fill_core_state_pattern(
    unsigned char* raw_states,
    gc_i32 state_size,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    unsigned char* row = raw_states + (gc_i64)env_index * state_size;
    for (gc_i32 offset = 0; offset < state_size; ++offset) {
        row[offset] = (gc_u8)((offset * 131 + env_index * 17 + 23) & 0xFF);
    }
}
