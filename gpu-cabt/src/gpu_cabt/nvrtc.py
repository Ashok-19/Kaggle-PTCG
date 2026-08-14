from __future__ import annotations

import ctypes
import hashlib
import os
import tempfile
from pathlib import Path
from types import ModuleType


def compute_arch_option(major: int, minor: int) -> str:
    if major <= 0 or minor < 0:
        raise ValueError("invalid CUDA compute capability")
    return f"--gpu-architecture=compute_{major}{minor}"


def sm_arch_option(major: int, minor: int) -> str:
    if major <= 0 or minor < 0:
        raise ValueError("invalid CUDA compute capability")
    return f"--gpu-architecture=sm_{major}{minor}"


def _find_nvrtc_library(cupy_module: ModuleType) -> Path:
    override = os.environ.get("GPU_CABT_NVRTC_LIBRARY")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"GPU_CABT_NVRTC_LIBRARY does not exist: {path}")
        return path

    cupy_path = Path(cupy_module.__file__).resolve()
    package_root = cupy_path.parent.parent
    candidates = sorted((package_root / "nvidia/cuda_nvrtc/lib").glob("libnvrtc.so*"))
    if not candidates:
        raise FileNotFoundError(
            "NVRTC library not found next to CuPy; install the isolated cuda-toolkit[nvrtc] runtime"
        )
    exact = [path for path in candidates if path.name in {"libnvrtc.so", "libnvrtc.so.12", "libnvrtc.so.13"}]
    return (exact[0] if exact else candidates[0]).resolve()


def compile_ptx(
    source: str,
    *,
    nvrtc_library: Path,
    major: int,
    minor: int,
    std: str = "c++14",
) -> bytes:
    """Compile freestanding CUDA source to PTX with NVRTC and no toolkit headers."""

    library = ctypes.CDLL(str(nvrtc_library))
    program_type = ctypes.c_void_p

    library.nvrtcCreateProgram.argtypes = [
        ctypes.POINTER(program_type),
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    library.nvrtcCreateProgram.restype = ctypes.c_int
    library.nvrtcCompileProgram.argtypes = [
        program_type,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_char_p),
    ]
    library.nvrtcCompileProgram.restype = ctypes.c_int
    library.nvrtcGetProgramLogSize.argtypes = [program_type, ctypes.POINTER(ctypes.c_size_t)]
    library.nvrtcGetProgramLogSize.restype = ctypes.c_int
    library.nvrtcGetProgramLog.argtypes = [program_type, ctypes.c_char_p]
    library.nvrtcGetProgramLog.restype = ctypes.c_int
    library.nvrtcGetPTXSize.argtypes = [program_type, ctypes.POINTER(ctypes.c_size_t)]
    library.nvrtcGetPTXSize.restype = ctypes.c_int
    library.nvrtcGetPTX.argtypes = [program_type, ctypes.c_char_p]
    library.nvrtcGetPTX.restype = ctypes.c_int
    library.nvrtcDestroyProgram.argtypes = [ctypes.POINTER(program_type)]
    library.nvrtcDestroyProgram.restype = ctypes.c_int

    program = program_type()
    create_status = library.nvrtcCreateProgram(
        ctypes.byref(program), source.encode(), b"gpu_cabt.cu", 0, None, None
    )
    if create_status != 0:
        raise RuntimeError(f"nvrtcCreateProgram failed with status {create_status}")

    options_text = (f"--std={std}", compute_arch_option(major, minor))
    options = (ctypes.c_char_p * len(options_text))(
        *(option.encode() for option in options_text)
    )
    try:
        compile_status = library.nvrtcCompileProgram(program, len(options_text), options)
        log_size = ctypes.c_size_t()
        library.nvrtcGetProgramLogSize(program, ctypes.byref(log_size))
        log = ""
        if log_size.value > 1:
            log_buffer = ctypes.create_string_buffer(log_size.value)
            library.nvrtcGetProgramLog(program, log_buffer)
            log = log_buffer.value.decode(errors="replace")
        if compile_status != 0:
            raise RuntimeError(f"NVRTC compile failed with status {compile_status}:\n{log}")

        ptx_size = ctypes.c_size_t()
        ptx_size_status = library.nvrtcGetPTXSize(program, ctypes.byref(ptx_size))
        if ptx_size_status != 0:
            raise RuntimeError(f"nvrtcGetPTXSize failed with status {ptx_size_status}")
        ptx = ctypes.create_string_buffer(ptx_size.value)
        ptx_status = library.nvrtcGetPTX(program, ptx)
        if ptx_status != 0:
            raise RuntimeError(f"nvrtcGetPTX failed with status {ptx_status}")
        return ptx.raw
    finally:
        library.nvrtcDestroyProgram(ctypes.byref(program))


def compile_cubin(
    source: str,
    *,
    nvrtc_library: Path,
    major: int,
    minor: int,
    std: str = "c++14",
    fast_compile: str | None = None,
) -> bytes:
    """Compile freestanding CUDA source directly to device-native CUBIN."""

    library = ctypes.CDLL(str(nvrtc_library))
    program_type = ctypes.c_void_p
    library.nvrtcCreateProgram.argtypes = [
        ctypes.POINTER(program_type), ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
    ]
    library.nvrtcCreateProgram.restype = ctypes.c_int
    library.nvrtcCompileProgram.argtypes = [
        program_type, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p),
    ]
    library.nvrtcCompileProgram.restype = ctypes.c_int
    library.nvrtcGetProgramLogSize.argtypes = [program_type, ctypes.POINTER(ctypes.c_size_t)]
    library.nvrtcGetProgramLogSize.restype = ctypes.c_int
    library.nvrtcGetProgramLog.argtypes = [program_type, ctypes.c_char_p]
    library.nvrtcGetProgramLog.restype = ctypes.c_int
    library.nvrtcGetCUBINSize.argtypes = [program_type, ctypes.POINTER(ctypes.c_size_t)]
    library.nvrtcGetCUBINSize.restype = ctypes.c_int
    library.nvrtcGetCUBIN.argtypes = [program_type, ctypes.c_char_p]
    library.nvrtcGetCUBIN.restype = ctypes.c_int
    library.nvrtcDestroyProgram.argtypes = [ctypes.POINTER(program_type)]
    library.nvrtcDestroyProgram.restype = ctypes.c_int

    program = program_type()
    create_status = library.nvrtcCreateProgram(
        ctypes.byref(program), source.encode(), b"gpu_cabt.cu", 0, None, None
    )
    if create_status != 0:
        raise RuntimeError(f"nvrtcCreateProgram failed with status {create_status}")

    options_list = [f"--std={std}", sm_arch_option(major, minor)]
    if fast_compile is not None:
        if fast_compile not in {"min", "mid", "max"}:
            raise ValueError("fast_compile must be one of: min, mid, max")
        options_list.append(f"--Ofast-compile={fast_compile}")
    options_text = tuple(options_list)
    options = (ctypes.c_char_p * len(options_text))(
        *(option.encode() for option in options_text)
    )
    try:
        compile_status = library.nvrtcCompileProgram(program, len(options_text), options)
        log_size = ctypes.c_size_t()
        library.nvrtcGetProgramLogSize(program, ctypes.byref(log_size))
        log = ""
        if log_size.value > 1:
            log_buffer = ctypes.create_string_buffer(log_size.value)
            library.nvrtcGetProgramLog(program, log_buffer)
            log = log_buffer.value.decode(errors="replace")
        if compile_status != 0:
            raise RuntimeError(f"NVRTC CUBIN compile failed with status {compile_status}:\n{log}")

        cubin_size = ctypes.c_size_t()
        cubin_size_status = library.nvrtcGetCUBINSize(program, ctypes.byref(cubin_size))
        if cubin_size_status != 0:
            raise RuntimeError(f"nvrtcGetCUBINSize failed with status {cubin_size_status}")
        cubin = ctypes.create_string_buffer(cubin_size.value)
        cubin_status = library.nvrtcGetCUBIN(program, cubin)
        if cubin_status != 0:
            raise RuntimeError(f"nvrtcGetCUBIN failed with status {cubin_status}")
        return cubin.raw
    finally:
        library.nvrtcDestroyProgram(ctypes.byref(program))


def _cubin_cache_dir() -> Path:
    override = os.environ.get("GPU_CABT_CUBIN_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".cache" / "gpu_cabt" / "standalone"


def _cubin_cache_key(
    source: str,
    *,
    major: int,
    minor: int,
    fast_compile: str | None,
    nvrtc_library: Path,
) -> str:
    stat = nvrtc_library.stat()
    payload = "\n".join(
        (
            "gpu-cabt-cubin-v1",
            hashlib.sha256(source.encode()).hexdigest(),
            f"sm_{major}{minor}",
            fast_compile or "optimized",
            str(nvrtc_library),
            str(stat.st_size),
            str(stat.st_mtime_ns),
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_cached_cubin(path: Path, cubin: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(cubin)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _compile_or_load_cached_cubin(
    source: str,
    *,
    cupy_module: ModuleType,
    major: int,
    minor: int,
    fast_compile: str | None,
) -> tuple[bytes, Path | None]:
    nvrtc_library = _find_nvrtc_library(cupy_module)
    cache_disabled = os.environ.get("GPU_CABT_CUBIN_CACHE_DISABLE") == "1"
    if cache_disabled:
        return (
            compile_cubin(
                source,
                nvrtc_library=nvrtc_library,
                major=major,
                minor=minor,
                fast_compile=fast_compile,
            ),
            None,
        )

    cache_dir = _cubin_cache_dir()
    key = _cubin_cache_key(
        source,
        major=major,
        minor=minor,
        fast_compile=fast_compile,
        nvrtc_library=nvrtc_library,
    )
    cache_path = cache_dir / f"{key}.cubin"
    try:
        cached = cache_path.read_bytes()
    except FileNotFoundError:
        cached = b""
    if cached:
        return cached, cache_path

    cubin = compile_cubin(
        source,
        nvrtc_library=nvrtc_library,
        major=major,
        minor=minor,
        fast_compile=fast_compile,
    )
    _write_cached_cubin(cache_path, cubin)
    return cubin, cache_path


def load_cupy_module(
    cupy_module: ModuleType,
    source: str,
    *,
    kernel_names: tuple[str, ...],
):
    """Compile source to device-native CUBIN, then load it through CuPy."""

    properties = cupy_module.cuda.runtime.getDeviceProperties(0)
    major = int(properties["major"])
    minor = int(properties["minor"])
    fast_compile = os.environ.get("GPU_CABT_NVRTC_FAST_COMPILE") or None
    cubin, cache_path = _compile_or_load_cached_cubin(
        source,
        cupy_module=cupy_module,
        major=major,
        minor=minor,
        fast_compile=fast_compile,
    )

    def load(value: bytes):
        module = cupy_module.cuda.function.Module()
        module.load(value)
        for name in kernel_names:
            module.get_function(name)
        return module

    try:
        return load(cubin)
    except Exception:
        if cache_path is None:
            raise
        try:
            cache_path.unlink()
        except FileNotFoundError:
            pass
        fresh = compile_cubin(
            source,
            nvrtc_library=_find_nvrtc_library(cupy_module),
            major=major,
            minor=minor,
            fast_compile=fast_compile,
        )
        _write_cached_cubin(cache_path, fresh)
        return load(fresh)
