from ptcg_rl.gpu_cabt.qualification import LocalGpuQualification


def test_online_training_gate_passes_only_complete_local_qualification() -> None:
    gate = LocalGpuQualification()
    assert gate.online_training_allowed(
        differential_equivalence=True,
        deterministic_replay=True,
        unsupported_transition_count=0,
        peak_vram_bytes=3 * 1024**3,
        throughput_measured=True,
    )


def test_online_training_gate_rejects_semantic_mismatch() -> None:
    gate = LocalGpuQualification()
    assert not gate.online_training_allowed(
        differential_equivalence=False,
        deterministic_replay=True,
        unsupported_transition_count=0,
        peak_vram_bytes=3 * 1024**3,
        throughput_measured=True,
    )


def test_online_training_gate_rejects_vram_over_budget() -> None:
    gate = LocalGpuQualification()
    assert not gate.online_training_allowed(
        differential_equivalence=True,
        deterministic_replay=True,
        unsupported_transition_count=0,
        peak_vram_bytes=gate.max_vram_bytes + 1,
        throughput_measured=True,
    )
