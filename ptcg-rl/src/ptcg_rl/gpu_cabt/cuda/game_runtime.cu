namespace gpu_cabt {

__device__ __forceinline__ RuleTableView make_game_rule_view(
    const RuleCardMaster* cards,
    const RuleSkill* skills,
    const RuleAttack* attacks,
    const RuleEffect* effects,
    const RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words
) {
    RuleTableView view{};
    view.cards = cards;
    view.skills = skills;
    view.attacks = attacks;
    view.effects = effects;
    view.triggers = triggers;
    view.substring_masks = masks;
    view.card_count = card_count;
    view.skill_count = skill_count;
    view.attack_count = attack_count;
    view.effect_count = effect_count;
    view.trigger_count = trigger_count;
    view.substring_mask_count = mask_count;
    view.substring_mask_words = mask_words;
    return view;
}

__device__ __forceinline__ bool load_policy_response_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 selected_count,
    const gc_i32* selected_indices,
    gc_i32 selected_stride
) {
    if (state.select_type == kSelectNone || selected_count < state.select_min
        || selected_count > state.select_max || selected_count < 0
        || selected_count > selected_stride || selected_count > kSelectedCapacity) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    if (selected_count > 0 && selected_indices == nullptr) {
        runtime.error_flags |= kRuntimeErrorInvalidSelection;
        return false;
    }
    runtime.selected_count = (gc_u16)selected_count;
    for (gc_i32 i = 0; i < selected_count; ++i) {
        const gc_i32 option_index = selected_indices[i];
        if (option_index < 0 || option_index >= (gc_i32)runtime.option_count) {
            runtime.error_flags |= kRuntimeErrorInvalidSelection;
            return false;
        }
        for (gc_i32 previous = 0; previous < i; ++previous) {
            if (runtime.selected[previous] == option_index) {
                runtime.error_flags |= kRuntimeErrorInvalidSelection;
                return false;
            }
        }
        runtime.selected[i] = option_index;
    }
    return true;
}

__device__ __forceinline__ void advance_game_to_boundary_full(
    BattleCoreState& state,
    BattleRuntimeState& runtime,
    const RuleTableView& rules,
    bool has_response
) {
    bool response_available = has_response;
    for (gc_i32 guard = 0; guard < 512; ++guard) {
        if (runtime.error_flags != 0 || state.game_result != 0) return;

        if (state.select_type != kSelectNone && !response_available) return;

        if (runtime.main_action_active) {
            const gc_u8 stage = runtime.main_action_stage;
            if (stage >= kMainActionAttackReady) resume_attack_full(state, runtime, rules);
            else resume_main_action_full(state, runtime, rules);
            response_available = false;
            continue;
        }

        if (runtime.refresh_process_active) {
            resume_refresh_full(state, runtime, rules);
            response_available = false;
            continue;
        }
        if (runtime.turn_cycle_active) {
            resume_turn_cycle_full(state, runtime, rules);
            response_available = false;
            continue;
        }
        if (runtime.ko_process_active) {
            resume_ko_selection_full(state, runtime, rules);
            response_available = false;
            continue;
        }

        if (runtime.trigger_resolution_active || runtime.trigger_activation_waiting
            || runtime.effect_execution_active) {
            if (runtime.pending_effect_kind == kPendingTriggerOrder)
                resume_trigger_order_full(state, runtime, rules);
            else {
                if (state.select_type != kSelectNone || runtime.pending_effect_kind != kPendingNone)
                    resume_effect_selection_full(state, runtime, rules, runtime.trigger_resolution_depth);
                continue_trigger_activation_full(state, runtime, rules);
            }
            response_available = false;
            continue;
        }

        if (runtime.setup_process_active) {
            if (state.select_type != kSelectNone)
                resume_setup_selection_full(state, runtime, rules);
            else
                continue_setup_full(state, runtime, rules);
            response_available = false;
            continue;
        }

        if (state.select_type == kSelectMain) {
            start_selected_main_full(state, runtime, rules);
            response_available = false;
            continue;
        }

        if (state.select_type != kSelectNone) {
            runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
            return;
        }

        if (state.phase == 1) {
            begin_main_select_full(state, runtime, rules);
            return;
        }

        runtime.error_flags |= kRuntimeErrorUnsupportedTransition;
        return;
    }
    runtime.error_flags |= kRuntimeErrorInterpreterLimit;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_post_setup_begin(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gpu_cabt::RuleCardMaster* cards,
    const gpu_cabt::RuleSkill* skills,
    const gpu_cabt::RuleAttack* attacks,
    const gpu_cabt::RuleEffect* effects,
    const gpu_cabt::RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    if (runtime.error_flags != 0 || state.game_result != 0) return;
    const auto rules = gpu_cabt::make_game_rule_view(
        cards, skills, attacks, effects, triggers, masks,
        card_count, skill_count, attack_count, effect_count,
        trigger_count, mask_count, mask_words);
    gpu_cabt::advance_game_to_boundary_full(state, runtime, rules, false);
}

extern "C" __global__ void gpu_cabt_game_step(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    const gpu_cabt::RuleCardMaster* cards,
    const gpu_cabt::RuleSkill* skills,
    const gpu_cabt::RuleAttack* attacks,
    const gpu_cabt::RuleEffect* effects,
    const gpu_cabt::RuleTrigger* triggers,
    const gc_u32* masks,
    gc_i32 card_count,
    gc_i32 skill_count,
    gc_i32 attack_count,
    gc_i32 effect_count,
    gc_i32 trigger_count,
    gc_i32 mask_count,
    gc_i32 mask_words,
    const gc_u8* response_present,
    const gc_i32* selected_counts,
    const gc_i32* selected_indices,
    gc_i32 selected_stride,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    auto& state = *reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    if (runtime.error_flags != 0 || state.game_result != 0) return;
    const auto rules = gpu_cabt::make_game_rule_view(
        cards, skills, attacks, effects, triggers, masks,
        card_count, skill_count, attack_count, effect_count,
        trigger_count, mask_count, mask_words);
    const bool has_response = response_present != nullptr && response_present[env_index] != 0;
    if (has_response) {
        if (selected_counts == nullptr || selected_stride < 0) {
            runtime.error_flags |= gpu_cabt::kRuntimeErrorInvalidSelection;
            return;
        }
        const gc_i32 count = selected_counts[env_index];
        const gc_i32* row = count > 0 && selected_indices != nullptr
            ? selected_indices + (gc_i64)env_index * selected_stride : nullptr;
        if (!gpu_cabt::load_policy_response_full(state, runtime, count, row, selected_stride)) return;
    }
    gpu_cabt::advance_game_to_boundary_full(state, runtime, rules, has_response);
}
