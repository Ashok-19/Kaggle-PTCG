from pathlib import Path
from types import SimpleNamespace

import pytest

from ptcg_rl.gpu_cabt import nvrtc
from ptcg_rl.gpu_cabt.nvrtc import compute_arch_option


def test_compute_arch_option() -> None:
    assert compute_arch_option(8, 6) == "--gpu-architecture=compute_86"
    assert compute_arch_option(9, 0) == "--gpu-architecture=compute_90"


def test_compute_arch_option_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        compute_arch_option(0, 0)
    with pytest.raises(ValueError):
        compute_arch_option(8, -1)


def test_cubin_cache_key_changes_with_build_identity(tmp_path: Path) -> None:
    library = tmp_path / "libnvrtc.so"
    library.write_bytes(b"nvrtc-a")
    base = nvrtc._cubin_cache_key(
        "source-a", major=8, minor=6, fast_compile=None, nvrtc_library=library
    )
    assert base == nvrtc._cubin_cache_key(
        "source-a", major=8, minor=6, fast_compile=None, nvrtc_library=library
    )
    assert base != nvrtc._cubin_cache_key(
        "source-b", major=8, minor=6, fast_compile=None, nvrtc_library=library
    )
    assert base != nvrtc._cubin_cache_key(
        "source-a", major=8, minor=6, fast_compile="max", nvrtc_library=library
    )
    assert base != nvrtc._cubin_cache_key(
        "source-a", major=8, minor=9, fast_compile=None, nvrtc_library=library
    )


def test_compile_or_load_cached_cubin_reuses_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "libnvrtc.so"
    library.write_bytes(b"nvrtc")
    cache = tmp_path / "cache"
    calls: list[str] = []

    monkeypatch.setenv("GPU_CABT_CUBIN_CACHE_DIR", str(cache))
    monkeypatch.delenv("GPU_CABT_CUBIN_CACHE_DISABLE", raising=False)
    monkeypatch.setattr(nvrtc, "_find_nvrtc_library", lambda _: library)

    def fake_compile(source: str, **_: object) -> bytes:
        calls.append(source)
        return b"cubin-bytes"

    monkeypatch.setattr(nvrtc, "compile_cubin", fake_compile)
    cupy = SimpleNamespace()
    first, first_path = nvrtc._compile_or_load_cached_cubin(
        "source", cupy_module=cupy, major=8, minor=6, fast_compile=None
    )
    second, second_path = nvrtc._compile_or_load_cached_cubin(
        "source", cupy_module=cupy, major=8, minor=6, fast_compile=None
    )
    assert first == second == b"cubin-bytes"
    assert first_path == second_path
    assert first_path is not None and first_path.read_bytes() == b"cubin-bytes"
    assert calls == ["source"]
