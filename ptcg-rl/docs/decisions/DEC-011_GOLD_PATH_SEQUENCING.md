# DEC-011: Supersede PPO-First Sequencing with the Evidence-Gated Gold Path

Date: 2026-07-24  
Status: Accepted

## Decision

Preserve every accepted G1R, G2, R1 and G3a engineering result, but supersede the
old G3b PPO-first execution sequence. The active strategy is now:

```text
Mega Lucario provisional specialist
→ exact deck/teacher/replay qualification
→ full-compound-action recurrent behavior cloning
→ on-policy and held-out competence evaluation
→ bounded KL/auxiliary-BC recurrent PPO
→ at most 500k choices before another decision
→ frozen tournament and submission selection
```

The unchanged deterministic Mega Lucario rule policy remains a continuously
shippable hedge. It is a baseline and rollback candidate, not a declaration of
the final submitted deck.

## Scope of supersession

This decision supersedes only the sequencing and launch recommendations that
placed 1M/5M scratch PPO competence runs before exact-deck teacher qualification
and real CABT bridge qualification. It does not rewrite, delete or invalidate:

- DEC-009 or DEC-010;
- G1R, G2, R1, G3a or G3b evidence already produced;
- `configs/g3b_competence_plan_v1.json`;
- `reports/artifacts/g3b-competence-plan-v1.json`;
- `reports/artifacts/g3b-competence-plan-review-v1.json`;
- any negative TPU, throughput, reliability or leaderboard evidence.

Those files remain immutable historical evidence of the state and assumptions
under which they were created.

## Frozen immediate work orders

`configs/gold_path_work_orders_v1.json` is the machine-readable contract for:

1. **E01-A** — public teacher/replay qualification and a zero-transfer,
   version-pinned acquisition dry run;
2. **E01-B** — controlled local rule-teacher qualification using an exact deck,
   exact source hashes and the official local simulator;
3. **E04** — a zero-optimizer-step CABT actor/learner and on-policy evaluation
   bridge, progressing from a single-process trace to 10 games and then 100
   games with at least 10,000 meaningful decisions;
4. **E08** — byte-frozen deterministic Mega Lucario hedge and perturbation
   controls.

## Preserved technical boundaries

- actor and critic consume public information only;
- reward is terminal win/draw/loss only;
- compound actions are ordered, without replacement, with first-class STOP;
- forced calls advance recurrence and create no policy-loss node;
- learner policy-version lag is zero;
- no search by default;
- no reward shaping;
- no broad offline Q-learning;
- the 970,022-parameter architecture remains unchanged until a qualified
  ablation authorizes a change;
- invalid actions, fallback, stale/duplicate/out-of-order requests, nonfinite
  values, terminal errors, probability replay mismatch, recurrent ownership
  crossing and resume mismatch have zero tolerance.

## Authorization boundary

This decision authorizes repository implementation, deterministic review,
unit tests and read-only public manifest inspection. It does **not** authorize:

- transfer of any named replay body;
- behavior-cloning or PPO optimizer steps;
- meaningful self-play or league training;
- a Kaggle notebook, TPU run, Modal job or paid compute;
- a competition submission;
- staging, committing or pushing the four user-provided `audit-reports/` files.

Every external transfer or compute action requires a separate, smallest-possible
approval naming the exact source, version, budget and expected outputs.

## Evidence frozen for this decision

- `audit-reports/KPTCG_GOLD_AUDIT_REPORT.md` —
  `f6481bec4d351b718ff362f5a2fab4b20888cf5ea2745af50642e8d444aed112`
- `audit-reports/KPTCG_GOLD_AUDIT_DECISIONS.json` —
  `2152bbb44f029489143af43328af772c265759b54adc5ed56c45a543f0401691`
- `audit-reports/KPTCG_EXPERIMENT_BACKLOG.csv` —
  `21735dab7122f72b3c2589efc650e3de753d92faffb60af3295a0820352b2dc4`
- `audit-reports/KPTCG_RESEARCH_LOG.csv` —
  `26822019a76e3b914451b1390133ca0b09964b6c5185ca79f2e8fe4f7cac67ce`
- historical G3b plan config —
  `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26`
- historical G3b plan artifact —
  `f64c6a4e0d122ce219c19ed06db5f4d8c98289e7b454af1c98b9d9130419b006`
- historical G3b independent review —
  `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`

## Consequence

E01 and E04 are the next decision-critical gates. No learned policy is promoted
from offline action accuracy, random-agent wins, mirror results, toy PPO,
throughput evidence or a short leaderboard movement. A later decision may
permit a bounded BC run only after E01 qualification, and may permit a bounded
KL/auxiliary-BC PPO run only after both competence and E04 qualification pass.
