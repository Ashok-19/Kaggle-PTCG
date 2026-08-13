from __future__ import annotations

from pathlib import Path

NATIVE_HEADERS = (
    "state_core.h",
    "state_fields.h",
    "runtime_state.h",
    "rule_static.h",
)

CUDA_RUNTIME_MODULES = (
    "rng_shuffle.cu",
    "public_log_core.cu",
    "public_log_emit.cu",
    "rule_runtime_helpers.cu",
    "selection_runtime.cu",
    "card_move.cu",
    "target_list.cu",
    "satisfy_condition.cu",
    "effect_continual.cu",
    "refresh_effect.cu",
    "pull_trigger.cu",
    "card_move_full.cu",
    "evolution_full.cu",
    "attach_full.cu",
    "damage_heal.cu",
    "energy_discard.cu",
    "coin_runtime.cu",
    "attack_damage.cu",
    "effect_instant_0_29.cu",
    "effect_instant_30_47.cu",
    "effect_instant_48_55.cu",
    "effect_instant_56_71.cu",
    "effect_instant_72_95.cu",
    "effect_instant_96_110.cu",
    "effect_instant_111_135.cu",
    "effect_instant_136_158.cu",
    "effect_instant_159_170.cu",
    "effect_driver.cu",
    "effect_resume.cu",
    "special_condition_checkup.cu",
    "trigger_stack.cu",
    "ko_process.cu",
    "state_based_refresh.cu",
    "turn_cycle.cu",
    "main_select.cu",
    "main_action.cu",
    "attack_frame.cu",
    "setup_runtime.cu",
    "game_runtime.cu",
    "public_log_project.cu",
)

CUDA_POLICY_MODULES = (
    "policy_projection.cu",
    "runtime_api.cu",
)


def build_cuda_source(*, include_policy: bool = True, package_root: Path | None = None) -> str:
    """Build the canonical freestanding GPU CABT translation unit."""
    root = (package_root or Path(__file__).resolve().parent).resolve()
    native = root / "native"
    cuda = root / "cuda"
    modules = CUDA_RUNTIME_MODULES + (CUDA_POLICY_MODULES if include_policy else ())
    paths = tuple(native / name for name in NATIVE_HEADERS) + tuple(cuda / name for name in modules)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"GPU CABT source component(s) missing: {missing}")
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)
