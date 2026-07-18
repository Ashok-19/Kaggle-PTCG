# Project Status Analysis

Last reviewed UTC: 2026-07-18

The previous G1 result is retained as historical evidence but is not an acceptance
certificate. Independent review found that its 50-game smoke did not enforce the
handbook's million-selection, 10,000-game, four-rule-agent, shipped-versus-built,
worker-restart, throughput, log-burst, or six-hour RSS requirements. The smoke
predicate also allowed failed or capped games to satisfy `PASS`, provenance was
copied from an expected-hash manifest instead of the loaded assets, and the action,
STOP-trace, fail-closed semantic, and recurrent-lifecycle boundaries were incomplete.

G1 is therefore reopened as **G1R / BLOCKED / NOT_REVIEWED**. G2, PPO, training,
deck promotion, and replay episode acquisition remain out of scope. The only allowed
parallel replay work is the capped R0 manifest-only probe while a long G1R acceptance
run is actually active.

The active checkout was verified at `7fee6493c2ea3f6181438265d141c879e464d2ab`
before G1R edits. The only pre-existing untracked user artifacts were the root
`AGENTS.md` and `PTCG.zip`; the ZIP remains untracked and must never be committed.

