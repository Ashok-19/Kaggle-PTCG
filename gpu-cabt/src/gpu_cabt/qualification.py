from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalGpuQualification:
    """Fail-closed local qualification policy for GPU CABT training use."""

    max_vram_bytes: int = 4 * 1024**3
    require_differential_equivalence: bool = True
    require_deterministic_replay: bool = True
    require_no_unsupported_transitions: bool = True
    require_memory_headroom: bool = True
    require_throughput_measurement: bool = True

    def online_training_allowed(
        self,
        *,
        differential_equivalence: bool,
        deterministic_replay: bool,
        unsupported_transition_count: int,
        peak_vram_bytes: int,
        throughput_measured: bool,
    ) -> bool:
        return (
            differential_equivalence
            and deterministic_replay
            and unsupported_transition_count == 0
            and 0 < peak_vram_bytes <= self.max_vram_bytes
            and throughput_measured
        )
