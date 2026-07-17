# Repository Instructions for Codex

## Mission

Maximize the probability of a top-20/gold finish in the 2026 Pokémon TCG AI Battle competition. Work one evidence-gated milestone at a time.

## Fixed decisions

- Strategic play is learned from environment reward. Public replay actions are not policy/value supervision in v0.
- First agent is one exact-deck recurrent specialist, <2M parameters.
- v0 is custom PyTorch recurrent PPO with visible semantic entities, GRU memory, complete legal-option scoring, ordered autoregressive multi-select, public critic and terminal `+1/0/-1` reward.
- Main Modal training waits for engine, PPO, deck-selection and scale gates.
- Deck/checkpoint selection uses hard reliability/matchup constraints followed by meta-weighted expected match score `(wins + 0.5 × draws) / games`; never invent a blended score.

## Safety and legal boundaries

- Keep the repository private.
- Never commit/push the official engine, native libraries, card data, sample notebooks, raw replays, checkpoints, submissions, credentials or signed URLs.
- Read and obey the competition-only engine license; do not change or redistribute engine semantics/source.
- Do not submit, launch paid compute or mutate external services without explicit user authorization.
- Preserve user changes; use non-destructive Git/filesystem operations.

## Engine invariants

- Exactly one active battle per process.
- Check terminal result before stale selection data.
- Retrieve consumptive logs once per transition and reuse the snapshot.
- Resolve positional options against the exact current snapshot.
- Dispatch by selection/option types and factual fields, not `selectContext` alone.
- Never truncate the legal option set.
- Multi-select is one ordered, unique list satisfying min/max; STOP only when legal.
- Separate recurrent state per battle/player/policy; reset at initial deck request and terminal/error.
- Development fails loudly with a reproduction capsule. Submission logs and returns a deterministic legal fallback.

## Replay invariants

- Never download a whole daily dataset.
- Fetch index manifest, then daily manifest, then individual named JSON files.
- Default to dry-run; enforce exact byte/file/free-space caps.
- Do not invent Kaggle MCP schemas. Complete `LOCAL_KAGGLE_MCP_NOTES.md` with the user.
- Treat source as elite, rating- and size-selected; do not claim unbiased ladder frequencies.
- PPO buffers accept only `SELF_ROLLOUT` provenance.

## Engineering practice

- Read `PROJECT_STATUS.md` and relevant design doc before editing.
- Maintain one source package; notebooks are thin launchers.
- Strict typed config, unknown keys rejected, resolved config/hash saved for every run.
- Add tests with every fix; minimize failures into regression fixtures.
- Small commits by milestone; never claim a gate without raw evidence.
- Every costly job has run ID, limits, checkpoint/resume, kill command and artifact destination.
- Stop on invalid/fallback, unexplained crash, NaN/Inf, unbounded memory, data/cost cap, checkpoint failure or train/submission parity mismatch.

## Handoff after each gate

Update `PROJECT_STATUS.md` and fill `PROGRESS_REPORT.md` with exact commit, commands, tests, throughput, reliability, metrics, cost and artifacts. Stop before the next compute-heavy phase and request review.
