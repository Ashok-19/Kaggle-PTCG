# 02 — Repository and Environment Specification

## Target repository layout

```text
ptcg-rl/
├── AGENTS.md
├── README.md
├── PROJECT_STATUS.md
├── LICENSE-NOTES.md
├── pyproject.toml
├── uv.lock
├── locks/                      # generated, pinned platform profiles
│   ├── local-cpu.txt
│   ├── colab-cuda.txt
│   ├── kaggle-cuda.txt
│   └── modal-cuda.txt
├── .env.example
├── .gitignore
├── configs/
│   ├── assets/
│   ├── replay/
│   ├── model/
│   ├── train/
│   ├── league/
│   ├── evaluation/
│   └── cloud/
├── src/ptcg_rl/
│   ├── cli.py
│   ├── config.py
│   ├── provenance.py
│   ├── assets/
│   ├── engine/
│   │   ├── native.py
│   │   ├── battle.py
│   │   ├── types.py
│   │   ├── resolver.py
│   │   ├── worker.py
│   │   └── errors.py
│   ├── encoding/
│   │   ├── cards.py
│   │   ├── observation.py
│   │   ├── options.py
│   │   └── ragged.py
│   ├── models/
│   │   ├── entity_gru.py
│   │   ├── option_decoder.py
│   │   └── checkpoint.py
│   ├── rl/
│   │   ├── rollout.py
│   │   ├── recurrent_batch.py
│   │   ├── gae.py
│   │   ├── ppo.py
│   │   └── learner.py
│   ├── league/
│   │   ├── registry.py
│   │   ├── matchmaking.py
│   │   └── promotion.py
│   ├── replay/
│   │   ├── providers.py
│   │   ├── catalog.py
│   │   ├── filters.py
│   │   ├── download.py
│   │   ├── parse.py
│   │   └── meta.py
│   ├── decks/
│   │   ├── validate.py
│   │   ├── archetypes.py
│   │   ├── mutate.py
│   │   └── bakeoff.py
│   ├── evaluation/
│   │   ├── tournament.py
│   │   ├── statistics.py
│   │   └── reports.py
│   └── submission/
│       ├── package.py
│       └── validate.py
├── scripts/
│   ├── bootstrap_assets.py
│   ├── smoke_local.sh
│   └── modal_app.py
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── notebooks/                 # thin analysis views; no source-of-truth logic
├── docker/
│   ├── Dockerfile.cpu
│   └── Dockerfile.cuda
├── data/                      # ignored; catalogs may be backed up separately
├── private/                   # entirely ignored; competition/private bytes
│   ├── assets/
│   │   ├── official/
│   │   ├── sample_agents/
│   │   └── research/
│   └── assets.lock.json       # full paths/hashes; ignored
├── asset_hashes.redacted.json # tracked hashes/versions only; no private paths
├── runs/                      # ignored locally; manifests/summary may be tracked
└── submissions/               # entirely ignored staging/ZIPs; track only redacted hashes elsewhere
```

Use a `src/` package and make every notebook import it. Do not let Colab/Kaggle notebooks become a divergent implementation.

## Git exclusions before asset import

At minimum ignore:

```gitignore
.env
.venv/
private/
data/raw/
data/cache/
data/derived/
runs/
checkpoints/
submissions/
*.so
*.dll
*.dylib
*.pt
*.pth
*.ckpt
*.parquet
*.duckdb
*.sqlite*
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

Track small configuration, schemas, tests, redacted summaries and hashes—not restricted or bulky bytes.

## Toolchain

Initial development baseline:

- Ubuntu 22.04;
- Python 3.11;
- `uv` for environment and lock management;
- `g++` with C++20 support;
- PyTorch version selected to match the cloud CUDA image;
- Git and Git LFS only if later needed for user-owned artifacts (never for the restricted engine).

The local agent must first verify the competition submission Python/runtime constraints. If they conflict, use the submission-compatible Python version everywhere and record the decision.

Suggested Ubuntu packages:

```bash
sudo apt-get update
sudo apt-get install -y build-essential g++ git curl unzip zip libgomp1
```

Do not ask Codex to run `sudo` without the user’s approval. Report missing packages and provide the command.

## Python dependency groups

Keep the initial dependency set small and pinned.

Do not install `--all-extras` across every platform. Maintain one dependency definition plus verified platform-specific lock/export profiles. In particular, preserve the CUDA-compatible PyTorch build supplied/selected for Colab, Kaggle and Modal; a generic sync must not silently replace it with a CPU or incompatible wheel. Every GPU profile runs a CUDA forward/backward doctor test before training and records wheel/index/image hashes.

Core:

- `torch`, `numpy`, `orjson`, `pydantic`, `pyyaml`, `typer`, `rich`, `psutil`;
- `pandas` or `polars`, `pyarrow`, `duckdb` for replay/meta data;
- `kagglehub` plus the user’s local MCP adapter;
- `tensorboard` for local/cloud metrics;
- `scipy` for statistical tests/intervals only if needed.

Development:

- `pytest`, `pytest-xdist`, `hypothesis`, `coverage`, `ruff`, `mypy`;
- avoid large RL frameworks in the hot path.

Cloud:

- `modal` in an optional dependency group;
- exact CUDA/PyTorch wheels pinned in the cloud image.

Potential performance dependencies such as `safetensors`, `torchrl`, `numba` or a C++ extension are added only after profiling shows a need.

## Asset bootstrap contract

The bootstrap command must accept explicit paths rather than searching the whole home directory:

```bash
uv run ptcg assets import \
  --official-archive /absolute/path/pokemon-tcg-ai-battle.zip \
  --sample-agents /absolute/path/sample-agents.zip \
  --research /absolute/path/PTCG.zip
```

Required behavior:

1. refuse missing/unreadable files;
2. compute SHA-256 before extraction;
3. inspect archive members and block path traversal/symlink escape;
4. extract into a staging directory;
5. locate required files by validated signatures, not only one assumed folder name;
6. copy/link into the ignored `private/assets/` tree (or make `PTCG_ASSET_ROOT` point to an equally private external tree);
7. read and copy the engine license notice to `LICENSE-NOTES.md` as a summary/link, without relicensing anything;
8. write ignored `private/assets.lock.json` containing source paths, hashes, imported time, discovered version and per-file hashes, plus tracked `asset_hashes.redacted.json` containing only non-sensitive hashes/versions;
9. never overwrite an existing different asset without `--force` and a backup;
10. delete staging on success and preserve it on diagnostic failure.

Expected official assets include the native engine/library, wrapper package, source/readme/license, sample submission, `deck.csv`, and English card data. Verify actual contents on the user machine.

## Doctor command

`uv run ptcg doctor --json runs/doctor.json` must report:

- Git commit and dirty state;
- OS/architecture/Python/compiler;
- torch/CUDA visibility and device details;
- CPU/RAM/local free disk;
- all asset hashes and license presence;
- native library load and minimal start/select/finish test;
- card CSV parse/count and duplicate-ID checks;
- Kaggle authentication/provider availability without printing secrets;
- Modal authentication/volume availability only when `--cloud` is passed;
- official deadline/runtime limits from a manually verified config;
- pass/fail with actionable remediation.

The command must redact tokens, home-directory secrets and signed URLs.

## CLI contract

Use one stable CLI so local, notebooks and cloud invoke identical code:

```text
ptcg doctor
ptcg assets import|verify
ptcg engine build|smoke|benchmark|soak
ptcg replay sync-index|sync-manifest|plan|download|parse|meta
ptcg deck discover|validate|screen|bakeoff
ptcg train smoke|run|resume
ptcg league inspect|evaluate|promote
ptcg eval tournament|report
ptcg submission build|validate
```

Every mutating or costly command supports `--config`, `--output-dir`, `--dry-run`, `--max-seconds` where meaningful, and exits nonzero on partial failure.

## Configuration and provenance

Use YAML parsed into strict Pydantic models:

- compose an explicit ordered profile list (for example `base → model_v0 → ppo_smoke` or `base → model_v0 → approved PPO → league_main → compute`) and record that list/hashes; later layers may override only schema-declared fields;
- reject unknown keys;
- reject duplicate/conflicting fields that are not declared overrides, and validate mixture sums, caps and cross-field conditions after composition;
- reject any unresolved string beginning with `REQUIRED` before execution;
- resolve paths to absolute form at startup;
- materialize the full resolved config into the run directory;
- calculate a config hash;
- allow CLI overrides but record them;
- never embed secrets in the resolved file.

Each run directory contains:

```text
run_manifest.json
config.resolved.yaml
metrics.jsonl
stdout.log
checkpoints/
eval/
artifacts.json
```

The run manifest follows `schemas/run_manifest.schema.json` and records exact code, data, deck, model, training-opponent population, held-out evaluation population when decision-bearing, and cloud/cost provenance. Training/evaluation/submission manifests cannot validate without model identity; decision-bearing bakeoff/promotion/final-selection manifests cannot validate without frozen meta and held-out-population hashes.

## Reproducible setup acceptance test

From a fresh clone and supplied private asset paths:

```bash
# One-time, reviewed lock creation after pyproject/platform sources are defined:
uv lock
# Thereafter, local reproducibility uses only the local/dev profile:
uv sync --frozen --group local --group dev
uv run ruff check .
uv run pytest -q tests/unit
uv run ptcg assets import --official-archive ... --sample-agents ... --research ...
uv run ptcg doctor
```

Gate G0 passes after a second clean-clone `uv sync --frozen --group local --group dev` succeeds without editing the lock and all planned GPU profile exports/configurations exist. G0 itself is local-only. Each Colab, Kaggle or Modal profile must pass its pinned CUDA/target-environment doctor immediately before that platform’s first gate; it is not a G0 prerequisite.
