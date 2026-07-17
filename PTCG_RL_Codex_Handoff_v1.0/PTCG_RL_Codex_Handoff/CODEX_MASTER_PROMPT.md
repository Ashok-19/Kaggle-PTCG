# Master Prompt for the Local Codex Agent

Copy the text below into the local Codex session and attach or point it to this full handoff bundle.

---

You are the implementation agent for a greenfield Kaggle Pokémon TCG AI Battle project targeting a top-20/gold finish by 2026-08-16. Read every file in this handoff bundle before editing. Treat `docs/00_DECISION_RECORD.md` as the governing decision record and `docs/01_MASTER_PLAN.md` as the gate sequence.

The user has local copies of `PTCG.zip`, `sample-agents.zip`, the current official competition package/dataset, and possibly replay files. Ask for missing absolute paths, the exact configured Kaggle MCP interface, and official runtime/deadline facts that cannot be inspected. Also stop for genuinely blocking authorization or choices involving credentials, paid cloud use, license-sensitive asset transfer, destructive operations, or a material cost/scope change. Do not assume archive layout or package version; inventory and hash them.

Operating requirements:

1. Work in a new private Git repository. Never push, submit, spend meaningful cloud budget or mutate external services unless explicitly asked.
2. Do not commit or redistribute competition-only engine code/binaries, card datasets, secrets, downloaded replays, checkpoints or large run artifacts. Read and preserve the engine license. Add asset paths to `.gitignore` before copying anything.
3. Implement one gate at a time. Start at G0. Do not launch main training or broad replay downloads. Stop after each gate, update `PROJECT_STATUS.md`, and produce `PROGRESS_REPORT.md` with raw evidence for review.
4. Use RL reward for strategic policy learning. Public replay actions must not become action labels, PPO transitions or value targets in v0. Replays are allowed for meta/deck discovery, coverage, debugging and evaluation design.
5. Never download an entire daily replay dataset. First fetch the small official index, then the selected daily `manifest.csv`, apply a user-approved filter with `--dry-run`, enforce byte/file caps, and download individual episode files. Keep Kaggle MCP, KaggleHub and CLI details behind the provider protocol. If the daily manifest schema or MCP method is unknown, stop R0 and ask; never invent it.
6. Treat the engine as one battle per process. Check terminal result before selection, retrieve consumptive logs exactly once, preserve ordered multi-select semantics, keep separate recurrent state per player, and reset at initial deck request. Dispatch by selection/option types and factual fields; `selectContext` is only a feature, not control flow.
7. Score all legal options semantically. Do not copy the sample notebook’s first-64 combination behavior. Multi-select is internal ordered, unique, without-replacement autoregression with STOP only when legal.
8. v0 is a <2M PyTorch Entity-Transformer-GRU recurrent PPO specialist with public critic and terminal `+1/0/-1` reward. No BC, shaping, inference search, privileged critic or universal multi-deck policy in v0.
9. The sample Mega Abomasnow deck may be used only as an engineering baseline. Select the main exact deck through the documented replay/simulator/equal-budget RL bakeoff. Use the constrained objective—reliability and matchup eligibility first, meta-weighted expected match score `(wins + 0.5 × draws) / games` second—not a blended score.
10. Colab/Kaggle are for smoke and validation. Modal is for the main run only after G4. Every cloud job must have a cost/time cap, durable checkpoints, a resume test and a kill command.
11. Preserve user changes, use non-destructive commands, make small commits, run targeted tests after every edit, and report exact commands. If evidence contradicts the plan, surface it and propose a controlled change rather than silently changing scope.

Initial execution:

- Restate G0’s concrete deliverables.
- Inspect Git/worktree and the supplied archives read-only.
- Create the repository skeleton from `docs/02_REPOSITORY_ENVIRONMENT.md` and copy `templates/AGENTS.md` to repository root as `AGENTS.md`.
- Create `PROJECT_STATUS.md` from its template.
- Implement only G0: asset bootstrap, environment locks, doctor command, `.gitignore`, basic CLI/test discovery and provenance output.
- Run the G0 acceptance commands on the user’s Ubuntu 22 machine.
- Stop and return the completed progress report, including unresolved facts and exact next gate. Do not start G1 until review.

When the user later authorizes the next gate, read the relevant document again before implementation and update the plan/status accordingly.

---
