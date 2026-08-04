# DEC-015 — Prepare the smallest same-submission E01 consistency probe

Status: Accepted  
Date: 2026-07-24  
Scope: E01 public replay provenance and policy/deck consistency only

## Decision

Supersede only the next E01 replay-probe scope after DEC-014. Preserve every
accepted engineering result and every authorization boundary. Prepare one exact,
non-authorizing request for the smallest additional July 23 replay belonging to
the already probed Benarg submission `54933084`.

The selected additional file is exactly:

- dataset: `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-23`, version `1`;
- episode: `87741212`;
- filename: `87741212.json`;
- declared bytes: `559779`;
- Benarg player index: `1`;
- Benarg terminal reward: `-1`.

The existing probe episode `87703034` has Benarg at player index `0` with reward
`1`. The selected additional candidate therefore provides opposite seat and
opposite terminal-result coverage for the same exact submission while adding the
fewest bytes among the 111 other same-submission episodes present in the pinned
dataset.

## Evidence

The completed one-file provenance probe is independently accepted as
`ACCEPT_PROVENANCE_ONLY_E01_SCREENING_BLOCKED`:

- consumed request:
  `configs/e01_provenance_probe_request_v2.json`, SHA-256
  `b9e27cd30f4ebd8f3db767c3da5708b3330a5052f651b5f666420e02815ce34b`;
- downloaded replay: `87703034.json`, exactly `3641302` bytes, SHA-256
  `58089ab3824ac703dddb5d1364718684d4770d3ebf853ea198ca00efdc6a43db`;
- independent probe review:
  `reports/artifacts/e01-provenance-probe-review-v1.json`, file SHA-256
  `94c8d1e90400f9fb950f1950e1a3ef37b66fca3a81767c0ab502affa5e58d92c`,
  self-hash
  `f09117848e457b836c020c7c8112519d24daf392a74f14ba4c26a81b1618fec7`;
- review script SHA-256:
  `6161b820c330ecfe756cd6c31bf91c7a2cf15b3c6cad8080892fdc1ee26dd7ee`.

That review proves:

- one and only one replay body was transferred;
- both exact 60-card deck multiset hashes were recovered;
- both decks pass construction checks against current frozen card data;
- 128 active selection requests and their lagged actions pass the existing
  fail-closed action-alignment contract;
- zero agent logs, raw-step exports, action-sequence exports, observation exports,
  training labels or optimizer steps were produced.

It does not prove exact historical deck legality because replay module version
`1.32.2` has no accepted exact engine/card-asset mapping. It also does not prove
teacher strength, policy identity or cross-episode policy consistency.

The read-only same-submission candidate evidence is:

- `reports/artifacts/raw/e01-benarg-consistency-candidate-metadata-v1.json`;
- file SHA-256
  `971e4f2b9323aa17bfa98e6b6a16f17a99d4e4b17af2acbae1b7dd02d69ff577`;
- 252 public episodes for submission `54933084`;
- 112 present in the pinned daily dataset, including the completed probe;
- 111 other candidates;
- `87741212.json` is the smallest at exactly `559779` bytes.

No replay body or agent log was used to choose the additional candidate.

## Permitted next request

A request may be prepared for exactly one additional replay file,
`87741212.json`, under these boundaries:

- no overwrite;
- no agent logs;
- no third replay;
- no raw replay-body export;
- no action-sequence or observation export;
- no training-label export;
- no optimizer step, training, notebook, accelerator, external compute or
  submission;
- stop after comparing the Benarg deck hash, replay schema and aggregate
  action-alignment evidence against episode `87703034`.

## Authorization

This decision does **not** authorize downloading `87741212.json` or any other
file. The exact request must remain `authorized: false` until the user separately
approves that named request after reviewing its path, byte cap and boundaries.

## Qualification state

- DEC-014 provenance probe: `PASS`;
- exact deck hashes available: `PASS`;
- current-asset construction compatibility: `PASS`;
- action-aligned supervision availability: `PASS`;
- exact historical deck legality: `UNPROVEN`;
- teacher strength: `UNPROVEN`;
- same-submission deck consistency: `UNPROVEN`;
- same-submission policy consistency: `UNPROVEN`;
- E01 screening gate: `BLOCKED`;
- training: `NOT_AUTHORIZED`.
