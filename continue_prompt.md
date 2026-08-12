# Continue KPTCG — copy/paste this into the new ChatGPT session

Continue the KPTCG Kaggle Pokémon TCG AI Battle project from the **repository-grounded canonical handoff**. Do not reconstruct the project from memory or assumptions.

Use Local MCP with both approved repository roots:

- `ptcg` = `/home/nnmax/Desktop/kaggle/PTCG` — canonical Git root and `.chatgpt/handoffs`.
- `ptcg-rl` = `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl` — source, tests, scratch experiments and reports.

The actual Git top-level is `/home/nnmax/Desktop/kaggle/PTCG`.

## Mandatory first reads

Read these **fully and in order** before proposing or implementing the next experiment:

1. `.chatgpt/handoffs/current.local.md` using repo id `ptcg`.
2. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md` using repo id `ptcg`.
3. `.chatgpt/handoffs/2026-08-13-0027-kptcg-lane-promotion-live-regression-continuation.local.md` using repo id `ptcg`.
4. `RULES.md` using repo id `ptcg`.
5. root `AGENTS.md` using repo id `ptcg`.
6. `AGENTS.md` using repo id `ptcg-rl`.
7. `.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md` using repo id `ptcg-rl`.
8. `.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md` using repo id `ptcg-rl`.
9. `ptcg-rl/.chatgpt/handoffs/2026-08-12-submission-55454433.md` and `...55452443.md` when reviewing deployment history.
10. If old production-BC/training details are needed, read `ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md` instead of guessing.

Then verify current repository state read-only:

```bash
git status --short
git log --oneline --decorate -15
git branch -vv
git remote -v
```

If status is too large, summarize it programmatically; **do not clean/reset/stash** the worktree.

At the handoff, HEAD and decorated `origin/main` were `d501448` (`Prefer direct Candy attacker completion`). The worktree was intentionally very dirty: before the handoff writes, a bounded audit found 22 tracked dirty paths and 561 untracked entries. Preserve unrelated changes.

The user explicitly requires **every accepted incremental project change to be committed locally**. Use narrow exact-path commits only. Rejected experiments should not be committed. Never mass-stage. Never push unless explicitly requested.

## Mission and required research style

The objective is to maximize the realistic probability of a **top-10 / gold-range finish**, but never claim a guaranteed Elo/rank before live evidence exists.

The user explicitly wants a **lane approach**:

- do not get trapped in one local optimum;
- do not keep polishing one Dawn heuristic family indefinitely;
- do not overfit one named opponent, one deck, or one current-meta snapshot;
- maintain multiple structurally distinct lanes with falsifiable hypotheses, bounded budgets, kill conditions, independent holdouts and clear promotion gates;
- seek a **different-order / structural improvement**, not cosmetic fixes;
- after the lane cycle is genuinely complete, submit the **current best agent**.

`RULES.md` is the durable contract. Follow it.

The existing hard project promotion target is **>95% overall native win rate on a broad, diverse, both-seat evaluation suite while remaining generalized**. Do not hide catastrophic cells behind aggregate rate.

## Most important fresh live fact — do not miss this

Fresh Kaggle state at the handoff showed:

- raw Dawn submission `55454433`: **858.3** public score — strongest observed NNMax live result;
- 4-Dawn / 3-Spikemuth latest hybrid `55464450`: **682.8**;
- latest `d501448` Boss/Candy agent `55465516`: **605.3**.

The two newer agents had locally defensible/proven changes but were severe live regressions. Therefore **HEAD is not the live-strength anchor**. Raw Dawn is.

Fresh leaderboard at the same snapshot:

1. Luca 1225.4
2. Oshbocker 1193.5
3. flg 1182.9
4. ANDPAD 1174.6
5. Majkel1337 1157.3
6. LumenLiquidity 1155.4
7. LiamK 1149.9
8. Thai 1142.1
9. AlphaTcg 1140.9
10. palsystem 1129.5

These are mutable. Refresh Kaggle before using them. Before any new submission, also refresh NNMax's active/public-safe submissions and remaining daily eligibility/quota.

Do **not** spend another submission slot on an intermediate cosmetic Dawn variant.

## Current Dawn anchor

Raw live-generalist source:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`

Current research source:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`

Exact current deck:

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

Historical broad confirmation for this Dawn/Petrel substrate was 67/80 = 83.75% across eight opponent families. Raw Dawn later had 84/100 retained multi-meta before submission and reached 858.3 live.

During the latest lane session, the post-submission latest Dawn branch screened only 38/48 = 79.17% across the standard eight families:

- Iono 4/6
- Abomasnow 2/6
- stock Lucario 4/6
- Dragapult 5/6
- Alakazam 6/6
- Lopunny 6/6
- current Dragapult 6/6
- modern Lucario 5/6.

>95% has not been achieved.

## Exact engine disposition

Exact current-turn engine:

`ptcg-rl/.chatgpt/tmp/current-engine-v1/`

Important accepted lineage includes exact final-prize Adrena, Shadow Bullet split finishes, tactical search scheduler, early proof-world rejection and shortest exact-goal witness rescue (`33c619b`). Search recall/completeness is already good; ROOT_CAP and shortlist size were audited and were not the bottleneck.

Critical limitation: official native shuffle RNG is not exposed/branch-local seedable. Current-turn terminal/prize proofs are useful; long-horizon board/full-game rollout value is not reproducible enough for live authority.

Submission-style `dawn-exact` was already tested and rejected: 1/10 wins with 4 timeout failures. Keep exact search **offline** unless runtime architecture changes materially.

Latest accepted policy commits:

- `e45747a` guaranteed midgame Boss prizes
- `d30d8da` restrict Boss guard to proven prize routes
- `d501448` direct Candy attacker completion.

Because the `d501448` live score is only 605.3 at handoff, treat these as locally valid tactical corrections, not as live-strength proof.

## Lanes already screened/rejected

Do not repeat these without a materially new premise.

### Existing local Mega-Lucario policies

Six exact-deck controller variants screened against the same eight-family both-seat panel:

- rank1-control 19/32 = 59.375%
- rank1-aura 18/32 = 56.25%
- mk-lgb 16/32 = 50.0%
- modernluc-agent 20/32 = 62.5%
- planner-guards 13/32 = 40.625%
- lunar-ultra 9/32 = 28.125%.

Luca being #1 does not make our local Lucario controller equivalent. Deck != policy.

### Existing Ogerpon/Hydrapple policy

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/oger-hybrid-v3/` had only about 52% semantic agreement with high-rated replay policy and went 4/10 versus old Grim control. Rejected.

Oshbocker remains strategic evidence that a different deck/principle can matter, but our old Grass controller is not a shortcut.

### Dawn deck/resource shapes

- Handheld Fan/Petrel: 24/32, reject.
- Munk3/Boss3: 25/32, reject.
- Petrel4/Stadium3: 25/32, reject.
- Dawn4/Stadium3: 28/32 small local discovery, then **682.8 live**; preserve as a major small-screen overfitting failure.

## High-rated replay/meta assets

Local top-Aug10 sample:

`ptcg-rl/scratch/top-episodes-2026-08-10/`

Top 100 episodes were downloaded individually from the official daily dataset. Current/high-rated deck families found included Mega Lopunny/Froslass, Mega Lucario, Alakazam, Ogerpon/Hydrapple, James/Henry toolbox, Slowking/Kanga, flg Dragapult/Munkidori and Festival grass.

Do not build fake current opponent proxies by putting these decks under unrelated low-overlap policies.

Keep the designated Kanga/Slowking final holdout untouched until the intended final holdout stage unless the user changes that rule.

`ptcg-rl/.venv` contains LightGBM; the generic system Python previously did not. Use `.venv/bin/python` / correct `uv run` for any local model research.

## Immediate task — do this before another heuristic

### Step 1: refresh live truth

Use the current Kaggle tools to requery:

- leaderboard top 20;
- all NNMax recent submissions;
- active/public-safe NNMax agents;
- scores and episode counts for `55454433`, `55464450`, `55465516`;
- submission quota/eligibility.

Do not submit yet.

### Step 2: diagnose the live transfer failure

Get a bounded set of public episodes for:

- raw Dawn `55454433`;
- Dawn4 `55464450`;
- d501448 `55465516`.

Build an evidence report comparing:

- opponent archetypes;
- seat;
- result and game/prize-race length;
- first Grim timing;
- Munkidori + Darkness access/timing;
- search/supporter sequencing;
- board continuity / stranded Active / resource depletion;
- Boss/Candy guard activations where reconstructable;
- recurring failure states;
- generic action/state differences between raw Dawn and later variants.

These episodes are unmatched under native entropy, so use them to discover **patterns/hypotheses**, not claim paired causality.

### Step 3: run at least two structurally distinct research lanes

**Lane A — raw-Dawn structural generalist**

Use raw Dawn as the control. Only alter a generic strategic weakness identified from live evidence. Candidate themes may include resource conservation, attacker continuity, energy/Munkidori distribution, search timing or disruption timing. Do not route on opponent identity.

**Lane B — different strategic basin/controller**

Use current high-level evidence to test a genuinely different principle, but only when a credible controller/policy path exists. A top deck alone is insufficient.

**Lane C — different control architecture**, if evidence supports it

A generic public-state strategic ranker/resource-continuity planner may be tested if it materially differs from already-rejected full-game value/search methods. Do not resurrect a failed global value head without a new target/representation premise.

Kill weak lanes quickly instead of investing equally forever.

### Step 4: broaden the evaluation suite

The old eight-family panel failed to predict the latest live regressions. Add at least one new independent live-derived/faithful family or state holdout before calling a new candidate exponential.

### Step 5: promotion gate

A real survivor must:

- materially beat raw Dawn, not by a one- or two-game noise margin;
- work in both seats;
- have zero invalid/fallback/runtime defects;
- avoid catastrophic family cells;
- survive an independent holdout not used to invent the change;
- then pass a much larger fresh confirmation.

The project target remains >95% generalized native win rate.

### Step 6: package and submit the actual winner

Before submission:

- exact cold package extraction/import;
- root `main.py` + `deck.csv`;
- exact 60-card startup;
- raw `exec` without assuming `__file__`;
- realistic MAIN/non-MAIN callbacks;
- both-seat CABT/native package games;
- zero failures;
- record archive identity and keep rollback artifact;
- refresh quota and active agents.

The user has **already explicitly authorized submitting the current best agent after this lane cycle is genuinely complete**. That authorization is not permission to submit interim cosmetic variants.

If no candidate is truly stronger than the 858.3 raw-Dawn benchmark under the project gates, do not falsely claim an exponential improvement. Continue the structural lane search or report the blocker.

## Important safety/tool rules

- NEVER call `kaggle_create_benchmark_task_from_prompt` unless explicitly asked to create a benchmark task.
- Discover exact Kaggle connector schemas before write-like calls.
- User normally runs heavy Kaggle notebooks manually; assistant prepares/updates and then reads outputs.
- Kaggle auto-extracts ZIP and auto-decompresses `.gz`; mounted filenames are source of truth.
- Do not proliferate unnecessary Kaggle datasets/models.
- Do not use opponent identity or hidden deck/prize information in submitted logic.
- Native `battle_start` is unseeded/system-entropy; independent A/B panels are descriptive, not deterministic causal proofs.
- Some policy copies have absolute-import/module-cache collisions; use import isolation/subprocesses for direct behavior comparisons.
- No reset/clean/stash/mass-stage.
- Commit every accepted change locally, exact intended paths only.
- No Git push unless explicitly requested.

Do not stop at planning. Continue through diagnosis, lane experimentation, broad evaluation and package qualification. Submit only after the evidence supports a real winner under the recorded user instruction.
