# KPTCG Working Rules

These are the current user-specific operating rules for the KPTCG project. Read together with `AGENTS.md`; when this file gives a more recent workflow preference, follow this file unless it conflicts with a higher-priority safety/legal requirement.

## Evidence first

- Treat repository code, generated reports, actual model/game results, and fresh tool output as source of truth.
- Do not work from assumptions, stale leaderboard values, guessed Modal state, or remembered file names when they can be verified cheaply.
- Distinguish dynamic facts from historical facts. Re-check dynamic Kaggle/Modal/Git state when it affects an action.
- Do not repeatedly re-prove stable facts without a concrete reason.

## No routine SHA/checksum gates

- Do **not** spend time recomputing SHA-256/checksums as a routine startup, preflight, or promotion gate.
- Existing hashes in historical reports/handoffs may be kept as provenance/reference, but they are not a required verification ceremony.
- Prefer behavioral/model-load/config/path/tests and actual game outcomes.
- Use checksum verification only when the user explicitly asks for it or when there is a specific artifact-integrity ambiguity that cannot be resolved more directly.

## Code style and implementation

- Write concise, maintainable code.
- Reuse existing helpers/modules rather than cloning large scripts.
- Prefer small focused changes over giant framework rewrites.
- Avoid duplicated configuration, duplicated model construction, and unnecessary abstraction layers.
- Remove new dead code created by the current change, but do not mass-clean historical scratch/evidence without review.
- Add focused tests for real behavior/bugs; do not add ceremonial tests that cannot change a decision.

## Git

- Commit every incremental **tracked code/config change** after focused validation.
- Review exact intended paths before committing.
- Never mass-add unrelated `.cache`, scratch, raw data, checkpoints, credentials, or generated submissions.
- Preserve unrelated user changes.
- Do not claim push/sync state without checking when it matters.

## Compute

- Local RTX 3050 Laptop GPU has only 4 GiB VRAM. Use it for development, smoke tests, local native evaluation, and small benchmarks.
- Use Modal for meaningful large self-play/RL/evaluation runs.
- The intended production RL GPU is RTX PRO 6000-class, but do not allocate it before a measured preflight/plan.
- CPU-only acquisition/materialization/cache work should remain CPU-only.
- Stop every Modal app after its job completes and verify 0 tasks.
- Long Modal jobs must use durable server-side execution/checkpointing; do not tie them to a fragile local CLI lifetime.
- Do not create automations/schedules unless the user explicitly asks.

## RL transition

- Pure BC is considered complete as the primary optimization method unless new evidence establishes a specific prerequisite.
- The user chose the **v7 final checkpoint** as the RL initializer because it contains newer final-day policy knowledge.
- Do not switch back to v5 automatically even though v5 had a slightly better fixed native BC result.
- At the beginning of a new session, **do not code or launch RL immediately**.
- First read the active handoff, inspect the existing PPO/self-play/GPU-native implementation, and produce a clear detailed RL training plan.
- Only implement/launch after that plan is complete and the user says to proceed.

## RL quality gates

- Main objective is game-winning performance, not replay NLL.
- Terminal game reward is authoritative: win +1, draw 0, loss -1.
- Keep BC/expert/KL anchoring only as anti-forgetting/stability support, not as the primary objective.
- Do not use only symmetric self-play; plan an opponent league with frozen policies/baselines/historical checkpoints.
- Current first strict regression gate is **64/64** on the fixed four-opponent native suite with zero invalid/fallback/failure/nonterminal games.
- After 64/64, confirm on larger/randomized seeds and stronger opponents; do not overfit the fixed 64 games.
- Select checkpoints by actual frozen-suite/league game strength and reliability, not final training step or BC NLL.
- Scale progressively. Do not jump blindly to 1B samples. Measure end-to-end throughput first and increase budget only while strength is improving.

## Kaggle

- Kaggle simulation agent source is executed through raw `exec`; do not rely on `__file__`.
- Reuse the proven minimal v5/v6 neural submission layout.
- Kaggle competition inference is CPU-only; keep runtime dependency closure minimal.
- Never use benchmark-task creation tools unless the user explicitly asks to create a benchmark task.
- Treat leaderboard/submission scores as dynamic and re-query them before making decisions.

## Modal/Kaggle accounts

- Current Modal profile is `ashokraja863801` unless a fresh check proves otherwise.
- Historical profile `ashok-19` contains old history and must not be confused with the current training workspace.
- Current volume is `kptcg-training`.
- Existing `kaggle-credentials` Modal secret may be used without printing its values.

## Codex

- If Codex is used for code generation, use only `gpt-5.6-luna-xhigh`.

## Preserve evidence

- Keep useful `.cache` diagnostics, evaluation JSON, migration reports, and scratch probes unless they are proven unnecessary.
- Do not delete files merely to make the repo look cleaner.
- The active handoffs are local continuation files; archived handoffs under `.chatgpt/handoffs/archive/` are historical and should not drive current decisions.
