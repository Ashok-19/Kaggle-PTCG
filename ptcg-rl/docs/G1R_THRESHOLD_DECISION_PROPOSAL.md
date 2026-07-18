# G1R Threshold Decision Proposal

Date: 2026-07-18
Decision required before qualifying long acceptance runs: yes

The handbook fixes the million-operation, 10,000-game, 70%-throughput, log-burst,
worker-restart, and six-hour-soak requirements, but does not fix the following
acceptance thresholds.

| Item | Recommended preregistration | Sensitivity |
|---|---|---|
| Matchup/player-slot cells | Six baselines by six ordered opponent/seat cells; 280 games per cell, 10,080 total | 278 gives 10,008 but leaves less margin for classified exclusions; 300 costs about 7% more |
| Shipped/built comparison | 1,000 games per library; exact invariant/type-set equality; KS <= 0.10 and mean difference <= max(10%, 2 pooled standard errors) | KS 0.05 is stricter and more entropy-sensitive; 0.15 is weaker than useful regression detection |
| RSS sampling | Every 60 seconds; exclude first 30 minutes | 30-second samples add noise/storage; 5-minute samples weaken transient evidence |
| RSS leak verdict | Theil-Sen slope with deterministic bootstrap 95% CI; upper CI <= 1 MiB/hour/worker | 0.5 MiB/hour is stricter; 2 MiB/hour could hide about 48 MiB/day/worker |
| RSS peak | <= 2 GiB per worker | 1 GiB may reject stable engine behavior; 4 GiB weakens eight-worker local safety |

Forced actual-first/actual-second experiments are diagnostics and are never pooled
with natural-deployment results. Engine entropy means exact trajectory equality and
paired-seed claims are prohibited.

