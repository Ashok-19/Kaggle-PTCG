namespace gpu_cabt {

static constexpr gc_i32 kPublicEventWidth = 10;

__device__ __forceinline__ gc_i32 public_log_start_for_actor(
    const BattleRuntimeState& runtime,
    gc_i32 actor
) {
    if (actor < 0 || actor > 1) return -1;
    return (gc_i32)runtime.public_log_index[actor];
}

__device__ __forceinline__ bool public_move_card_visible_to_actor(
    const PublicLogState& log,
    gc_i32 actor
) {
    if (actor < 0 || actor > 1) return false;
    const gc_i32 player = log.param[0];
    const gc_i32 open_type = log.param[5];
    return open_type == 0
        || (open_type == 1 && player == actor)
        || (open_type == 3 && actor == 0)
        || (open_type == 4 && actor == 1);
}

__device__ __forceinline__ void project_public_log_for_actor(
    const PublicLogState& log,
    gc_i32 actor,
    gc_i32 raw_index,
    gc_i32* row
) {
    #pragma unroll
    for (gc_i32 i = 0; i < kPublicEventWidth; ++i) row[i] = 0;

    // Native ApiJson.h exposes an opponent draw only as DrawReverse. The
    // private card id/serial remain in the raw simulator log but must never
    // cross the actor-facing projection boundary.
    if (log.type == kLogDraw && log.param[0] != actor) {
        row[0] = kLogDrawReverse;
        row[1] = 1;
        row[2] = log.param[0];
        row[9] = raw_index;
        return;
    }

    // MoveCard's openType is internal visibility metadata. Native CABT either
    // emits the five public MoveCard fields or a three-field MoveCardReverse;
    // it never exposes openType itself to the agent.
    if (log.type == kLogMoveCard) {
        if (!public_move_card_visible_to_actor(log, actor)) {
            row[0] = kLogMoveCardReverse;
            row[1] = 3;
            row[2] = log.param[0];
            row[3] = log.param[3];
            row[4] = log.param[4];
            row[9] = raw_index;
            return;
        }
        row[0] = kLogMoveCard;
        row[1] = 5;
        row[2] = log.param[0];
        row[3] = log.param[1];
        row[4] = log.param[2];
        row[5] = log.param[3];
        row[6] = log.param[4];
        row[9] = raw_index;
        return;
    }

    row[0] = (gc_i32)log.type;
    row[1] = (gc_i32)log.param_count;
    #pragma unroll
    for (gc_i32 p = 0; p < 7; ++p) row[2 + p] = log.param[p];
    row[9] = raw_index;
}

__device__ __forceinline__ void project_public_logs_for_actor(
    const BattleCoreState& state,
    BattleRuntimeState& runtime,
    gc_i32 actor,
    gc_i32* rows,
    gc_i32& count,
    gc_u32& status,
    bool acknowledge
) {
    count = 0;
    status = 0;
    const gc_i32 start = public_log_start_for_actor(runtime, actor);
    const gc_i32 end = (gc_i32)runtime.public_log_count;
    if (start < 0 || start > end || end > kPublicLogCapacity) {
        status = kRuntimeErrorUnsupportedTransition;
        return;
    }
    count = end - start;
    for (gc_i32 i = 0; i < count; ++i) {
        const PublicLogState& log = runtime.public_logs[start + i];
        project_public_log_for_actor(
            log, actor, start + i, rows + (gc_i64)i * kPublicEventWidth);
    }
    if (acknowledge) {
        runtime.public_log_index[actor] = runtime.public_log_count;
        compact_public_logs(runtime);
    }
    (void)state;
}

}  // namespace gpu_cabt

extern "C" __global__ void gpu_cabt_project_events(
    const unsigned char* raw_states,
    unsigned char* raw_runtimes,
    gc_i32* events,
    gc_i32* event_counts,
    gc_u32* event_status,
    gc_u8 acknowledge,
    gc_i32 env_count
) {
    const gc_i32 env_index = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (env_index >= env_count) return;
    const auto& state = *reinterpret_cast<const gpu_cabt::BattleCoreState*>(
        raw_states + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleCoreState));
    auto& runtime = *reinterpret_cast<gpu_cabt::BattleRuntimeState*>(
        raw_runtimes + (gc_i64)env_index * (gc_i32)sizeof(gpu_cabt::BattleRuntimeState));
    const gc_i32 actor = state.select_type != gpu_cabt::kSelectNone ? state.select_player : -1;
    if (actor < 0 || actor > 1) {
        event_counts[env_index] = 0;
        // Terminal/no-selection environments have no actor and therefore no
        // event delivery boundary. This is a clean no-op, not an engine error.
        event_status[env_index] = 0;
        return;
    }
    gpu_cabt::project_public_logs_for_actor(
        state, runtime, actor,
        events + (gc_i64)env_index * gpu_cabt::kPublicLogCapacity * gpu_cabt::kPublicEventWidth,
        event_counts[env_index], event_status[env_index], acknowledge != 0);
}
