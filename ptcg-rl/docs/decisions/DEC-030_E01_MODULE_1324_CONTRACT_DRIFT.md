# DEC-030 - Stop corpus supplement on module 1.32.4 contract drift

- Status: accepted fail-closed stop; compatibility probe prepared but unauthorized
- Date: 2026-08-05

## Decision

Treat the exact DEC-029 supplemental authorization as consumed after one approved replay-body read. Saved version 1 failed before any replay-body read because the temporary runner import path was incomplete. Saved version 2 verified the frozen dataset inventory and manifest, read only review-order-1 file `90037133.json` (4882237 bytes), observed module `1.32.4`, and stopped before action/deck qualification because the approved module set was `1.32.2` and `1.32.3`.

Corpus v2 remains unchanged at 337 episodes and 23,460 policy-loss targets. No corpus-v3 file, replay-body export, agent log, training label, optimizer step, model mutation, promotion, submission, commit or push was produced.

## Next boundary

Prepare exactly one unauthorized compatibility probe for `90037133.json`. It may re-read only that body on private Kaggle CPU to evaluate module `1.32.4` against the existing Mega Lucario deck and full action contract. It must not promote any corpus record or continue the 48-file supplement. A new explicit approval binding the probe request SHA-256 is required.
