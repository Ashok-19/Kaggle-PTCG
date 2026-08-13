namespace gpu_cabt {

static constexpr gc_u8 kSelectTypeYesNo = 10;
static constexpr gc_u8 kSelectContextIsFirst = 42;
static constexpr gc_u8 kSelectOptionYes = 1;
static constexpr gc_u8 kSelectOptionNo = 2;

__device__ __forceinline__ void zero_runtime(BattleRuntimeState* runtime) {
    gc_u8* bytes = reinterpret_cast<gc_u8*>(runtime);
    for (gc_i32 offset = 0; offset < (gc_i32)sizeof(BattleRuntimeState); ++offset) {
        bytes[offset] = 0;
    }
}

__device__ __forceinline__ void shuffle_deck_refs(
    FixedListU8<gc_u8, kCardListCapacity>* deck,
    gc_u64 seed,
    gc_u64 stream,
    gc_u64* draw_index
) {
    for (gc_i32 index = (gc_i32)deck->count - 1; index > 0; --index) {
        const gc_u32 swap_index = bounded_u32(seed, stream, draw_index, (gc_u32)(index + 1));
        const gc_u8 tmp = deck->values[index];
        deck->values[index] = deck->values[swap_index];
        deck->values[swap_index] = tmp;
    }
}

__device__ __forceinline__ void add_option(
    BattleRuntimeState* runtime,
    gc_u8 option_type
) {
    if (runtime->option_count >= kOptionCapacity) {
        runtime->error_flags |= kRuntimeErrorOptionOverflow;
        return;
    }
    SelectOptionState* option = &runtime->options[runtime->option_count++];
    gc_u8* bytes = reinterpret_cast<gc_u8*>(option);
    #pragma unroll
    for (gc_i32 index = 0; index < (gc_i32)sizeof(SelectOptionState); ++index) bytes[index] = 0;
    option->type = option_type;
}

__device__ __forceinline__ void push_continuation(
    BattleRuntimeState* runtime,
    gc_u16 opcode
) {
    if (runtime->continuation_count >= kContinuationCapacity) {
        runtime->error_flags |= kRuntimeErrorContinuationOverflow;
        return;
    }
    ContinuationState* continuation = &runtime->continuations[runtime->continuation_count++];
    gc_u8* bytes = reinterpret_cast<gc_u8*>(continuation);
    #pragma unroll
    for (gc_i32 index = 0; index < (gc_i32)sizeof(ContinuationState); ++index) bytes[index] = 0;
    continuation->opcode = opcode;
    continuation->call_count = 1;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_runtime_size(gc_u64* output) {
    if (blockIdx.x == 0 && threadIdx.x == 0) output[0] = sizeof(gpu_cabt::BattleRuntimeState);
}

extern "C" __global__ void gpu_cabt_setup_is_first(
    unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_u64 seed,
    gc_u64 stream_base,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;

    auto* state = reinterpret_cast<gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    auto* runtime = reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    gpu_cabt::zero_runtime(runtime);

    const gc_u64 stream = stream_base + (gc_u64)env_index;
    for (gc_i32 player = 0; player < 2; ++player) {
        auto* deck = &state->players[player].deck;
        if (deck->count > 0) {
            state->changed = 1;
            gpu_cabt::shuffle_deck_refs(deck, seed, stream, &runtime->rng_draw_index);
        }
    }

    state->select_type = gpu_cabt::kSelectTypeYesNo;
    state->select_context = gpu_cabt::kSelectContextIsFirst;
    state->select_player = 0;
    state->select_min = 1;
    state->select_max = 1;
    gpu_cabt::add_option(runtime, gpu_cabt::kSelectOptionYes);
    gpu_cabt::add_option(runtime, gpu_cabt::kSelectOptionNo);
    gpu_cabt::push_continuation(runtime, gpu_cabt::kContinuationSelectedIsFirst);
}

static constexpr gc_i32 kSetupSnapshotSize = 140;

extern "C" __global__ void gpu_cabt_setup_is_first_snapshot(
    const unsigned char* raw_states,
    const unsigned char* raw_runtimes,
    gc_i32* output,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto* state = reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState)
    );
    const auto* runtime = reinterpret_cast<const gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState)
    );
    gc_i32* row = output + (gc_i64)env_index * kSetupSnapshotSize;
    gc_i32 cursor = 0;

    row[cursor++] = (gc_i32)state->changed;
    row[cursor++] = (gc_i32)state->select_type;
    row[cursor++] = (gc_i32)state->select_context;
    row[cursor++] = (gc_i32)state->select_player;
    row[cursor++] = state->select_min;
    row[cursor++] = state->select_max;
    row[cursor++] = (gc_i32)runtime->option_count;
    row[cursor++] = (gc_i32)runtime->selected_count;
    row[cursor++] = (gc_i32)runtime->continuation_count;
    row[cursor++] = (gc_i32)runtime->error_flags;
    row[cursor++] = (gc_i32)(runtime->rng_draw_index & 0xffffffffull);
    row[cursor++] = (gc_i32)(runtime->rng_draw_index >> 32);
    row[cursor++] = (gc_i32)runtime->options[0].type;
    row[cursor++] = (gc_i32)runtime->options[1].type;
    row[cursor++] = (gc_i32)runtime->continuations[0].opcode;
    row[cursor++] = (gc_i32)runtime->continuations[0].call_count;
    row[cursor++] = (gc_i32)state->players[0].deck.count;
    row[cursor++] = (gc_i32)state->players[1].deck.count;
    for (gc_i32 player = 0; player < 2; ++player) {
        for (gc_i32 index = 0; index < gpu_cabt::kDeckSize; ++index) {
            row[cursor++] = (gc_i32)state->players[player].deck.values[index];
        }
    }
    row[cursor++] = state->move_counter;
    row[cursor++] = state->turn;
    if (cursor != kSetupSnapshotSize) row[0] = -999999;
}
