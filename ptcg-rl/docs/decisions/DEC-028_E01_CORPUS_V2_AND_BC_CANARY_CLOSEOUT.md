# DEC-028 - Complete the Majkel corpus review and BC engineering canary

- Status: accepted with production corpus target floor still blocked
- Date: 2026-08-04

## Decision

Consume both exact one-time approvals. Accept the private Kaggle CPU review of the 269 named Majkel replay bodies and accept the bounded 64-step local-CPU BC engineering canary as non-promotable engineering evidence. Preserve the frozen 25,000-policy-target production floor. Do not start production BC from corpus v2 because it contains 23,460 valid policy-loss targets, a shortfall of 1,540.

## Results

- All 269 newly read Majkel files qualified; zero were rejected.
- Exactly 1,030,207,171 new bytes were read; the two prior probe bodies were reused without rereading.
- No replay body or agent log was exported.
- Corpus v2 contains 337 episodes, 25,058 teacher requests, 1,598 forced recurrent calls and 23,460 policy-loss targets.
- The 200-episode floor passes; the 25,000-target floor remains blocked by 1,540 targets.
- The BC canary consumed exactly 64 cumulative AdamW steps: 10 steps before a fail-closed forced-only-chunk scheduler error and 54 recovery steps after the scheduler was corrected to skip that zero-loss chunk.
- Loss and gradients remained finite; the step-32 checkpoint restored exactly. The checkpoint is permanently non-promotable and establishes no policy competence.

## Boundaries

Production label materialization, production training, further optimizer steps, additional replay reads, GPU/TPU use, model promotion, deck freeze, submission, Git commit and Git push remain unauthorized. The next admissible data action is an exact, separately approved supplemental replay review expected to add at least 1,540 valid policy-loss targets while preserving the frozen data and split contracts.
