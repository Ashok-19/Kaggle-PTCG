# DEC-027 - Freeze the pretraining configuration and Majkel primary source

Status: Accepted

Date: 2026-08-04

## Decision

Freeze the initial learned-policy configuration so training can begin immediately after the remaining exact approvals and data review complete.

### Primary teacher and initial training deck

- Primary teacher: `Majkel1337`
- Stable team ID: `16374395`
- Stable active submission ID: `55186239`
- Initial behavior-cloning deck: Mega Lucario ex
- Exact teacher deck multiset SHA-256: `dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278`
- Accepted observed source modules for body review: `1.32.2` and `1.32.3`, tracked separately

The latest refreshed leaderboard still places Majkel1337 first. Volatile score values are monitoring signals only; team, submission, dataset version, episode ID, declared bytes, body hash, deck hash, module and contract results are the frozen identities.

This locks Majkel as the **primary training teacher** and the reviewed Mega Lucario deck as the **initial BC training deck**. It does not declare the final submitted deck. Final D1 selection remains contingent on held-out, cross-deck and important-matchup evaluation.

### Model architecture

Freeze the existing G2 compact recurrent semantic policy for initial BC and the first bounded PPO stage:

- 970,022 trainable parameters
- architecture SHA-256 `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`
- public-information actor and critic
- entity attention, public-event and recurrent GRUs
- ragged semantic option scoring
- STOP-aware autoregressive compound-action decoder

No architecture change is permitted before a qualified ablation or a demonstrated blocker. This prevents architecture churn from delaying training.

### Data policy

Retain the immutable qualified multi-teacher corpus v1 as a diversity and anti-overfitting set:

- 66 qualified episodes
- 7,140 policy-loss targets
- 50 / 8 / 8 train / validation / test split
- 402 forced singleton requests retained for recurrence and excluded from policy loss

Prepare one exact private-Kaggle-CPU request covering the remaining 269 files in the 271-file Majkel August 3 version-1 intersection. Reuse the two already reviewed probe files rather than reading or exporting them again. The newly read replay-body cap is exactly `1,030,207,171` bytes. No replay body is exported from the notebook.

A Majkel episode qualifies for corpus v2 only when all of the following pass:

- exact team and submission binding;
- schema 1, CABT `1.0.0`, and module `1.32.2` or `1.32.3`;
- exact Mega Lucario deck hash `dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278`;
- current-card construction compatibility;
- complete terminal records and lag-aligned legal compound actions;
- no duplicate episode or content hash;
- forced singleton calls advance recurrence but create no policy loss.

All four seat/result strata remain eligible. Training sampling is Majkel-dominant while retaining at least 20% legacy qualified-teacher sampling. Majkel examples are sampled equally across the four seat/result strata as far as available. New qualified episodes receive deterministic episode-level 80/10/10 train/validation/test assignments stratified by module and seat/result using the frozen split seed `20260804`.

The data is called final only after the exact request is approved, all candidate bodies are reviewed, corpus v2 is emitted, and the resulting episode and target counts are known. No unsupported target-count projection is treated as a guarantee.

### Training and gold sequence

Freeze the execution sequence:

1. Run the existing exact 64-step BC engineering canary after its separate approval.
2. In parallel, execute the exact 269-file Majkel corpus review after its separate approval.
3. Freeze corpus v2 and prepare a production recurrent BC request from its exact hashes and counts.
4. Run held-out and on-policy competence evaluation before production checkpoint promotion.
5. Only after BC competence, permit bounded KL/auxiliary-BC recurrent PPO, capped at 500,000 choices before another decision.
6. Run equal-budget deck/checkpoint tournament evaluation and freeze the final submission deck only after D1 thresholds pass.

Gold remains the objective, not a guarantee. The strategy is finalized; stage-specific execution budgets remain exact-approval gated.

## Authorization boundary

This decision authorizes only repository planning, deterministic metadata processing, request generation, contract review and tests. It does not authorize:

- the private Kaggle CPU read of the 269 named replay bodies;
- corpus promotion or training-label materialization;
- the 64 BC optimizer steps;
- production BC, PPO, self-play or any model mutation;
- GPU, TPU, Modal or paid compute;
- model or dataset publication;
- deck freeze for submission;
- competition submission, Git commit or Git push.

## Revisit trigger

Revisit if Majkel's active submission identity changes, the pinned daily source changes, the exact deck or module/action contract fails at scale, corpus v2 cannot meet training needs, the BC canary fails, a qualified ablation is proposed, or any production training, accelerator, model promotion, final deck freeze or submission scope is requested.
