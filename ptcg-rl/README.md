# PTCG RL

Private, gated implementation of the Pokemon TCG AI Battle recurrent RL specialist.

G0 setup:

```bash
uv sync --frozen --group local --group dev
uv run ptcg assets import \
  --official-archive /absolute/path/pokemon-tcg-ai-battle.zip \
  --sample-agents /absolute/path/sample-agents.zip \
  --research /absolute/path/PTCG.zip
uv run ptcg doctor --policy development --json runs/preflight/g0-doctor.json
uv run ruff check .
uv run pytest -m unit -q
```

Competition assets are imported only into ignored `private/` storage. No external service, submission, replay download, or paid compute is invoked by G0.

Python 3.11 is the primary runtime-matching profile; the shared lock also
supports Python 3.12 as secondary development compatibility. Final submission
qualification uses `ptcg doctor --policy submission` and remains blocked until
the exact official Python patch and timeout are verified.

The isolated read-only dashboard is documented in `dashboard/README.md`.

`Ashok-19/Kaggle-PTCG` is the sole active private repository. Local work is
limited to development, metadata, filtered acquisition, tests, tiny engine
smoke, packaging and final-model inference/runtime validation. Small training
smokes run on Colab/Kaggle; meaningful self-play, PPO/league training and large
evaluation run on Modal.
