# KPTCG Evidence-First Continuation — Lane Promotion After Live Regression

Timestamp: **2026-08-13 00:27 IST**

## Why this handoff exists

The chat became slow/laggy during a lane-based promotion cycle. The next session must continue without reconstructing the project from assumptions.

The crucial new evidence is that two locally attractive Dawn variants were actually submitted and both underperformed the older raw-Dawn live agent. This changes the immediate research priority from “finish the latest local patch” to “diagnose live transfer failure and search a genuinely different strategic basin.”

## Current mission

Maximize the probability of a top-10 / gold-range finish before the competition deadline. The user explicitly wants:

- lane-based exploration;
- no local-optimum tunnel vision;
- no one-meta overfitting;
- no cosmetic fixes presented as exponential progress;
- after a genuine improvement cycle, submit the current best agent.

The durable rules are now in root `RULES.md`.

## Repository identity

Actual Git root:

`/home/nnmax/Desktop/kaggle/PTCG`

Main code/experiment root:

`/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`

Use Local MCP:

- repo id `ptcg` for canonical root/handoffs;
- repo id `ptcg-rl` for code/scratch/tests.

Branch: `main`.

Verified HEAD and decorated `origin/main` at handoff: `d501448` (`Prefer direct Candy attacker completion`).

Remote: `https://github.com/Ashok-19/Kaggle-PTCG.git`.

Worktree is intentionally very dirty. Pre-handoff bounded audit: 22 tracked dirty paths, 561 untracked entries. Preserve them. No reset/clean/stash/mass-stage/restore unrelated files.

The user requires every **accepted** incremental change to be committed locally. Rejected experiments are not committed. No push unless explicitly requested.

## Canonical files to read first

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
3. this file
4. `continue_prompt.md`
5. `RULES.md`
6. root `AGENTS.md`
7. `ptcg-rl/AGENTS.md`
8. `ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md`
9. `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`
10. submission receipts `ptcg-rl/.chatgpt/handoffs/2026-08-12-submission-55454433.md` and `...55452443.md`

For old E01/training history, read `ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md` instead of guessing.

## Fresh live Kaggle state at handoff

Fresh leaderboard top 10:

1. Luca 1225.4
2. Oshbocker 1193.5
3. flg 1182.9
4. ANDPAD kaggler team 1174.6
5. Majkel1337 1157.3
6. LumenLiquidity 1155.4
7. LiamK 1149.9
8. Thai 1142.1
9. AlphaTcg 1140.9
10. palsystem 1129.5

Scores move; refresh before reuse.

### NNMax live submissions that define the current problem

**Raw Dawn `55454433`**

- COMPLETE
- observed score: **858.3**
- strongest observed NNMax live result at this handoff
- local archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-raw-generalized-v1.tar.gz`
- pre-submit retained multi-meta: 84/100

**Dawn4/Stadium3 `55464450`**

- COMPLETE
- observed score: **682.8**
- archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn4-stadium3-latest-v1.tar.gz`
- bytes 2,646,373
- SHA `8149ed3578693386dbd58da0a6e5fa5e919f52f3c28573ebdadb272899c3d380`
- this candidate had looked excellent on a small local discovery screen (28/32 = 87.5%) but failed to transfer live.

**Latest d501448 `55465516`**

- COMPLETE
- observed score: **605.3**
- archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-d501448-v1.tar.gz`
- bytes 2,611,726
- SHA `cfab956c9cf8742eedf1b6c47fda545a5b1a4643c8ec7fe5b2d51d1e3632aa9a`
- description cites proven Boss prize routing + direct Rare Candy attacker completion.

This is the core new evidence. Do not call the newest code stronger merely because it is more locally “correct.”

## Current generalist Dawn substrate

Primary source:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`

Raw live source:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`

Current exact deck:

- 10 Darkness Energy
- 4 Munkidori
- 4 Impidimp
- 4 Morgrem
- 4 Grimmsnarl ex
- 4 Rare Candy
- 1 Unfair Stamp
- 4 Poffin
- 3 Night Stretcher
- 2 Pokégear
- 4 Poké Pad
- 2 Boss
- 3 Petrel
- 4 Lillie
- 3 Dawn
- 4 Spikemuth

Historical broad 80-game result for `flg-nf-dawn3-petrel3`: 67/80 = 83.75% across eight opponents.

Raw Dawn later had 84/100 retained multi-meta and then reached 858.3 live.

Fresh current-branch eight-family screen during the latest lane session: 38/48 = 79.17%:

- Iono 4/6
- Aboma 2/6
- stock Luc 4/6
- Drag 5/6
- Alak 6/6
- Lop 6/6
- current Drag 6/6
- modern Luc 5/6.

Hard >95% generalized target remains unmet.

## Exact current-turn engine state

Scratch root:

`ptcg-rl/.chatgpt/tmp/current-engine-v1/`

Key files:

- `symbolic_turn_planner.py`
- `symbolic_adversarial_planner.py`
- `symbolic_belief_planner.py`
- `semantic_plan_executor.py`
- `stateful_terminal_oracle.py`
- `exact_authority_runtime.py`

Latest major accepted engine commit before policy guards: `33c619b` shortest exact-goal witness rescue.

Engine recall/completeness audit over 43 eligible states found fallback complete 43/43, all searched roots complete, zero cap-incomplete states. ROOT_CAP 14 and exact shortlist 3 were not the bottleneck.

Important limitation: official native shuffle RNG is not exposed or branch-local seedable. Current-turn exact terminal/prize proofs are trustworthy enough; future board/full-game rollout value is not reproducible enough for live authority.

A submission-style exact runtime wrapper was directly tested and rejected: 1/10 wins with 4 timeout failures vs old control. Keep exact search offline unless runtime architecture changes materially.

## Current accepted guard history

- `6be5c01` exact final-prize Adrena KO guard
- `f9acff5` exact Shadow Bullet split finish guard
- `4fe1d99` tactical-route search scheduler
- `7bbb55f` early reject failed proof worlds
- `33c619b` shortest exact proof witnesses
- `e45747a` guaranteed midgame Boss prize route
- `d30d8da` restrict Boss guard to proven prize routes
- `d501448` direct Candy attacker completion

The latest two live submissions prove that locally exact tactical improvements are not sufficient to raise live Elo. Do not keep stacking similar rules without a structural diagnosis.

## Latest lane tournament results

### Alternative Mega-Lucario controller lane

Six exact-deck local policy substrates were screened and all lost to Dawn generalized strength:

- rank1-control 19/32 = 59.375%
- rank1-aura 18/32 = 56.25%
- mk-lgb 16/32 = 50.0%
- modernluc-agent 20/32 = 62.5%
- planner-guards 13/32 = 40.625%
- lunar-ultra 9/32 = 28.125%

Luca being #1 does not make our local policies equivalent. Deck != controller.

### Ogerpon/Hydrapple lane

Old exact-deck policy `ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/oger-hybrid-v3/` had only ~52% semantic agreement overall with the top replay policy, weak held-out Oshbocker agreement, and went 4/10 against old Grim control. Rejected.

Oshbocker evidence still matters strategically: an older high-rated Grass submission and a lower Mega-Lucario sibling were different decks, supporting the existence of different strategic basins. But our Grass controller is not yet competitive.

### Dawn resource/deck variants

- Fan1/Petrel4: 24/32 = 75.0%, Iono collapse; reject.
- Munk3/Boss3: 25/32 = 78.125%; reject.
- Petrel4/Stadium3: 25/32 = 78.125%; reject.
- Dawn4/Stadium3: 28/32 = 87.5% discovery, then **682.8 live**; live rejection of the small-screen promotion narrative.

## Public high-rated replay branch

Local sample:

`ptcg-rl/scratch/top-episodes-2026-08-10/`

Top 100 Aug-10 episodes were downloaded individually from the official daily dataset. Major current/high-rated deck families identified included Mega Lopunny/Froslass, Mega Lucario, Alakazam, Ogerpon/Hydrapple, James/Henry toolbox, Slowking/Kanga, flg Dragapult/Munkidori, and Festival grass.

Exact local policy/deck proxies exist for Lopunny, Alakazam, several Lucario variants, and Slowking/Kanga deck lists. No credible policy substrate existed for Oger/Hydrapple, James toolbox, or Festival grass, so do not make fake deck-swap proxies.

Do not consume the designated Kanga/Slowking final holdout prematurely.

## LightGBM environment note

System Python previously raised `ModuleNotFoundError: lightgbm`. `ptcg-rl/.venv` **does** contain LightGBM. Use `.venv/bin/python` or appropriate `uv run` for local model research.

## Main next task

### 1. Refresh live truth

Requery leaderboard, all NNMax submissions, active/public-safe agents, episode counts, and quota. Do not submit yet.

### 2. Compare live failure patterns

Pull bounded public episodes for:

- `55454433` raw Dawn
- `55464450` Dawn4/Stadium3
- `55465516` d501448

Compare opponent archetypes, seats, game length, prize-race timing, first Grim timing, Munkidori/Darkness access, supporter/search sequencing, Boss/Candy guard activations where reconstructable, board collapse/resource starvation, and repeated failure states.

This is descriptive because episodes are unmatched and native randomness is uncontrolled. Use it to generate hypotheses, not to claim causal proof.

### 3. Open at least two structurally distinct lanes

**Lane A — raw-Dawn structural generalist**

Use raw Dawn as the anchor. Fix a generic strategic failure found in live episodes: continuity, resource conservation, energy distribution, search timing, disruption timing, or similar. Exact current-turn search may prove safety but cannot be the only reason to promote.

**Lane B — different strategic basin**

Choose a different deck/control principle only if there is a credible controller path, not merely a top deck. Candidates may come from current Luca/Oshbocker/flg/other high-ranked public evidence.

**Lane C — different control architecture** if warranted

A generic public-state strategic scorer/ranker or bounded continuity planner may be worth testing if it materially differs from the already-rejected full-game value/search approaches.

Kill weak lanes quickly.

### 4. Broaden evaluation beyond the old eight-family panel

The old panel failed to predict the latest live regressions. Add new independent live-derived/faithful family evidence and holdout diagnostics. Do not optimize only on the same eight families.

### 5. Promotion

A survivor must be structurally better, both-seat, broad, zero-defect, and survive independent holdouts. Existing project hard target remains >95% generalized native win rate.

### 6. Package and submit only the actual winner

The user has explicitly asked for the current best agent to be submitted after the lane cycle is complete. Do not burn slots on interim micro-variants. Reverify quota and active agents first.

## Important paths

- `ptcg-rl/scratch/promotion-v1/run_generalized_panel.py`
- `ptcg-rl/.chatgpt/tmp/promotion-v1/dawn4-stadium3-latest/`
- `ptcg-rl/.chatgpt/tmp/current-engine-v1/`
- `ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`
- `ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`
- `ptcg-rl/scratch/top-episodes-2026-08-10/`
- `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/`
- `ptcg-rl/.chatgpt/tmp/today-lucario-variants/`
- `ptcg-rl/.chatgpt/tmp/submissions/`

## Kaggle/tool safety

- NEVER call `kaggle_create_benchmark_task_from_prompt` unless the user explicitly requests a benchmark task.
- Discover exact Kaggle connector tool schemas before write-like calls.
- User generally runs heavy Kaggle notebooks manually.
- Kaggle auto-extracts ZIP and decompresses `.gz`; mounted filenames are source of truth.
- Do not create unnecessary dataset/model clutter.

## Final stopping state

The project is **not** at >95%, not at 1000+, and not top 10.

The current live benchmark to beat is raw Dawn at 858.3, while the two newest variants are much worse live. The correct next move is not another cosmetic guard; it is to use live episode evidence to find the missing strategic dimension and run a disciplined multi-lane search for a different-order improvement.
