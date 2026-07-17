# 10 — Calendar and Review Gates

Assumed competition close: 2026-08-16. Immediately confirm the exact Kaggle hour/timezone and move all final cutoffs earlier if needed.

## Calendar

| Dates | Phase | Deliverable/review gate |
|---|---|---|
| Jul 17–18 | G0 inventory/setup | Private repo, hashes, license boundary, platform locks, doctor |
| Jul 18–21 | G1 engine contract | lifecycle/resolver, 1M legal selections, tournaments, benchmark/soak begun |
| Jul 18–23 | R0→R1 replay pipeline (parallel) | provider probe, filtered seven-day sync, parser, 3/7-day snapshot plus 14-day stability only with extension coverage |
| Jul 21–24 | G2 model/action | tensor schemas, <2M recurrent model, complete semantic action coverage |
| Jul 24–26 | G3a/G3b PPO proof | 100k-choice correctness smoke, then bounded 1–5M-choice competence run |
| Jul 23–30 | D1 deck funnel (overlapping) | replay shortlist, optional simulator screen, predeclared RL successive halving; exact deck freeze by Jul 30 |
| Jul 30–31 | G4 Modal canary | image, cost/throughput benchmark, bounded-chunk restart proof, main-run approval |
| Jul 31–Aug 9 | G5 main league | champion PPO, frozen league/PFSP, periodic promotion evaluation |
| **Aug 9** | **Architecture freeze (T−7)** | no new model/action/algorithm architecture |
| Aug 9–12 | G6 hard-matchup work | exploiters, controlled continuation, final challenger selection |
| **Aug 12** | **Training code/config freeze (T−4)** | only already-defined continuation/evaluation; no new training logic |
| Aug 13 | Final tournament | anchor/challenger matrix, latency/memory/reliability report |
| **Aug 14** | **Packaging freeze (T−2)** | build final ZIPs, offline clean-room validation |
| Aug 15–16 | Ladder/contingency | safe anchor active; only emergency correctness/package fixes |

Replay index/meta refresh continues daily, but post-freeze meta changes inform ladder choice and diagnosis—not unvalidated architecture churn.

## Critical path

```text
G0 setup → G1 engine correctness → G2 action/model → G3 PPO proof
                                              ↘
R1 replay/meta → deck funnel/screening → D1 equal-budget bakeoff
                                              ↓
G4 Modal canary → G5 main league → G6 final package
```

The engine and replay workstreams can overlap once the repository exists. D1 needs both a reliable simulator and a working small PPO. Main Modal training needs all prior gates.

## Daily operating rhythm for a solo project

The user’s 2–3 active hours should be spent on:

1. inspect previous automated run/report;
2. resolve one highest-impact blocker or approve one gate;
3. launch one bounded, resumable next job;
4. update status/decision log;
5. ensure overnight job has a cap, checkpoint and stop condition.

Automation handles replay index checks, tournaments, checkpointing and bounded training. Never require the user to babysit unbounded notebooks.

## Review points

Return a progress report after:

- G0 environment/asset setup;
- G1 engine/action correctness and benchmark;
- R1 first real filtered replay sync/meta report;
- G2 model/action schema benchmark;
- G3 first learning run;
- each deck bakeoff round and D1 selection;
- G4 Modal cost/scale canary;
- every candidate champion promotion;
- any failed main run or surprising ladder result;
- architecture/code/package freezes;
- final submission validation.

## Schedule recovery rules

If behind schedule:

1. preserve engine/action correctness and packaging;
2. reduce candidate decks and ablations through successive halving;
3. keep one PPO implementation and one main model size;
4. reduce search/exploiter breadth before reducing final validation;
5. submit the last validated anchor rather than a stronger untested checkpoint.

Do not recover time by skipping replay byte caps, correctness gates, checkpointing, held-out evaluation or submission soak.
