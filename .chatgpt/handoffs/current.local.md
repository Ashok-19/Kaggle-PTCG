# KPTCG Current Canonical Handoff

Updated: **2026-08-13 00:27 IST** after the lane-promotion cycle exposed a major live-transfer failure: raw Dawn remains the strongest observed NNMax live agent, while two locally attractive newer Dawn variants scored much worse.

## Read in order

1. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
2. `.chatgpt/handoffs/2026-08-13-0027-kptcg-lane-promotion-live-regression-continuation.local.md`
3. `continue_prompt.md`
4. `RULES.md`
5. root `AGENTS.md`
6. `ptcg-rl/AGENTS.md`
7. `ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md`
8. `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`
9. latest relevant source/scratch/submission files named in the master prompt.

Use repo id `ptcg` for the canonical Git root/handoffs and repo id `ptcg-rl` for code/experiments.

## Current mission

Use a **lane approach** to find a structurally stronger agent. Do not keep polishing the same Dawn heuristic basin because recent live evidence shows that locally proven tactical corrections can regress badly on the ladder.

The user explicitly wants:

- no local-optimum tunnel vision;
- no one-meta or one-opponent specialization;
- no cosmetic fixes marketed as exponential improvement;
- multiple distinct research lanes with kill criteria and independent holdouts;
- after a genuine improvement cycle, submit the current best agent.

Root `RULES.md` is the durable operating contract.

## Verified Git state at handoff

- actual Git top-level: `/home/nnmax/Desktop/kaggle/PTCG`
- code root: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`
- branch: `main`
- HEAD: `d501448` — `Prefer direct Candy attacker completion`
- decorated `origin/main` also pointed at `d501448` at handoff verification
- remote: `https://github.com/Ashok-19/Kaggle-PTCG.git`
- bounded worktree audit before handoff writes: 22 tracked dirty paths, 561 untracked entries

Preserve the dirty worktree. No reset/clean/stash/mass-stage/restore unrelated paths. User requires every accepted incremental change to be committed locally; rejected experiments should not be committed. No push without explicit instruction.

## Fresh live correction — most important fact

Fresh Kaggle query at handoff:

- `55454433` raw Dawn generalized v1: **858.3** — strongest observed NNMax live result.
- `55464450` Dawn4 / 3 Spikemuth + latest guards: **682.8**.
- `55465516` d501448 Boss/Candy latest: **605.3**.

The two newer agents are severe live regressions despite looking locally defensible. Therefore do **not** continue from the premise that HEAD is the strongest policy.

Observed leaderboard top-10 cutoff at the same refresh was ~1129.5; #1 Luca was 1225.4. Reverify all scores before reuse.

## Current Dawn anchor

Raw/live-generalist source:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`

Current research source:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`

Exact current 60:

10 Darkness, 4 Munkidori, 4 Impidimp, 4 Morgrem, 4 Grimmsnarl ex, 4 Rare Candy, 1 Unfair Stamp, 4 Poffin, 3 Night Stretcher, 2 Pokégear, 4 Poké Pad, 2 Boss, 3 Petrel, 4 Lillie, 3 Dawn, 4 Spikemuth.

Historical broad result for current Dawn/Petrel substrate: 67/80 = 83.75% across eight opponents. Raw Dawn later had 84/100 retained multi-meta and reached 858.3 live.

Fresh latest-branch eight-family screen during the interrupted lane session: 38/48 = 79.17%. >95% generalized target remains unmet.

## Current engine disposition

`ptcg-rl/.chatgpt/tmp/current-engine-v1/` contains the exact current-turn symbolic engine. Search recall/completeness is strong and shortest exact witness rescue is accepted (`33c619b`), but long-horizon native rollout is nondeterministic because shuffle RNG is not exposed.

Submission-style `dawn-exact` runtime was rejected: 1/10 wins with 4 timeout failures. Keep exact search as an offline tactical proof/oracle unless runtime architecture changes materially.

## Lane findings already completed

### Existing local Mega-Lucario policy lane

All six screened exact-deck controller variants were below Dawn generalized strength: 59.4%, 56.3%, 50.0%, 62.5%, 40.6%, 28.1%. Deck identity does not reproduce Luca's #1 controller.

### Existing Ogerpon/Hydrapple lane

Old exact-deck `oger-hybrid-v3` had ~52% semantic agreement with high-rated replay behavior and went 4/10 locally. Rejected as current promotion.

### Dawn resource variants

- Fan/Petrel lane: 24/32, reject.
- Munk3/Boss3: 25/32, reject.
- Petrel4/Stadium3: 25/32, reject.
- Dawn4/Stadium3: 28/32 local discovery but 682.8 live, so its promotion narrative is rejected by live counterevidence.

## Immediate next task

1. Refresh leaderboard, NNMax submissions, active/public-safe agents, episode counts and quota.
2. Pull bounded public episodes for `55454433`, `55464450`, `55465516`.
3. Compare live failure patterns: opponent families, seat, game/prize pace, first Grim timing, Munkidori + Darkness access, search/supporter timing, resource depletion, Boss/Candy activation where reconstructable, and recurring board-collapse states.
4. Use that evidence to formulate **generic strategic failure modes**, not named-opponent patches.
5. Open at least two structurally distinct lanes:
   - raw-Dawn structural generalist;
   - a genuinely different strategic basin/controller; optionally a different generic control architecture if evidence supports it.
6. Broaden evaluation beyond the old eight-family panel because it failed to predict the latest live regressions.
7. Kill weak lanes quickly; promote only broad both-seat zero-defect survivors with independent holdouts.
8. Hard project target remains >95% generalized native win rate.
9. Package-qualify the actual winner.
10. User has explicitly asked that the current best agent be submitted **after** the lane cycle is genuinely complete; do not burn slots on interim cosmetic variants.

## Safety / tooling

- NEVER use `kaggle_create_benchmark_task_from_prompt` unless the user explicitly asks for a benchmark task.
- Kaggle scores/leaderboard are mutable; requery before decisions.
- User normally runs heavy Kaggle notebooks manually.
- `ptcg-rl/.venv` contains LightGBM; system Python previously did not.
- Do not consume the designated Kanga/Slowking final holdout prematurely.
- No opponent identity/hidden-deck routing as a shortcut to the generalized target.

## Current truth

>95%: not achieved. 1000+: not achieved. Top 10: not achieved. Raw Dawn 858.3 is the live benchmark to beat. Latest local-proof variants transferred poorly. The next session must search for a different-order improvement, not accumulate more patches.
