from __future__ import annotations

import ctypes
import os
from pathlib import Path
from types import ModuleType


def compute_arch_option(major: int, minor: int) -> str:
    if major <= 0 or minor < 0:
        raise ValueError("invalid CUDA compute capability")
    return f"--gpu-architecture=compute_{major}{minor}"


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


def load_cupy_module(
    cupy_module: ModuleType,
    source: str,
    *,
    kernel_names: tuple[str, ...],
):
    """Compile source with direct NVRTC, then load PTX through CuPy's driver wrapper."""

    properties = cupy_module.cuda.runtime.getDeviceProperties(0)
    major = int(properties["major"])
    minor = int(properties["minor"])
    ptx = compile_ptx(
        source,
        nvrtc_library=_find_nvrtc_library(cupy_module),
        major=major,
        minor=minor,
    )
    module = cupy_module.cuda.function.Module()
    module.load(ptx)
    for name in kernel_names:
        module.get_function(name)
    return module
