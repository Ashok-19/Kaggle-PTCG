# GPU CABT training simulator

This package is an isolated, competition-use-only training simulator derived from the bundled CABT engine semantics.

Design invariants:

- The official CABT source/library remains the CPU reference oracle and is not modified by this package.
- GPU transitions must be differentially validated against the official engine before they may produce PPO training rewards.
- Unsupported or unqualified transitions fail closed; they never silently approximate CABT semantics.
- Local qualification is required before any online/Kaggle/H100 training run.
- The local qualification target must fit within a 4 GiB GPU memory budget.

The initial implementation is intentionally staged: portable fixed-capacity state/RNG primitives and CPU/GPU equivalence tests first, then progressively wider CABT transition coverage.
