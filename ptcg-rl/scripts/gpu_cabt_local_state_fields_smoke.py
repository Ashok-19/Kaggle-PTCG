from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module

_WORDS = 19


def main() -> int:
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-fields-") as tmp:
        exe = Path(tmp) / "probe"
        subprocess.run(
            [
                "g++",
                "-std=c++23",
                "-O2",
                "-I",
                str(official),
                str(repo_root / "scripts/gpu_cabt_state_fields_probe.cpp"),
                "-o",
                str(exe),
            ],
            check=True,
        )
        raw = subprocess.check_output([str(exe)])
    expected = np.frombuffer(raw, dtype=np.uint64)
    if expected.size != _WORDS:
        raise RuntimeError(f"native probe words {expected.size} != {_WORDS}")

    source = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in (
            "src/ptcg_rl/gpu_cabt/native/state_core.h",
            "src/ptcg_rl/gpu_cabt/native/state_fields.h",
            "src/ptcg_rl/gpu_cabt/cuda/state_fields_probe.cu",
        )
    )
    module = load_cupy_module(cp, source, kernel_names=("gpu_cabt_state_fields_probe",))
    output = cp.zeros(_WORDS, dtype=cp.uint64)
    module.get_function("gpu_cabt_state_fields_probe")((1,), (1,), (output,))
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(output)
    match = bool(np.array_equal(actual, expected))
    mismatch = [
        {"index": index, "native": int(expected[index]), "cuda": int(actual[index])}
        for index in range(_WORDS)
        if actual[index] != expected[index]
    ]
    print({"word_count": _WORDS, "raw_words_match": match, "mismatches": mismatch})
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
