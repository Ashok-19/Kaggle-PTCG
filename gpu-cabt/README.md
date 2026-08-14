# GPU-CABT standalone

This directory is the isolated CUDA battle-runtime project. It intentionally has no dependency on the broader `ptcg-rl` Python package or its virtual environment.

## Runtime dependencies

The project pins NumPy, CuPy CUDA 12.x, and the CUDA 12 NVRTC runtime in its own virtual environment. Development adds only pytest and ruff.

The official competition engine headers are **not copied into this project**. By default they are read from:

`../pokemon-tcg-ai-battle/ptcg_engine/ptcgProgram 22`

Override with `GPU_CABT_OFFICIAL_DIR=/absolute/path/to/ptcgProgram 22` when needed.

## Local safety

The qualification harness constrains itself to two logical CPU cores and uses `GPU_CABT_NVRTC_FAST_COMPILE=max` on the local RTX 3050 host. Fully optimized NVRTC compilation previously triggered the host OOM killer and must not be retried on this machine.

## Setup

```bash
uv sync --offline --group dev
```

## Core checks

```bash
.venv/bin/pytest -q
GPU_CABT_NVRTC_FAST_COMPILE=max .venv/bin/python scripts/gpu_cabt_local_public_policy_differential.py
GPU_CABT_NVRTC_FAST_COMPILE=max .venv/bin/python scripts/gpu_cabt_local_public_log_differential.py
GPU_CABT_NVRTC_FAST_COMPILE=max .venv/bin/python scripts/gpu_cabt_local_final_qualification.py
```

Benchmark deck fixtures live under `data/decks/`. Machine-local reports should go under `reports/local/`.
