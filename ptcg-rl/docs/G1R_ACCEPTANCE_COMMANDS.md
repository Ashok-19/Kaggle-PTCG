# G1R Acceptance Commands

These commands are non-interactive, bounded, and perform no training. Set the
private asset variables locally; do not place their resolved values in reports.

```bash
export PTCG_ENGINE_ROOT=private/path/to/sample_submission
export PTCG_BUILT_ENGINE_ROOT=private/path/to/source_build
export PTCG_CARD_DATA=private/path/to/EN_Card_Data.csv
export PTCG_DEFAULT_DECK=private/path/to/default/deck.csv
export PTCG_BASELINES=private/path/to/baselines
export PTCG_SAMPLE_AGENTS=private/path/to/sample-agent-notebooks
```

## Contract And Baselines

```bash
.venv/bin/python scripts/bootstrap_rule_baselines.py --notebooks "$PTCG_SAMPLE_AGENTS"
.venv/bin/ptcg g1 inventory
.venv/bin/ptcg g1 validate
.venv/bin/ptcg g1 schema-export
.venv/bin/pytest -q tests
.venv/bin/ruff check .
.venv/bin/ptcg g1 acceptance-contract --valid-operations 1000000
```

## Qualifying Runs

The following values remain preregistration proposals until the user approves
`docs/G1R_THRESHOLD_DECISION_PROPOSAL.md`.

For an unattended, resumable run of all four repetitive acceptance jobs, use:

```bash
bash scripts/g1r_run_long_acceptance.sh --accept-proposed-thresholds
```

The approval flag is an explicit acceptance of the preregistered proposal. The
runner preserves immutable per-step evidence, emits a completion receipt, then
recalculates G1R and rebuilds/health-checks the dashboard even when a step
fails. Re-run the same command to resume the arena or RSS soak. Use a new
`--run-dir` after a partial non-resumable comparison or benchmark.

```bash
.venv/bin/ptcg g1 engine-compare \
  --shipped-engine-root "$PTCG_ENGINE_ROOT" --built-engine-root "$PTCG_BUILT_ENGINE_ROOT" \
  --card-data "$PTCG_CARD_DATA" --default-deck "$PTCG_DEFAULT_DECK" \
  --private-baselines "$PTCG_BASELINES" --games-per-library 1000 --workers 8 \
  --ks-max 0.10 --mean-relative-max 0.10 --mean-se-floor 2

.venv/bin/ptcg g1 arena \
  --engine-root "$PTCG_ENGINE_ROOT" --card-data "$PTCG_CARD_DATA" \
  --default-deck "$PTCG_DEFAULT_DECK" --private-baselines "$PTCG_BASELINES" \
  --policies random,first,rule:dragapult-ex,rule:iono,rule:mega-abomasnow-ex,rule:mega-lucario-ex \
  --games-per-cell 280 --workers 8 --wall-seconds 7200 \
  --max-evidence-bytes 1073741824

.venv/bin/ptcg g1 benchmark \
  --engine-root "$PTCG_ENGINE_ROOT" --card-data "$PTCG_CARD_DATA" \
  --default-deck "$PTCG_DEFAULT_DECK" --private-baselines "$PTCG_BASELINES" \
  --workers 1,2,4,8 --games-per-point 200
```

Use an already-reviewed local Python 3.11 image and disable network for the
six-hour run. The launcher exits rather than pulling a missing image.

```bash
bash scripts/g1r_launch_durable.sh ptcg-g1r-soak "$G1R_LOCAL_PYTHON_IMAGE" \
  g1 rss-soak --engine-root "$PTCG_ENGINE_ROOT" --card-data "$PTCG_CARD_DATA" \
  --default-deck "$PTCG_DEFAULT_DECK" --private-baselines "$PTCG_BASELINES" \
  --policy first --workers 4 --duration-seconds 21600 --sample-seconds 60 \
  --warmup-seconds 1800 --peak-bytes-per-worker 2147483648 \
  --slope-upper-mib-per-hour 1.0 --force-restart-after-seconds 300 \
  --max-evidence-bytes 1073741824 --output runs/g1r-rss-soak-qualifying
```

An interrupted arena or soak resumes with the identical command, identical
output directory, and `--resume`. A changed config is rejected.

## Projection And Cloud Validation

```bash
.venv/bin/ptcg dashboard rebuild
.venv/bin/ptcg dashboard doctor
PTCG_ENGINE_ROOT="$PTCG_ENGINE_ROOT" PTCG_CARD_DATA="$PTCG_CARD_DATA" \
  PTCG_DECK="$PTCG_DEFAULT_DECK" bash scripts/g1_cloud_validate.sh
```
