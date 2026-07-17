# PTCG RL

Private, gated implementation of the Pokemon TCG AI Battle recurrent RL specialist.

G0 setup:

```bash
uv sync --frozen --group local --group dev
uv run ptcg assets import \
  --official-archive /absolute/path/pokemon-tcg-ai-battle.zip \
  --sample-agents /absolute/path/sample-agents.zip \
  --research /absolute/path/PTCG.zip
uv run ptcg doctor --json runs/preflight/g0-doctor.json
uv run ruff check .
uv run pytest -m unit -q
```

Competition assets are imported only into ignored `private/` storage. No external service, submission, replay download, or paid compute is invoked by G0.

