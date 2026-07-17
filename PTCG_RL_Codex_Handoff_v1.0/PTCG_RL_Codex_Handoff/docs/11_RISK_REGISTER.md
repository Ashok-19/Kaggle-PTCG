# 11 — Risk Register

| Risk | Severity | Early signal | Prevention/mitigation | Stop/escalation trigger |
|---|---|---|---|---|
| Wrong engine lifecycle | Critical | stale selection, native crash | terminal-first checks; one battle/process; immutable snapshots | any unexplained engine/adapter failure |
| Wrong positional action resolution | Critical | legal but wrong card/target | typed resolver, snapshot-local bounds, regression capsules | unresolved observed option or mapping mismatch |
| Multi-select order/count bug | Critical | invalid or nonsensical list | autoregressive order, STOP/min/max property tests | any invalid/duplicate/out-of-range selection |
| Hidden-information leakage | Critical | train/eval disparity; visualizer field in actor | public schema allowlist, dependency tests | any actor input unavailable at submission |
| Public replay action leakage | High | replay tensors in policy/value loss | provenance firewall and import tests | any non-self rollout in PPO buffer |
| Accidental 20 GiB replay download | High | missing `path`, large plan | provider fail-closed, mandatory dry-run, hard byte caps | provider cannot guarantee one-file fetch |
| Replay selection bias | High | treating elite corpus as ladder share | label corpus, stratify days, held-out breadth, ladder cross-check | deck choice justified only by raw frequency |
| Replay schema drift | High | parse/quarantine spike | versioned adapters, manifest/hash retention | unknown schema or <99% explained current files |
| Weak-bot local optimum | High | rule wins, no population improvement | early self-play/frozen league/PFSP | fixed-population plateau after healthy PPO proof |
| Self-play collapse/forgetting | High | anchor matchup regression | anchor probability, immutable champions, promotion gates | catastrophic cell violates declared floor |
| PPO numerical instability | High | NaN, KL/clip spike, entropy collapse | toy tests, small epochs, grad clip, rollback | any NaN/Inf or unreproducible logp |
| Wrong recurrent resets | Critical | seat leakage, episode contamination | `(battle,player,policy)` key, reset tests | hidden state survives reset/changes owner |
| Native memory growth | High | positive RSS slope/container kill | soak, worker recycle only after root-cause study | declared slope/memory limit exceeded |
| Throughput below budget | High | GPU idle, queue bottleneck | profile packing/IPC/inference, compare CPU-local | projected main run misses decision/cost gate |
| Modal cost runaway | High | concurrency duplication, stale job | hard caps, learner lock, heartbeats, kill command | cost/time reaches 90% cap without checkpoint |
| Checkpoint corruption | Critical | resume failure/missing league | atomic writes, hashes, periodic restore test | latest safe checkpoint older than limit |
| Deck overfitting/meta drift | High | seven-day weights move; one bad cell | 3/7 windows, coverage-qualified 14-day stability, held-out variants, anchor/challenger | important new deck absent from evaluation |
| False promotion from noise | High | tiny samples, post-hoc metrics | frozen protocol, CIs, full matrix | threshold/weights changed after results |
| Leaderboard overreaction | High | action after 25–50 games | smoke-only interpretation, replay diagnosis | replacing anchor on noisy rating alone |
| Runtime/package failure | Critical | load delay, fallback, missing lib | clean-room offline validation and 1k-game soak | any final fallback/crash/timeout |
| License/privacy breach | Critical | engine/replays/secrets in Git/artifact | private repo, denylist, ignored staging, deletion plan | restricted file staged or public upload attempted |
| Cloud environment mismatch | High | different logits/hash/package | one CLI/lock, parity fixtures, asset hashes | unresolved local/cloud tensor/checkpoint difference |
| Solo-project scope creep | High | multiple algorithms/models unfinished | gates, decision record, successive halving | new major branch before v0 gate passes |
| User availability | Medium | job blocks awaiting manual action | bounded automation, durable status/report | no resume/hand-off information exists |

## Risk operating rule

Every progress report updates only risks whose likelihood, evidence or mitigation changed. Critical triggers stop the affected expensive work. Preserve diagnostics and last safe checkpoint, then request review. Do not normalize repeated failures by relabeling them as expected losses.

## Post-competition obligation

Before deleting any competition-only files, verify the exact license/competition requirement and the user’s archival obligations. Then remove restricted local/cloud copies, cached images/volumes and submission staging in a deliberate, explicit cleanup operation with the user’s approval. Never run a broad destructive command.
