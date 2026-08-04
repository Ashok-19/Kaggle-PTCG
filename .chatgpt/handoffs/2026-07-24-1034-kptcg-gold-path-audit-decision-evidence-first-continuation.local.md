# KPTCG Gold-Path Audit Decision Evidence-First Continuation

Generated UTC: `2026-07-24T10:34:42Z`

## Summary

**Track:** Formalize the audited hybrid specialist path and execute E01/E04/E08 decision gates without meaningful training.

**Repository:** `ptcg` at `/home/nnmax/Desktop/kaggle/PTCG` with main project under `ptcg-rl/`.

**State:** Local `main` is at `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`. Tracked project files are unchanged, but the root worktree is not technically clean because the four user-provided files under `audit-reports/` are untracked. Local handoff files are ignored and do not appear in status. The locally known `origin/main` is `e561fdea3202c643c724b1132a575c369da71c8a`; local is one commit ahead and zero behind that local reference. Branch has no upstream annotation. No push occurred. Preserve the audit files exactly; do not delete, overwrite, stage or commit them without a deliberate user-approved integration decision.

G0/G1R/R1/G2/G3a are PASS only for their exact engineering/data-contract/algorithm-correctness scopes. G3b is `BLOCKED / NOT_REVIEWED`. No CABT actor/learner bridge, Pokémon competence, competitive strength, exact learned specialist, topology canary or training result exists.

The old G3b PPO-first plan is historically frozen and reviewed, but an independent expert audit concluded that its sequencing is not the best use of limited compute. The user accepted a new working direction: exact specialist/teacher qualification, full-action recurrent imitation, on-policy validation, bounded KL/BC-regularized PPO, plus a deterministic Mega Lucario hedge. This accepted direction has not yet been formalized in a repository decision record.

No meaningful training, replay expansion, Kaggle run, external mutation, deck freeze, submission, active-agent change, paid compute, Modal job or Git push is authorized by this handoff.

## Current Git

- Branch: `main`
- HEAD: `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`
- Subject: `fix(g3b): repair TPU environment qualification`
- Locally known `origin/main`: `e561fdea3202c643c724b1132a575c369da71c8a`
- Ahead/behind against local remote ref: `0 1` from `origin/main...main`
- Tracked files: unchanged
- Untracked user evidence: the four files under `audit-reports/`
- Local handoff files: ignored and absent from Git status
- Remote: `https://github.com/Ashok-19/Kaggle-PTCG.git`
- Push performed: no

Recent commits:

```text
32376b0 fix(g3b): repair TPU environment qualification
e561fde feat(g3b): add TPU environment qualification runner
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

Reverify all of this at the start of the next session. The remote ref may be stale.

## Completed Work

### Foundational gates

- G0 repository consolidation complete; private `Ashok-19/Kaggle-PTCG` is active, `Kaggle-PTCG-RL` is inactive backup, clean lineage root `08be5cec0fac9a954a3fe127a3f51122be4736d1`.
- G1R engine/action contract PASS with one-battle-per-process, terminal-first handling, complete legal option scoring, ordered unique multi-select, first-class STOP, public-only information and strict recurrent ownership/fail-closed behavior.
- R1 replay contract PASS on 20 approved episodes: 83,981,423 bytes, 2,999 decisions, 3,275 selected options, 21 reconstructed STOP markers, 16 ordered requests, zero unresolved, semantic stream SHA-256 `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`.
- G2 recurrent semantic policy PASS as engineering artifact: 970,022 trainable parameters, architecture SHA-256 `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`.
- G2 deterministic checkpoint package: 5,429,190 bytes, SHA-256 `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`.
- G2 10,000-game T4x2 reliability PASS: 1,213,203 engine requests, 20,791 multiselect requests, 1,156,383 meaningful choices, zero reliability counters, 1.97684 games/s, 228.59829116666842 choices/s.

### G3a correctness

- Project-native PPO/GAE/recurrent/checkpoint stack implemented and tested.
- Local toy tasks passed all three seeds after comparing three configurations.
- The first cloud run revealed a greedy-vs-seeded-categorical rollout mismatch; it was reproduced and fixed without changing thresholds or budgets.
- Final user-run private Kaggle notebook `ashok205/kptcg-g3a-cloud-correctness-v1`, saved version 2 / scriptVersionId `337365875`, passed all 12 25k-choice streams, three fresh-process resumes and a 220-entry output manifest over 20,617,497 bytes.
- G3a is PASS for toy algorithm correctness only; policy strength is unestablished.

### Historical G3b plan

- Frozen plan commit `098997ae96b3e96a8739cc407fcb16e845c60774`.
- Config `ptcg-rl/configs/g3b_competence_plan_v1.json`, 12,291 bytes, SHA-256 `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26`.
- Independent review SHA-256 `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`.
- Selected staged private Kaggle T4x2 with zero-training bridge, 100k topology canary, 1M broad and 5M cumulative per seed.
- No notebook, canary or training run was launched under this plan.

### TPU environment work

- Initial runner commit `e561fdea3202c643c724b1132a575c369da71c8a`.
- First user saved run: `scriptVersionId=337469673`.
- It observed 8 TPU devices, 96 CPU threads and provisional CABT throughput from 251.74 choices/s at 16 workers to 344.26 at 96 workers.
- It returned `NOT_QUALIFIED_FOR_TRAINING_CANARY`, report 182,840 bytes SHA-256 `fd2eee72f50b9630e21d2bb757f892f056e849792374523914a759c27ceba786`, manifest 3,829 bytes SHA-256 `fdc467c93967627b7da7620f24cf4a9109f10e1458cdc51e7da9f090dc9ffee7`.
- The negative verdict was caused by three harness defects: XLA GRU inference/autograd context, missing multi-device `__main__` guard and CABT initial-ready batch-cap accounting.
- Repaired commit: `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`, tree `81e7067123916d010b7e594d0b6b17477f5d2002`.
- Notebook now supports interactive repeated attempts, preserves previous outputs, does not crash on a completed negative verdict, and still raises for integrity/infrastructure failures.
- Local notebook path: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl/private/kaggle/notebooks/kptcg-g3b-tpu-environment-v1.ipynb`.
- Notebook bytes/hash: 20,132 / `a90083da0e2a435e1f9a46befb27f510ea6148598e0b345097150cb81832b156`.
- Private dataset: `ashok205/kptcg-g3b-tpu-environment-inputs`, version 2, private READY when last verified, exactly four v2 files, total 17,526,780 bytes.
- v2 source bundle hash `1fde0d8554aa741a9bea04c70d6ad90a2a24770a569f0d91cb77f1cff9e8d67a`.
- v2 asset archive hash `aa5011b8187e5e93781abad3dafcea97350aa5adf4865274aa7da29e0625cc20`.
- v2 input manifest hash `789118d5a5f53dfec17d3e8c18d702ad6f61f26b8dbf77ab6190ed49c0c10d60`.
- v2 asset manifest hash `75cc05e8a3b171491f4c73a6c97ffb027e5eaff048e43da0cc73b809afefdaa4`.
- Post-repair validation: 27 focused, 212 G3, 416 full Python, Ruff PASS, repeated attempt simulation PASS.
- No repaired TPU v2 run has been completed/reviewed.

### Audit package and expert audit

- Audit ZIP: `ptcg-rl/private/audit/KPTCG_GOLD_AUDIT_BUNDLE_2026-07-24_FINAL.zip`, 1,445,133 bytes, SHA-256 `2cabfdc24c3cd008be79541c4b3f5020754a08e1577b8cfed6d42649ed83d77f`.
- Expert prompt: `ptcg-rl/private/audit/KPTCG_GOLD_AUDIT_PROMPT_2026-07-24_FINAL.md`, 24,664 bytes, SHA-256 `9231dfd84940a8cd5d036c4e6aa219bcee5a7117a1b78d5bc4e17fcfd39a6338`.
- Audit deliverables under root `audit-reports/`:
  - report SHA-256 `f6481bec4d351b718ff362f5a2fab4b20888cf5ea2745af50642e8d444aed112`
  - decisions SHA-256 `2152bbb44f029489143af43328af772c265759b54adc5ed56c45a543f0401691`
  - backlog SHA-256 `21735dab7122f72b3c2589efc650e3de753d92faffb60af3295a0820352b2dc4`
  - research log SHA-256 `26822019a76e3b914451b1390133ca0b09964b6c5185ca79f2e8fe4f7cac67ce`.
- Audit confidence 0.76; gold `POSSIBLE_BUT_LOW_CONFIDENCE`.
- Audit reviewed 34 project, 10 official/live, 62 Kaggle discussion, 31 primary research and five other sources.

## Accepted Decisions

1. Preserve all verified engineering and historical evidence; do not rewrite old plan artifacts.
2. Supersede PPO-first sequencing through a new reviewed decision record.
3. Primary learned path: exact-deck recurrent full-action BC followed by bounded KL/aux-BC PPO.
4. Provisional first deck: Mega Lucario; it is not frozen final deck.
5. First challenger: Starmie, but only after exact list, two teachers, >=25k safe labels and >=8pp equal-budget advantage without floor breach.
6. Keep deterministic Mega Lucario continuously shippable and evaluate it in parallel immediately.
7. Run E01 teacher/deck/replay qualification, E04 zero-update CABT bridge and E08 deterministic hedge in parallel after formal decision.
8. Split E01 into public teacher E01-A and controlled callable local rule teacher E01-B; preserve provenance separation.
9. BC must learn the full ordered compound action and STOP, preserve recurrence and exclude forced rows from policy loss.
10. Action accuracy is diagnostic only; on-policy H2H and held-out matchup/teacher/time transfer decide promotion.
11. PPO entry requires E03 and E04 PASS. Start with one 100k-choice canary; cap at 500k before a new decision.
12. Do not prioritize TPU, search, reward shaping, offline Q-learning, model enlargement or a second learned deck before competence evidence.
13. No meaningful training or external launch is currently authorized.

## Immediate Work Programme

### 1. Verify repository and mutable facts

Read the new master prompt, this handoff, AGENTS, status/task/gate files, historical G3b plan and all four audit files. Then verify Git, current official rules/deadlines/runtime, leaderboard, current forum, accelerator quota and private Kaggle asset versions. Timestamp every mutable observation.

### 2. Formalize the new strategy

Create `ptcg-rl/docs/decisions/DEC-011_...md` or `DEC-AUDIT-001` and corresponding safe machine-readable planning evidence if required.

The decision must:

- preserve G1/G2/G3a/R1 and old G3b evidence;
- supersede sequencing only;
- permit gated BC after E01;
- make Lucario provisional;
- cap PPO at 100k then 500k;
- require public/local teacher provenance separation;
- define meta/equal/worst-cell evaluation;
- require predeclared partial-update handling;
- preserve public actor/critic, terminal reward, zero lag and search-off default;
- grant no training or launch authorization itself.

Do not edit DEC-010 or old `g3b_competence_plan_v1.json` in place.

### 3. Freeze E01-A, E01-B, E04 and E08 work orders

Each needs exact entry gates, assets/hashes, caps, controls, output manifests, pass/fail/ambiguous thresholds, stop conditions and authorization fields.

E01-A must produce a dry-run of exact replay files and bytes before transfer approval. Never download whole daily datasets.

### 4. Implement E04 bridge with zero optimizer steps

Stages:

- one single-process trace;
- 10 complete games;
- 100 games and >=10k decisions.

Must pass exact compound logprob replay <=1e-5, initial ratio <=1e-5, forced-chain recurrence, both-player terminal attachment, truncation classification, owner/version isolation, stale/duplicate/out-of-order injections, partial multi-select/STOP, worker death and checkpoint/resume parity.

Any fallback, policy lag, recurrent crossing, swallowed failure, invalid or replay mismatch blocks PPO.

### 5. Establish unchanged deterministic Mega Lucario hedge

Freeze exact deck/policy and run submission-equivalent smoke. Treat every proposed guard as a controlled ablation with unchanged and perturbation controls. Maintain rollback artifact and hash.

### 6. Ask only exact approvals

Once dry-runs/configs are immutable, ask for one narrow action: exact named replay files/bytes, exact 5k-label BC run, or exact topology canary. Never ask broad blanket training permission.

## E01/E02/E03/E05 Gates

### E01-A screen

- exact legal list
- one strong teacher
- >=5k valid meaningful decisions
- zero unresolved labels.

### E01-A confirmation

- exact list
- >=2 independent recent teachers
- >=25k meaningful decisions
- episode dedup
- teacher/time/matchup/deck-version splits
- zero unresolved
- documented authorization/provenance.

### E01-B

Use included Mega Lucario rule policy to validate schema/loss/action grammar and optionally DAgger learner states. It is a controlled teacher, not gold evidence.

### E02

Option-position feature versus current order-blind model, with random permutation and simple baselines. Do not include position unless offline and on-policy gates pass.

### E03

Budgets 5k, 25k, 100k labels. Three seeds where applicable. Full ordered selection + STOP. Promotion requires on-policy/held-out competence, zero invalid/fallback and consistent seed direction.

### E05

One seed, 100k meaningful choices, six full 16,384 updates + 1,696 remainder with frozen handling. Initialize from BC, use teacher KL and auxiliary BC. Stop on aggregate -5pp, matchup -10pp, KL/entropy/value/reliability/resume failure. Only PASS unlocks staged 500k.

## Deck Status

- Mega Lucario: provisional first learned specialist and deterministic hedge. Exact deck hash `406e2e9bd6ae82b8008b16ee64ffcbb58e4a50cd6bc36e33ae655456c6b9afee`; policy hash `ab8563b67b88b3666c2ff9c308505085a84fdac676c194c5b484d8544478c3b2`.
- Starmie: data-gated challenger; no project-qualified exact list/teachers.
- Dragapult: exact high-complexity hard anchor/second wave.
- Crustle: low-complexity comparator, possible stale/counter ceiling.
- Alakazam: research/search candidate only.
- Mega Abomasnow: engineering anchor only.

No final deck is selected or frozen.

## Evaluation Rules

- Reliability is a hard gate.
- Report meta-weighted primary, equal-anchor diagnostic, each matchup/seat and worst important cell.
- Public top episodes are selected and nonrepresentative.
- Use 100–200 games/cell only for large-effect screening; 600–1,200 for finalists; >=3,000 frozen-population games for champion selection.
- Use confidence intervals, sequential stopping and multiple-comparison control.
- Do not claim CRN or deterministic game trajectories from Python seeds.

## Authorization Boundaries

Explicit user approval required for:

- additional replay transfer/use as labels;
- BC/PPO/self-play/league training;
- Kaggle/TPU/GPU notebook launch;
- external dataset/model/notebook mutation unless specifically authorized;
- deck freeze/change;
- architecture/algorithm/reward/critic/search/promotion-rule changes;
- Modal/paid compute;
- submissions/active-agent changes;
- Git push/PR.

The user manually runs Kaggle notebooks unless they explicitly change that rule. The assistant prepares stable notebooks/assets and retrieves outputs through tools when supported.

## Important Files

Startup/governance:

- `.chatgpt/handoffs/current.local.md`
- `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
- this structured handoff
- `AGENTS.md`
- `01_MASTER_PLAN.md`
- `ptcg-rl/PROJECT_STATUS_ANALYSIS.md`
- `ptcg-rl/PROJECT_STATUS.md`
- `ptcg-rl/PROGRESS_REPORT.md`
- `ptcg-rl/reports/tasks/current.json`.

Audit:

- `audit-reports/KPTCG_GOLD_AUDIT_REPORT.md`
- `audit-reports/KPTCG_GOLD_AUDIT_DECISIONS.json`
- `audit-reports/KPTCG_EXPERIMENT_BACKLOG.csv`
- `audit-reports/KPTCG_RESEARCH_LOG.csv`.

G3/current:

- `ptcg-rl/configs/g3a_evaluation_v1.json`
- `ptcg-rl/configs/g3b_competence_plan_v1.json`
- `ptcg-rl/reports/gates/g3a.json`
- `ptcg-rl/reports/gates/g3b.json`
- `ptcg-rl/reports/artifacts/g3b-competence-plan-v1.json`
- `ptcg-rl/reports/artifacts/g3b-competence-plan-review-v1.json`
- `ptcg-rl/src/ptcg_rl/g3/ppo.py`
- `ptcg-rl/src/ptcg_rl/g3/gae.py`
- `ptcg-rl/src/ptcg_rl/g3/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g3/competence_plan.py`
- `ptcg-rl/scripts/kaggle/g3b_tpu_environment_qualification.py`
- `ptcg-rl/tests/g3/`.

Replay/model:

- `ptcg-rl/src/ptcg_rl/replay/semantic_loader.py`
- `ptcg-rl/src/ptcg_rl/replay/acquisition.py`
- `ptcg-rl/src/ptcg_rl/g2/network.py`
- `ptcg-rl/src/ptcg_rl/g2/projection.py`
- `ptcg-rl/src/ptcg_rl/g2/checkpoint.py`.

Private:

- `ptcg-rl/private/baselines/mega-lucario-ex/`
- `ptcg-rl/private/baselines/dragapult-ex/`
- `ptcg-rl/private/baselines/iono/`
- `ptcg-rl/private/baselines/mega-abomasnow-ex/`
- `ptcg-rl/private/kaggle/notebooks/kptcg-g3b-tpu-environment-v1.ipynb`
- `ptcg-rl/private/kaggle/bundles/g3b-tpu-environment-input-v2.json`.

## Validation and Git Workflow

- Add regression tests before correctness fixes.
- Run narrow tests, all relevant G3/replay/G2 tests, full Python suite and Ruff.
- Run dashboard rebuild/doctor and frontend/build/browser tests when status/evidence views change.
- Independently recalculate reports; do not hand-edit generated evidence.
- Review exact paths/untracked files before local commit.
- Never push without approval.
- Handoff files remain local/ignored.

Last clean TPU-repair validation counts were 27 focused, 212 G3 and 416 full Python plus Ruff. Do not repeat those as validation of future changes unless rerun.

## Risks

- The audit’s July 25/26 deadlines become stale; recalculate from current time.
- The new strategy is not repository-authoritative until the decision record is reviewed.
- Public teacher data may fail identity/list/dedup/authorization gates and consume schedule.
- High action accuracy may fail on policy.
- Deterministic Lucario may be below current meta; it is hedge/baseline, not presumed winner.
- Repaired TPU has not been rerun.
- Current project status/task files still point to the old sole next action.
- Forum and visible replay data are selected, nonstationary and strategically incomplete.
- Multiple comparisons can create false winners.
- Remote tracking may be stale.

## Open Questions

- Which exact current public teachers and 60-card lists pass E01-A under a small cap?
- Is the included Lucario rule teacher sufficiently coherent for useful BC/DAgger validation?
- What exact PPO remainder policy should be frozen?
- What additional generic on-policy evaluation adapter is needed beyond the old bridge plan?
- Which current meta weights are defensible enough for primary evaluation?
- Should TPU v2 be rerun for environment evidence now or deferred until E05 shows a bottleneck?

## Startup Prompt

Use `Local_mcp` with repo id `ptcg`.

Read in order:

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
3. `.chatgpt/handoffs/2026-07-24-1034-kptcg-gold-path-audit-decision-evidence-first-continuation.local.md`
4. `AGENTS.md`
5. the project status/task/gate files
6. all four `audit-reports/` deliverables.

Then run `repo_git_status`, verify log/remote/ahead-behind, refresh current official/leaderboard/forum/quota facts, and continue from **Immediate Work Programme**. Do not launch training or external jobs. The first repository milestone is the superseding decision record plus frozen E01/E04/E08 work orders.
