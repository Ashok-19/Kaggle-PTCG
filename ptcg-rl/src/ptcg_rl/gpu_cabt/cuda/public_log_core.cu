namespace gpu_cabt {

static constexpr gc_u8 kLogShuffle = 0;
static constexpr gc_u8 kLogHasBasicPokemon = 1;
static constexpr gc_u8 kLogTurnStart = 2;
static constexpr gc_u8 kLogTurnEnd = 3;
static constexpr gc_u8 kLogDraw = 4;
static constexpr gc_u8 kLogDrawReverse = 5;
static constexpr gc_u8 kLogMoveCard = 6;
static constexpr gc_u8 kLogMoveCardReverse = 7;
static constexpr gc_u8 kLogSwitch = 8;
static constexpr gc_u8 kLogChange = 9;
static constexpr gc_u8 kLogPlay = 10;
static constexpr gc_u8 kLogAttach = 11;
static constexpr gc_u8 kLogEvolve = 12;
static constexpr gc_u8 kLogDevolve = 13;
static constexpr gc_u8 kLogMoveAttached = 14;
static constexpr gc_u8 kLogAttack = 15;
static constexpr gc_u8 kLogHpChange = 16;
static constexpr gc_u8 kLogPoisoned = 17;
static constexpr gc_u8 kLogBurned = 18;
static constexpr gc_u8 kLogAsleep = 19;
static constexpr gc_u8 kLogParalyzed = 20;
static constexpr gc_u8 kLogConfused = 21;
static constexpr gc_u8 kLogCoin = 22;
static constexpr gc_u8 kLogResult = 23;

__device__ __forceinline__ void compact_public_logs(BattleRuntimeState& runtime) {
    const gc_u16 acknowledged = runtime.public_log_index[0] < runtime.public_log_index[1]
        ? runtime.public_log_index[0] : runtime.public_log_index[1];
    if (acknowledged == 0) return;
    const gc_u16 remaining = (gc_u16)(runtime.public_log_count - acknowledged);
    for (gc_i32 i = 0; i < (gc_i32)remaining; ++i)
        runtime.public_logs[i] = runtime.public_logs[i + acknowledged];
    runtime.public_log_count = remaining;
    runtime.public_log_index[0] -= acknowledged;
    runtime.public_log_index[1] -= acknowledged;
}

__device__ __forceinline__ void append_public_log(
    BattleRuntimeState& runtime, gc_u8 type, gc_u8 param_count,
    gc_i32 p0 = 0, gc_i32 p1 = 0, gc_i32 p2 = 0, gc_i32 p3 = 0,
    gc_i32 p4 = 0, gc_i32 p5 = 0, gc_i32 p6 = 0
) {
    if (runtime.error_flags != 0) return;
    if (param_count > 7) {
        runtime.error_flags |= kRuntimeErrorLogOverflow;
        return;
    }
    if (runtime.public_log_count >= kPublicLogCapacity) compact_public_logs(runtime);
    if (runtime.public_log_count >= kPublicLogCapacity) {
        runtime.error_flags |= kRuntimeErrorLogOverflow;
        return;
    }
    PublicLogState& log = runtime.public_logs[runtime.public_log_count++];
    log.type = type;
    log.param_count = param_count;
    log.reserved = 0;
    log.param[0] = p0; log.param[1] = p1; log.param[2] = p2; log.param[3] = p3;
    log.param[4] = p4; log.param[5] = p5; log.param[6] = p6;
}

}  // namespace gpu_cabt
