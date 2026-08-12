# KPTCG Gold-Path / Lane-Promotion Master Continuation Prompt

Canonical update: **2026-08-13 00:27 IST**

This is the current master continuation context for the 2026 Kaggle Pokémon TCG AI Battle project. It supersedes earlier startup instructions where they conflict, while preserving earlier handoffs and repository evidence as historical sources.

The next session must work from repository evidence, current engine behavior, retained artifacts, and freshly verified Kaggle state. Do not fill gaps with assumptions. The project goal is top-10/gold-range competitiveness, but no local result can guarantee a rank or Elo.

---

# 0. Immediate operating instruction

The user's latest substantive project instruction before this handoff is:

- continue improving with a **lane approach** rather than iterating one local optimum;
- do not get stuck on one meta, one deck, or one class of heuristic;
- seek a **different-order / structural strength improvement**, not cosmetic fixes;
- after the improvement cycle is genuinely complete, submit the **current best agent**;
- the intended comparison is against the approximately 850-Elo raw-Dawn result, so a new submission must not merely be locally defensible while live strength regresses.

The user then requested this handoff because the chat became slow/laggy. Therefore the next session should **resume the project directly** after verification; do not ask the user to repeat context already recorded here.

A durable operating contract now exists at root `RULES.md`. Read it before research. It explicitly defines lane discipline, anti-local-optimum rules, anti-meta-overfitting, evaluation gates, Git rules, and submission discipline.

---

# 1. Repository topology and tool routing

Actual Git top-level:

`/home/nnmax/Desktop/kaggle/PTCG`

Main code/experiment subtree:

`/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`

Local MCP repository IDs:

- `ptcg` -> `/home/nnmax/Desktop/kaggle/PTCG` — use for **canonical root files and `.chatgpt/handoffs`**.
- `ptcg-rl` -> `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl` — use for source, tests, scratch experiments, private baselines, reports, and local arena work.

Canonical handoff directory:

`.chatgpt/handoffs/` at the **parent Git root**, not `ptcg-rl/.chatgpt/handoffs`.

The nested `ptcg-rl/.chatgpt/handoffs` directory contains important historical E01/training context but is not the canonical current pointer.

Git remote:

`https://github.com/Ashok-19/Kaggle-PTCG.git`

Do not use a fabricated/older repo namespace. Do not use web search for local repository facts that Local MCP can verify.

---

# 2. Mandatory read/verification order in the new session

Read in this order before changing code or launching an experiment:

1. `.chatgpt/handoffs/current.local.md` using repo id `ptcg`.
2. This file `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md` using repo id `ptcg`.
3. The dated handoff referenced by `current.local.md`.
4. `continue_prompt.md` at Git root.
5. `RULES.md` at Git root.
6. root `AGENTS.md` using repo id `ptcg`.
7. `ptcg-rl/AGENTS.md` using repo id `ptcg` or `AGENTS.md` using repo id `ptcg-rl`.
8. `ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md`.
9. `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`.
10. latest relevant submission receipts in `ptcg-rl/.chatgpt/handoffs/`.
11. current exact source and scratch files referenced below.
12. only when historical E01/training detail is needed, read `ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md` completely.

Then verify mutable state:

```bash
git status --short
git log --oneline --decorate -15
git branch -vv
git remote -v
```

If `git status` floods the tool output, use a bounded read-only summary; do not clean the worktree.

Refresh Kaggle before any current leaderboard/submission claim:

- competition metadata/deadline/quota if relevant;
- leaderboard top field;
- NNMax submissions and active/public-safe submission set;
- specific submission episodes when diagnosing live failures.

Fresh evidence wins over the text in this handoff if the state changed after 2026-08-13 00:27 IST.

---

# 3. Verified Git state at this handoff

Branch:

`main`

HEAD and `origin/main` at handoff:

`d501448` — `Prefer direct Candy attacker completion`

Recent commits, newest first:

```text
d501448 Prefer direct Candy attacker completion
d30d8da Restrict Boss guard to proven prize routes
e45747a Take guaranteed midgame Boss prizes
90ffcc1 Record submission 55454433
d78ca8d Record submission 55452443
33c619b Rescue exact proofs with shortest witnesses
7bbb55f Early reject failed proof worlds
4fe1d99 Schedule exact search on tactical routes
f9acff5 Take exact Shadow Bullet split finishes
6be5c01 Take exact final-prize Adrena knockouts
b3cafae Use functional action count for search eligibility
940ac52 Structure adversarial discard search
0daa390 Deduplicate functional search actions
2e751f5 Harvest completed turn children immediately
69d3a2f Verify exact root shortlist
```

`git branch -vv` showed `main d501448 Prefer direct Candy attacker completion` with no upstream annotation, while the decorated log showed `origin/main` at the same commit. Reverify rather than assuming this remains true.

The user explicitly requires: **every accepted incremental change must be committed locally**. Rejected experiments should be reverted/not committed. Use narrow-path commits only. Never mass-stage.

At the pre-handoff worktree audit there were:

- `22` tracked dirty paths;
- `561` untracked entries.

Tracked dirty paths at that snapshot:

```text
.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md
.chatgpt/handoffs/current.local.md
.chatgpt/operations/last-write.json
ptcg-rl/.chatgpt/tmp/counterfactual-q/collector.py
ptcg-rl/.chatgpt/tmp/opponent-route/ceiling_analyzer.py
ptcg-rl/.chatgpt/tmp/opponent-route/test_ceiling_analyzer.py
ptcg-rl/.chatgpt/tmp/outcome-ranker/opponent_transition_label_v1.schema.json
ptcg-rl/PROGRESS_REPORT.md
ptcg-rl/PROJECT_STATUS.md
ptcg-rl/configs/gold_path_work_orders_v1.json
ptcg-rl/progress.md
ptcg-rl/reports/artifacts/gold-path-work-orders-review-v1.json
ptcg-rl/reports/decisions/current.json
ptcg-rl/reports/deterministic/CURRENT_HANDOFF.md
ptcg-rl/reports/gates/g3b.json
ptcg-rl/reports/tasks/current.json
ptcg-rl/scripts/gold_path_review.py
ptcg-rl/src/ptcg_rl/decision_engine/__init__.py
ptcg-rl/src/ptcg_rl/deterministic/b1_oracle.py
ptcg-rl/src/ptcg_rl/g3/gold_path.py
ptcg-rl/tests/g3/test_competence_plan_report.py
ptcg-rl/tests/g3/test_gold_path.py
```

Preserve all unrelated dirty state. Do not reset, clean, stash, restore unrelated paths, mass-delete scratch, or overwrite someone else's work merely to make status clean.

---

# 4. Competition/live state freshly verified for this handoff

Competition slug:

`pokemon-tcg-ai-battle`

Recorded final deadline remains `2026-08-16 23:59 UTC` / `2026-08-17 05:29 IST`; reverify if schedule-critical.

Fresh leaderboard top 10 at the handoff query:

1. Luca — `1225.4`
2. Oshbocker — `1193.5`
3. flg — `1182.9`
4. ANDPAD kaggler team — `1174.6`
5. Majkel1337 — `1157.3`
6. LumenLiquidity — `1155.4`
7. LiamK — `1149.9`
8. Thai — `1142.1`
9. AlphaTcg — `1140.9`
10. palsystem — `1129.5`

Thus the observed top-10 cutoff was roughly `1129.5`, far above NNMax's strongest live result. This is dynamic and must be refreshed.

## NNMax submission history relevant to current strategy

Fresh submission search at handoff showed:

### `55465516` — latest submission

- date: `2026-08-12T18:50:08.650Z`
- description: `KPTCG d501448 Dawn v1; proven Boss prize routing + direct Rare Candy attacker completion`
- file: `kptcg-dawn-d501448-v1.tar.gz`
- status: `COMPLETE`
- public score at handoff query: **`605.3`**
- local archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-d501448-v1.tar.gz`
- bytes: `2,611,726`
- SHA-256: `cfab956c9cf8742eedf1b6c47fda545a5b1a4643c8ec7fe5b2d51d1e3632aa9a`

### `55464450` — 4-Dawn / 3-Spikemuth hybrid

- date: `2026-08-12T17:49:14.387Z`
- description: `KPTCG Dawn4 Stadium3 latest: 4 Dawn / 3 Spikemuth architecture + latest accepted Boss/Rare-Candy guards`
- file: `kptcg-dawn4-stadium3-latest-v1.tar.gz`
- status: `COMPLETE`
- public score at handoff query: **`682.8`**
- local archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn4-stadium3-latest-v1.tar.gz`
- bytes: `2,646,373`
- SHA-256: `8149ed3578693386dbd58da0a6e5fa5e919f52f3c28573ebdadb272899c3d380`

### `55454433` — raw Dawn generalized v1

- date: `2026-08-12T09:15:41.490Z`
- description: `KPTCG raw Dawn generalized v1; 84/100 retained multi-meta anchor; replaces over-specialized Shaymin/Cage live build`
- status: `COMPLETE`
- public score at handoff query: **`858.3`**
- local archive: `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-raw-generalized-v1.tar.gz`
- archive SHA from receipt: `582a7d30d978c9497f8a933fa1fd7dfe0d1f306f2659a4df3707ed92c30fa652`
- source `main.py`: `b13bfbabb9b4fb2898de587c82bd3ee65b49dc73bd944ea3334df62a1cc248ca`
- source `deck.csv`: `b7889f39b27779a581ff847814b84075796da33513a9da4ef8df855d1bdf4cdb`
- detailed receipt: `ptcg-rl/.chatgpt/handoffs/2026-08-12-submission-55454433.md`

### `55452443` — Shaymin/Cage anti-control lead

- public score at handoff query: `794.9`
- historically over-specialized; broad local follow-up was weaker than raw Dawn.
- receipt: `ptcg-rl/.chatgpt/handoffs/2026-08-12-submission-55452443.md`

Earlier relevant submissions:

- `55399342` repaired public Nithin: `670.6`
- `55372188` Grim Damage-Transfer Control: `786.2`
- `55356773` compact Lucario: `655.4`
- `55355826` pure-Python Majkel LGB: `581.6`
- `55355636` / `55355125`: validation errors
- `55346905` deterministic Mega Lucario: `575.3`
- `54757553` historical Improved Probabilistic: `715.8`

## Critical live conclusion

The raw-Dawn submission `55454433` is the **strongest observed NNMax live result at this handoff: 858.3**.

The two newer locally plausible variants were severe live regressions at the current snapshot:

- Dawn4/Stadium3: 682.8
- d501448 Boss/Candy: 605.3

Therefore the project must not describe those latest local changes as a meaningful live promotion. They are strong evidence that the current local evaluation/proof loop is missing something important about live strength.

Do not simply keep stacking similar guards. First diagnose why local proof/arena wins failed to transfer.

Simulation competitions can have multiple active agents and scoring eligibility can differ from raw submission history. Requery the public-safe active submissions before deciding what is currently active or before using a new submission slot.

---

# 5. Durable strategy and anti-overfitting rules

Read `RULES.md` for full detail. The most important principles are:

- maintain multiple **structurally different lanes**;
- do not spend the entire budget on Dawn micro-rules;
- do not pivot to a top deck unless the policy/controller is also credible;
- do not optimize one named opponent;
- both seats + diverse families + independent holdouts are mandatory;
- the current hard promotion target is >95% generalized native win rate;
- small screens are discovery only;
- live ladder regressions are counterevidence, not noise to explain away;
- accepted changes are committed locally; rejected changes are not;
- never use opponent identity or hidden-deck knowledge as a shortcut;
- no new Dawn RL/model training by default; deterministic/search-heavy direction remains active unless the user changes it;
- exact search is primarily an offline proof oracle because long-horizon native continuation is nondeterministic and live layering timed out;
- after a complete lane cycle, the user has explicitly asked for the current best agent to be submitted, but not for intermediate cosmetic candidates to consume slots.

---

# 6. Current Dawn generalist substrate

Primary current source:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`

Historical current-engine consistent copies:

- `ptcg-rl/.chatgpt/tmp/current-engine-v1/dawn-deck-consistent-v1/`
- `ptcg-rl/.chatgpt/tmp/current-engine-v1/dawn-deck-consistent-v2/`

Raw live-submission source:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`

## Exact current 60-card Dawn deck

- 10 x Darkness Energy (`7`)
- 4 x Munkidori (`112`)
- 4 x Impidimp (`646`)
- 4 x Morgrem (`647`)
- 4 x Grimmsnarl ex (`648`)
- 4 x Rare Candy (`1079`)
- 1 x Unfair Stamp (`1080`)
- 4 x Poffin (`1086`)
- 3 x Night Stretcher (`1097`)
- 2 x Pokégear (`1122`)
- 4 x Poké Pad (`1152`)
- 2 x Boss's Orders (`1182`)
- 3 x Petrel (`1219`)
- 4 x Lillie (`1227`)
- 3 x Dawn (`1231`)
- 4 x Spikemuth (`1259`)

No Froslass/Snorunt in this current generalist deck.

## Important card semantics used by accepted rules/search

### Grimmsnarl ex `648`

- 320 HP.
- Punk Up on evolution searches deck for up to five Basic Darkness Energy and attaches them to Marnie's Pokémon.
- Shadow Bullet: 180 active damage plus 30 bench damage.

### Munkidori `112`

- Adrena-Brain: if Darkness Energy is attached, move up to three damage counters from one of own Pokémon to an opponent Pokémon once per turn.
- The agent must manually get Darkness Energy onto Munkidori.

### Unfair Stamp `1080`

Legal when one of our Pokémon was KO'd during the opponent's previous turn; own hand to 5, opponent to 2.

### Boss `1182`

Gust; accepted exact guards only force it when the prize route has been proven under the current tactical state.

### Spikemuth `1259`

Searches for Marnie's Pokémon.

### Petrel `1219`

Searches deck for a Trainer.

### Dawn `1231`

Searches deck for a Basic, Stage 1, and Stage 2 Pokémon.

### Poké Pad `1152`

Searches Pokémon without a Rule Box.

### Rare Candy `1079`

Basic -> Stage 2 from hand when legal; not on first turn / newly played Basic restrictions still apply.

### Lillie `1227`

Shuffle hand and draw six, or eight when at six prizes.

### Poffin `1086`

Up to two Basic Pokémon <=70 HP.

### Night Stretcher `1097`

Recover Pokémon or Basic Energy.

---

# 7. Dawn historical strength and current reality

The old strongest broad substrate confirmation was:

`ptcg-rl/.chatgpt/tmp/flg-floor4-research/live-vs-best-confirm-5.json`

For `flg-nf-dawn3-petrel3`:

- **67/80 = 83.75%** across eight opponents, five games per seat per family.
- Alak 9/10
- current Drag 10/10
- stock Drag 7/10
- Iono 9/10
- Lopunny 10/10
- modern Lucario 9/10
- Abomasnow 8/10
- stock/mega Lucario 5/10

This beat historical sibling candidates but was still below the >95% goal.

Raw Dawn later received a retained-meta confirmation of **84/100** before live submission `55454433`. That live agent reached **858.3** at the current handoff query.

## Fresh generalized screen of the post-submission latest Dawn branch

During the lane-promotion session, the latest accepted Dawn code was screened against the eight standard families at three games per seat. Combined result:

- **38/48 = 79.17%**
- Iono: 4/6
- Abomasnow: 2/6
- stock Lucario: 4/6
- stock Dragapult: 5/6
- Alakazam: 6/6
- Lopunny: 6/6
- current Dragapult: 6/6
- modern Lucario: 5/6

This is not a >95% agent and is not evidence of an exponential improvement. It also shows Abomasnow and Lucario are recurring local liabilities.

---

# 8. Accepted exact current-turn engine lineage

Scratch engine root:

`ptcg-rl/.chatgpt/tmp/current-engine-v1/`

Important files:

1. `symbolic_turn_planner.py`
2. `symbolic_adversarial_planner.py`
3. `symbolic_belief_planner.py`
4. `semantic_plan_executor.py`
5. `stateful_terminal_oracle.py`
6. `exact_authority_runtime.py`
7. consistent Dawn agent copies under this directory.

Accepted engine commits leading into the current branch:

- `69d3a2f` Verify exact root shortlist
- `2e751f5` Harvest completed turn children immediately
- `0daa390` Deduplicate functional search actions
- `940ac52` Structure adversarial discard search
- `b3cafae` Use functional action count for search eligibility
- `6be5c01` Take exact final-prize Adrena knockouts
- `f9acff5` Take exact Shadow Bullet split finishes
- `4fe1d99` Schedule exact search on tactical routes
- `7bbb55f` Early reject failed proof worlds
- `33c619b` Rescue exact proofs with shortest witnesses

Then live-policy guards continued:

- `e45747a` Take guaranteed midgame Boss prizes
- `d30d8da` Restrict Boss guard to proven prize routes
- `d501448` Prefer direct Candy attacker completion

## Exact proof witness rescue — `33c619b`

Problem: some candidates exact-dominated fallback across hidden worlds but the linear semantic proof path diverged, causing false rejection.

Rejected solutions before the accepted one:

- development-before-attack ordering: regressed proof coverage;
- semantic contingent trie: 0/5 divergent winners fully separable; conflicting verified continuations could remain simultaneously legal;
- joint hidden-world beam policy search: too brute-force; 500 expansions without policy on first modern-Luc divergence;
- boundary-only / shortest-prefix instrumentation: reduced lengths but did not robustly rescue.

Accepted solution: a dedicated shortest exact-goal witness search that is only allowed to reach the **same already-proven exact `(terminal, prizes)` pair**. It cannot invent a better value.

Constants in `symbolic_turn_planner.py`:

- `PROOF_WITNESS_DEPTH = 9`
- `PROOF_WITNESS_WIDTH = 16`
- `PROOF_WITNESS_EXPANSIONS = 350`

Functions:

- `_shortest_exact_witness(...)`
- `verify_shortest_exact_witnesses(...)`

Diagnostics:

- `proof_witness_searches`
- `proof_witness_rescues`
- `proof_witness_failures`
- `proof_witness_expansions`
- `proof_witness_seconds`

Invariant: witness exact-dominance pair set must equal original verified exact pair set.

Examples:

- Abomasnow divergent candidate: old strategic path lengths `[8,8,9,9]`; same exact goal found in four semantic steps in all worlds.
- Alakazam divergent candidate: old `[6,5,6,10]`; witness `[4,4,4,4]`, roughly 0.435 seconds total.
- hard Iono +2-prize target hit the 350 expansion cap and was cleanly rejected.

Live validation after wiring included successful witness rescues with zero plan/search/invalid failures in the tested samples.

## Search recall/completeness audit

Across 43 eligible states on the generalized panel:

- fallback complete: 43/43
- every searched root complete in every particle
- incomplete roots: 0
- cap-incomplete: 0
- mean solve time roughly 2.997 s/state
- exact shortlist states 10/43
- 26 exact shortlisted roots total.

ROOT_CAP 14 vs functional eligibility 16 audit found 10 rare states with 15-16 roots, but no omitted exact root. Omitted actions were mostly RETREAT/END. Do not raise root cap without new evidence.

Exact shortlist of 3 was also audited: no lower-ranked proposal among roots 4-6 produced a missed passing/better exact route in the sampled high-proposal states. Do not raise shortlist by default.

## Robust exact root classes observed

Among nine audited robust exact-gain roots:

- Darkness attachment: 3
- Munkidori ability: 2
- attack: 1
- Boss: 1
- Petrel: 1
- Night Stretcher: 1

Conclusion: immediate exact misses were often sequencing/setup moves enabling same-turn prize gain, not simply “forgot to attack.”

---

# 9. Accepted tactical guards and rejected broad versions

## Final Adrena guard — `6be5c01`

Audit found 60 exact Adrena KO opportunities: Dawn took 27 and missed 33.

A broad KO guard was rejected by paired terminal-MC diagnostic: fallback 24 wins vs forced KO 21.

Accepted narrow guard: in context 13 after the real context-40 counter packet, force only when target prize value is at least all remaining prizes — an exact final-prize condition.

## Shadow Bullet exact split — `f9acff5`

Corrected protection-aware audit:

- 85 unprotected bench KOs available
- 56 taken
- 29 missed
- necessary final-split opportunities: 8
- Dawn took 7, missed 1.

Guard accounts for active KO, active prize insufficiency, Tera bench protections (IDs 96/117), Shaymin `343` Flower Curtain non-rulebox bench protection, <=30 HP target, and combined prize coverage.

## Unfair Stamp

Audit showed Dawn already used 6/7 high-hand legal opportunities including all Alakazam examples. No broad guard promoted.

## Boss

Generic broad Boss forcing was previously mixed/neutral and rejected. Later accepted commits only force **proven prize routes**, culminating in `e45747a` then `d30d8da`.

## Rare Candy direct attacker completion — `d501448`

This accepted local rule prefers direct Candy attacker completion under its proven condition. It is the current HEAD change. However its live submission `55465516` was only 605.3 at the handoff snapshot, so treat it as a locally valid tactical correction, **not evidence of a stronger live policy**.

---

# 10. Search scheduler and verifier details

`4fe1d99` added `_plausible_exact_turn_route` so search is attempted only when a public same-turn damage route exists:

- attack legal;
- direct Grim evolution legal (`source_id=648`);
- Rare Candy legal;
- Munkidori ability legal;
- retreat into a ready bench Grim.

Tactical final guards run before the scheduler.

A fresh 32-state audit found zero false-negative exact roots/states. A broader functional census reduced search eligibility from 547/557 states to 431, saving about 21% of search calls.

`7bbb55f` early verification reject:

- candidate exact outcome must be >= fallback in every hidden world;
- stop on the first incomplete/worse world;
- exhaustive synthetic 65,792-combination test: zero false rejects and zero missed rejects;
- passing all-world candidates unchanged.

---

# 11. Long-horizon native rollout limitation — do not forget this

`stateful_terminal_oracle.py` was built with module-global snapshot/restore and semantic probe-memory synchronization.

Full-game repeated-rollout canaries were not reproducible even when forcing the same root, hidden determinization seed, and manual coin sequence. Fresh `AgentStart()` did not reset native shuffle RNG.

Examples included repeated Iono/Abomasnow/modern-Lucario trajectories flipping outcomes.

Official `cg.api.search_begin()` exposes hidden deck/prizes/manual coin but **no shuffle RNG seed**. There is no exposed branch-local deterministic shuffle control.

Reproducibility findings:

### Full visible state signatures

- end current turn: 4/8
- next own turn: 1/8

### Exact race tuple `(terminal/result, own prizes, opponent prizes)`

- end current turn: 8/8
- next own turn: 7/8

### Broader board/resource metrics

- end turn: 5/8
- next own turn: 1/8

Conclusion:

- native simulation is trustworthy enough for **current-turn exact terminal/prize proofs**;
- future board/value rollout is not reproducible enough for live authority;
- next-turn exact race results may be diagnostic when repeat-qualified but are not a general value target.

A direct “evolve Grim earlier” next-turn experiment was rejected: a first sparse Drag state looked positive, but a targeted fresh set found zero nondown exact gain across stable cases.

---

# 12. Live exact-search runtime lane — rejected

A submission-style exact runtime wrapper exists at:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-exact/`

It layers `ExactAuthorityRuntime` over Dawn fallback.

Direct native control test versus the old Grim control:

- 10 games
- only 1 win
- 4 timeout failures
- no invalid selections.

This live exact-search lane is rejected. The exact engine remains an offline tactical oracle/proof tool.

Do not reintroduce it into the submission path unless runtime architecture changes materially and a fresh broad strength test passes.

---

# 13. High-rated public replay / live-meta branch

This branch was opened because exact current-turn mechanics were becoming strong while strategic horizon remained the bottleneck.

Official episode index dataset:

`kaggle/pokemon-tcg-ai-battle-episodes-index`

At the earlier evidence snapshot:

- dataset id `10788915`
- version `56`
- index updated 2026-08-11
- `manifest.csv` listed daily episode datasets through 2026-08-10.

Aug-10 dataset:

`kaggle/pokemon-tcg-ai-battle-episodes-2026-08-10`

- dataset id `11598417`
- version 1
- 4,603 episodes
- ~21.47 GB
- top manifest average rating around 1209.623166.

Local disposable sample:

`ptcg-rl/scratch/top-episodes-2026-08-10/`

The daily manifest and top 100 episode JSON files were downloaded individually. Do not commit those large replay files.

Existing Majkel trainer convention confirms the teacher action for observation at step `t` is taken from `steps[t+1][seat].action`; still revalidate on any new replay schema.

## Top-30 / top-100 deck signatures observed

Eight major unique decks appeared among high-rated seats:

1. Mega Lopunny / Froslass.
2. Mega Lucario.
3. AlphaStarmie Alakazam.
4. Ogerpon / Hydrapple grass.
5. James Cox & Henry Chao Area-Zero / Raging Bolt / Ogerpon / Mega Kangaskhan toolbox.
6. ANDPAD/Thai Slowking + Mega Kangaskhan.
7. flg Dragapult + Munkidori / Budew.
8. Dipam Festival grass.

Important exact local deck matches found among 1,198 local `deck.csv` files:

- Lopunny exact: `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/liam-current-lopunny`
- current top Lucario exact: many `ptcg-rl/.chatgpt/tmp/today-lucario-variants/rank1-*`
- Alak exact: `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/alpha-current-alakazam`
- Slowking/MegaKanga exact: many `ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/kanga-own-v*`

flg replay deck was roughly 58/60 overlap with `dipam-current-dragapult`.

No credible local exact/near policy substrate was found for:

- Ogerpon/Hydrapple;
- James toolbox;
- Festival grass.

Do not make fake “current opponent proxies” by swapping these decks under unrelated policies.

Historical top-100 exact-deck occurrence counts from the downloaded sample:

- Ogerpon/Hydrapple: 25 unique episodes / 27 seats; palsystem 15, Oshbocker 12.
- James toolbox: 26 episodes/seats.
- flg/213tubo Dragapult-Munkidori: 19 exact episodes/seats in the main signature.
- Festival grass: only 3 episodes; too sparse then for a credible proxy.

---

# 14. Ogerpon/Hydrapple alternative lane — important negative result

An older exact-deck agent already existed:

`ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/oger-hybrid-v3/`

The deck was exact, but the deterministic policy was not faithful to the high-Elo Grass controllers.

Replay semantic audit over 25 exact-deck episodes / 1,093 decisions found roughly:

- overall exact semantic agreement: `0.5197`
- overall family agreement: `0.6551`
- held-out exact: `0.4981`
- held-out family: `0.6255`
- held-out Oshbocker exact agreement was especially weak (~43.5% in the sampled split).

The old policy over-fired Teal Dance/Ogerpon ability heavily relative to the real high-Elo policy.

Interpretable decision-tree diagnostics suggested useful gates for Teal Dance, Hydrapple ability, Ultra Ball, etc., but they were research clues only.

Native result versus old Grim control:

- `oger-hybrid-v3`: **4/10**.

Therefore this Grass lane was not promoted.

## Important Oshbocker strategic evidence

Two Oshbocker high-rated submissions were observed only ~57 seconds apart in the episode list, one around 1203.9 and one around 1163.2 in the earlier snapshot. They were **not the same deck**:

- stronger submission used the Ogerpon/Hydrapple Grass deck;
- lower sibling used the exact Mega-Lucario shell.

This supports the lane philosophy: large strength differences can come from a different strategic basin, not tiny polishing. But it does not mean our old Grass controller is good.

Fresh leaderboard at this handoff has Oshbocker at 1193.5.

---

# 15. Current top Mega-Lucario alternative lane — closed for existing local policies

Luca is current #1 at the fresh handoff leaderboard with 1225.4. His observed deck is the same exact 60-card Mega-Lucario shell for which the repo has many local variants.

Six conceptually different exact-deck local substrates were screened against the same eight-family both-seat panel, two games per seat/family:

- `rank1-control`: 19/32 = **59.375%**
- `rank1-aura`: 18/32 = **56.25%**
- `mk-lgb`: 16/32 = **50.0%**
- `modernluc-agent`: 20/32 = **62.5%**
- `planner-guards`: 13/32 = **40.625%**
- `lunar-ultra`: 9/32 = **28.125%**

All were below Dawn's generalized level.

Conclusion: the **deck is not the shortcut**. Luca's strength is policy/controller quality we do not currently possess. Do not keep rescreening the same local Lucario variants because the current leaderboard deck is attractive.

If the Lucario lane is reopened, it needs a genuinely better controller reconstruction/principle, not another parameter/priority variant of the existing local set.

---

# 16. Lane-promotion deck/resource tournament immediately before handoff

The lane session mined older Dawn resource-shape variants and re-screened structurally distinct ones.

## `fan1-petrel4`

Old candidate path:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-fan1-dawn1`

Deck change relative to current Dawn was effectively:

- +1 Handheld Fan (`1161`)
- +1 Petrel
- -2 Dawn.

Handheld Fan text: when attached Active is damaged by opponent attack, move an Energy from the attacking Pokémon to an opponent Bench.

Fresh panel result:

- 24/32 = **75.0%**
- helps some Aboma/Luc cells but badly hurts Iono.

Rejected as general promotion.

## `munk3-boss3`

Path:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn2-munk3-boss3`

Resource change:

- +1 Boss
- +1 Petrel
- -1 Munkidori
- -1 Dawn.

Fresh result:

- 25/32 = **78.125%**.

Rejected as no meaningful broad improvement.

## `petrel4-stadium3`

Path:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-dawn-co-23`

Resource change:

- +1 Petrel
- -1 Spikemuth.

Fresh result:

- 25/32 = **78.125%**.

Rejected as no meaningful broad improvement.

## `dawn4-stadium3`

Old path:

`ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn4-stadium3`

Deck change:

- +1 Dawn
- -1 Spikemuth.

Small discovery panel result:

- 28/32 = **87.5%**
- Iono: 1/4
- Abomasnow: 4/4
- stock Lucario: 4/4
- Drag: 4/4
- Alak: 3/4
- Lop: 4/4
- current Drag: 4/4
- modern Lucario: 4/4.

This was the first local deck-shape challenger to clearly exceed the contemporaneous small Dawn screen.

A clean hybrid was built at:

`ptcg-rl/.chatgpt/tmp/promotion-v1/dawn4-stadium3-latest/`

It combined the current accepted Dawn policy/guards with the 4-Dawn/3-Spikemuth deck. Its scratch receipt was updated to the new exact deck/module hashes after the local NativeRulePolicy harness correctly rejected a stale receipt.

This hybrid was later packaged and submitted as `55464450`.

**Live result at handoff query: 682.8.**

Therefore the 87.5% small local discovery signal did **not** transfer. Preserve this as a high-value negative result and a warning against small-panel promotion.

---

# 17. Current strongest-live control and what it implies

Observed strongest NNMax live agent remains raw Dawn `55454433` at 858.3.

The locally more “correct” Dawn4 and d501 variants were much worse live. This gives a new high-priority research question:

> What strategic behavior present in raw Dawn is being disturbed by locally rational tactical/resource corrections, or what opponent distribution/failure mode is missing from the local panel?

Do not answer this from intuition. Use public submission episodes.

The immediate next session should obtain/read the episode lists for:

- raw Dawn `55454433`;
- Dawn4 `55464450`;
- d501448 `55465516`.

Then compare, using public-visible state only:

- opponent archetype distribution;
- early board development timing;
- first Grim timing;
- Munkidori access / Darkness attachment;
- support/search sequencing;
- prize-race pace;
- Boss/Candy override activations where reconstructable;
- failure modes by seat;
- any repeated board-collapse pattern;
- action disagreement between raw Dawn and later versions on same/similar state classes;
- whether the later deck/guards are causing resource overcommitment, search starvation, or tempo loss.

Do not claim causality from unmatched stochastic episodes. Use patterns to formulate new structural hypotheses, then test those hypotheses in controlled local states and fresh broad panels.

---

# 18. Native panel currently used for generalized screening

Primary eight-family opponents:

- Iono: `ptcg-rl/private/baselines/iono`
- Mega Abomasnow: `ptcg-rl/private/baselines/mega-abomasnow-ex`
- stock Mega Lucario: `ptcg-rl/private/baselines/mega-lucario-ex`
- stock Dragapult: `ptcg-rl/private/baselines/dragapult-ex`
- current Alak proxy: `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/alpha-current-alakazam`
- current Lopunny proxy: `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/liam-current-lopunny`
- current Drag proxy: `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/dipam-current-dragapult`
- modern Lucario: `ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1`

Important caveats:

- Some private opponents do not support reset by calling `agent({})`; do not assume Iono can be reset that way.
- Alak proxy can throw `NameError: sys is not defined` in the stateful terminal oracle path even though normal native games work. Treat oracle errors as invalid diagnostics, not losses.
- Native `battle_start` is unseeded/system-entropy. Independent A/B panels are descriptive, not causal.
- Keep the Kanga/Slowking final holdout untouched until the designated final holdout stage unless the user changes this rule.

The current panel is useful but demonstrably insufficient to predict live score perfectly. Add **new independent families/live-derived failure patterns**, not just more games against the same eight, before calling the next candidate exponential.

---

# 19. Public ~1208 agent benchmark negative

A public ~1208 agent was extracted/tested at:

`ptcg-rl/.chatgpt/tmp/public-1200/agent-souta-1208-current/`

64 generalized games:

- overall 35/64 = 54.6875%
- Iono 0/8
- Aboma 4/8
- stock Luc 6/8
- Drag 2/8
- Alak 7/8
- Lop 5/8
- current Drag 4/8
- modern Luc 7/8.

Not a shortcut.

Lesson: public Elo/deck/policy transfer is not reliable without direct native verification.

---

# 20. Production BC / model-training history — preserve but do not restart by default

The old E01 production recurrent BC effort is fully documented in:

`ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md`

Read it for exact 362-episode / 25,056-target corpus history, Kaggle dataset/version quirks, notebook v1/v2/v3 incidents, checkpoint reconstruction, approval contracts, and historical hashes.

Later deterministic handoff evidence records that production recurrent BC ultimately completed:

- 840 optimizer steps;
- epoch 4 selected;
- held-out MAIN agreement ~0.9991;
- fresh Majkel MAIN agreement ~0.9996;
- all-context agreement ~0.9949;
- native H2H/promotion tied or regressed.

Therefore no BC policy became the champion.

The user has since explicitly shifted Dawn development to deterministic/search-heavy work. **Do not start new Dawn RL/model training unless the user changes direction.**

A lightweight research model for an evaluation-only proxy is a different use case and must not be confused with training Dawn.

---

# 21. LightGBM/tooling environment detail

A previous local imitation experiment failed under the generic workspace Python with:

`ModuleNotFoundError: No module named 'lightgbm'`

This was a tooling/environment failure, not a model result.

Later inspection found LightGBM installed at:

`ptcg-rl/.venv/lib/python3.11/site-packages/lightgbm`

Use `ptcg-rl/.venv/bin/python` or an appropriate `uv run` environment for LightGBM-based local research. Do not repeat the false conclusion that LightGBM is unavailable.

Existing reusable trainer:

`ptcg-rl/.chatgpt/tmp/majkel-history/train_semantic_history.py`

It uses semantic labels such as PLAY / ATTACH / EVOLVE / ABILITY / RETREAT / ATTACK / END and splits by episode. For arbitrary new decks, there is no generic `NativeRulePolicy` strategic fallback; supplied private baselines are deck-specific.

---

# 22. Kaggle CLI/MCP operational facts

Local Kaggle CLI is installed/authenticated:

`/home/nnmax/.local/bin/kaggle`

Historical CLI/API version observed: `1.7.4.5`.

The generic installed Kaggle SDK lacked the newer `ApiGetEpisodeReplayRequest` class during one attempt. Do not treat that as data unavailability; use the Local MCP Kaggle episode APIs or the appropriate cached/new SDK when necessary.

Kaggle functions are discoverable through `api_tool.list_resources(paths=["Local_mcp"], query="...")`. Inspect exact schema before invoking.

**NEVER invoke `kaggle_create_benchmark_task_from_prompt`** unless the user explicitly asks to create a benchmark task. Historical benchmark-task incidents from the older E01 workflow must not recur.

The user normally runs Kaggle notebooks manually. Assistant workflow:

1. update one notebook/code package;
2. keep inputs/dataset/model versions tidy;
3. user imports/attaches required inputs and runs;
4. assistant reads/downloads outputs afterward and continues.

Do not proliferate unnecessary datasets/models.

Follow `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`:

- uploaded ZIPs auto-extract;
- `.gz` auto-decompress;
- mounted filenames are source of truth;
- do not add gratuitous runtime checksum/integrity gates unless user asks.

---

# 23. Candidate/package architecture details

Current Dawn package `main.py` is a dependency-free compact tree ensemble + layered deterministic controller. Key modules include:

- `policy_features.py`
- `strategic_policy.py`
- `experts/mirror/main.py`
- `experts/tempo/main.py`
- `coalition_expert.py`
- `matchup_router.py`
- `human_controller.py`
- `residual_guard.py`
- `advisor_guard.py`
- `tactical_guard.py`
- `development_guard.py`
- `robustness_guard.py`
- `human_memory.py`

The package loads compact model assets under `models/` and uses pure Python scoring.

Kaggle raw `exec` may not define `__file__`; current package contains a fallback base-path search under `/kaggle_simulations/agent` / current working directory. Preserve raw-exec compatibility in every new package.

NativeRulePolicy local receipt hash checking is a **local harness identity boundary**. When making a scratch deck hybrid, update its local receipt consistently before running the harness. This is distinct from the user's Kaggle runtime rule against gratuitous notebook checksum gates.

---

# 24. Known rejected directions — do not repeat without new premise

This project has accumulated many negative results. Preserve them to avoid loops.

## Dawn/Grim tactical/resource rejects

- broad Adrena KO forcing;
- generic Boss forcing without exact prize proof;
- broad Budew KO forcing;
- generic early Grim evolution rule;
- development-before-attack global ordering;
- global development-guard removal;
- complete Punk Up trim removal;
- Handheld Fan/Petrel Dawn swap as a general promotion;
- Munk3/Boss3 resource variant;
- Petrel4/Stadium3 resource variant;
- 4-Dawn/3-Stadium small-screen promotion narrative — live score strongly rejected it;
- latest d501 exact Candy/Boss narrative as a live promotion — live score strongly rejected it.

## Search/value rejects

- slow full-turn native search as live authority;
- full-game terminal MC as deterministic label;
- broad one-ply/value search;
- macro heuristic search;
- terminal-only belief search;
- stale four-anchor belief search;
- joint hidden-world beam policy search;
- semantic contingent trie for proof divergence;
- raising root cap without evidence;
- raising exact shortlist without evidence.

## Learned/imitation rejects

- production BC as direct champion;
- generic trajectory/value head for counterfactual ranking;
- public ~1208 agent as a direct policy shortcut;
- existing local Mega-Lucario variants as a Luca-level substitute;
- old Oger/Hydrapple policy as an Oshbocker-level substitute;
- deck-only current-meta proxy when policy substrate has low strategic overlap.

## Older Grim/current-meta rejects from Aug-9 handoffs

Also preserve the older negative set documented in the Aug-9 master/handoffs, including:

- exact flg deck swap;
- broad flg action-order imitation;
- residual clone variants;
- global Spikemuth-first / attack-over-Poffin rules;
- generic Trainer tech churn;
- Lana's Aid broad promotion;
- Crustle/Hari broad router patch beyond minimal proven guard;
- various Lucario continuity/planner/BC grids that did not generalize.

A rejected branch may be reopened only when a premise changes materially.

---

# 25. Immediate next task — lane cycle after the live regression discovery

The next session should **not** start by adding another Dawn guard.

Run the following sequence.

## Step 1 — re-establish live truth

Refresh:

- leaderboard top 20;
- NNMax submission list;
- active/public-safe NNMax agents;
- score/episode count for `55454433`, `55464450`, `55465516`;
- daily submission availability.

Do not submit yet.

## Step 2 — live failure differential: raw Dawn vs the two regressions

Download/read a bounded, recent set of public episodes for the three submissions above.

Build a compact report that compares:

- opponent archetype distribution;
- seat;
- result;
- game length / prize-race timing;
- first Grim timing;
- number/timing of Munkidori with Darkness;
- search supporter usage;
- Boss/Candy guard activations if reconstructable;
- board collapse / stranded active / resource depletion patterns;
- contexts where later agents choose differently from raw Dawn.

This is diagnostic, not paired causal proof.

The objective is to identify **one or more generic strategic failure modes** explaining why locally rational changes transferred poorly.

## Step 3 — launch at least two genuinely different research lanes

### Lane A: Dawn structural generalist

Use raw Dawn as the live anchor, not d501.

Possible themes only if supported by Step 2 evidence:

- preserve early search/development entropy;
- reduce overcommitment of search/evolution resources;
- improve attacker continuity rather than immediate prize greed;
- improve energy/Munkidori resource distribution;
- improve hand-reset/disruption timing;
- generic board-value/race heuristics derived from public state, not opponent identity.

Use exact current-turn engine to prove tactical safety but do not let tactical proof override strategic broad evidence.

### Lane B: different strategic basin

Choose a lane that is not merely Dawn with one card changed. Candidate sources of principle include current high-ranked decks/policies:

- Luca Mega Lucario — only if a materially better controller reconstruction can be obtained;
- Oshbocker/palsystem Ogerpon-Hydrapple — only if the policy can be made much more faithful than the rejected old hybrid;
- flg current Dragapult/Munkidori;
- ANDPAD/Thai Slowking/Kanga as **holdout intelligence**, not necessarily an immediate training target;
- another current top family if fresh public replays reveal a simpler reproducible controller.

A top deck alone is not enough. The lane must include a plausible high-quality decision principle.

### Lane C: policy/control architecture

If Step 2 indicates local hand-coded priority is the limitation, explore a deterministic public-state scoring architecture that can generalize across contexts without heavy runtime search. Examples include:

- generic strategic state score / race score learned or hand-constructed from public variables, validated counterfactually on exact current-turn branches;
- action ranking distilled from exact proofs + high-quality public policy behavior, with hard legality/tactical guards;
- generic resource-continuity planner that evaluates a small number of public strategic invariants rather than full native rollouts.

Do not restart a global value head that already failed counterfactual ranking unless the target/representation is materially different.

## Step 4 — lane kill/promotion screen

Each lane gets a bounded discovery screen, then kill weak lanes fast.

A survivor must:

- beat raw Dawn by a material margin, not 1-2 noisy wins;
- have zero reliability defects;
- preserve both seats;
- avoid catastrophic family cells;
- pass at least one family/state holdout unused in its design.

The existing >95% broad generalized promotion target remains the hard project target.

## Step 5 — broaden beyond the old eight-family panel

Because the old panel failed to predict the latest live regressions, add at least one new independent source of evaluation:

- faithful current family agent if available;
- replay-derived held-out state/action diagnostic;
- final designated holdout only when the project reaches the intended holdout stage;
- current live submission failure states used as **unseen diagnostics**, not memorized opponent routes.

## Step 6 — large fresh confirmation

Only after a lane has a real structural lead:

- run a substantially larger independent both-seat panel;
- report aggregate + each family;
- keep failures in denominator;
- compare to raw Dawn anchor;
- do not cherry-pick seeds/episodes.

## Step 7 — package qualification

Exact candidate artifact must pass:

- cold extraction/import;
- root `main.py` + `deck.csv`;
- exact 60-card startup;
- raw `exec` without `__file__` assumption;
- realistic MAIN and non-MAIN callbacks;
- CABT/native games across both seats;
- zero invalid/fallback/runtime/package failures.

## Step 8 — submit only the real winner

The user has already explicitly requested a submission after the lane cycle is complete. That authorization does **not** justify intermediate cosmetic live canaries.

Before submission, refresh quota/active agents and preserve the best known rollback artifact.

If no candidate is genuinely stronger than the 858.3 raw-Dawn benchmark under the project promotion criteria, do not call a weak variant “exponentially better.” Continue the lane search or report the blocker rather than fabricating progress.

---

# 26. Important scratch/artifact paths

## Current Dawn / engine

- `ptcg-rl/.chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/`
- `ptcg-rl/.chatgpt/tmp/current-engine-v1/`
- `ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/`
- `ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-exact/`

## Current promotion experiment

- `ptcg-rl/scratch/promotion-v1/run_generalized_panel.py`
- `ptcg-rl/.chatgpt/tmp/promotion-v1/dawn4-stadium3-latest/`

## Live submission archives

- `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-raw-generalized-v1.tar.gz`
- `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn4-stadium3-latest-v1.tar.gz`
- `ptcg-rl/.chatgpt/tmp/submissions/kptcg-dawn-d501448-v1.tar.gz`

## Current opponent proxies

- `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/alpha-current-alakazam`
- `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/liam-current-lopunny`
- `ptcg-rl/.chatgpt/tmp/current-deck-proxies/arena-agents/dipam-current-dragapult`
- `ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1`

## Replay/meta research

- `ptcg-rl/scratch/top-episodes-2026-08-10/`
- `ptcg-rl/.chatgpt/tmp/majkel-history/train_semantic_history.py`
- `ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/oger-hybrid-v3/`

## Older current-meta / Grim context

- `ptcg-rl/.chatgpt/tmp/current-meta/`
- `ptcg-rl/.chatgpt/tmp/meta-panel/`
- `ptcg-rl/.chatgpt/tmp/grim-punk-tuning/`
- `ptcg-rl/.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`

## Historical full E01/training context

- `ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md`
- `ptcg-rl/reports/deterministic/CURRENT_HANDOFF.md`

---

# 27. Historical handoff lineage worth reading when needed

Canonical parent handoffs preserve prior phases:

- `.chatgpt/handoffs/2026-07-22-2053-kptcg-g3a-cloud-plan-evidence-first-continuation.local.md`
- `.chatgpt/handoffs/2026-07-24-1034-kptcg-gold-path-audit-decision-evidence-first-continuation.local.md`
- `.chatgpt/handoffs/2026-08-04-1435-kptcg-gold-path-evidence-first-continuation.local.md`
- `.chatgpt/handoffs/2026-08-09-0036-kptcg-grim-current-meta-evidence-first-continuation.local.md`
- `.chatgpt/handoffs/2026-08-09-0125-kptcg-grim-qualified-next-live-slot.local.md`
- `.chatgpt/handoffs/2026-08-09-0435-kptcg-grim-engine-floor4-continuation.local.md`
- `.chatgpt/handoffs/2026-08-09-1237-kptcg-full-context-reconstruction.local.md`

Nested E01 handoffs:

- `ptcg-rl/.chatgpt/handoffs/KPTCG_E01_PRODUCTION_BC_MASTER_PROMPT.local.md`
- `ptcg-rl/.chatgpt/handoffs/2026-08-07-1247-kptcg-e01-production-bc-v3-evidence-first-continuation.local.md`

Do not delete these. They are provenance/history even when their startup instructions are stale.

---

# 28. Special engine/runtime quirks

- Exactly one active native battle per process.
- Check terminal before stale selection state.
- Logs are consumptive; retrieve once per transition and reuse.
- Never truncate legal option sets.
- Multi-select is ordered, unique, and must satisfy min/max; STOP only when legal.
- Separate recurrent/mutable policy state per battle/player/policy.
- Development failures should be visible; promotable runs require zero fallback.
- Native shuffle entropy is not controllable with Python seed.
- Some opponent modules are not safe to reset with `agent({})`.
- Module import collisions are real when loading multiple sibling policy copies with absolute imports. Use import isolation/subprocesses for direct behavior comparisons.
- Raw Kaggle execution may not define `__file__`.

---

# 29. What not to do immediately

Do not:

- submit another Dawn micro-variant before diagnosing the live regression;
- claim d501448 is the current best because it is HEAD;
- claim Dawn4 is best because it won 28/32 locally;
- use exact search live again without solving its timeout issue;
- restart full PPO/Dawn training;
- create fake Oger/James/Festival opponent proxies from unrelated policies;
- treat Luca's deck as Luca's controller;
- consume Kanga/Slowking final holdout prematurely;
- reset/clean/stash the dirty worktree;
- mass-stage or commit unrelated changes;
- push without explicit instruction;
- invoke Kaggle benchmark-task creation;
- trust stale leaderboard scores or active-agent assumptions.

---

# 30. Handoff success criteria for the next session

A good continuation should eventually produce one of two outcomes:

## A. Real promotion

A structurally different candidate that:

- materially beats raw Dawn on broad both-seat native testing;
- survives independent holdouts;
- approaches/passes the >95% generalized target under a large fresh confirmation;
- package-qualifies cleanly;
- has a credible mechanism that is not one named-opponent exploit;
- is then submitted under the user's existing instruction after quota/state refresh.

## B. Evidence-backed blocker / pivot

If no such candidate exists after bounded lane exploration:

- kill failed lanes explicitly;
- preserve the raw-Dawn 858.3 live anchor;
- report exactly what prevents an exponential jump;
- recommend the highest-EV next structural pivot rather than spending submission slots on cosmetic fixes.

Never manufacture “progress” by renaming a locally proven tactical patch as a stronger agent after live evidence says otherwise.

---

# 31. Final concise state snapshot

As of this canonical handoff:

- Git root: `/home/nnmax/Desktop/kaggle/PTCG`
- code root: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`
- branch: `main`
- HEAD / decorated origin/main: `d501448`
- strongest observed NNMax live score: **raw Dawn `55454433` at 858.3**
- newer Dawn4 submission: `55464450` at **682.8**
- newest d501448 submission: `55465516` at **605.3**
- live top-10 cutoff at refresh: roughly **1129.5**
- current #1 at refresh: Luca **1225.4**
- >95% generalized native target: **not achieved**
- 1000+ / top-10: **not achieved and not guaranteed**
- exact current-turn engine: mechanically strong offline, not live-runtime viable
- current local proof/search improvements: insufficient to predict live strength
- existing local Lucario controller lane: rejected
- existing old Oger/Hydrapple controller lane: rejected
- current key problem: identify a new strategic basin / structural control improvement that transfers to live play
- next immediate action: live episode differential across `55454433`, `55464450`, `55465516`, then run at least two structurally distinct research lanes
- user has authorized submitting the current best agent **after** a genuine lane-completion/promotion cycle; do not spend slots on interim cosmetic variants.

End of master continuation prompt.
