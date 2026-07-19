# G1R Remediation And Acceptance Report

## Outcome And Recommendation

**Outcome: SUCCEEDED / PASS.** Close G1R. The repaired contract and every original
acceptance criterion passed an independent raw-artifact recalculation. Recommend G2
deck/replay-meta implementation with parallel R1, but do not begin either in this work order.

## Repository State

- Active repository: `Ashok-19/Kaggle-PTCG` only.
- Acceptance source commit: `c2540459428cfe99b2c587ab3a361abfacfd2db7`.
- Acceptance source hash: `5a98d55f542d0bfafd333a94ba146b292691bfd1c6a907c21a4da167cd8ac6f8`.
- Worktree during qualifying runs: dirty only because of the pre-existing untracked
  root `PTCG.zip`; the manifest records its dirty digest.
- Local implementation commits: `656b30af8d78b80aa8abe7e8d1adb68413269f6b` and
  `c2540459428cfe99b2c587ab3a361abfacfd2db7`.
- External mutations, pushes, submissions, paid jobs, and training: none.
- Cost: USD `0`.

## Governing Criteria

| Criterion | Result | Retained evidence |
|---|---|---|
| Lifecycle, action, semantic, recurrent, failure, and provenance regressions | SUCCEEDED | latest `g1r-verification-*` manifest; 58 tests |
| 1,000,000 valid legal-selection operations | SUCCEEDED | `g1r-contract-acceptance-20260718T125639.823874Z-ff31e3be7e05` |
| Malformed cases counted separately | SUCCEEDED | 4 rejected forgeries, excluded from the million |
| Log burst larger than 200 | SUCCEEDED | 257 ordered events, zero loss/truncation |
| Worker death/replacement and recurrent isolation | SUCCEEDED | forced exit 23, replacement ready, lifecycle tests |
| Four exact native rule-agent/deck integrations | SUCCEEDED | 25/25 integration games, zero invalid/failure/fallback/post-terminal events |
| Ubuntu 22.04 source build/load | SUCCEEDED | unmodified July 17 source compiled and loaded; built library hash below |
| Shipped-versus-built qualifying comparison | SUCCEEDED | 1,000 games/library; ABI, type sets, distributions, and zero-error checks passed |
| Balanced random/rule arena | SUCCEEDED | 10,080/10,080 games, 36 ordered cells at 280 each, all error counters zero |
| 1/2/4/8 throughput matrix | SUCCEEDED | 2,400/2,400 games across 12 points, zero failures, retained profile |
| Six-hour RSS soak | SUCCEEDED | 21,600 active seconds, 1,693,121 games, zero unexpected failures, leak thresholds passed |
| Independent artifact verdict | PASS | sealed raw evidence recomputed by `review/g1r_acceptance_review.py` |

## Contract Repair

- Contract version: `2`.
- Observation schema: `15ae066097c4b0bf29cee0de46f1c8bec11c9b0269eb1103013230fb0570bf72`.
- Action schema: `711964b2e52f70dc6bada8ea1f263957aca58ec05e482ebc3cb10642b76a4b3b`.
- Trajectory schema: `d404dce955e2f9214e0b6958121c2e5b2bd9a01c7d8efe8aba027e11bf176224`.
- Terminal detection now precedes all selection-local parsing.
- Unknown enums, required-field omissions, impossible positions, and unresolved
  physical references fail closed with bounded diagnostics.
- Every action is revalidated immediately before native dispatch.
- STOP is a decoded token with mask, state, probability, log probability, and exact
  joint-log-probability replay.
- Recurrent ownership is `(episode_uuid, player, policy_id)` with monotonic request
  identity, idempotent duplicates, stale rejection, and lifecycle resets.
- Submission fallback is deterministic and counted; promotable runs require zero use.

## Assets And Baselines

- Official archive: `09ad210b15476f5064c1509addb32a459c777d92d4e4e7db470f9d0c039c3282`.
- Loaded shipped `libcg.so`: `feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887`.
- Locally built unmodified `libcg.so`: `06be5a891f05f2020d17c7759620614b6c4df7819bfe9d7da8fb96e9440c6077`.
- Loaded English card data: `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`.
- Exact private decks: Dragapult `30c8c7365c75f38fd6e7e1d8543c42ce7055ed6fd1c6e9eb244e44484b78e724`,
  Iono `e36d46c5bcafdef8a5d0e6caeb34dd8db09119c62d8fb67c99e89e7eed39f974`,
  Mega Abomasnow `7af2d7e111c084da535b89758730b3fd6cbb7c0543a9444499c5b61efdc8aecd`,
  Mega Lucario `406e2e9bd6ae82b8008b16ee64ffcbb58e4a50cd6bc36e33ae655456c6b9afee`.
- The four downloads contained 1,153 bytes total and exactly four `deck.csv` files.
  No dataset archive or unrelated source was downloaded.

## Bounded Results

- Qualifying arena: 10,080/10,080 games across 36 ordered policy-slot cells at 280
  games each; 1,075,936 engine requests; player 0/1 realized first-player counts
  7,518/2,562; zero invalid, failure, fallback, timeout, or post-terminal events.
- Arena aggregate: 19.85 games/s, 2,117.78 choices/s; action latency p50/p95/p99
  `0.579/1.013/2.338 ms`; peak RSS 149.32 MiB.
- Valid-operation corpus: 1,000,000 operations across 935 structural cases in
  63.74 seconds; all 11 selection and 17 option enums covered synthetically.
- Final-source engine comparison: 1,000 games/library; request-count KS `0.034`
  against `0.10`; mean delta `2.19` against allowed `4.5514`; ABI, observed selection
  and option sets, and error-counter checks all passed.
- Throughput benchmark: 2,400/2,400 games, zero failures. Raw/encoded/rule choices/s
  were worker 1 `404.12/325.86/451.54`, worker 2 `826.60/669.13/859.44`, worker 4
  `1638.68/1062.35/1600.66`, and worker 8 `1976.12/1827.82/2545.20`.
- Benchmark p99 action latency stayed at or below `0.307 ms` raw, `0.207 ms` encoded,
  and `2.188 ms` rule-policy. Profile SHA-256 is
  `79dcda2d169495c590d76b1f190fa14bd17a1507c59b7a8c61c2fb7ab99cf4dc`.
- RSS soak: exactly 21,600 active seconds and 1,693,121 complete games; zero invalid,
  failure, fallback, post-terminal, or unexpected worker-death events; one forced death
  and replacement; peak RSS 43.51 MiB against 2 GiB/worker.
- Four eligible worker slope estimates were `-0.0851`, `0.0435`, `0.0993`, and
  `0.0018 MiB/hour`; worst 95% upper bound was `0.1627`, below `1.0 MiB/hour`.
- Acceptance elapsed about 6 hours 59 minutes including the intentional interruption;
  qualifying soak active time was exactly six hours. Independent final-source comparison,
  raw review, and final verification added about two minutes. Local cost remained USD `0`.
- Config hashes: arena
  `11ce92f1890beca4446642ee3abdbb6977a115807d909a5b10a7996ab2541106`, benchmark
  `08c247693e761af3272d7ee26f7e28a223d865317d06436819cf232b773d444b`, soak
  `6597408501b400cf0abc73f6decaf1cdc372a9d7224a3616fc7f0239c25b21be`, comparison
  `bfad694243d3ebdc3944e289ddee530d3ea962210a7ffcee60fcc3995a57c672`.

Qualifying benchmark values (exact floats remain in the sealed manifest):

| Workers | Mode | Games/s | Choices/s | p50 ms | p95 ms | p99 ms |
|---:|---|---:|---:|---:|---:|---:|
| 1 | raw-engine | 10.292 | 404.116 | 0.129414 | 0.178721 | 0.210219 |
| 1 | encoded-observation | 7.387 | 325.861 | 0.045745 | 0.088976 | 0.140239 |
| 1 | rule-policy | 2.841 | 451.542 | 0.443066 | 0.653006 | 1.266691 |
| 2 | raw-engine | 21.484 | 826.604 | 0.127528 | 0.175508 | 0.206936 |
| 2 | encoded-observation | 15.365 | 669.133 | 0.043231 | 0.077173 | 0.117192 |
| 2 | rule-policy | 5.690 | 859.442 | 0.450609 | 0.686180 | 1.288132 |
| 4 | raw-engine | 36.419 | 1638.684 | 0.131858 | 0.184029 | 0.214968 |
| 4 | encoded-observation | 27.264 | 1062.351 | 0.055803 | 0.100849 | 0.157280 |
| 4 | rule-policy | 10.073 | 1600.657 | 0.496145 | 0.754484 | 1.510016 |
| 8 | raw-engine | 47.474 | 1976.115 | 0.145617 | 0.235222 | 0.307436 |
| 8 | encoded-observation | 41.956 | 1827.818 | 0.072844 | 0.121033 | 0.207077 |
| 8 | rule-policy | 16.741 | 2545.203 | 0.578137 | 0.961630 | 2.188235 |

## R0 Disposition

- Index manifests transferred: `0` files, `0` bytes.
- Daily manifests transferred: `0` files, `0` bytes.
- Episode JSON transferred: `0` files, `0` bytes.
- One read-only Kaggle metadata query confirmed index dataset version 32; the user then
  explicitly paused all work until the acceptance run finished. No manifest transfer was
  attempted, so R0 remains a next-gate task rather than evidence for G1R.
- Replay action alignment remains an unresolved behavior-cloning blocker, not a fact.

## Evidence And Dashboard

- Command journal: `runs/g1r-preflight-20260718T115802Z/command-journal.jsonl`.
- Final journal seal at report generation: 83 entries, SHA-256
  `2511c9295cfc6ca718f03bdc8a318b8f0de6fcb4742ae51b9b92ca6babdd77a1`.
- Every journal entry records UTC time, argv, exit code, duration, and stdout/stderr
  hashes. Signed query strings are redacted.
- Raw run directories are unique and ignored. Completed manifests have sidecar seals.
- Final dashboard tests, production build, rebuild (36 records, zero quarantine), and
  doctor all passed; legacy
  self-verdicts remain projected as `SUCCEEDED / NOT_REVIEWED` unless a reviewed gate
  decision exists.
- Independent recalculation source: `ptcg g1 recalculate-gate` and
  `reports/gates/g1r.json`.
- First unattended receipt:
  `runs/g1r-user-long-acceptance/completion-receipt-20260718T140302Z.json`.
- Final unattended receipt:
  `runs/g1r-user-long-acceptance/completion-receipt-20260718T205756Z.json`; journal
  14 entries, SHA-256
  `94989e7f97a024ebf29a993fe7f038dddb221a93b6e39c65093f46384693cb61`.
- Receipt review/fix journal:
  `runs/g1r-receipt-review-20260718T1420Z/command-journal.jsonl`; repaired source hash
  `5a98d55f542d0bfafd333a94ba146b292691bfd1c6a907c21a4da167cd8ac6f8`.
- Independent raw review:
  `runs/g1r-independent-review-pass-20260719/run_manifest.json`; all six review groups
  passed. The first review attempt is retained and records a reviewer-only flattened-record
  parsing defect corrected before the passing attempt.

## Deviations And Residual Risk

- The user accepted the preregistered thresholds by invoking the runner's explicit
  `--accept-proposed-thresholds` flag.
- The first unattended run completed engine comparison, then stopped after 71 of 2,400
  benchmark games exposed native transient negative HP during knockout cleanup. The
  failed benchmark remains immutable. The validator now preserves that legal observation,
  a regression covers it, and 100 focused rule games plus a 12-point development
  benchmark passed before retry.
- The original comparison preceded that contract fix. A final-source 1,000-game/library
  comparison was therefore rerun during review and passed; no old-source comparison is
  used for the final decision.
- The unattended host runner `scripts/g1r_run_long_acceptance.sh` is resumable for
  interrupted arena/soak work, journals every command, and refreshes the independent
  verdict and dashboard on exit. The separate Docker launcher remains available if a
  reviewed Ubuntu 22.04 image is required.
- Engine entropy invalidates paired-seed and exact-trajectory comparisons.
- Observed request coverage and maxima are not guarantees.

## Next Action

Close G1R. The next reviewed gate is G2: replay/meta manifest implementation plus
quantitative deck discovery, with R1 replay acquisition permitted under its own explicit
caps. After G2 review, run the first small Colab/Kaggle training smoke. Do not begin PPO,
deck promotion, or Modal training from this report alone.
