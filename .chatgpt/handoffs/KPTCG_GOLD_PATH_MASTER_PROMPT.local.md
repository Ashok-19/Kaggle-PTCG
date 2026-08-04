# KPTCG Gold-Path Evidence-First Master Continuation Prompt

Generated UTC: `2026-07-24T10:34:42Z`

This is the authoritative local-only continuation prompt for the KPTCG Kaggle Pokémon TCG AI Battle project. It supersedes the old G3a-cloud-plan handoff as the current session context, but does not delete or rewrite historical evidence. Read this file completely before proposing, editing, launching, publishing, or training anything.

---

## Paste the following into the new session

Continue the KPTCG Kaggle Pokémon TCG AI Battle project from the repository-grounded evidence handoff.

Use `Local_mcp` with repository id `ptcg`. Do not use an older/invented repository namespace and do not bypass repository safety with ad hoc writes, staging, commits, deletion, or external mutation. Use repository inspection/write/review tools and deterministic `workspace_exec` commands.

The governing rule is: **never work from assumptions when repository evidence, retained artifacts, current official sources, or tool output can answer the question.** Treat mutable facts—including leaderboard position, quota, forum content, Kaggle asset versions, notebook status, remote Git state, deadlines, runtime and hardware—as untrusted until reverified. Reports and dashboards are claims to recalculate, not proof merely because they contain `PASS`.

The current strategy is no longer the frozen PPO-first sequencing. An independent expert audit concluded that the highest expected gold-decision value per compute is a gated hybrid path: exact-deck/teacher qualification, full-compound-action recurrent imitation, on-policy validation, then bounded KL/BC-regularized PPO, while keeping a deterministic Mega Lucario specialist shippable. This strategy has been accepted as the working decision in conversation, but **has not yet been formalized in a repository decision record**. The first repository change must be a reviewed superseding decision (`DEC-011` or `DEC-AUDIT-001`), not silent mutation of the frozen G3b plan.

No meaningful training is currently authorized. No Kaggle notebook launch, topology canary, PPO run, replay expansion, submission, active-agent change, deck freeze, model publication, Git push, paid compute, Modal job, or external mutation is implied by this handoff.

## Mandatory first reads

Read these in order:

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
3. the timestamped structured handoff referenced by `current.local.md`
4. `AGENTS.md`
5. `01_MASTER_PLAN.md`
6. `ptcg-rl/PROJECT_STATUS_ANALYSIS.md`
7. `ptcg-rl/PROJECT_STATUS.md`
8. `ptcg-rl/PROGRESS_REPORT.md`
9. `ptcg-rl/reports/tasks/current.json`
10. `ptcg-rl/reports/gates/g3a.json`
11. `ptcg-rl/reports/gates/g3b.json`
12. `ptcg-rl/configs/g3a_evaluation_v1.json`
13. `ptcg-rl/configs/g3b_competence_plan_v1.json`
14. `ptcg-rl/reports/artifacts/g3b-competence-plan-v1.json`
15. `ptcg-rl/reports/artifacts/g3b-competence-plan-review-v1.json`
16. `ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`
17. all four files under `audit-reports/`, especially `KPTCG_GOLD_AUDIT_REPORT.md` and `KPTCG_GOLD_AUDIT_DECISIONS.json`
18. relevant implementation/tests listed later in this prompt.

Also read the old handoff only as historical background when needed:

- `.chatgpt/handoffs/KPTCG_G3A_CLOUD_PLAN_MASTER_PROMPT.local.md`
- `.chatgpt/handoffs/2026-07-22-2053-kptcg-g3a-cloud-plan-evidence-first-continuation.local.md`

Those old files are obsolete as startup instructions because G3a cloud qualification, G3b planning, TPU work and the external audit occurred afterward.

If any cited file is missing, search the repository and report the exact discrepancy. Never fabricate contents or silently substitute a similarly named file.

## Mandatory repository verification

Immediately verify:

```bash
git status -sb
git log --oneline --decorate -12
git branch -vv
git remote -v
git rev-list --left-right --count origin/main...main
```

Use `Local_mcp.repo_git_status` and `Local_mcp.workspace_exec` rather than assuming this handoff remains current.

Verified at handoff creation:

- repository root: `/home/nnmax/Desktop/kaggle/PTCG`
- project directory: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`
- repository id: `ptcg`
- branch: `main`
- HEAD: `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`
- HEAD subject: `fix(g3b): repair TPU environment qualification`
- tracked project files: unchanged at handoff creation
- current worktree: not technically clean because the four user-provided `audit-reports/` deliverables are untracked; local handoff files are ignored and do not appear in status
- preserve the four untracked audit reports exactly; do not delete, overwrite, stage or commit them unless the user deliberately approves integrating them into project history
- remote: `origin` -> `https://github.com/Ashok-19/Kaggle-PTCG.git`
- locally known `origin/main`: `e561fdea3202c643c724b1132a575c369da71c8a`
- local branch: one commit ahead and zero behind the locally known remote reference (`0 1` from `origin/main...main`)
- `main` has no upstream annotation in `git branch -vv`
- no push of commit `32376b...` occurred in this session.

Recent commits, newest first:

```text
32376b0 fix(g3b): repair TPU environment qualification
e561fde (origin/main) feat(g3b): add TPU environment qualification runner
d308abc chore(g3b): seal competence plan evidence
098997a feat(g3b): freeze competence plan contract
da0a89f chore(g3a): close cloud correctness gate
3a9aaaa chore(g3a): seal seeded rollout correction
6b7975b fix(g3a): restore stochastic cloud rollouts
2698eaa chore(g3a): seal corrected Kaggle inputs
95651d6 fix(g3a): remove Kaggle preflight checks
4022845 chore(g3a): publish approved Kaggle inputs
b699f3d docs(g3a): freeze reviewed Kaggle correctness plan
78633d3 fix(g3a): report reviewed plans consistently
```

The remote-tracking reference can be stale. Never claim a push, remote equality, or current GitHub state without verification. Never push unless explicitly requested.

Handoff files are intentionally local/ignored. Do not stage or commit `.chatgpt/handoffs/*.local.md` unless the user explicitly converts them into tracked documentation.

## Source-of-truth hierarchy

Resolve contradictions in this order:

1. current official Kaggle/organizer rules, engine, card data and runtime contract;
2. direct user instructions and `AGENTS.md`;
3. reviewed repository decision records and immutable configs;
4. raw run artifacts, manifests, exact hashes and contract tests;
5. independently recalculated gate reports;
6. project status/progress/task files;
7. external audit conclusions, which are recommendations unless converted into a repository decision;
8. Kaggle discussion reports and research transfer arguments;
9. dashboards and old narrative summaries.

A current official fact can supersede a stale local snapshot. A forum claim never becomes project fact without replication or appropriate evidence classification.

## Mission and current deadlines

The mission is to maximize the realistic probability of a top-20/gold-medal finish without implying a medal is guaranteed.

Recorded deadlines:

- Simulation entry/team deadline: `2026-08-09T23:59:00Z`
- Simulation final deadline: `2026-08-16T23:59:00Z`
- Strategy entry deadline: `2026-09-06T23:59:00Z`
- Strategy final/report deadline: `2026-09-13T23:59:00Z`
- internal architecture/deck lock target: approximately August 7–9
- internal training/config freeze: approximately August 12
- internal packaging freeze: approximately August 14.

These are mutable external facts. Verify current official sources before making schedule-critical decisions. The audit’s dates were calculated at `2026-07-24T09:43:04Z` and become stale automatically.

## Current gate truth

Verified repository state before the new audit decision is formalized:

- `G0`: `SUCCEEDED / PASS`
- `G1R`: `SUCCEEDED / PASS`
- `R1`: `SUCCEEDED / PASS` on the approved retained sample
- `G2`: `SUCCEEDED / PASS` as architecture, parity, checkpoint and reliability evidence
- `G3a`: `SUCCEEDED / PASS` for toy PPO correctness only
- `G3b`: `BLOCKED / NOT_REVIEWED`; only its old PPO-first plan is frozen/reviewed
- `D1`: not started; no exact specialist has been selected or frozen
- `G4`, `G5`, `G6`: not started.

No Pokémon policy competence, competitive strength, gold-level performance or settled live result is established.

The old current task `T-G3B-INTEGRATION-001` remains valid as an infrastructure requirement, but it is no longer the sole sequential task. It should run in parallel with teacher/deck qualification and the deterministic hedge after the superseding decision record is created.

## Immutable completed history

### G0 repository consolidation

- active private repository: `Ashok-19/Kaggle-PTCG`
- inactive private migration backup: `Ashok-19/Kaggle-PTCG-RL`
- clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`
- ROGII is read-only reference material and must not be modified.

### G1R engine/action contract

G1R is closed as PASS. Preserve these invariants:

- one native battle per process;
- terminal checked before stale selection data;
- consumptive logs retrieved once per transition and reused;
- complete legal option set, never first-N truncation;
- final adapter revalidates request identity/type/count/uniqueness/range/legality/availability;
- ordered unique multi-selection without replacement;
- first-class STOP with legality mask and log-probability contribution;
- recurrent state owned by `(episode_uuid, player, policy_id)`;
- exact duplicate inference is idempotent;
- stale/out-of-order requests fail closed;
- unknown/impossible semantics fail closed with bounded reproduction evidence;
- development fallback is forbidden in qualifying runs;
- actor and critic consume public information only.

Historical evidence includes the one-million-operation selection corpus, 10,080-game arena, throughput matrix, worker replacement/recurrent isolation, >200-log burst handling and six-hour RSS soak. Read exact reports before quoting metrics not listed here.

### R1 replay contract

R1 PASS facts:

- approved plan SHA-256: `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934`
- episode files: `20`
- bytes: `83,981,423`
- largest file: `6,303,684`
- acquisition audit SHA-256: `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`
- decisions: `2,999`
- selected options: `3,275`
- reconstructed STOP markers: `21`
- ordered requests: `16`
- official card-data SHA-256: `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`
- semantic stream SHA-256: `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`
- independent mismatches: `0`
- peak loader RSS: `68.17578125 MiB`
- resolved incident: `ptcg-rl/reports/incidents/r1-card-data-provenance-hash.json`.

The loader maps action at step `t` to the preceding active selection request at `t-1`, validates zero-based legal indices, uniqueness/count/availability and infers STOP when selected count is below maximum.

The approved R1 sample does not authorize new episode download or action-supervision training. A new decision must define exact files, bytes, provenance and label use before E01 acquisition/training.

### G2 model and action schema

G2 is PASS as an engineering artifact:

- model schema SHA-256: `61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68`
- private card-table SHA-256: `7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0`
- trainable parameters: `970,022`
- architecture SHA-256: `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`
- compact target remains below 2M parameters unless separately changed.

Architecture:

- public semantic projection;
- static card/entity encoding and relation features;
- transformer pooling;
- event/public GRU recurrence;
- ragged complete legal-option scorer;
- public value head;
- autoregressive ordered unique multi-select;
- first-class STOP.

Raw serial magnitude and option transport order were intentionally excluded from actor features. The audit recommends treating option position as an explicit ablation, not silently adding it.

### G2 CPU/GPU parity

- current-source qualification bundle v4 commit: `c660f74b26fca74915931091ac0fe365f7f005f5`
- bundle SHA-256: `56b4e93671609a8d24887480cbf1d0dfc0c38b60e1cad55d0cf95f4e50744506`
- 11 manifest entries matched; 10 local preflight checks passed; seven gradients selected; no optimizer/training loop.
- private GPU version id: `336514431`, Tesla T4
- private CPU version id: `336517420`
- 1,596 numeric values, zero parity failures under combined `atol=rtol=1e-5`
- maximum absolute difference: `1.52587890625e-05`
- maximum tolerance ratio: `0.4138225953505397`
- CPU batch-1 p99 latency: `8.802885 ms`
- external HTTP blocked in CPU probes.

An automatic CLI launch once received a P100 and was rejected. Hardware must be observed, not assumed. The user manually selects required accelerator sessions.

### G2 deterministic checkpoint

- implementation commit: `6b3a3b4829b205d62e210fae7e396db33fdb9a5a`
- package path: `ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip`
- bytes: `5,429,190`
- SHA-256: `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`
- sorted ZIP_STORED, pickle-free canonical tensor stream;
- duplicate builds byte-identical;
- 1,150 numeric and 16 exact actor/value/recurrent/decoder/log-prob values reproduced;
- zero required drift;
- 25 adversarial fail-closed branches.

### G2 10,000-game reliability

- user-run notebook: `ashok205/kptcg-g2-neural-reliability-v1`
- script version id: `336684242`
- Internet off; exactly two Tesla T4 devices
- 10,000/10,000 complete games
- 1,213,203 engine requests
- 20,791 multi-select requests
- 1,156,383 meaningful choices
- zero invalid, fallback, post-terminal, recurrent, nonfinite, crash and timeout counters
- 1.97684 games/s
- 228.59829116666842 meaningful choices/s
- notebook wall approximately 85.50 minutes
- games ledger bytes: `28,783,333`
- games ledger SHA-256: `39d7d43d142bec64bcace5da5151ca6bccba2bd533c47d1957a4ad7505cc918f`
- runner receipt SHA-256: `9afc97ffe2df08dcb84ebe087e993649b868719e547204efb04c51b776f7c3e7`
- independent review SHA-256: `7a1f77f452db96015a18c54631952b3d67b8bcd7cea7314372f3e45003681e6e`
- dataset `ashok205/g2-neural-reliability-inputs`, version 1, READY
- input bytes `12,088,771`, SHA-256 `d4fa4a09e5c86cc3a2c93461b2127634dc197a7241d99d36f78bc35ce878b6ec`.

This proves reliability, not game strength.

### G3a recurrent PPO correctness

The project-native PPO stack supports:

- exact compound-action replay including STOP;
- complete-action forced classification;
- PPO clipping/KL/value/entropy logic;
- terminal/live-truncation GAE;
- recurrent slices that cannot cross owner/version/boundaries;
- finite-gradient gates;
- atomic SHA-bound restricted training checkpoints;
- model/optimizer/scheduler/counters/league/rollout boundary/Python RNG/NumPy RNG/Torch CPU/CUDA RNG restoration.

Local implementation commits:

- `68407689ccfb18236f14f78dd68360704f408682`
- `cae42da47bc9f3491869e8afd0e1254061b9f585`
- promotion history culminated in later G3a close commit `da0a89f...`.

Toy tasks: masked bandit, recurrent cue and variable-option ordered multiselect. Local selected configuration used 1,024 choices/model at lr 0.005. Candidate 512/lr 0.005 failed multi-select 0.75; 1,024/lr 0.01 passed but was rejected for peak preclip gradient 1.5519 versus 0.8668. All three declared seeds passed with trainable scores 1.0, stateless cue 0.5, recurrent margin 0.5 and zero replay/ratio/counter errors.

The first cloud run failed because the cloud runner used greedy collection instead of seed-bound categorical sampling. This was reproduced and corrected without changing thresholds/budgets. The corrected source commit is `6b7975bf518c36ff59338b6793ec52530c73f173`, rollout sampling `seeded_categorical`, seed XOR `23063`.

Final user-run private Kaggle cloud qualification:

- notebook `ashok205/kptcg-g3a-cloud-correctness-v1`
- saved version 2 / scriptVersionId `337365875`
- input dataset `ashok205/kptcg-g3a-correctness-inputs`, version 3, private READY
- three seeds; four streams each; exactly 25,000 choices/stream and 100,000/seed
- all 12 streams passed
- three fresh-process resumes passed
- 220-entry output manifest, 20,617,497 bytes, zero missing/extra/hash/byte mismatches
- 84 checkpoint payloads + 84 sidecars + 12 final checkpoints
- all reported task scores 1.0; stateless 0.5; all zero-tolerance/replay/resume errors zero
- strict review SHA-256 `abc8dcd3db3489a968840d98fc4450d3164c699473a3336e7625c7295ea8565b`
- assistant did not launch the notebook.

G3a PASS establishes algorithm correctness only.

### Frozen historical G3b PPO-first plan

The exact old plan is retained at:

- `ptcg-rl/configs/g3b_competence_plan_v1.json`
- bytes: `12,291`
- SHA-256: `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26`
- planner commit: `098997ae96b3e96a8739cc407fcb16e845c60774`
- sealed evidence/review commits later include `d308abc...`
- review SHA-256: `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`.

It selected staged private Kaggle T4x2, requires a zero-training bridge, then a 100k topology canary, then 1M broad and 5M cumulative choices per seed across three seeds. It uses the engineering sample Mega Abomasnow deck, `behavior_cloning=false`, equal rule-anchor weights, update size 16,384 and terminal reward only.

The audit does not invalidate its implementation evidence; it supersedes its sequencing recommendation. Do not edit this historical config in place. Create a new decision/config lineage.

### TPU environment qualification work

Tracked runner:

- `ptcg-rl/scripts/kaggle/g3b_tpu_environment_qualification.py`
- initial implementation commit `e561fdea3202c643c724b1132a575c369da71c8a`
- repaired source commit `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`
- repaired source tree `81e7067123916d010b7e594d0b6b17477f5d2002`.

The runner inventories CPU/RAM/NUMA/filesystem/packages/network, verifies source/assets/checkpoint, probes JAX 8-device TPU, PyTorch/XLA model parity/backward/state roundtrip, XLA all-reduce and CABT CPU worker scaling 16/32/48/64/80/96. It performs zero meaningful training choices, zero optimizer steps, no PPO and no submission.

First saved notebook run:

- URL supplied by user: `https://www.kaggle.com/code/ashok205/kptcg-g3b-tpu-environment-v1?scriptVersionId=337469673`
- source commit then `e561fdea...`
- observed 8 TPU chips and 96 CPU threads
- JAX probe passed
- provisional CABT throughput: 251.74 choices/s at 16 workers to 344.26 choices/s at 96 workers
- decision `NOT_QUALIFIED_FOR_TRAINING_CANARY`
- report bytes `182,840`, SHA-256 `fd2eee72f50b9630e21d2bb757f892f056e849792374523914a759c27ceba786`
- output manifest bytes `3,829`, SHA-256 `fdc467c93967627b7da7620f24cf4a9109f10e1458cdc51e7da9f090dc9ffee7`
- cell raised `NotebookQualificationError` after the runner returned 2.

The failure was traced to three harness defects, not a demonstrated bad TPU host:

1. PyTorch/XLA GRU test used an inference context that disabled needed autograd.
2. Multi-device XLA subprocess lacked a proper `__main__` spawn guard.
3. CABT inference server could accept more initial ready requests than its declared batch cap, invalidating accounting despite valid games.

The notebook was changed to be interactive-rerun-safe:

- attempt-scoped `attempt-0001`, `attempt-0002`, ... outputs;
- no fixed output collision on rerun;
- completed negative verdict does not crash the notebook cell;
- infrastructure/corruption/missing-output failures still raise;
- previous attempts preserved;
- temporary clone/input copies cleaned;
- Git branch/detached-HEAD advice suppressed.

Repaired v2 identities:

- notebook path: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl/private/kaggle/notebooks/kptcg-g3b-tpu-environment-v1.ipynb`
- notebook bytes: `20,132`
- notebook SHA-256: `a90083da0e2a435e1f9a46befb27f510ea6148598e0b345097150cb81832b156`
- input manifest: `private/kaggle/bundles/g3b-tpu-environment-input-v2.json`, 1,517 bytes, SHA-256 `789118d5a5f53dfec17d3e8c18d702ad6f61f26b8dbf77ab6190ed49c0c10d60`
- source bundle: `g3b-tpu-environment-source-v2.bundle`, 10,270,946 bytes, SHA-256 `1fde0d8554aa741a9bea04c70d6ad90a2a24770a569f0d91cb77f1cff9e8d67a`
- asset archive: `g3b-tpu-environment-assets-v2.zip.bin`, 7,250,850 bytes, SHA-256 `aa5011b8187e5e93781abad3dafcea97350aa5adf4865274aa7da29e0625cc20`
- asset manifest: 3,467 bytes, SHA-256 `75cc05e8a3b171491f4c73a6c97ffb027e5eaff048e43da0cc73b809afefdaa4`
- asset members: 21
- dataset metadata: `ashok205/kptcg-g3b-tpu-environment-inputs`
- dataset version: 2, private, READY when last verified
- dataset contains exactly the four loose v2 files; total 17,526,780 bytes when verified.

Validation after repair:

- focused tests: 27 passed
- full G3 suite: 212 passed
- full Python suite: 416 passed
- Ruff PASS
- repeated interactive-attempt simulation PASS
- exact bundle clone/asset extraction PASS
- frozen competence-plan validation PASS
- the tracked TPU repair commit itself was validated from a clean source state at `32376b...`; the current root worktree later gained four untracked audit deliverables.

No repaired v2 TPU run has been completed/reviewed. The external audit says defer E11 until a learning path passes E03/E05 or T4 integrated throughput proves below 100 choices/s. Do not optimize TPU merely because the notebook exists.

### Audit package and expert audit

A curated audit archive and prompt were built locally:

- archive: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl/private/audit/KPTCG_GOLD_AUDIT_BUNDLE_2026-07-24_FINAL.zip`
- archive bytes: `1,445,133`
- archive SHA-256: `2cabfdc24c3cd008be79541c4b3f5020754a08e1577b8cfed6d42649ed83d77f`
- 346 ZIP members; 345 manifest payload entries; 7,252,506 uncompressed evidence bytes
- ZIP test, manifest rehash and secret/prohibited-binary scan PASS
- prompt: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl/private/audit/KPTCG_GOLD_AUDIT_PROMPT_2026-07-24_FINAL.md`
- prompt bytes: `24,664`
- prompt SHA-256: `9231dfd84940a8cd5d036c4e6aa219bcee5a7117a1b78d5bc4e17fcfd39a6338`.

The audit deliverables are in the repository root:

- `audit-reports/KPTCG_GOLD_AUDIT_REPORT.md`, 56,878 bytes, SHA-256 `f6481bec4d351b718ff362f5a2fab4b20888cf5ea2745af50642e8d444aed112`
- `audit-reports/KPTCG_GOLD_AUDIT_DECISIONS.json`, 21,812 bytes, SHA-256 `2152bbb44f029489143af43328af772c265759b54adc5ed56c45a543f0401691`
- `audit-reports/KPTCG_EXPERIMENT_BACKLOG.csv`, 23,503 bytes, SHA-256 `21735dab7122f72b3c2589efc650e3de753d92faffb60af3295a0820352b2dc4`
- `audit-reports/KPTCG_RESEARCH_LOG.csv`, 77,104 bytes, SHA-256 `26822019a76e3b914451b1390133ca0b09964b6c5185ca79f2e8fe4f7cac67ce`.

Audit date: `2026-07-24T09:43:04Z`, source commit `32376b...`, confidence 0.76, gold assessment `POSSIBLE_BUT_LOW_CONFIDENCE`.

It reviewed 34 project sources, 10 official/live sources, 62 Kaggle discussions (56 full archived reads and six current snippets), 31 primary research sources and five other high-quality sources. It explicitly distinguishes Verified Project Fact, Verified Live Fact, Provisional Measurement, Forum Report, Research Inference and Auditor Hypothesis.

The audit’s core verdict:

- preserve G1/G1R, R1, G2, G3a, checkpoint/PPO/evaluation engineering;
- supersede PPO-first sequencing;
- qualify an exact specialist/teacher corpus;
- train full-action recurrent autoregressive/listwise BC;
- judge on-policy H2H and held-out matchup transfer, not action accuracy;
- complete CABT bridge in parallel;
- run only a 100k-choice KL/BC-regularized PPO canary after BC+bridge pass;
- expand to at most 500k before a new decision;
- maintain deterministic Mega Lucario as a hedge;
- do not authorize the 15M scratch programme, unconditional search, broad offline RL or TPU competence training now.

### Discussion/research lessons that matter

Forum evidence is not project fact, but it changed the expected-value ordering:

- pure RL reports range from poor/plateaued to silver after millions of games and careful curriculum;
- one detailed report claimed ~7k steps/s, ~45 games/s, 3–5M games and still undertrained;
- behavior cloning can achieve high action agreement cheaply, but reports show 66–99% accuracy can still yield only 10–41% teacher H2H;
- a high-ranked participant reported BC + RL + search, with BC only 20–30% of eventual strength;
- native option order may encode a strong cheap prior, but needs permutation controls;
- shallow search helped a weak Alakazam policy and harmed a stronger Starmie policy in one detailed report;
- deck and pilot are entangled; low-branching specialists can be more compute-efficient;
- selected public top episodes are biased toward high average participant rating, not a hidden-field sample;
- rule-based agents have achieved meaningful/high positions, so a deterministic hedge is rational.

Do not quote a forum rank or claim without rereading the live thread and all comments when the claim is material. Current forum and leaderboard facts must be rechecked.

## Accepted working strategic decision

The conversation accepted the audit direction with one operational adjustment: run the deterministic hedge in parallel immediately rather than waiting behind E01/E04.

### Active primary learned path

```text
Mega Lucario provisional specialist
→ E01 exact deck/teacher/replay qualification
→ E02 option-order ablation
→ E03 full-action recurrent BC at 5k/25k/100k labels
→ E05 100k-choice KL/aux-BC PPO canary
→ at most E07 staged 500k confirmation
→ E10 frozen tournament/package selection
```

### Active backup path

```text
Unchanged deterministic Mega Lucario
→ submission-equivalent smoke
→ E08 controlled guard/option-order perturbation ablations
→ shippable rollback artifact throughout
```

### Active infrastructure path

```text
E04 CABT actor/learner + on-policy evaluation bridge
→ zero optimizer steps
→ 10-game smoke
→ 100-game / >=10k-decision qualification
→ exact probability/recurrent/terminal/checkpoint evidence
```

### Formalization requirement

Before implementation/training changes, create a reviewed `DEC-011` or `DEC-AUDIT-001` that:

- preserves prior gate evidence and old configs as history;
- explicitly supersedes PPO-first sequencing, not G3a correctness;
- permits gated behavior cloning only after E01;
- makes Mega Lucario provisional, not frozen final deck;
- caps initial PPO at 100k choices and 500k before redecision;
- separates public replay teachers from controlled local rule teachers;
- requires meta-weighted primary + equal-anchor diagnostic + worst-cell floors;
- freezes treatment of incomplete 16,384-choice PPO update remainders before any run;
- preserves terminal W/D/L reward, public actor/critic, zero policy lag and no search by default;
- states no training/launch/publication/submission authorization is granted by the decision itself.

Do not silently modify DEC-010 or `g3b_competence_plan_v1.json`.

## Experiment programme and gates

### E01-A public teacher/replay qualification

Goal: determine whether public imitation is legal, semantically safe and statistically defensible.

Candidate order: Mega Lucario default, Starmie challenger, Dragapult high-complexity comparator. Crustle/Alakazam only with fresh evidence.

Require before 5k training labels:

- exact legal 60-card deck fingerprint and provenance;
- teacher identity/submission/team and relevant time window;
- recent settled strength or sufficient games;
- no timeout/native/fallback errors;
- full action/request reconstruction including ordered multi-select and STOP;
- episode-level exact/near-duplicate control;
- no split contamination;
- explicit data-use authorization/provenance;
- zero unresolved labels.

Screen: one exact list, one strong teacher, >=5k valid decisions, zero unresolved.

Confirm: exact list, >=2 independent recent teachers, >=25k meaningful decisions, teacher/time/matchup/deck-version holdouts, documented authorization and zero unresolved.

Fail: stop public imitation; continue deterministic hedge, controlled rule-teacher pipeline and at most a bounded scratch PPO canary after E04.

Do not download broad daily datasets. Freeze exact file/byte limits before acquisition.

### E01-B controlled local rule teacher

Use the included Mega Lucario policy as a callable exact teacher to validate the full supervised pipeline and optionally collect DAgger-style learner-state labels.

Purposes:

- validate data schema/loss/action grammar;
- generate exact compound-action labels including STOP;
- test neural reproduction of a known tactical policy;
- provide low-variance teacher H2H;
- prevent public-data uncertainty from blocking all model engineering.

It does not prove gold-level policy strength. Keep rule-teacher and public-teacher provenance separate; do not silently mix them.

### E04 bridge qualification

No optimizer steps and zero meaningful training choices.

Must cover:

- exact G2 projection and decoder;
- both-player trajectories and terminal outcomes;
- forced calls advance recurrence but create no PPO node;
- stored full compound action/log probability replay error <=1e-5;
- initial ratio error <=1e-5;
- terminal versus live truncation classification;
- owner/version isolation and reset;
- duplicate/stale/out-of-order injection;
- partial multi-select/STOP;
- worker death and swallowed-exception rejection;
- deterministic checkpoint/resume parity;
- no fallback, invalid, policy lag or unclassified boundary.

Stages: single-process trace, 10-game smoke, then 100 games and >=10k decisions.

Any silent fallback, recurrent crossing, nonzero policy lag, swallowed failure or replay mismatch blocks PPO.

### E08 deterministic hedge

First freeze the unchanged included Mega Lucario rule policy and exact deck. Run submission-equivalent package/runtime smoke.

Every proposed guard must have:

- original policy control;
- guard-only variant;
- equivalent-option permutation/negative control;
- targeted loss-bucket result;
- aggregate and worst-matchup result;
- balanced seats and zero reliability failures.

Screen at ~400 games/variant; confirm only finalists at ~1,200. No narrative guard survives merely because it sounds strategically correct.

### E02 option-position ablation

Compare the existing order-blind semantic model to a small normalized option-position feature. Include random-permutation validation, option-zero baseline, uniform/frequency/card-only and shuffled-label controls.

Screen: >=5% held-out NLL improvement and no >10pp permutation collapse. Confirm: >=5pp on-policy gain with no held-out archetype regression >3pp under sufficient games.

Failure means keep the current order-blind projection.

### E03 BC scaling

Budgets: 5k → 25k → 100k labels. Three seeds at 25k and 100k where permitted.

Train the full sequence:

- all selected options in order;
- without replacement;
- STOP;
- forced rows zero policy loss but recurrently retained;
- whole-episode recurrent boundaries.

Use teacher/deck/time/matchup episode splits after deduplication. Prefer both wins and losses; winner-only is a biased ablation, not default.

Metrics:

- token/full-action NLL;
- full-action exact match;
- calibration;
- teacher regret;
- H2H versus teacher and rule anchors;
- state-distribution divergence;
- held-out teacher/time/matchup transfer;
- seat split;
- zero illegal/fallback.

25k screen from audit: >=25% NLL reduction versus strongest non-neural baseline, >=60% full-action exact match, zero illegal/fallback and either >=30% teacher H2H or >=5pp over deterministic baseline.

100k confirmation: >=70% full-action exact match, >=40% teacher H2H, >=5pp aggregate over deterministic hedge, no important matchup below 35%, consistent direction in >=2/3 seeds.

Offline accuracy alone never promotes. If offline metrics rise while H2H drops >=5pp twice, stop expansion.

### E05 bounded hybrid PPO

Entry: E03 and E04 pass.

Initial run:

- one seed;
- exactly 100,000 meaningful choices;
- update size 16,384;
- six full updates plus 1,696-choice remainder;
- remainder handling must be frozen/tested before launch;
- initialize from best BC;
- adaptive teacher KL approximately 0.01–0.03;
- auxiliary BC weight decays from 1.0 toward 0.1;
- all parameters trainable;
- T4x2 preferred; TPU only after later E11 qualification.

Suggested frozen opponent mixture from audit: 40% deterministic/rule anchors, 30% historical BC/checkpoints, 20% self-play, 10% hard exploiters, with opponents fixed per episode.

Screen: +5pp point estimate over BC, no important matchup worse by 5pp, KL within target, zero reliability failures.

Stop/revert if aggregate -5pp, any important matchup -10pp, KL >0.05 for two updates, entropy collapse, value divergence, invalid/fallback or resume mismatch.

Only a confirmed 100k result can unlock 500k staged training. Beyond 500k requires a new decision.

### Other experiments

- E06 Starmie: only after exact list + two teachers + >=25k safe labels; replace Lucario only with >=8pp equal-budget pooled advantage and no floor breach.
- E07 500k: five 100k chunks, preserve every historical champion, stop after two regressions; no 5M extension.
- E09 search: not critical path; exact package/API/latency proof and no-search control required.
- E10 tournament: frozen package-ready candidates, meta-weighted primary, equal diagnostic, worst-cell floors, multiple-comparison control.
- E11 TPU: only after E05 passes or T4 integrated throughput <100 choices/s; require >=1.5x information/hour to promote TPU.
- E12 representation changes: only after documented E03/E05 plateau; compare to width-matched and shuffled-target controls.

## Specialist deck status

No exact learned specialist is qualified or frozen.

Provisional order:

1. Mega Lucario — default first specialist and deterministic hedge because exact included list and tactical policy exist; current field strength unproven.
2. Starmie — data-gated challenger; promising low branching, but no exact list/teachers established in project.
3. Dragapult/Psychic — exact list and complex planner exist; high ceiling, high sequencing/prize-map sample cost; hard anchor/second wave.
4. Crustle — low-complexity comparator/possible hedge; stale/counter/ceiling risk.
5. Alakazam — research/search candidate; current exact list/teacher uncertain and branching/search-sensitive.
6. Mega Abomasnow — engineering anchor only; easy but likely ceiling.

Relevant included private baselines:

- `ptcg-rl/private/baselines/mega-lucario-ex/`
- `ptcg-rl/private/baselines/dragapult-ex/`
- `ptcg-rl/private/baselines/iono/`
- `ptcg-rl/private/baselines/mega-abomasnow-ex/`.

Mega Lucario deck SHA-256: `406e2e9bd6ae82b8008b16ee64ffcbb58e4a50cd6bc36e33ae655456c6b9afee`; policy SHA-256: `ab8563b67b88b3666c2ff9c308505085a84fdac676c194c5b484d8544478c3b2`; receipt SHA-256: `dc94ec50448e7a0dd40423d62cd33c480d6021870d2726c9849ba0429045713e`.

Do not call this the final deck until its decision gate passes and user approval freezes it.

## Evaluation/statistics policy

Reliability is a hard gate, never blended into a strength score.

Report separately:

- meta-weighted primary estimate with uncertainty and timestamped weight provenance;
- equal-anchor diagnostic;
- each matchup and seat;
- worst important cell;
- runtime/package reliability.

Public top episodes are selected and not an unbiased meta distribution. Use 3/7/14-day sensitivity and lower-rating/losing episodes where available. Keep training and held-out opponents separate.

Approximate 95% half-width at p=0.5:

- 100 games ±9.8pp
- 200 ±6.9pp
- 400 ±4.9pp
- 600 ±4.0pp
- 1,200 ±2.8pp
- 6,000 ±1.27pp.

Use 100–200 games/cell for large-effect screening; 600–1,200 for finalists; >=3,000 frozen-population games for champion selection. Use Wilson/beta/Dirichlet-multinomial intervals, episode-level bootstrap where appropriate, seat balancing, sequential alpha spending and Holm correction for promoted comparisons.

The official engine uses nondeterministic entropy. Do not claim exact trajectory reproduction or common random numbers from Python seeds. Engine modification for seeded CRN is not approved and may create license/runtime-parity risk.

## Compute truth

Measured G2 inference/reliability: 228.598 meaningful choices/s and 1.97684 games/s. This is not integrated PPO throughput.

Provisional failed-harness TPU host observations: 251.74–344.26 choices/s. Do not treat as qualified capacity.

Audit sensitivity:

- 344.26 choices/s: 1M ≈0.81h
- 251.74: 1M ≈1.10h
- 228.60: 1M ≈1.22h
- 100: 1M ≈2.78h
- 57.15: 1M ≈4.86h
- 35: 1M ≈7.94h.

The audit’s July 24 pre-refresh snapshot reported 24.358 GPU hours and 18.425 TPU hours remaining. This is stale/mutable; re-fetch current quota before scheduling.

First decision window should spend near-zero accelerator on E01/E04/E08. Do not authorize the old 15M scratch programme. Seven-day cap from audit: <=20 GPU hours, <=4 optional TPU hours and <=500k on-policy choices before a new decision.

## Kaggle workflow and tool facts

User preference:

- maintain one notebook per current workflow rather than many variants;
- update versions of a small stable dataset/model set instead of creating noisy new assets;
- user manually imports/opens notebook, selects accelerator, attaches existing assets and runs;
- assistant should retrieve output files itself through Kaggle tools when available;
- verify every asset version/status/file list/download hash;
- do not ask the user to manually transfer outputs when tools can retrieve them.

Use `api_tool.list_resources` to discover current `Local_mcp` Kaggle schemas. Do not invent endpoints. Numeric saved/script/dataset versions are required where available.

Known private dataset:

- `ashok205/kptcg-g3b-tpu-environment-inputs`, version 2, private READY at last verification.

No notebook run should be launched automatically. Preparation and private dataset versioning require the exact external-mutation authorization for that action. Training/qualification launch remains user-controlled unless they explicitly change that rule.

When a user reports a saved notebook run:

1. retrieve notebook info/status;
2. list session outputs, including pagination;
3. download output ZIP/files;
4. verify the notebook output manifest first;
5. recalculate the verdict independently;
6. retain exact bytes/hashes;
7. update repository gates only after evidence review.

Notebook UI status alone is never proof.

## Authorization boundaries

Explicit user approval is required before:

- additional replay acquisition beyond an exact reviewed cap;
- using replay actions as training labels;
- launching BC/PPO/self-play/league training;
- running a Kaggle topology or training canary;
- running Modal or paid compute;
- freezing/changing the submitted deck;
- adding a new architecture feature after E02/E12 decision;
- changing algorithm, reward, critic information, promotion rules or search;
- creating/updating external datasets/models/notebooks unless specifically authorized;
- submitting or changing active Kaggle agents;
- pushing Git/opening a PR.

The user’s request for an audit and handoff is not training authorization.

Allowed without a new training authorization inside the active milestone:

- repository inspection;
- formal decision drafting;
- source/config/test implementation;
- tiny bounded local correctness/inference smoke that obeys local rules;
- read-only Kaggle/forum/leaderboard/quota research;
- exact dry-run acquisition plan;
- local commits of intentional safe source/test/config/report files after review.

No meaningful training or large local evaluation.

## Immediate next lifecycle

The next session must not merely restate the audit. Complete the following evidence-first lifecycle as far as authorization permits.

### Step 1 — verify state and refresh mutable facts

- Git/status/log/remote/ahead-behind.
- Current official rules/deadlines/runtime.
- Current Kaggle accelerator quota.
- Current competition leaderboard frontier.
- Current forum discussions material to deck/teacher/strategy, reading full comments/replies.
- Current private dataset/notebook state.

Record access timestamps and evidence class. Do not let live research silently change locked project facts.

### Step 2 — create the superseding decision

Draft and review `DEC-011`/`DEC-AUDIT-001` with the exact boundaries above. Update task/gate/status planning records only after review. The old G3b plan remains historical and blocked; no competence claim.

Before committing, run the decision/config/task tests and validate dashboard envelopes if new machine-readable reports are created.

### Step 3 — freeze parallel work orders

Create versioned, predeclared work orders/configs for:

- E01-A public teacher/replay gate with exact file/byte caps and zero training;
- E01-B controlled rule-teacher schema/pilot;
- E04 zero-update CABT bridge qualification;
- E08 unchanged deterministic Mega Lucario baseline/package evaluation.

Do not launch/acquire/train until each authorization boundary is satisfied. E01-A download expansion likely needs explicit user approval after a dry-run.

### Step 4 — implement E04 and controlled local pipeline

Within local safety, implement bridge code/tests, supervised example schema/loss plumbing and deterministic hedge packaging/evaluation harness. No meaningful training. Map every edge case to a test.

### Step 5 — request the smallest exact approvals

Once dry-run evidence is complete, ask only for exact necessary approvals, such as:

- approve transfer of N named replay files / X bytes for E01-A;
- approve a bounded 5k-label BC run on a specified private notebook;
- approve a specified topology canary after E04 pass.

Do not ask broad permission for “training.”

## Edge cases that must remain explicit

Bridge/action:

- zero/one/many options;
- min/max count boundaries;
- optional STOP before/after minimum;
- effective maximum completion;
- ordered permutations;
- duplicate/unavailable/out-of-range rejection;
- >64 options;
- forced complete action despite multiple raw options;
- forced calls update recurrence only;
- both-player terminal attachment;
- live truncation versus terminal;
- long forced chains;
- exact old compound log probability replay;
- initial ratio one;
- finite logits/loss/gradient/state;
- owner/version/reset;
- duplicate/stale/out-of-order requests;
- worker replacement/death;
- policy version lag zero.

Replay/BC:

- action/request off-by-one negative control;
- exact/near duplicate episodes;
- deck-list variants;
- forced/setup/deck-response rows;
- empty/invalid/parser-uncertain actions;
- teacher identity/time/rating mismatch;
- winner-only bias;
- split by whole episode before rows;
- hold out teacher, exact list, time and matchup;
- full ordered selection + STOP labels;
- no future/reward/team/leaderboard leakage in actor input;
- recurrent boundaries at game/seat/owner transitions;
- shuffled-label/history-dropped/card-only/order baselines.

Checkpoint/evidence:

- atomic write cleanup;
- truncated/corrupt payload;
- manifest hash/size mismatch;
- wrong keys/shapes/dtypes;
- optimizer/scheduler presence mismatch;
- counters/data cursor/opponent schedule/rollout boundary/RNG restoration;
- fixed reference parity;
- exact budget once, no duplicate updates;
- collision-resistant run directory;
- dashboard-valid envelope;
- complete output pagination/download/hash parity.

## Important file index

Governance/current:

- `AGENTS.md`
- `01_MASTER_PLAN.md`
- `ptcg-rl/PROJECT_STATUS_ANALYSIS.md`
- `ptcg-rl/PROJECT_STATUS.md`
- `ptcg-rl/PROGRESS_REPORT.md`
- `ptcg-rl/reports/tasks/current.json`
- `ptcg-rl/reports/gates/g3a.json`
- `ptcg-rl/reports/gates/g3b.json`
- `ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`.

Audit:

- `audit-reports/KPTCG_GOLD_AUDIT_REPORT.md`
- `audit-reports/KPTCG_GOLD_AUDIT_DECISIONS.json`
- `audit-reports/KPTCG_EXPERIMENT_BACKLOG.csv`
- `audit-reports/KPTCG_RESEARCH_LOG.csv`.

G1/R1:

- `ptcg-rl/src/ptcg_rl/g1/actions.py`
- `ptcg-rl/src/ptcg_rl/g1/environment.py`
- `ptcg-rl/src/ptcg_rl/g1/recurrent.py`
- `ptcg-rl/src/ptcg_rl/g1/semantic.py`
- `ptcg-rl/src/ptcg_rl/replay/semantic_loader.py`
- `ptcg-rl/src/ptcg_rl/replay/acquisition.py`
- `ptcg-rl/src/ptcg_rl/replay/independent_review.py`
- `ptcg-rl/reports/replays/`
- `ptcg-rl/tests/replay/`.

G2:

- `ptcg-rl/src/ptcg_rl/g2/network.py`
- `ptcg-rl/src/ptcg_rl/g2/projection.py`
- `ptcg-rl/src/ptcg_rl/g2/models.py`
- `ptcg-rl/src/ptcg_rl/g2/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g2/reliability.py`
- `ptcg-rl/reports/artifacts/g2-policy-v1.json`
- `ptcg-rl/reports/artifacts/g2-policy-checkpoint-v1.json`
- `ptcg-rl/reports/evaluations/g2-neural-reliability-v1.json`
- `ptcg-rl/tests/g2/`.

G3:

- `ptcg-rl/configs/g3a_evaluation_v1.json`
- `ptcg-rl/configs/g3b_competence_plan_v1.json`
- `ptcg-rl/src/ptcg_rl/g3/ppo.py`
- `ptcg-rl/src/ptcg_rl/g3/gae.py`
- `ptcg-rl/src/ptcg_rl/g3/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g3/toy.py`
- `ptcg-rl/src/ptcg_rl/g3/local_correctness.py`
- `ptcg-rl/src/ptcg_rl/g3/competence_plan.py`
- `ptcg-rl/scripts/kaggle/g3b_tpu_environment_qualification.py`
- `ptcg-rl/tests/g3/`.

Private exact policies/assets:

- `ptcg-rl/private/baselines/mega-lucario-ex/`
- `ptcg-rl/private/baselines/dragapult-ex/`
- `ptcg-rl/private/baselines/iono/`
- `ptcg-rl/private/baselines/mega-abomasnow-ex/`
- `ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip`
- `ptcg-rl/private/kaggle/notebooks/kptcg-g3b-tpu-environment-v1.ipynb`
- `ptcg-rl/private/kaggle/bundles/g3b-tpu-environment-input-v2.json`
- `ptcg-rl/private/kaggle/bundles/g3b-tpu-environment-source-v2.bundle`
- `ptcg-rl/private/kaggle/bundles/g3b-tpu-environment-assets-v2.zip.bin`
- `ptcg-rl/private/kaggle/bundles/g3b-tpu-environment-assets-v2.manifest.json`.

Research:

- `research-docs/research_index.md` or repository equivalent
- audit research log
- current full Kaggle discussion threads and official sources.

Dashboard/reporting:

- `ptcg-rl/src/ptcg_rl/dashboard/`
- `ptcg-rl/dashboard/frontend/`
- `ptcg-rl/tests/dashboard/`.

## Testing and evidence workflow

For each change:

1. inspect governing code/tests and existing paths;
2. write failing/regression tests first for correctness changes;
3. implement a small reviewable increment;
4. run narrow tests;
5. run all relevant G3/replay/G2 tests;
6. run the full Python suite and Ruff;
7. run dashboard rebuild/doctor if records/status changed;
8. run frontend/build/browser tests when dashboard-visible behavior changed;
9. independently recalculate generated reports;
10. review Git diff including untracked files;
11. locally commit exact intended paths only after validation;
12. verify clean HEAD and report remote/push truth.

Known most recent clean validation for TPU repair: 27 focused, 212 G3, 416 full Python, Ruff PASS. Do not repeat those counts as current validation after new changes unless rerun.

Use declared dependency groups in isolated checkouts. Distinguish missing private asset/environment failures from project assertion failures. Never hand-edit generated evidence to make it pass.

Every committed machine-readable record needs a dashboard envelope (`schema_version`, `record_id`, `created_at_utc`, `source_path`, `producer`, status/decision). Dashboard must exclude private raw assets, secrets and signed URLs.

## Git discipline

- inspect before editing;
- preserve unrelated user work;
- use `repo_write_file`/`repo_write_changes` for approved edits;
- use `repo_git_review` before commit;
- use `repo_write_stage_commit` for local commits;
- never use shell Git to bypass review controls;
- never push without explicit approval;
- verify local/remote status after commit;
- handoff files stay untracked/local.

## Stop/ask conditions

Stop and request the smallest exact user decision when:

- a formal strategy change needs user approval under `AGENTS.md`;
- E01-A requires additional replay download beyond a frozen dry-run cap;
- behavior cloning labels/training are ready but not authorized;
- a Kaggle/TPU/GPU notebook launch is ready;
- deck freeze or submission is proposed;
- official rules contradict recorded constraints;
- required private assets are absent;
- the repository/remote state materially differs;
- a proposed change affects reward, critic information, algorithm, architecture or promotion rules beyond the accepted decision;
- the exact next external run is frozen and ready for approve/reject.

Do not stop merely because one safe implementation attempt fails. Diagnose, test alternatives and close each experiment with retained pass/fail/ambiguous evidence.

## Required final report from the next session milestone

Report:

- exact repository HEAD/dirty/remote state;
- formal decision path and files/hashes;
- current mutable fact refresh with timestamps/sources;
- exact E01/E04/E08 configs and authorization state;
- files changed and local commits;
- tests/commands/results;
- any replay files proposed/acquired with exact counts/bytes/hashes;
- no-training statement or exact approved run identity if later authorized;
- compute/quota used;
- experiment verdicts and thresholds;
- blockers and reversal triggers;
- next smallest approval question;
- push/submission/external-mutation truth.

## Final reminder

The next objective is to **formalize and execute the lowest-cost decision gates that can demonstrate one exact specialist’s genuine on-policy competence**. Do not spend scarce compute optimizing infrastructure or scaling PPO before E01/E03/E04 evidence exists. Preserve a shippable deterministic Mega Lucario hedge at all times. Gold remains possible, not demonstrated.
