# G1R Remediation And Acceptance Report

## Outcome And Recommendation

**Outcome: PARTIAL / BLOCKED / NOT_REVIEWED.** Keep G1R open. Do not begin G2,
episode replay acquisition, PPO, deck promotion, or training. Contract remediation is
complete, but four original acceptance criteria still lack qualifying evidence.

## Repository State

- Active repository: `Ashok-19/Kaggle-PTCG` only.
- Evidence source commit: `7fee6493c2ea3f6181438265d141c879e464d2ab`.
- Worktree at evidence collection: dirty with intentional G1R changes plus the
  pre-existing untracked root `PTCG.zip` and root instruction file.
- Local commits at report generation: none yet; the final response records any
  intentional local commit created after restricted-file review.
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
| Balanced random/rule arena | BLOCKED | 10,080 games not reached because the first runner stopped at benchmark |
| 1/2/4/8 throughput matrix | BLOCKED | first qualifying attempt exposed and retained a transient-negative-HP validator defect |
| Six-hour RSS soak | BLOCKED | runner/resume proof exists; six-hour run not launched |
| Independent artifact verdict | BLOCKED | recalculator correctly reports the three missing criteria |

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

- Current native smoke: 50/50 games; 2,475 requests; 2,253 meaningful choices;
  222 forced requests; 46 multi-select requests; zero invalids, failures, timeouts,
  fallbacks, or post-terminal actions. Observed maxima were 42 options and 3 selected.
- Exact-rule integration: 25/25 complete with all error counters zero.
- Valid-operation corpus: 1,000,000 operations across 935 structural cases in
  63.74 seconds; all 11 selection and 17 option enums covered synthetically.
- Resume proof: an intentionally interrupted soak resumed from its immutable plan,
  preserved earlier RSS samples, classified the forced worker death, and completed
  with 222 games and zero unexpected failures.
- Short RSS diagnostic only: 6.24 seconds, 247 games, peak 41,635,840 bytes. Its
  short-window slopes and confidence intervals are not leak evidence and do not
  substitute for the six-hour criterion.

The one-game-per-point throughput diagnostic is not a qualifying benchmark. Choices/s
for raw, encoded, and rule modes respectively were: worker 1 `1541.68/163.95/429.09`,
worker 2 `279.66/155.63/414.96`, worker 4 `1387.16/211.17/failed`, and worker 8
`185.13/192.89/433.52`. The sample is too small and includes one rule-worker failure.
The retained profile (`34ed45a2584dc769dc6a34534a8a6894141e9e02a61e8f82b4ec0f1d72c52214`)
identifies recursive `dataclasses.asdict`
serialization as the dominant encoded overhead. A larger qualifying matrix remains due.

## R0 Disposition

- Index manifests transferred: `0` files, `0` bytes.
- Daily manifests transferred: `0` files, `0` bytes.
- Episode JSON transferred: `0` files, `0` bytes.
- Reason: the work order permits R0 implementation only while a qualifying long G1R
  run is active. No such run was authorized or launched.
- Replay action alignment remains an unresolved behavior-cloning blocker, not a fact.

## Evidence And Dashboard

- Command journal: `runs/g1r-preflight-20260718T115802Z/command-journal.jsonl`.
- Final journal seal at report generation: 83 entries, SHA-256
  `2511c9295cfc6ca718f03bdc8a318b8f0de6fcb4742ae51b9b92ca6babdd77a1`.
- Every journal entry records UTC time, argv, exit code, duration, and stdout/stderr
  hashes. Signed query strings are redacted.
- Raw run directories are unique and ignored. Completed manifests have sidecar seals.
- The dashboard rebuild ingested 24 records with zero quarantine before final
  verification; legacy self-verdicts are projected as `SUCCEEDED / NOT_REVIEWED`,
  never as gate `PASS`.
- Independent recalculation source: `ptcg g1 recalculate-gate` and
  `reports/gates/g1r.json`.
- First unattended receipt:
  `runs/g1r-user-long-acceptance/completion-receipt-20260718T140302Z.json`.
- Receipt review/fix journal:
  `runs/g1r-receipt-review-20260718T1420Z/command-journal.jsonl`; repaired source hash
  `5a98d55f542d0bfafd333a94ba146b292691bfd1c6a907c21a4da167cd8ac6f8`.

## Deviations And Residual Risk

- The user accepted the preregistered thresholds by invoking the runner's explicit
  `--accept-proposed-thresholds` flag.
- The first unattended run completed engine comparison, then stopped after 71 of 2,400
  benchmark games exposed native transient negative HP during knockout cleanup. The
  failed benchmark remains immutable. The validator now preserves that legal observation,
  a regression covers it, and 100 focused rule games plus a 12-point development
  benchmark passed before retry.
- The unattended host runner `scripts/g1r_run_long_acceptance.sh` is resumable for
  interrupted arena/soak work, journals every command, and refreshes the independent
  verdict and dashboard on exit. The separate Docker launcher remains available if a
  reviewed Ubuntu 22.04 image is required.
- Engine entropy invalidates paired-seed and exact-trajectory comparisons.
- Observed request coverage and maxima are not guarantees.

## Next Action

Approve or revise `docs/G1R_THRESHOLD_DECISION_PROPOSAL.md`, then run
`bash scripts/g1r_run_long_acceptance.sh --accept-proposed-thresholds`. It executes only
the four blocked repetitive jobs and updates the dashboard automatically. Run R0's two
manifest-only transfers concurrently with one of those long jobs. Independently review
the retained artifacts; proceed to G2 only if every criterion passes.
