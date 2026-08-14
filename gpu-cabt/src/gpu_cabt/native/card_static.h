#pragma once

namespace gpu_cabt {

struct SetupCardStatic {
    gc_u8 is_basic_pokemon;
    gc_u8 is_setup_doll;
    gc_u8 can_setup;
    gc_u8 can_setup_active;
};

static_assert(sizeof(SetupCardStatic) == 4, "SetupCardStatic ABI");

}  // namespace gpu_cabt
