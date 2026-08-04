# Current Handoff

- Title: KPTCG gold-path audit decision evidence-first continuation
- Master prompt: `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
- Structured handoff: `.chatgpt/handoffs/2026-07-24-1034-kptcg-gold-path-audit-decision-evidence-first-continuation.local.md`
- Repository id: `ptcg`
- Branch: `main`
- Head at handoff: `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`
- Locally known origin/main: `e561fdea3202c643c724b1132a575c369da71c8a`
- Tracked files at handoff: unchanged
- Git status caveat: four user-provided `audit-reports/` files are untracked; preserve them and do not stage/commit without deliberate approval
- Current next milestone: create the reviewed superseding strategy decision, then freeze E01-A/E01-B/E04/E08 work orders; no meaningful training or external launch.

## Startup Prompt

Use `Local_mcp` with repository id `ptcg`.

Read completely, in order:

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`
3. `.chatgpt/handoffs/2026-07-24-1034-kptcg-gold-path-audit-decision-evidence-first-continuation.local.md`
4. `AGENTS.md`
5. `01_MASTER_PLAN.md`
6. project status/task/gate files
7. all four files under `audit-reports/`.

Then verify Git status/log/branch/remotes/ahead-behind and refresh every mutable official/Kaggle fact before acting. Treat repository evidence and verified tool output as the source of truth. Do not revert to the obsolete PPO-first startup plan, silently edit the historical G3b config, or launch training/external jobs.
