from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from gpu_cabt.device_runtime import GpuCabtRuntime, build_cuda_source


class _KernelCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, ...], tuple[int, ...], tuple[object, ...]]] = []

    def __call__(self, grid, block, args) -> None:
        self.calls.append((grid, block, args))


class _FakeCupy:
    ndarray = np.ndarray
    int32 = np.int32
    uint8 = np.uint8

    @staticmethod
    def asarray(value):
        return np.asarray(value)

    @staticmethod
    def ascontiguousarray(value):
        return np.ascontiguousarray(value)


def _runtime() -> tuple[GpuCabtRuntime, _KernelCapture]:
    runtime = object.__new__(GpuCabtRuntime)
    runtime.cp = _FakeCupy()
    runtime.env_count = 4
    runtime.abi = SimpleNamespace(deck_size=60)
    runtime.states = object()
    runtime.runtimes = object()
    kernel = _KernelCapture()
    runtime._kernels = {"gpu_cabt_game_reset_selected": kernel}
    return runtime, kernel


def test_cuda_source_exports_selective_reset_kernel() -> None:
    source = build_cuda_source()
    assert 'extern "C" __global__ void gpu_cabt_game_reset_selected' in source


def test_reset_selected_passes_full_decks_and_device_mask_to_kernel() -> None:
    runtime, kernel = _runtime()
    decks = np.zeros((4, 2, 60), dtype=np.int32)
    mask = np.array([0, 1, 0, 1], dtype=np.uint8)
    runtime.reset_selected(decks, mask, seed=123, stream_base=400)
    assert len(kernel.calls) == 1
    grid, block, args = kernel.calls[0]
    assert grid == (1,)
    assert block == (128,)
    assert np.array_equal(args[2], decks)
    assert np.array_equal(args[3], mask)
    assert int(args[4]) == 123
    assert int(args[5]) == 400
    assert int(args[6]) == 4


def test_reset_selected_rejects_wrong_mask_shape() -> None:
    runtime, _ = _runtime()
    decks = np.zeros((4, 2, 60), dtype=np.int32)
    with pytest.raises(ValueError, match="reset_mask"):
        runtime.reset_selected(decks, np.ones(3, dtype=np.uint8), seed=1)
