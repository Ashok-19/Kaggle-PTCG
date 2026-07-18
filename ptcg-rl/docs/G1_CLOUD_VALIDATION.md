# G1 Cloud Validation

The cloud entry point is contract-only and non-interactive. It installs the frozen project,
runs unit/integration contract tests, then executes the same bounded native smoke runner used
locally. It contains no training mode, credentials or official assets.

Set private paths in the Colab/Kaggle runtime and run:

```bash
export PTCG_ENGINE_ROOT=/private/path/to/sample_submission
export PTCG_CARD_DATA=/private/path/to/EN_Card_Data.csv
export PTCG_DECK_PATH=/private/path/to/deck.csv
export G1_GAMES=50
export G1_REQUEST_CAP=20000
export G1_WALL_SECONDS=1800
sh scripts/g1_cloud_validate.sh
```

The command emits one immutable manifest under a unique ignored `runs/` directory with
contract, exact loaded-artifact, code, Git/config and coverage/failure evidence. Paths are
stored only as labels relative to their common private root. No training can start from this
entry point; a future training command must use a separate explicit mode and gate.
