# KPTCG G3a cloud plan evidence-first continuation
## Summary
Track: G3a exact private Kaggle or Colab correctness plan; no launch authorized
State: Repository `ptcg` is on clean local `main` at `5f50189cb76f9f2acd6787b7700e9bc55eb28f86` before local handoff files. G0, G1R, R1, and G2 are PASS. The strict G3a evaluation contract and the project-native local PPO correctness harness are complete and independently reviewed, but G3a remains BLOCKED / NOT_REVIEWED because the exact 25,000-to-100,000-choice-per-seed private cloud plan and explicit user training approval do not exist. The next authorized action is to freeze and review that plan only, then present it for approval without launching.
Why: The current chat became slow. The next session must preserve the full evidence history, exact hashes and commits, tool workflow, no-assumption discipline, local/cloud boundaries, and the precise next milestone without redoing completed work or accidentally launching training.
## Git
- Branch: main
- Head: 5f50189cb76f9f2acd6787b7700e9bc55eb28f86
- Clean: true
## Completed Work
- Frozen G3a evaluation contract implemented at `6ca84cf7ccd79e49341998314da6d32aa8f1de45` and promoted at `0275023bb2c6654080730326c061036a7584ca67`; config SHA-256 `51f5d0d800a0a3832cc0ea8873828f6c68262eb4f24e55a8b11ae4143a2dae72`, semantic SHA-256 `bd3e0e6b5331fe6f6028df65403ecf2446250ebb8f375961544de26cf0ffc3b6`.
- Implemented project-native PPO math, compound-action replay, forced classification, GAE, recurrent rollout slicing, finite-gradient gates, and restricted atomic training checkpoints at `68407689ccfb18236f14f78dd68360704f408682`.
- Hardened local correctness report generation with a complete dashboard envelope and exact clean-Git provenance at `cae42da47bc9f3491869e8afd0e1254061b9f585`.
- Promoted independent local correctness evidence and status at `5f50189cb76f9f2acd6787b7700e9bc55eb28f86`.
- Completed three candidate experiments: 512 choices at lr 0.005 rejected for multi-select 0.75; 1024 choices at lr 0.005 selected; 1024 choices at lr 0.01 rejected as the higher-gradient passing candidate.
- Completed all three declared seeds with trainable toy task scores 1.0, stateless control 0.5, recurrent margin 0.5, probability replay errors 0, initial ratio errors 0, zero-tolerance counters 0, and checkpoint restoration PASS.
- Generated authoritative clean-source report `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-v1.json`, 27,889 bytes, SHA-256 `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`.
- Independent review `ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-review-v1.json` passed candidate, seed, source/config hash, resource, checkpoint, and authorization recalculation.
- Final validation passed 144 focused G3 tests, 347 full Python tests, Ruff, dashboard rebuild with 111 records and zero quarantine, dashboard doctor, 7 frontend unit tests, production build, and 4 Playwright tests.
- Verified current local Git: `main` at `5f50189...`, clean before handoff files; locally known `origin/main` at `e2ce735...`; local main six commits ahead and zero behind the locally known remote ref; no push occurred.
- Created full master continuation prompt `.chatgpt/handoffs/KPTCG_G3A_CLOUD_PLAN_MASTER_PROMPT.local.md`, 48,639 bytes, SHA-256 `b6130942458d42ac79577259c20784ec3a953734112e79b850f47ac8de4eca3a`. 

## Decisions
- Use evidence-first, fail-closed development. Do not infer mutable facts from memory or narrative reports when repository or official evidence can verify them.
- Local correctness closes only `T-G3-PPO-001`; G3a remains blocked until an exact cloud plan is frozen, explicitly approved, executed, downloaded, and independently reviewed.
- Do not launch Kaggle, Colab, Modal, self-play, a submission, or a push automatically.
- Preserve recurrent PPO, public actor/critic, terminal +1/0/-1 reward, no shaping, no privileged critic, no behavior cloning, no replay action supervision, no inference search, compact under-2M model, exact-deck specialist, and zero policy-version lag unless separately approved.
- Future notebook workflow should use one maintained notebook and a small stable set of versioned input datasets/models; the user manually runs the notebook, and the assistant retrieves and reviews outputs through Kaggle MCP where supported.
- The missing-dashboard-envelope report attempt was invalid and not promoted; future evidence must have a dashboard envelope and exact clean-Git provenance from the start.

## Workflow
- First read `current.local.md`, the master prompt, this structured handoff, `AGENTS.md`, project status files, the G3a gate/tasks/configs/review, DEC-010, and handbook `07_PPO_LEAGUE.md`.
- Immediately verify Git status, log, branches, remotes, and ahead/behind state. Do not assume the locally known remote ref is current.
- Use `Local_mcp` with repo id `ptcg`; discover exact schemas through `api_tool.list_resources`.
- Inspect existing cloud-plan/notebook conventions before creating paths.
- Resolve the exact frozen budget interpretation from code/tests/decision evidence; if genuinely ambiguous, present the smallest decision proposal instead of guessing.
- Compare Kaggle CPU, Colab CPU, and viable alternatives using actual availability, core limits, internet-off behavior, checkpoint persistence, output retention/download, reproducibility, and measured runtime evidence.
- Add fail-closed plan/config/reviewer tests before implementation, then validate narrow tests, all G3 tests, full suite, Ruff, dashboard, frontend, and browser as applicable.
- Freeze and independently review the exact plan in a clean commit, then present it to the user and stop before launch.
- After future user-run notebook completion, inspect notebook status/output listings, download artifacts, verify hashes, independently recalculate the verdict, and update gates only after evidence passes.

## Constraints
- No meaningful PPO/self-play/league training or large evaluation locally.
- Local correctness boundary is CPU only, two PyTorch threads, one interop thread, zero workers, and at most 4096 choices per model unless a reviewed change remains a tiny correctness benchmark.
- G3a cloud plan must use all declared seeds `1197953491`, `20344180`, `1491619630`; exact 25,000-to-100,000 non-forced choices per seed; equal budgets within 0.0025; predeclared task allocation; at most four CPU cores; checkpoint cadence and resume proof; artifact destinations; and fail-closed stop conditions.
- Do not assume whether the budget applies in aggregate or per task/model. Resolve from repository evidence or ask the exact ambiguity.
- Zero tolerance for crashes, fallbacks, hidden-state cross-owner events, invalid actions, NaN/Inf, stale requests, timeouts, and unclassified truncations.
- Probability replay and initial ratio errors must be no greater than 1e-5 before the first update.
- Checkpoint must restore model, optimizer, scheduler/scaler, counters, league, rollout boundary, and all available RNG states with fixed tensor atol 1e-5 and rtol 0.
- Additional replay retrieval, action-supervision training, behavior cloning, Modal, deck freeze, submissions, external mutations, and Git push require separate approval.
- Private competition assets and raw evidence remain ignored/private and must not be committed or redistributed.
- Local handoff files are untracked local aids and should not be included in project commits.

## Next Steps
### 1. Verify repository and handoff state
- Goal: Confirm current HEAD, worktree, remote tracking, existing cloud-plan work, and all cited files/hashes.
- Done when: Git/tool outputs and file reads establish the exact starting state with discrepancies explicitly recorded.

### 2. Resolve cloud-budget semantics
- Goal: Determine from the frozen contract, implementation, tests, DEC-010, and handbook exactly how the per-seed budget and stateless control are counted.
- Done when: One evidence-supported interpretation is documented, or a narrowly scoped user decision proposal is produced if the repository remains ambiguous.

### 3. Compare execution platforms
- Goal: Evaluate private Kaggle CPU, private Colab CPU, and any viable alternative using current availability and artifact/checkpoint constraints.
- Done when: A retained comparison selects one platform with explicit rejection reasons and runtime sensitivity estimates.

### 4. Freeze exact G3a cloud plan
- Goal: Create a versioned, fail-closed plan/config/notebook/reviewer with exact seeds, budgets, allocation, cores, wall caps, checkpoint/resume, artifacts, and stop conditions.
- Done when: Plan tests, source tests, full validation, hashes, and independent clean-source review pass and a local commit is clean.

### 5. Request explicit launch approval
- Goal: Present the immutable plan and one narrow approve/reject question to the user.
- Done when: No notebook has been launched and the user has the exact plan, versions, run steps, runtime/cost estimate, kill procedure, and output-review process.

## Important Files
- .chatgpt/handoffs/KPTCG_G3A_CLOUD_PLAN_MASTER_PROMPT.local.md
- .chatgpt/handoffs/current.local.md
- AGENTS.md
- ptcg-rl/PROJECT_STATUS_ANALYSIS.md
- ptcg-rl/PROJECT_STATUS.md
- ptcg-rl/PROGRESS_REPORT.md
- ptcg-rl/reports/gates/g3a.json
- ptcg-rl/reports/tasks/current.json
- ptcg-rl/configs/g3a_evaluation_v1.json
- ptcg-rl/configs/g3a_local_correctness_v1.json
- ptcg-rl/src/ptcg_rl/g3/evaluation.py
- ptcg-rl/src/ptcg_rl/g3/ppo.py
- ptcg-rl/src/ptcg_rl/g3/checkpoint.py
- ptcg-rl/src/ptcg_rl/g3/toy.py
- ptcg-rl/src/ptcg_rl/g3/local_correctness.py
- ptcg-rl/scripts/g3a_local_correctness.py
- ptcg-rl/reports/artifacts/g3a-evaluation-contract-v1.json
- ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-v1.json
- ptcg-rl/reports/artifacts/g3a-ppo-local-correctness-review-v1.json
- ptcg-rl/tests/g3/
- ptcg-rl/docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md
- PTCG_RL_Codex_Handoff_v1.0/PTCG_RL_Codex_Handoff/docs/07_PPO_LEAGUE.md

## Risks
- The locally known `origin/main` may be stale; verify before any remote-state claim.
- The frozen per-seed budget wording may be ambiguous about aggregate versus per-task/model counting; do not choose by convenience.
- A cloud notebook can silently run on unexpected hardware or with different core/thread counts; fail closed on environment mismatch.
- Notebook UI completion does not prove all artifacts exist or are valid; list/download/hash outputs.
- Fresh isolated environments may omit model/dev dependency groups or ignored private assets; distinguish environment setup failures from project failures.
- Creating many Kaggle datasets/models/notebooks would make the workflow noisy; use version updates of a small stable asset set after verifying tool behavior.
- Local toy success can be mistakenly described as policy strength or G3a completion; preserve the non-claim boundary.

## Open Questions
- Does the frozen 25,000-to-100,000 per-seed budget apply to the aggregate across trainable tasks, to each task/model, or include the stateless control? Resolve from evidence first.
- Which current platform best supports at most four CPU cores, internet-off execution, durable checkpoints, manual user launch, and reliable output download?
- What exact checkpoint cadence and intentional interruption point provide a meaningful resume proof without excessive overhead?
- Should plan preparation update an existing private Kaggle input asset or create the first version of one stable G3a input asset? Verify current asset inventory and external-mutation authorization before acting.

## Startup Prompt
Använd GPT-Repo-MCP mot repo_id `ptcg`.
Läs `.chatgpt/handoffs/current.local.md` och sedan `.chatgpt/handoffs/2026-07-22-2053-kptcg-g3a-cloud-plan-evidence-first-continuation.local.md`.
Kör `repo_git_status`.
Fortsätt från handoffens "Next steps".
## Local Metadata
- Handoff: .chatgpt/handoffs/2026-07-22-2053-kptcg-g3a-cloud-plan-evidence-first-continuation.local.md
- Current pointer: .chatgpt/handoffs/current.local.md