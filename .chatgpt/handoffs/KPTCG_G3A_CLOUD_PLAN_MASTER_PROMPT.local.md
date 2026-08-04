# KPTCG G3a Cloud-Plan Master Continuation Prompt

Generated UTC: `2026-07-22T15:16:26Z`

This is a local-only continuation prompt for the KPTCG project. It is intentionally comprehensive. Read it completely before proposing, editing, running, or launching anything.

---

## Paste the following into the new session

Continue the KPTCG Kaggle Pokémon TCG AI Battle project from the repository-grounded evidence handoff.

Use the `Local_mcp` tool namespace with repository id `ptcg`. Do not use an older or invented repository namespace. Do not bypass the repository safety layer with ad hoc shell writes, Git staging, Git commits, deletion, or external mutation. Use repository read/write/review tools and `workspace_exec` only for approved deterministic commands.

The central operating rule is: **never work from assumptions when repository evidence, retained artifacts, official rules, or tool verification can answer the question.** Treat every mutable fact as untrusted until verified. Do not lower a threshold, reinterpret a gate, call a run successful, claim a push, or describe policy strength merely because a report says so. Recalculate important claims independently from raw evidence.

The user explicitly requires the following work style:

- inspect evidence before acting;
- evaluate multiple plausible approaches before selecting one;
- validate whether a new path is worth pursuing before implementing it;
- do not abandon a path after one failed attempt when safe alternative branches remain;
- finish every experiment that is started, or explicitly terminate it with a retained failure record and reason;
- test edge cases and fail-closed behavior, not only happy paths;
- preserve exact provenance, hashes, limits, commands, and authorization boundaries;
- do not launch a cloud job, training run, Modal job, submission, push, deck freeze, or external mutation without the specific required approval.

## Mandatory first reads

Read these files in order before making a plan:

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_G3A_CLOUD_PLAN_MASTER_PROMPT.local.md`
3. the timestamped structured handoff referenced by `current.local.md`
4. `AGENTS.md`
5. `ptcg-rl/PROJECT_STATUS_ANALYSIS.md`
6. `ptcg-rl/PROJECT_STATUS.md`
7. `ptcg-rl/PROGRESS_REPORT.md`
8. `ptcg-rl/reports/gates/g3a.json`
9. `ptcg-rl/reports/tasks/current.json`
10. `ptcg-rl/configs/g3a_evaluation_v1.json`
11. `ptcg-rl/configs/g3a_local_correctness_v1.json`
12. `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-review-v1.json`
13. `ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`
14. `PTCG_RL_Codex_Handoff_v1.0/PTCG_RL_Codex_Handoff/docs/07_PPO_LEAGUE.md`
15. the implementation and tests listed later in this prompt.

If any file is missing, do not fabricate its contents. Search the repository and report the exact discrepancy.

## Mandatory repository verification

Immediately verify, using `Local_mcp.repo_git_status` and `Local_mcp.workspace_exec` as appropriate:

```bash
git status -sb
git log --oneline --decorate -12
git branch -vv
git remote -v
git rev-list --left-right --count origin/main...main
```

At this handoff, the verified local state was:

- repository root: `/home/nnmax/Desktop/kaggle/PTCG`
- main project directory: `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`
- Local MCP repository id: `ptcg`
- branch: `main`
- local HEAD: `5f50189cb76f9f2acd6787b7700e9bc55eb28f86`
- worktree: clean before writing these local handoff files
- remote: `origin` -> `https://github.com/Ashok-19/Kaggle-PTCG.git`
- locally known `origin/main`: `e2ce735f7640588af2a7bcd6f1e83f400cca5514`
- local `main` was six commits ahead and zero behind the locally known `origin/main`
- `git branch -vv` showed no upstream annotation on `main`
- no push occurred in the completed G3a local-correctness work.

The local remote-tracking reference can be stale. Verify current remote state before saying whether commits were pushed. Never push unless the user explicitly asks. A read-only fetch may still require verification of tool policy and network availability; do not imply it happened if it did not.

Recent verified local commits, newest first:

```text
5f50189 Promote local G3a PPO correctness
cae42da Harden G3a local report provenance
6840768 Implement G3a PPO correctness harness
0275023 Promote frozen G3a evaluation contract
6ca84cf Implement frozen G3a evaluation contract
b1c1ed7 Ignore local scratch and transient artifacts
e2ce735 Promote verified G2 neural reliability pass
097745d Record G2 reliability readiness
b536f3a Canonicalize reliability ledger evidence
ba89a0d Bind reliability runner config
e4c1247 Add G2 reliability harness
459cfb6 feat(g2): qualify deterministic checkpoint package
```

Do not stage or commit `.chatgpt/handoffs/*.local.md` unless the user explicitly converts them into tracked documentation. They are local continuation aids.

## Source-of-truth order

Resolve contradictions in this order:

1. current official Kaggle rules, engine, card data, and runtime contract;
2. direct user decisions and `AGENTS.md`;
3. approved decision records and the handbook/master design;
4. contract tests and retained raw run evidence;
5. project status and machine-readable gate reports;
6. dashboard projections and older narrative summaries.

A dashboard is a projection, not primary evidence. A JSON field named `PASS` is not proof until the governing criteria and raw evidence are independently checked.

## Mission and deadline

The project is the private 2026 Kaggle Pokémon TCG AI Battle effort. The objective is to maximize the probability of a top-20/gold-medal finish without claiming a medal is guaranteed.

Current recorded milestone dates:

- competition close: `2026-08-16T23:59:00Z`
- entry/team-merger deadline: `2026-08-09T23:59:00Z`
- architecture freeze: `2026-08-09T23:59:00Z`
- training code/config freeze: `2026-08-12T23:59:00Z`
- packaging freeze: `2026-08-14T23:59:00Z`

These dates are mutable external facts. Verify official current rules before relying on them for a new decision.

## Current gate state

Verified at handoff:

- `G0`: `SUCCEEDED / PASS`
- `G1R`: `SUCCEEDED / PASS`
- `R1`: `SUCCEEDED / PASS`
- `G2`: `SUCCEEDED / PASS`
- `G3a`: `BLOCKED / NOT_REVIEWED`
- `G3b`: not started
- `D1`: not started
- `G4`: not started
- `G5`: not started
- `G6`: not started

The exact current G3a authorization string is:

```text
LOCAL_CORRECTNESS_COMPLETE_CLOUD_TRAINING_NOT_AUTHORIZED
```

The local PPO correctness prerequisite is complete. The actual frozen-budget private Kaggle/Colab G3a qualification has not run. Local toy success does not establish Pokémon policy strength and does not authorize cloud training.

## Exact next task

The next authorized task is **not to launch training**. It is to freeze and independently review one exact private Kaggle or Colab G3a cloud correctness plan.

The plan must include, before any run:

- exact environment selection and reason;
- one immutable source commit;
- one exact versioned config;
- all three frozen seeds;
- exact non-forced-choice budget per seed between 25,000 and 100,000;
- the same budget across seeds within the frozen maximum relative difference of `0.0025`;
- exact per-task allocation determined before results are observed;
- explicit treatment and budget of the stateless recurrent-cue control;
- at most four CPU cores;
- device policy and proof that accidental GPU use fails closed if the plan is CPU-only;
- maximum wall time for each model, each seed, and the complete notebook;
- checkpoint cadence;
- a deliberate interruption/resume proof;
- output/artifact destinations;
- canonical manifest and source hashes;
- zero-tolerance counters;
- fail-closed stop conditions;
- download/review procedure;
- independent verdict recalculation;
- user approval boundary.

After the plan is frozen, present it to the user and wait for explicit training approval. Do not automatically launch Kaggle, Colab, Modal, or any other external job.

## Do not assume the budget interpretation

The frozen evaluation file says:

```text
minimum_non_forced_choices_per_seed = 25000
maximum_non_forced_choices_per_seed = 100000
same_budget_across_seeds = true
maximum_relative_budget_difference = 0.0025
task_allocation_required_before_run = true
```

Before writing the cloud config, inspect the evaluation implementation, tests, decision record, and task semantics to determine precisely whether the per-seed budget applies to:

- the aggregate across trainable tasks;
- each trainable task individually;
- each model including the equal-budget stateless control;
- or another explicitly encoded interpretation.

Do not guess. Search these files and relevant tests:

- `ptcg-rl/src/ptcg_rl/g3/evaluation.py`
- `ptcg-rl/tests/g3/test_evaluation.py`
- `ptcg-rl/tests/g3/test_evaluation_script.py`
- `ptcg-rl/tests/g3/test_evaluation_report.py`
- `ptcg-rl/configs/g3a_evaluation_v1.json`
- `ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`
- handbook `07_PPO_LEAGUE.md`.

If the repository remains ambiguous after exhaustive inspection, create a narrowly scoped decision proposal that lists all interpretations, costs, statistical implications, and a recommended interpretation. Ask the user only for that exact decision. Do not silently choose the cheapest interpretation.

## Required approach-selection work

Before implementing the cloud plan, compare at least these viable branches using evidence:

1. private Kaggle CPU notebook;
2. private Colab CPU notebook;
3. any repository-supported alternative that satisfies the same immutable artifact and download requirements.

Compare:

- current availability;
- core count and enforceability;
- dependency reproducibility;
- internet-off behavior;
- session wall-time limits;
- notebook output retention;
- checkpoint persistence;
- output download support;
- ease of user manual launch;
- risk of hidden accelerator/default environment changes;
- artifact provenance;
- recovery after notebook interruption;
- total expected duration based on measured local throughput, with uncertainty and overhead.

Do not select Kaggle merely because it was used before. Do not select Colab merely because it seems simpler. Retain the comparison and rejection reasons.

## User-preferred future Kaggle workflow

Preserve this user preference:

- maintain a single notebook for the current workflow rather than creating many notebook variants;
- after each source update, update that notebook code;
- prepare versioned input datasets/models so the user only needs to import/open the notebook, attach the required existing input asset(s), select the required session, and run it;
- avoid creating many noisy datasets/models; prefer updating versions of a small stable set;
- after the user runs the notebook, use Kaggle MCP tools to inspect status, list outputs, and download the notebook outputs;
- continue the project from downloaded artifacts without asking the user to manually transfer individual result files when the tools can retrieve them.

Do not assume these operations work merely because tools are listed. Verify the exact current MCP behavior before depending on it. Retain numeric dataset/model/notebook versions and exact owner/slug identifiers. Never claim an upload, version update, notebook run, or output download succeeded without checking the corresponding returned metadata and artifact bytes.

Relevant Kaggle MCP capabilities that have been available include:

- notebook information and status;
- notebook file listing;
- session-output listing;
- notebook output and output-ZIP download;
- dataset information/status/file listing;
- model-version file listing/download;
- dataset/model/notebook upload/update tools when exposed.

Discover current schemas through `api_tool.list_resources` rather than inventing arguments.

## External launch boundary

The assistant did not launch the successful G2 reliability notebook. The user manually ran it after selecting the required session. Preserve the same explicit-launch discipline for G3a unless the user gives new permission.

No automatic launch is authorized. Preparation, versioned code, configs, tests, notebook generation, local commits, and a frozen plan are allowed. Starting the actual private Kaggle/Colab training smoke requires explicit user approval after the exact plan is presented.

## Project history and immutable evidence

### Repository consolidation / G0

- active repository: private `Ashok-19/Kaggle-PTCG`
- inactive migration backup: private `Ashok-19/Kaggle-PTCG-RL`
- clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`
- ROGII is a read-only dashboard/workflow reference and must not be modified.

### G1R contract recertification

G1R is closed as `SUCCEEDED / PASS`. Its non-negotiable invariants remain binding:

- complete requested counts and zero invalid/failure/timeout/post-terminal/fallback counters;
- provenance hashes actual engine, wrapper, card data, source, and config;
- final adapter revalidates request identity, type, count, uniqueness, range, legality, and availability;
- terminal state is handled before stale selection-local data;
- unknown or impossible semantics fail closed with bounded reproduction evidence;
- `STOP` is a first-class autoregressive action and joint log probability replays exactly;
- recurrent state is owned by `(episode_uuid, player, policy_id)`;
- exact duplicate inference requests are idempotent;
- stale/out-of-order requests are rejected;
- logs are read once and bursts larger than 200 are preserved;
- legal options are never truncated;
- actor/critic inputs contain only public information.

Completed historical evidence includes the one-million-operation contract corpus, 10,080-game arena, throughput matrix, six-hour RSS soak, worker/recurrent isolation, and independent review. Read the actual gate and reports before quoting metrics not stated here.

### R1 replay pipeline

R1 is closed as `SUCCEEDED / PASS`.

Exact retained facts:

- approved R0 plan hash: `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934`
- files: `20`
- total bytes: `83,981,423`
- largest file: `6,303,684` bytes
- audit hash: `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`
- decoded decisions: `2,999`
- selected options: `3,275`
- reconstructed STOP markers: `21`
- ordered requests: `16`
- official card-data SHA-256: `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`
- semantic stream SHA-256: `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`
- independent review mismatches: `0`
- peak loader RSS: `68.17578125 MiB`
- resolved provenance incident: `ptcg-rl/reports/incidents/r1-card-data-provenance-hash.json`.

Additional replay retrieval and action-supervision training are not authorized. Public replay actions must never enter PPO rollout storage. Behavior cloning requires a separate explicit experiment and approval.

### G2 model/action schema

G2 is closed as `SUCCEEDED / PASS`.

Key sealed facts:

- model schema v1 SHA-256: `61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68`
- raw serial magnitude and option transport order are excluded from actor features;
- private card-table SHA-256: `7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0`
- card names and effect text are excluded from model metadata;
- compact policy trainable parameters: `970,022`
- architecture SHA-256: `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`
- target architecture remains under two million parameters unless explicitly changed.

Policy architecture and action contract:

- public-state semantic representation;
- complete legal-option scoring, never first-N truncation;
- GRU recurrent public memory;
- value head;
- ordered without-replacement multi-select;
- first-class `STOP` with legality mask and probability contribution;
- exact state ownership and reset contract.

Important source files:

- `ptcg-rl/src/ptcg_rl/g2/network.py`
- `ptcg-rl/src/ptcg_rl/g2/projection.py`
- `ptcg-rl/src/ptcg_rl/g2/models.py`
- `ptcg-rl/src/ptcg_rl/g2/card_table.py`
- `ptcg-rl/src/ptcg_rl/g2/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g2/reliability.py`
- `ptcg-rl/src/ptcg_rl/g1/recurrent.py`
- G2 and G1 contract tests.

### G2 CPU/GPU qualification

Current-source qualification bundle v4:

- source commit: `c660f74b26fca74915931091ac0fe365f7f005f5`
- bundle SHA-256: `56b4e93671609a8d24887480cbf1d0dfc0c38b60e1cad55d0cf95f4e50744506`
- all `11` manifest entries matched;
- local preflight passed all `10` checks;
- selected gradients: `7`;
- no optimizer or training loop was present.

Private Kaggle qualification:

- GPU notebook version id: `336514431`, Tesla T4;
- CPU notebook version id: `336517420`;
- strict combined `atol=rtol=1e-5` parity over `1,596` numeric values;
- failures: `0`;
- maximum absolute difference: `1.52587890625e-05`;
- maximum tolerance ratio: `0.4138225953505397`;
- CPU batch-1 p99 latency: `8.802885 ms`;
- external HTTP was blocked in both CPU probe attempts.

A prior automatic CLI launch received a Tesla P100 and was rejected before qualification. Never trust requested hardware; inspect actual visible devices. For G2 reliability the user manually selected `GPU T4 x2`.

### G2 deterministic checkpoint package

- implementation commit: `6b3a3b4829b205d62e210fae7e396db33fdb9a5a`
- package SHA-256: `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`
- package size: `5,429,190` bytes
- sorted `ZIP_STORED` archive;
- pickle-free canonical tensor stream;
- numeric card table, manifest, and fixed reference;
- duplicate builds matched exactly;
- reproduced `1,150` numeric and `16` exact actor/value/recurrent/decoder/log-probability values;
- drift: `0` under required tolerance;
- adversarial fail-closed branches: `25`.

This G2 package is distinct from the G3 training checkpoint, which intentionally contains optimizer and RNG state and is loaded with PyTorch `weights_only=True`.

### G2 10,000-game neural reliability qualification

Read:

- `ptcg-rl/reports/evaluations/g2-neural-reliability-v1.json`
- `ptcg-rl/reports/gates/g2.json`
- `ptcg-rl/reports/tasks/current.json` entries `T-G2-002` through `T-G2-005`.

Exact facts:

- user-run notebook: `ashok205/kptcg-g2-neural-reliability-v1`
- script version id: `336684242`
- internet: off
- visible GPUs: exactly two Tesla T4 devices
- completed games: `10,000 / 10,000`
- engine requests: `1,213,203`
- multi-select requests: `20,791`
- invalid selections: `0`
- fallbacks: `0`
- post-terminal actions: `0`
- recurrent-state violations: `0`
- nonfinite outputs: `0`
- crashes: `0`
- timeouts: `0`
- throughput: `1.97684 games/s`
- notebook wall time: approximately `85.50 minutes`
- games ledger bytes: `28,783,333`
- games ledger SHA-256: `39d7d43d142bec64bcace5da5151ca6bccba2bd533c47d1957a4ad7505cc918f`
- runner receipt SHA-256: `9afc97ffe2df08dcb84ebe087e993649b868719e547204efb04c51b776f7c3e7`
- independent review SHA-256: `7a1f77f452db96015a18c54631952b3d67b8bcd7cea7314372f3e45003681e6e`
- private input dataset: `ashok205/g2-neural-reliability-inputs`, version `1`, status `READY`
- input archive bytes: `12,088,771`
- input archive SHA-256: `d4fa4a09e5c86cc3a2c93461b2127634dc197a7241d99d36f78bc35ce878b6ec`.

This proves reliability/architecture qualification only. It does not prove strategic strength, win rate, PPO readiness, or medal probability.

### Frozen G3a evaluation contract

Implementation:

- commit: `6ca84cf7ccd79e49341998314da6d32aa8f1de45`
- promotion commit: `0275023bb2c6654080730326c061036a7584ca67`
- config: `ptcg-rl/configs/g3a_evaluation_v1.json`
- config file SHA-256: `51f5d0d800a0a3832cc0ea8873828f6c68262eb4f24e55a8b11ae4143a2dae72`
- semantic SHA-256: `bd3e0e6b5331fe6f6028df65403ecf2446250ebb8f375961544de26cf0ffc3b6`
- evidence: `ptcg-rl/reports/artifacts/g3a-evaluation-contract-v1.json`.

Declared seeds:

```text
1197953491
20344180
1491619630
```

G3a pass rule:

```text
ALL_TASKS_PASS_IN_ALL_DECLARED_SEEDS
```

Budget:

- minimum non-forced choices per seed: `25,000`
- maximum non-forced choices per seed: `100,000`
- exact budget required before run;
- same budget across seeds;
- maximum relative budget difference: `0.0025`;
- task allocation required before run.

Tasks:

1. `masked-bandit-v1`
   - legal mask required;
   - invalid action is failure;
   - zero failed evaluation cases.
2. `recurrent-cue-v1`
   - cues `0` and `1`;
   - final decision observation identical across cues;
   - stateless theoretical ceiling `0.5`;
   - recurrent oracle ceiling `1.0`;
   - minimum recurrent score `0.85`;
   - minimum recurrent-over-stateless margin `0.25` in every seed.
3. `variable-option-multiselect-v1`
   - variable option count;
   - variable minimum/maximum count;
   - ordered unique selection;
   - first-class `STOP`;
   - invalid action is failure;
   - zero failed evaluation cases.

Probability replay before first update:

- maximum old compound log-probability absolute error: `1e-5`;
- maximum initial ratio absolute error from one: `1e-5`.

Zero-tolerance counters:

- crashes;
- fallbacks;
- hidden-state cross-owner events;
- invalid actions;
- NaN/Inf;
- stale inference requests;
- timeouts;
- unclassified truncations.

Checkpoint-resume requirements:

- counters;
- league;
- model;
- optimizer;
- rollout boundary;
- scheduler or scaler;
- all available RNG states;
- fixed tensor `atol=1e-5`, `rtol=0`.

Strength claims are forbidden at G3a.

The same frozen config also contains future G3b, D1, and champion thresholds. Do not weaken or rewrite them after observing results. Do not invent a blended promotion score.

### G3a local PPO correctness implementation

Implementation commits:

- `68407689ccfb18236f14f78dd68360704f408682` — initial project-native correctness harness;
- `cae42da47bc9f3491869e8afd0e1254061b9f585` — dashboard envelope and clean-Git provenance hardening;
- `5f50189cb76f9f2acd6787b7700e9bc55eb28f86` — reviewed promotion evidence/status.

Implementation files:

- `ptcg-rl/src/ptcg_rl/g3/ppo.py`
- `ptcg-rl/src/ptcg_rl/g3/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g3/toy.py`
- `ptcg-rl/src/ptcg_rl/g3/local_correctness.py`
- `ptcg-rl/scripts/g3a_local_correctness.py`
- `ptcg-rl/configs/g3a_local_correctness_v1.json`.

Core methods in `ppo.py`:

- `LocalExecutionLimitsV1`
- `apply_local_execution_limits`
- `validate_local_workload`
- `CompoundActionV1`
- `replay_compound_action`
- `compound_outcome_count`
- `is_forced_compound_action`
- `verify_probability_replay`
- `compute_gae`
- `RolloutEventV1`
- `split_recurrent_rollout`
- `ppo_loss`
- `require_finite_gradients`.

Important semantics:

- one non-forced engine selection request is one PPO action;
- decoder subchoices are internal to the compound action;
- optional STOP has its own log-probability;
- ordered selections are without replacement;
- action forcedness depends on the number of complete legal ordered submitted lists, not raw option count;
- forced engine calls are folded through recurrent state but create no actor/value/GAE node;
- terminal and live truncation behavior are separately classified;
- recurrent slices cannot cross owner, policy-version, terminal, or invalid reset boundaries;
- initial old/new probability ratio must equal one within tolerance before the first update;
- NaN/Inf and absent gradients fail closed.

Training checkpoint implementation in `checkpoint.py`:

- atomic payload + manifest writes;
- SHA-256 and size binding;
- restricted `torch.load(..., weights_only=True)`;
- exact model tensor key/shape/dtype validation;
- optimizer state;
- scheduler or scaler state;
- counters;
- league;
- rollout boundary;
- Python RNG;
- NumPy RNG;
- PyTorch CPU RNG;
- CUDA RNG when available and compatible;
- JSON-safe metadata validation;
- corruption, manifest mismatch, incompatible state, unsafe payload, and component-presence failures tested.

Toy implementation in `toy.py`:

- one small recurrent actor-critic using the same ordered selection and STOP semantics;
- `masked-bandit-v1`;
- `recurrent-cue-v1`;
- `variable-option-multiselect-v1`;
- stateless cue control;
- bounded CPU-only trainer;
- exact result records and checkpoint round trips.

Production-boundary integration:

- the generic compound-action replay is tested against the actual sealed G2 decoder, not only the toy model.

Key tests:

- `ptcg-rl/tests/g3/test_ppo.py`
- `ptcg-rl/tests/g3/test_training_checkpoint.py`
- `ptcg-rl/tests/g3/test_toy.py`
- `ptcg-rl/tests/g3/test_local_correctness.py`
- `ptcg-rl/tests/g3/test_local_correctness_report.py`
- `ptcg-rl/tests/g3/test_evaluation.py`
- `ptcg-rl/tests/g3/test_evaluation_script.py`
- `ptcg-rl/tests/g3/test_evaluation_report.py`.

### G3a local candidate experiments

Local config:

- path: `ptcg-rl/configs/g3a_local_correctness_v1.json`
- bytes: `1,781`
- SHA-256: `10874b321250cf87ff4824aafa7de35c557ad194bc76d255d2afc0d4a91471aa`.

Hard local safety envelope:

- device: CPU;
- maximum PyTorch threads: `2`;
- observed interop threads: `1`;
- worker processes: `0`;
- maximum allowed choices per model in the local harness: `4,096`;
- actual selected runs: `1,024` choices per model;
- CABT games: `0`;
- no GPU, cloud, self-play, or external service mutation.

Candidate A:

- `512` choices;
- learning rate `0.005`;
- failed because variable-option/multi-select score was `0.75`;
- recurrent margin `0.5`;
- maximum pre-clip gradient norm `0.8231383061358004`.

Candidate B, selected:

- `1,024` choices;
- learning rate `0.005`;
- all tasks passed;
- recurrent margin `0.5`;
- maximum pre-clip gradient norm `0.8668152256223083`.

Candidate C:

- `1,024` choices;
- learning rate `0.01`;
- all tasks passed;
- rejected because maximum pre-clip gradient norm was `1.5519256876696554`, materially higher than candidate B.

Selected three-seed result, every seed:

- masked bandit: `1.0`;
- recurrent cue: `1.0`;
- variable-option/multi-select: `1.0`;
- equal-budget stateless cue control: `0.5`;
- recurrent margin: `0.5`;
- maximum probability replay error: `0`;
- maximum initial ratio error: `0`;
- zero-tolerance total: `0`;
- checkpoint model tensors exact;
- fixed evaluation exact;
- model, optimizer, scheduler, counters, league, rollout boundary, Python RNG, NumPy RNG, and PyTorch CPU RNG restored.

Per-seed maximum model wall times in the final clean run:

- seed `1197953491`: `14.104740312000104` seconds;
- seed `20344180`: `13.908917884000402` seconds;
- seed `1491619630`: `13.623659962999227` seconds.

Complete clean runner wall time: `294.369` seconds.

Authoritative report:

- path: `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-v1.json`
- bytes: `27,889`
- SHA-256: `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`
- source commit: `cae42da47bc9f3491869e8afd0e1254061b9f585`
- clean Git status SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Independent review:

- path: `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-review-v1.json`
- SHA-256 at handoff: `654897a62b8802829d084568fee17f398142e4776a51fa1dcca981f88fa41e84`
- independent candidate, seed, resource, source/config hash, checkpoint, and authorization recalculation: PASS.

Validation:

- source-focused tests before clean run: `55` passed;
- isolated clean checkout suite: `334` passed, `4` environment-dependent skips;
- final focused G3 suite: `144` passed;
- final full Python suite: `347` passed;
- Ruff: PASS;
- dashboard rebuild: `111` records, `0` quarantined;
- dashboard doctor: PASS;
- frontend unit tests: `7` passed;
- production frontend build: PASS;
- Playwright browser tests: `4` passed;
- tracked browser screenshots restored after validation.

### Important provenance incident and fix

Do not omit this history:

1. The first generated local correctness report lacked the dashboard record envelope fields.
2. Dashboard rebuild quarantined it because `record_id`, `created_at_utc`, `source_path`, and `producer` were missing.
3. That report was not promoted.
4. The generator was changed to emit a complete dashboard envelope.
5. The generator was also changed to verify that the claimed source commit equals checked-out HEAD and that the worktree is clean before running.
6. A clean isolated clone of commit `cae42da...` was created.
7. The first isolated test attempt lacked PyTorch/NumPy because only default dependency groups were installed; it did not execute project logic.
8. The suite was rerun with declared `dev` and `model` groups.
9. One R1 test then failed solely because the ignored private official card-data file was absent from the clone.
10. The existing ignored private assets were copied/mounted into the isolated clone without tracking them.
11. The clean suite then passed `334` tests with `4` environment-dependent skips.
12. The full matrix was rerun from the clean commit.
13. The corrected report passed independent recalculation and dashboard ingestion with zero quarantine.
14. The temporary clone and copied private assets, approximately `1.69 GB`, were removed.

Future evidence generators must include a dashboard-valid envelope and exact clean-Git provenance from the start. Do not hand-edit generated evidence to make it pass.

## Cloud-plan design requirements

The plan must be versioned and fail closed. Inspect existing naming/schema conventions before choosing file paths. Probable paths may include a new config under `ptcg-rl/configs/`, a plan artifact under `ptcg-rl/reports/artifacts/`, a task/gate update, notebook source under the existing Kaggle notebook conventions, and tests under `ptcg-rl/tests/g3/`; do not create these blindly.

At minimum, the plan must define:

### Identity and source

- plan schema version;
- plan ID and run ID rules;
- exact source commit;
- clean-worktree requirement;
- exact source include/exclude hash rules;
- config path/bytes/SHA-256;
- Python and dependency lock identity;
- notebook source hash;
- input dataset/model owner, slug, numeric version, file list, bytes, and hashes;
- artifact output root and collision-resistant run directory.

### Environment

- Kaggle or Colab, selected after comparison;
- CPU-only unless the frozen plan explicitly demonstrates why another device is permitted;
- maximum four CPU cores;
- exact thread environment variables;
- PyTorch intra-op and inter-op limits;
- worker count;
- internet disabled and independently checked;
- platform fingerprint;
- fail if actual environment differs from the plan.

### Work allocation

- declared seeds exactly `1197953491`, `20344180`, `1491619630`;
- exact choices per seed;
- exact choices per task/model;
- same budget across seeds;
- stateless recurrent-cue control budget;
- choices per update;
- PPO epochs;
- learning rate and fixed PPO parameters;
- evaluation cadence;
- whether evaluation choices count toward the training budget, explicitly defined;
- deterministic task-case generation and coverage;
- no result-dependent budget extension.

### Checkpoint and resume

- checkpoint cadence in non-forced choices and wall time;
- atomic payload + manifest;
- checkpoint hashes and size limits;
- model, optimizer, scheduler/scaler, counters, league, rollout boundary, and all available RNG states;
- fixed-reference evaluation before interruption;
- intentional interruption at a predeclared boundary;
- fresh-process restore;
- exact fixed-reference parity after restore;
- continuation to the exact final budget;
- no hidden reset of optimizer/scheduler/counters;
- corrupted/incomplete checkpoint rejection;
- no checkpoint overwrite without content-addressed retention or explicit versioning.

### Fail-closed stop conditions

Stop and write a bounded diagnostic if any of the following occurs:

- invalid action;
- illegal mask selection;
- duplicate ordered selection;
- STOP when unavailable;
- selection count outside min/max;
- NaN/Inf output, loss, gradient, hidden state, or parameter;
- old compound log-probability mismatch above `1e-5`;
- initial ratio error above `1e-5`;
- stale or out-of-order recurrent request;
- hidden-state cross-owner/version event;
- unclassified terminal/truncation;
- timeout;
- crash or swallowed exception;
- fallback;
- checkpoint/manifest mismatch;
- failed resume parity;
- source/config/input hash mismatch;
- dirty source tree;
- unexpected GPU or core/thread count;
- network unexpectedly available when the plan requires internet off;
- budget drift above `0.0025`;
- missing task/seed/control result;
- artifact write/download failure.

### Required retained outputs

- resolved config;
- run manifest;
- environment fingerprint;
- per-update metrics;
- per-task/per-seed result records;
- old/new log-probability replay evidence;
- zero-tolerance counters;
- checkpoint manifests and resume receipt;
- fixed-reference tensors/hashes;
- wall time and resource observations;
- loss/gradient/KL/clip-fraction summaries;
- final model/checkpoint hashes;
- bounded failure capsules if any;
- canonical report with dashboard envelope;
- independent-review report;
- notebook-output file manifest;
- output download receipt and local hash verification.

### Acceptance and non-claims

- all tasks must pass in all three declared seeds;
- recurrent score at least `0.85` every seed;
- stateless score no greater than `0.5` under the frozen control;
- recurrent margin at least `0.25` every seed;
- probability errors within `1e-5`;
- every zero-tolerance counter zero;
- checkpoint/resume requirements pass;
- exact budget complete;
- no policy-strength claim;
- no G3b promotion;
- no CABT strategic claim from toy tasks.

## Edge cases that must be explicitly covered

Do not say “edge cases tested” without mapping each case to a test or retained run record.

Compound action and masks:

- zero-option valid forced STOP;
- optional STOP at minimum zero;
- STOP unavailable before minimum count;
- implicit completion only at effective maximum;
- minimum greater than available options;
- maximum greater than available options;
- one raw option but more than one complete action due to STOP;
- multiple options but exactly one complete legal ordered list;
- ordered permutations produce distinct compound actions when order matters;
- duplicate option rejection;
- unavailable option rejection;
- out-of-range option rejection;
- option sets larger than 64;
- variable min/max and variable option count;
- all masked outcomes rejected;
- legal logits finite; NaN and positive infinity rejected.

Probability and PPO:

- exact compound log-probability replay including STOP;
- multiple subchoice probability sum;
- single legal continuation normalized entropy behavior;
- initial ratio exactly one;
- mismatch just inside and just outside tolerance;
- advantage normalization with one and multiple valid actions;
- policy mask excludes forced/padding nodes;
- clipped and unclipped policy branches;
- clipped value loss branch;
- finite approximate KL and clip fraction;
- no valid learner action fails closed;
- finite gradients required;
- nonfinite gradient rejection.

GAE and boundaries:

- terminal bootstrap zero;
- live truncation bootstrap nonzero;
- truncation during opponent turn;
- truncation during a forced-selection chain;
- final node must close with terminal/truncation;
- terminal and truncation cannot both be true;
- trace cannot continue across a boundary;
- terminal outcome attached to both player trajectories where applicable;
- no cross-player stream interleaving.

Recurrent ownership:

- reset required at new episode/owner/version;
- exact duplicate request idempotence;
- stale request rejection;
- out-of-order request rejection;
- worker replacement clears all affected owner states;
- slices do not cross terminal;
- slices do not cross policy version;
- long forced chains fold into state without PPO nodes;
- policy-version lag exactly zero.

Checkpoint/resume:

- atomic write cleanup after failure;
- payload/manifest hash mismatch;
- truncated payload;
- noncanonical manifest;
- wrong model keys, shapes, or dtypes;
- scheduler/scaler presence mismatch;
- optimizer restoration;
- counters and budget restoration;
- league and rollout-boundary restoration;
- Python/NumPy/Torch RNG restoration;
- CUDA RNG mismatch if CUDA state exists;
- unsafe non-weights-only payload rejection;
- fixed evaluation exact before/after restore;
- continuation reaches exact budget once, without duplicate updates.

Cloud/notebook:

- missing input file;
- wrong input dataset/model version;
- wrong source commit;
- dirty source;
- output directory collision;
- interrupted notebook after checkpoint;
- notebook completion with missing report;
- report with missing dashboard envelope;
- output list pagination if applicable;
- ZIP and individual output download parity;
- local downloaded SHA-256 matches notebook manifest;
- no reliance on notebook UI status alone.

## Evidence-first implementation workflow

Use this sequence unless repository evidence requires a narrower adjustment:

1. Verify Git, remote state, current gate, task records, and handoff files.
2. Read the full frozen contract and implementation/tests.
3. Search for any existing G3a cloud-plan or notebook work before creating files.
4. Inspect current Kaggle MCP tool schemas and current platform availability.
5. Compare Kaggle CPU, Colab CPU, and any viable alternative.
6. Resolve the frozen budget interpretation from evidence.
7. Estimate runtime from recorded throughput, including uncertainty and overhead; do not extrapolate from a single point without sensitivity analysis.
8. Choose one plan only after alternatives are documented and rejected for specific reasons.
9. Add failing tests for config/schema/authorization/provenance/edge cases.
10. Implement the exact plan config, loader/reviewer, notebook source, and artifact schema.
11. Validate with narrow tests, then all G3 tests, full Python suite, Ruff, dashboard ingestion/doctor, frontend tests/build, and browser tests where the change affects dashboard data.
12. Independently review the frozen plan from a clean source commit.
13. Create a local commit containing only intentional source/config/test/safe-report paths.
14. Verify clean status and exact commit.
15. Present the immutable plan, runtime/cost estimate, asset/version strategy, and launch instructions to the user.
16. Stop. Do not launch until explicit approval is received.

Do not create a background process that may outlive the session without managed job metadata and verified durability. The current next task is plan preparation, not a long-running local job.

## Tool discipline

Use `Local_mcp` repository tools:

- `repo_git_status` for status;
- `repo_tree`, `repo_search`, `repo_fetch_file`, `repo_read_many` for inspection;
- `workspace_exec` for approved deterministic test and Git-inspection commands;
- `repo_write_file` or `repo_write_changes` for approved edits;
- `repo_git_review` before committing;
- `repo_write_stage_commit` for exact local commits;
- `workspace_acquire_official_lock` before official gate/status promotion writes;
- release every official lock after the serialized write;
- discover and use task-claim/release tools if present;
- `workspace_cleanup_paths` only for approved scratch paths;
- never use shell Git to bypass review/stage/commit controls.

Handoff files are local-only. They should not be part of experiment commits.

When using Kaggle tools:

- discover current exact schemas;
- use numeric versions;
- retain owner/slug/version IDs;
- inspect actual status and output file lists;
- download artifacts and verify bytes/hashes;
- do not expose private signed URLs or credentials;
- do not create or update datasets/models/notebooks until that external mutation is authorized for the specific plan preparation action;
- do not launch a notebook without explicit approval.

## Local resource boundary

Local work may include source changes, contract tests, tiny toy smoke, metadata, packaging, and completed-agent inference checks. Do not run meaningful self-play, CABT training, league training, or large evaluation locally.

The existing local correctness config limits:

- CPU only;
- two PyTorch threads;
- one interop thread observed;
- zero workers;
- maximum 4,096 choices per model;
- maximum 300 seconds per model.

Do not silently increase these. A larger local benchmark requires evidence that it remains a tiny correctness/timing experiment and a reviewed config change; otherwise estimate using existing evidence or use the approved cloud plan after authorization.

## Algorithm and architecture boundaries

Do not materially change these without explicit approval:

- recurrent PPO as the initial RL algorithm;
- public-information actor and critic;
- terminal reward `+1/0/-1`;
- no reward shaping;
- no privileged critic;
- no behavior cloning;
- no public-replay action supervision;
- no inference search;
- compact under-two-million-parameter architecture;
- exact-deck specialist rather than universal multi-deck actor;
- ordered without-replacement multi-select with STOP;
- zero learner policy-version lag.

The current task should not add CABT actor/learner integration unless the frozen cloud-plan implementation genuinely requires a narrow adapter and that change is clearly within the existing approved architecture. G3a toy qualification is not the moment to build the full league or main self-play system.

## Future stages, not current authorization

After G3a cloud qualification passes and is independently reviewed, later stages remain separate:

- G3b competence against random/rule anchors and frozen opponents;
- D1 equal-budget deck selection and matchup floors;
- G4 Modal canary/readiness;
- G5 main league/champion training;
- G6 final package and submission.

Do not skip ahead. Do not start G3b because G3a local toy tasks passed.

## Dashboard and report requirements

Every committed machine-readable report must include a valid dashboard envelope, including at least:

- `schema_version`;
- `record_id`;
- `created_at_utc`;
- `source_path`;
- `producer`;
- status/decision fields appropriate to the record.

Run dashboard rebuild and require zero quarantine before promotion. The previous missing-envelope incident is a regression to prevent.

The dashboard must remain read-only and must not ingest private raw assets, checkpoints, card tables, credentials, or signed URLs.

## Validation commands

Use commands appropriate to the exact changes. Existing successful commands include:

```bash
cd ptcg-rl
uv run pytest -q tests/g3
uv run pytest -q
uv run ruff check .
uv run ptcg dashboard rebuild
uv run ptcg dashboard doctor

cd dashboard/frontend
npm test -- --run
npm run build
npx playwright test
```

When validating from a fresh isolated checkout, include declared dependency groups such as `--group dev --group model` when required. If ignored private assets are needed by existing tests, mount/copy the existing ignored assets without tracking or redistributing them. Distinguish environment-dependent skips from passed tests.

Restore tracked screenshots or generated tracked artifacts after validation. Do not commit generated caches or accidental output.

## Git and commit rules

- inspect before editing;
- preserve unrelated user changes;
- acquire official lock for gate/status promotion;
- use exact path lists;
- review new untracked files explicitly because normal Git review may exclude them;
- dry-run the exact stage/commit payload;
- commit locally only after all relevant tests pass;
- never push without explicit user approval;
- after commit, verify HEAD and clean status;
- report whether the local branch is ahead of the locally known remote reference and whether the remote was actually fetched.

## Required final report for the next task

When the cloud plan is ready for user approval, report:

- exact selected platform and rejected alternatives;
- exact source commit and clean status;
- exact config path, bytes, SHA-256, and semantic identity;
- exact seed and task allocation table;
- exact choice budgets and equality checks;
- expected runtime range and basis;
- maximum CPU cores/threads/workers;
- checkpoint cadence and intentional resume point;
- artifact paths;
- input dataset/model/notebook owner/slug/version strategy;
- single-notebook update strategy;
- exact user manual launch steps;
- exact stop/kill procedure;
- output download and review procedure;
- all tests and dashboard results;
- local commits created;
- branch/remote/push state;
- costs already incurred and estimated cloud cost/quota;
- explicit statement that no training was launched;
- one clear approval question for the immutable plan.

Do not end with a vague offer. The next user decision should be narrowly framed: approve or reject the exact frozen plan.

## Relevant file index

Repository governance/status:

- `AGENTS.md`
- `ptcg-rl/PROJECT_STATUS_ANALYSIS.md`
- `ptcg-rl/PROJECT_STATUS.md`
- `ptcg-rl/PROGRESS_REPORT.md`
- `ptcg-rl/reports/tasks/current.json`
- `ptcg-rl/reports/gates/g1r.json`
- `ptcg-rl/reports/gates/r1.json`
- `ptcg-rl/reports/gates/g2.json`
- `ptcg-rl/reports/gates/g3a.json`
- `ptcg-rl/reports/events/g3a-events.json`.

Decisions/design:

- `ptcg-rl/docs/decisions/DEC-008_G1_REOPENED.md`
- `ptcg-rl/docs/decisions/DEC-009_G1R_CLOSED.md`
- `ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`
- `PTCG_RL_Codex_Handoff_v1.0/PTCG_RL_Codex_Handoff/docs/07_PPO_LEAGUE.md`.

G1/G1R action/environment:

- `ptcg-rl/src/ptcg_rl/g1/actions.py`
- `ptcg-rl/src/ptcg_rl/g1/environment.py`
- `ptcg-rl/src/ptcg_rl/g1/recurrent.py`
- `ptcg-rl/src/ptcg_rl/g1/semantic.py`
- `ptcg-rl/src/ptcg_rl/g1/arena.py`
- `ptcg-rl/src/ptcg_rl/g1/soak.py`
- `ptcg-rl/tests/unit/test_g1_contracts.py`
- `ptcg-rl/tests/unit/test_g1_environment.py`.

R1 replay:

- `ptcg-rl/src/ptcg_rl/replay/acquisition.py`
- `ptcg-rl/src/ptcg_rl/replay/planner.py`
- `ptcg-rl/src/ptcg_rl/replay/semantic_loader.py`
- `ptcg-rl/src/ptcg_rl/replay/independent_review.py`
- `ptcg-rl/reports/replays/r1-semantic-loader.json`
- `ptcg-rl/reports/replays/r1-independent-review.json`
- `ptcg-rl/tests/replay/`.

G2:

- `ptcg-rl/src/ptcg_rl/g2/models.py`
- `ptcg-rl/src/ptcg_rl/g2/projection.py`
- `ptcg-rl/src/ptcg_rl/g2/card_table.py`
- `ptcg-rl/src/ptcg_rl/g2/network.py`
- `ptcg-rl/src/ptcg_rl/g2/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g2/reliability.py`
- `ptcg-rl/scripts/g2_checkpoint_package.py`
- `ptcg-rl/scripts/g2_neural_reliability.py`
- `ptcg-rl/reports/artifacts/g2-policy-v1.json`
- `ptcg-rl/reports/artifacts/g2-policy-checkpoint-v1.json`
- `ptcg-rl/reports/evaluations/g2-policy-cpu-gpu-parity-v4.json`
- `ptcg-rl/reports/evaluations/g2-neural-reliability-v1.json`
- `ptcg-rl/tests/g2/`.

G3 evaluation/local correctness:

- `ptcg-rl/configs/g3a_evaluation_v1.json`
- `ptcg-rl/configs/g3a_local_correctness_v1.json`
- `ptcg-rl/src/ptcg_rl/g3/evaluation.py`
- `ptcg-rl/src/ptcg_rl/g3/ppo.py`
- `ptcg-rl/src/ptcg_rl/g3/checkpoint.py`
- `ptcg-rl/src/ptcg_rl/g3/toy.py`
- `ptcg-rl/src/ptcg_rl/g3/local_correctness.py`
- `ptcg-rl/scripts/g3a_review.py`
- `ptcg-rl/scripts/g3a_local_correctness.py`
- `ptcg-rl/reports/artifacts/g3a-evaluation-contract-v1.json`
- `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-v1.json`
- `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-review-v1.json`
- `ptcg-rl/tests/g3/`.

Dashboard:

- `ptcg-rl/src/ptcg_rl/dashboard/store.py`
- `ptcg-rl/src/ptcg_rl/dashboard/app.py`
- `ptcg-rl/dashboard/frontend/`
- `ptcg-rl/tests/dashboard/`
- `ptcg-rl/dashboard/frontend/tests/dashboard.spec.ts`.

## Stop conditions for the new session

Stop and ask for the smallest exact user decision if:

- the frozen budget interpretation remains genuinely ambiguous after repository inspection;
- the selected platform requires an external mutation or launch not yet authorized;
- the plan would materially change PPO, reward, architecture, critic information, or evaluation rules;
- required private assets are absent and cannot be reconstructed from verified existing assets;
- the current repository or remote state differs materially from this handoff;
- current official competition rules contradict recorded constraints;
- the exact plan is complete and ready for launch approval.

Do not stop merely because one implementation attempt fails. Diagnose, branch to safe alternatives, and close every started experiment with evidence.

## Final reminder

The next milestone is an **immutable, independently reviewed cloud correctness plan**, not a cloud run and not strategic training. Preserve the no-training boundary until the user explicitly approves the exact plan.
