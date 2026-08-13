#pragma once

// Fixed-capacity runtime buffers kept separate from the stable battle core.
// Every mutation must fail closed through error_flags instead of allocating.

namespace gpu_cabt {

static constexpr int kOptionCapacity = 128;
static constexpr int kSelectedCapacity = 128;
static constexpr int kContinuationCapacity = 256;

static constexpr gc_u32 kRuntimeErrorOptionOverflow = 1u << 0;
static constexpr gc_u32 kRuntimeErrorSelectedOverflow = 1u << 1;
static constexpr gc_u32 kRuntimeErrorContinuationOverflow = 1u << 2;
static constexpr gc_u32 kRuntimeErrorZoneOverflow = 1u << 3;
static constexpr gc_u32 kRuntimeErrorUnsupportedTransition = 1u << 4;
static constexpr gc_u32 kRuntimeErrorInvalidSelection = 1u << 5;

static constexpr gc_u16 kContinuationNone = 0;
static constexpr gc_u16 kContinuationSelectedIsFirst = 1;
static constexpr gc_u16 kContinuationAfterOpeningDraw = 2;
static constexpr gc_u16 kContinuationSelectedMulligan = 3;

struct SelectOptionState {
    gc_u8 type;
    gc_u8 reserved;
    gc_i16 param0;
    gc_i16 param1;
    gc_i16 param2;
    gc_i16 param3;
    gc_i16 param4;
};

struct ContinuationState {
    gc_u16 opcode;
    gc_u8 arg_type;
    gc_u8 call_count;
    gc_u8 called_count;
    gc_u8 reserved0;
    gc_u16 reserved1;
    gc_i32 arg0;
    gc_i32 arg1;
    gc_i32 arg2;
};

struct BattleRuntimeState {
    gc_u32 error_flags;
    gc_u16 option_count;
    gc_u16 selected_count;
    gc_u16 continuation_count;
    gc_u16 reserved;
    gc_u64 rng_draw_index;
    SelectOptionState options[kOptionCapacity];
    gc_i32 selected[kSelectedCapacity];
    ContinuationState continuations[kContinuationCapacity];
};

static_assert(sizeof(SelectOptionState) == 12, "SelectOptionState ABI");
static_assert(sizeof(ContinuationState) == 20, "ContinuationState ABI");
static_assert(sizeof(BattleRuntimeState) <= 8 * 1024, "runtime buffer must stay compact");

}  // namespace gpu_cabt
