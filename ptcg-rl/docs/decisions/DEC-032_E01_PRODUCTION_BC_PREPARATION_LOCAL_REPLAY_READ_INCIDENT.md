# DEC-032 - Fail closed on a local replay-byte verification during production BC preparation

- Status: failed closed; production BC preparation stopped
- Date: 2026-08-05

## Decision

Stop production recurrent BC request preparation. A metadata-planning helper incorrectly called `Path.read_bytes()` for all 66 retained flg/Dries replay files while recomputing their byte counts and SHA-256 values. Exact replay-body reads were not approved by the generic `proceed` instruction, so the preparation cannot continue as though it remained metadata-only.

## Exact observed scope

- Local existing replay files read: 66.
- Local existing replay bytes read: 383,801,622.
- Train: 50 files / 303,098,913 bytes.
- Validation: 8 files / 38,460,832 bytes.
- Test: 8 files / 42,241,877 bytes.
- The helper performed raw-byte hashing only; it did not parse replay JSON or inspect game content.
- Every recomputed byte count and SHA-256 matched the frozen corpus-v3 manifest.

## Preserved boundaries

No replay file was copied or exported. No daily Majkel replay body or agent log was read. No label, dataset staging tree, Kaggle dataset mutation, notebook launch, optimizer, optimizer step, training, model mutation, model promotion, submission, Git commit, or Git push occurred. Corpus v3 remains unchanged at 362 episodes and 25,056 policy-loss targets.

## Evidence

- Incident: `reports/incidents/e01-production-bc-preparation-local-replay-read-v1.json`
- Incident file SHA-256: `9df0a700478da719442f89687f7d372d6f3d1cd26561aaf92c03322747464536`
- Incident self-hash: `de139b89f032ef9d51fd57250d517c43cd7574dd5a318f9f5250755660ac8b26`
- Corpus-v3 manifest SHA-256: `c032694d3601d2570c8e2199c886e452af11f2d72b47379ad08761f16a6b3267`
- Corpus-v3 manifest self-hash: `bb6319e23f3d5b12bd9ed7383b0f3e007dd7059cbf39afcd5325af12392c35a9`

## Next boundary

Any further replay-body read or transfer requires a new exact approval. A later metadata-only publication request must be generated exclusively from the frozen corpus-v3 manifest without rereading replay bodies.
