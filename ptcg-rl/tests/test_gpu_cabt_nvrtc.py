import pytest

from ptcg_rl.gpu_cabt.nvrtc import compute_arch_option


def test_compute_arch_option() -> None:
    assert compute_arch_option(8, 6) == "--gpu-architecture=compute_86"
    assert compute_arch_option(9, 0) == "--gpu-architecture=compute_90"


def test_compute_arch_option_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        compute_arch_option(0, 0)
    with pytest.raises(ValueError):
        compute_arch_option(8, -1)
