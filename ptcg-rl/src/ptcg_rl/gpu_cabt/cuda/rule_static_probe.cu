extern "C" __global__ void gpu_cabt_rule_static_probe(
    const gpu_cabt::RuleCardMaster* cards,
    const gpu_cabt::RuleSkill* skills,
    const gpu_cabt::RuleAttack* attacks,
    const gpu_cabt::RuleEffect* effects,
    const gpu_cabt::RuleTrigger* triggers,
    const gc_u32* substring_masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 substring_mask_count,
    gc_i32 substring_mask_words,
    gc_i32* output
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    gc_i32 cursor = 0;
    output[cursor++] = (gc_i32)sizeof(gpu_cabt::RuleCardMaster);
    output[cursor++] = (gc_i32)sizeof(gpu_cabt::RuleSkill);
    output[cursor++] = (gc_i32)sizeof(gpu_cabt::RuleAttack);
    output[cursor++] = (gc_i32)sizeof(gpu_cabt::RuleEffect);
    output[cursor++] = (gc_i32)sizeof(gpu_cabt::RuleTrigger);
    output[cursor++] = card_count;
    output[cursor++] = skill_count;
    output[cursor++] = attack_count;
    output[cursor++] = effect_count;
    output[cursor++] = trigger_count;
    output[cursor++] = substring_mask_count;
    output[cursor++] = substring_mask_words;
    output[cursor++] = cards[1].card_id;
    output[cursor++] = cards[card_count - 1].card_id;
    output[cursor++] = skills[2].skill_id;
    output[cursor++] = skills[skill_count - 1].skill_id;
    output[cursor++] = attacks[1].attack_id;
    output[cursor++] = attacks[attack_count - 1].attack_id;
    output[cursor++] = effects[0].effect_type;
    output[cursor++] = effects[effect_count - 1].effect_type;
    output[cursor++] = trigger_count > 0 ? triggers[0].trigger_type : -1;
    output[cursor++] = substring_mask_count > 0 && substring_mask_words > 0
        ? (gc_i32)substring_masks[0] : 0;
}

__device__ __forceinline__ unsigned long long gpu_cabt_fnv_bytes(
    unsigned long long hash,
    const unsigned char* data,
    long long size
) {
    for (long long index = 0; index < size; ++index) {
        hash ^= (unsigned long long)data[index];
        hash *= 1099511628211ull;
    }
    return hash;
}

extern "C" __global__ void gpu_cabt_rule_static_checksum(
    const unsigned char* cards,
    long long cards_size,
    const unsigned char* skills,
    long long skills_size,
    const unsigned char* attacks,
    long long attacks_size,
    const unsigned char* effects,
    long long effects_size,
    const unsigned char* triggers,
    long long triggers_size,
    const unsigned char* masks,
    long long masks_size,
    unsigned long long* output
) {
    if (blockIdx.x != 0 || threadIdx.x != 0) return;
    unsigned long long hash = 1469598103934665603ull;
    hash = gpu_cabt_fnv_bytes(hash, cards, cards_size);
    hash = gpu_cabt_fnv_bytes(hash, skills, skills_size);
    hash = gpu_cabt_fnv_bytes(hash, attacks, attacks_size);
    hash = gpu_cabt_fnv_bytes(hash, effects, effects_size);
    hash = gpu_cabt_fnv_bytes(hash, triggers, triggers_size);
    hash = gpu_cabt_fnv_bytes(hash, masks, masks_size);
    output[0] = hash;
}
