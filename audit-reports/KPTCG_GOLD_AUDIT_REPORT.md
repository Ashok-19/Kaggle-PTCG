# KPTCG Gold-Medal Audit Report

**Audit date (UTC):** 2026-07-24T09:43:04Z  
**Source commit:** `32376b090bbdb7587a6d8bbf82ff3a00b3f11925`  
**Mode:** independent, read-only, no training/cloud/submission mutation  
**Overall confidence:** 0.76  
**Gold attainability:** **POSSIBLE BUT LOW CONFIDENCE**

## Evidence-class legend

- **VF — Verified project fact:** direct source/config/test/report/manifest/hash or reproducible calculation in the archive.
- **VL — Verified live fact:** current official public source fetched during this audit.
- **PM — Provisional project measurement:** real observation whose harness, sample, or independent qualification is incomplete.
- **FR — Forum report:** participant claim, including detailed/high-ranked reports; host comments are identified but official pages override.
- **RI — Research-supported inference:** a mechanism transferred from primary literature or official implementations.
- **AH — Auditor hypothesis:** plausible but unverified; must have a falsification experiment.

A statement can have more than one class. Narrative status documents are not treated as authoritative when source/config/report evidence differs.

## 1. Executive verdict

**Verdict:** preserve the engineering stack, but **supersede the frozen PPO-first sequencing**. The highest expected gold-decision value per unit compute is:

1. qualify one exact specialist deck and a safe, policy-consistent teacher corpus;
2. train the existing recurrent semantic model by **autoregressive/listwise behavior cloning over the full compound action, including ordered without-replacement selections and STOP**;
3. promote only if on-policy H2H and held-out matchup transfer pass—not because action accuracy is high;
4. complete the minimal CABT bridge in parallel; then allow a **100k-choice KL-regularized recurrent PPO canary** with an auxiliary imitation loss;
5. expand to at most 500k choices before a new decision; and
6. keep a deterministic **Mega Lucario** specialist packaged and evaluable throughout.

This is neither pure imitation nor a rejection of PPO. It changes the order in which competence is acquired and limits the amount of terminal-reward self-play spent rediscovering setup, sequencing and deck tactics. **Pure BC is rejected as the terminal plan because of teacher ceiling and covariate shift. Pure scratch PPO is rejected as the default because the project has no CABT bridge, no real competence signal, and only provisional evidence that millions of choices can be generated cheaply enough.** [VF/FR/RI]

**Do not authorize now:** the original three-seed 1M→5M scratch PPO programme (15M total choices), TPU competence training, unconditional search, broad offline Q-learning, or a second learned deck. Each has lower immediate decision value than E01–E05.

## 2. Confidence and largest unknown

**Confidence in the strategic recommendation: 0.76.** Confidence is high that existing engineering should be preserved and that a 15M-choice scratch launch is premature. Confidence is lower on the exact deck because current exact-list/teacher evidence is missing.

**Largest unknown:** whether a current, exact-60-card, strong-teacher corpus can be acquired and authorized with sufficient policy consistency, matchup coverage, recency and duplicate control to produce on-policy competence that transfers to the non-stationary hidden ladder before **2026-08-16 23:59 UTC**. [VF/VL/AH]

The conclusion reverses if E01 fails, or if a predeclared 100k scratch PPO canary unexpectedly clears a strong held-out competence gate while BC fails.

## 3. Verified progress ledger

| Workstream | Status | Class | What is actually established | Primary evidence |
| --- | --- | --- | --- | --- |
| Archive provenance | PASS | VF | Clean commit 32376b090bbdb7587a6d8bbf82ff3a00b3f11925; 345 manifest payload entries independently rehashed with zero mismatches. | 00_READ_ME_FIRST.md; MANIFEST.json |
| G1/G1R environment/action | PASS | VF | One-battle lifecycle, terminal ordering, legal variable actions, ordered unique multi-select and STOP are tested/reported. | project/reports/gates/g1r-gate-report.json; project/src/ptcg_rl/g1/* |
| R1 replay contract | PASS on retained sample | VF | 20 episodes, 2,999 decisions, 3,275 selected options, zero unresolved; raw bodies omitted. | project/reports/gates/r1-gate-report.json; reports/replays/* |
| G2 architecture | PASS as engineering artifact | VF | 970,022 parameters; public recurrent semantic policy; deterministic checkpoint receipts. | project/reports/artifacts/g2-policy-v1.json; configs/g2_policy_v1.json |
| G2 reliability | PASS as systems evidence | VF | 10,000 complete games; zero invalid/fallback/error counters; 1.9768 games/s and 228.6 meaningful choices/s. | project/reports/evaluations/g2-neural-reliability-v1.json |
| G3a PPO correctness | PASS on toy contracts | VF | Masking, recurrent cue, variable-option multiselect, replay probability, checkpoint/resume. Strength claims explicitly forbidden. | project/configs/g3a_evaluation_v1.json; g3a gate/artifacts |
| G3b competence | BLOCKED | VF | CABT actor/learner bridge absent; no Pokémon training; no competence/strength. | 01_CURRENT_STATE_ADDENDUM.md; g3b gate |
| D1 specialist selection | NOT STARTED | VF | No exact specialist list selected/frozen; Abomasnow is engineering deck only. | 01_CURRENT_STATE_ADDENDUM.md |
| TPU qualification | NOT QUALIFIED | PM | 8 devices/96 logical threads and 251.74-344.26 choices/s observed, but first verdict invalidated by harness defects; no repaired retained run. | 01_CURRENT_STATE_ADDENDUM.md; v2 input contract |
| Live leaderboard/quota | PROVISIONAL | PM | Same-day connector snapshot retained; anonymous independent refresh unavailable. | 05_LIVE_KAGGLE_SNAPSHOT_2026-07-24.json |

### Recalculated retained measurements

- **G2 reliability:** 121.3203 requests/game, 115.6383 meaningful choices/game, 5.682 forced calls/game, 2.0791 multi-select requests/game, 228.598 meaningful choices/s and 1.97684 games/s. [VF]
- **R1 replay sample:** 149.95 decisions/episode, 163.75 selected options/episode, 140.90 meaningful decisions/episode, 6.0353% forced decisions and 1.0920 selected options/decision. [VF]
- These are engineering/data-contract measurements. They are **not policy-strength evidence**.

### Static checks performed

- `MANIFEST.json`: all **345** payload entries independently rehashed and byte-counted; zero mismatches. [VF]
- Initial retained audit test run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src pytest -q -p no:cacheprovider` reported **401 passed, 1 skipped, 14 failed**. The failures were attributable to omitted private/native/card assets, missing `.git`/pack-layout files, or interpreter/environment assumptions; no algorithmic assertion failure was reproduced. A repeat run in the current container reached 86% before the execution limit, so it does not add a clean-suite claim. `ruff` was unavailable. [VF with execution limitation]

## 4. Claims that are not established

| Claim | Why it is not established |
| --- | --- |
| Pokémon competence | No real CABT training/evaluation has shown competent play. |
| Gold-level strength | No settled live result or confirmed local tournament against current strong agents. |
| Teacher-label safety | Raw replay bodies/teacher identity/exact deck/dedup are absent; actions are not authorized as labels. |
| Exact specialist | No exact 60-card learned specialist has passed selection gates. |
| Bridge correctness on CABT | Source components are strong, but the real actor/learner integration is unimplemented. |
| TPU suitability | Only provisional host observations exist; no repaired qualification artifact. |
| Search value/runtime | API exists in documentation, but packaged runtime availability/latency and strength benefit are unqualified. |
| Meta representativeness | Public top episodes are selected and visible; hidden ladder distribution is unknown. |
| Gold cutoff | Rank/score frontier is provisional; exact medal cutoff/team count was not independently retrievable. |
| Checkpoint storage | Full G2 checkpoint omitted; storage numbers in this report are estimates. |

## 5. Evidence/provenance defects and contradictions

1. **Narrative versus gate reality.** The status documents describe a mature programme; the gate artifacts correctly show G3b blocked and D1 not started. The latter controls. [VF]
2. **Omitted raw replay bodies.** R1 proves the loader on 20 approved episodes, but this auditor cannot independently inspect teacher identity, exact deck, rank stability, duplicate contamination, hidden leakage, setup rows or label semantics without the omitted bodies. [VF]
3. **TPU summary without retained result.** The 251.74→344.26 choices/s observations are informative PMs, but the saved report/manifest was not retained and the run was rejected by known harness defects. They cannot be used as a capacity guarantee. [PM]
4. **Live snapshot freshness.** The July 24 connector snapshot is same-day, but live Kaggle pages are dynamically rendered and the official CLI requires authentication for the relevant calls. No credentials were requested. The exact same-minute leaderboard, team count, medal cutoff and late-July full forum tree could not be independently refreshed. [PM/VL limitation]
5. **Forum evidence is selected.** The July 16 archive research is unusually strong—146 current topics, 56 high-signal topics and nested replies—but is eight days stale. Current starter topics 728071, 724187, 728301, 727816 and 728168 were not all available as full anonymous text during this audit. [FR limitation]
6. **Sample-selection and survivorship bias.** Daily top episodes are intentionally biased toward high average participant rating; successful public methods are more likely to be posted, while top teams have incentives to withhold details. [FR]
7. **Multiple comparisons.** Many decks, checkpoints, guards, seeds and search settings make isolated wins likely. Existing champion gates are statistically serious, but early screens should not spend confirmation-sized samples on every candidate. [RI]
8. **Stale runtime reports.** CPU, memory, match rate, random-opponent fraction and time-limit reports changed during June. Current official/package behavior overrides old comments. [VL/FR]
9. **Project plan contradiction.** G3b freezes `behavior_cloning=false`; the current imitation-first hypothesis cannot be implemented as a silent tweak. It requires a reviewed decision that supersedes sequencing while preserving authorization boundaries. [VF]

## 6. Critical gap matrix

| Severity | Gap | Consequence | Cheapest decisive test | Owner | Deadline |
| --- | --- | --- | --- | --- | --- |
| Critical | No exact specialist/teacher corpus | Wrong deck or mixed-policy labels can invalidate all training. | E01, zero accelerator | Research/data lead | 2026-07-25 18:00Z |
| Critical | CABT actor/learner bridge absent | No safe on-policy eval/fine-tune; PPO plan cannot run. | E04 10/100-game no-update qualification | Systems/RL lead | 2026-07-26 00:00Z |
| Critical | No competence measurement | Engineering may mask a strategically weak policy. | E03 on-policy BC pilot; E08 deterministic tournament | Evaluation lead | 2026-07-28 00:00Z |
| High | Option-order signal intentionally excluded | May discard a strong cheap prior reported by participants. | E02 5k-label ablation | Model lead | 2026-07-26 12:00Z |
| High | Replay raw bodies omitted/labels unauthorized | Independent leakage/duplicate/action audit blocked. | Acquire minimal qualified sample under separate authorization | Data lead | Before E03 |
| High | Equal anchor weights only | Can mis-rank policies under current meta while hiding catastrophic holes. | Meta/equal/worst-cell tri-report in E10 | Evaluation lead | 2026-07-29 |
| High | Partial PPO update contract undefined | 1M/5M budgets leave 576/2,880 choices; may drift or discard data. | Predeclare pad/drop/partial minibatch behavior and test | RL lead | Before any PPO |
| High | Current live forum/leaderboard not fully refreshed | Late strategy/meta changes may reverse deck choice. | Authenticated owner-side refresh or current connector export | Owner | Daily through deadline |
| Medium | Representation lacks explicit deck/prize/belief/turn-plan features | May raise sample cost/ceiling, especially for high-complexity decks. | E12 only after a proven plateau | Model lead | After E05 |
| Medium | Recurrent ledger lock scope may serialize shared use | Potential throughput collapse if one global ledger spans compute. | Microbenchmark one-ledger vs per-env; inspect lock release | Systems lead | During E04 |
| Medium | TPU v2 rerun absent | Compute planning cannot rely on 344 choices/s. | E11 after competence path passes | Systems lead | 2026-08-02 |
| Medium | Fail-closed interactive UX | Negative verdict should be a returned report, while integrity failures still raise. | Retain v2 attempt-scoped behavior; no training impact | Notebook owner | Next notebook revision |

The evidence-first gates mostly improve decision quality. The drag comes from treating every intermediate checkpoint as confirmation-grade and from sequencing deck selection after a large generic competence programme. Move **deck/teacher qualification before major training**, keep bridge work parallel, and reserve 600–1,200-cell samples for finalists.

## 7. Architecture and representation audit

### What the model represents well

The actor consumes a public semantic projection rather than a fixed flat action index. It encodes card identity and numeric card attributes, public entities/roles/zones, public counts, event history, selection context, effect/context-card identifiers, legal option semantics and source/target relations. A transformer pools public entities; event and public GRUs carry history; the option scorer handles a ragged legal set; the decoder emits ordered unique selections and a first-class STOP. The critic is public-only. [VF]

This is a strong fit for variable legal actions and partial observability. The 970,022-parameter size is sufficient for a first exact-deck specialist; increasing width before competence is demonstrated would spend compute on the wrong uncertainty. [RI/AH]

### Ceilings and missing features

The card encoder emphasizes identity, type/stage/HP/cost/damage and count-like attributes. It does not explicitly encode effect text/ability semantics. The public projection does not provide explicit known-deck composition counts by card, a prize-map belief, opponent archetype belief, turn-plan/macro intent, or all official turn flags as dedicated features. It also intentionally omits arbitrary option position. [VF]

For a specialist, card-ID embeddings and recurrence may infer much of this. For Dragapult-like prize/spread planning, hidden-card beliefs and long-horizon resource sequencing may become the ceiling. This is why Mega Lucario is the lower-risk first learned deck and Dragapult is a hard anchor/high-ceiling second wave. [AH]

### Leakage and aliasing

- Public-only actor/critic is appropriately conservative; no privileged critic is authorized. [VF]
- Semantic entity sorting protects against arbitrary container order, but two states with the same public projection can require different actions because of hidden deck/prize/hand beliefs. Recurrence can only resolve this when the relevant evidence appeared in public events. [RI]
- Raw option index exclusion avoids a fragile shortcut, yet forum evidence says option order can be highly predictive. Treat it as an explicit feature ablation with permutation controls rather than permanently discarding it. [FR/AH]
- Card-ID memorization tightly entangles policy and exact deck. That is acceptable—and useful—for a specialist, but invalidates claims of generality.

### Capacity allocation decision

Do **not** enlarge the model first. Spend the first marginal parameters on: a small normalized option-position embedding if E02 passes; explicit known deck-count/public prize hypotheses only if E12 proves a plateau; and auxiliary next-event/value/count losses only with shuffled-target and width-matched controls.

## 8. PPO and actor/learner audit

### Correctness that is genuinely established

The source and toy qualification support exact stored compound-action replay, PPO ratio/KL/clip logic, terminal-aware GAE, forced-step recurrence without policy loss, recurrent owner/version separation, zero policy-version lag, optimizer/checkpoint/RNG restoration and deterministic resume evidence. [VF]

### What is not established

The real CABT actor/learner bridge, queueing and terminal ownership across both players are absent. Sparse terminal reward, critic calibration, exploration, catastrophic forgetting, opponent non-stationarity and real throughput are untested. [VF]

### Config audit

The frozen plan uses update size 16,384, sequence length 64, three epochs, learning rate 3e-4, gamma 1.0, GAE 0.95, clip/value clip 0.2, entropy 0.01, target KL 0.02/stop 0.03 and zero lag. These are defensible starting values, not competence evidence. With terminal-only outcomes and long episodes, gamma 1.0 is coherent, but the critic must be screened for scale/calibration and the entropy coefficient must not be allowed to preserve random compound sequences at the expense of tactics. [VF/RI]

### Exact update counts

| Choice budget | Full 16,384-choice updates | Remainder choices | Nominal updates |
| --- | --- | --- | --- |
| 50,000 | 3 | 848 | 3.051758 |
| 100,000 | 6 | 1696 | 6.103516 |
| 500,000 | 30 | 8480 | 30.517578 |
| 1,000,000 | 61 | 576 | 61.035156 |
| 5,000,000 | 305 | 2880 | 305.175781 |

The 1M and 5M budgets are not divisible by the update size. Before any run, freeze whether the remainder is dropped, carried to the next chunk, padded with masked samples, or used in a partial minibatch. Silent budget drift violates the plan’s own exact-budget standard.

### Decision on G3b

**Amend through a new decision record; do not delete the implementation.** Preserve the PPO stack and its acceptance criteria, but supersede:

- engineering Mega Abomasnow as learner deck;
- BC disabled by default;
- 1M/5M scratch sequencing before specialist/teacher evidence; and
- equal anchor weights as the only population summary.

The CABT bridge is still worth completing because on-policy H2H and bounded fine-tuning both need it. It should run in parallel with E01/E03, not block data qualification.

## 9. Replay, imitation and offline-RL audit

### Proven contract and remaining label requirements

The loader correctly lag-aligns the action recorded at step *t* to the selection request at *t−1*, validates zero-based legal indices, uniqueness/count/availability and infers STOP when the selected count is below maximum. [VF]

Before actions are safe labels, require: exact raw-body hashes; exact 60-card deck fingerprint; teacher submission/team identifier; rating/game-count recency; no timeout/native error; complete result and seat; duplicate/near-duplicate episode control; exact request/action resolution; and explicit authorization to use the data for supervision. None may be inferred from the 20-episode summary.

### Teacher selection

A passing teacher must be strong **and coherent**, not merely high-ranked once. Use settled strength or sufficient games, exact deck, recency, matchup coverage, low fallback/timeout, and policy consistency. Prefer at least two independent teachers. A current rank displayed beside an old comment or replay must not be treated as rank at the time.

### Label weighting

- Default: decisions from strong teachers in both wins and losses, weighted by teacher confidence/strength, episode integrity and state support—not winner-only.
- Winner-only supervision creates outcome-conditioned selection bias and removes difficult recovery states.
- Downweight forced choices to zero policy loss while retaining them for recurrent state progression/diagnostics.
- Encode the full ordered selection and STOP; do not flatten to unordered sets or top-1 options.
- Treat setup/deck response, invalid/empty actions and parser-uncertain rows as separate schemas or exclusions.
- Deduplicate before splitting. Split whole episodes first, then hold out teacher, exact deck/list version, matchup and time window.

### Metrics beyond top-1 accuracy

Full-action exact match; token/log-sequence NLL; calibration; regret to teacher; on-policy H2H; state-distribution divergence; illegal/fallback rate; teacher/time/matchup transfer; and seat-specific results. The forum’s 99% action-accuracy/28–41% H2H result is the canonical warning. [FR]

### Method decision

Use recurrent autoregressive/listwise BC first. DAgger is a conditional remedy only when a callable rule/copied teacher can label learner states. Use BC+KL/auxiliary PPO if E03 passes. Do not start AWAC/IQL/CQL/Decision Transformer: the retained data is too small/selected, rewards and behavior support are not sufficiently qualified, and a Q over structured compound actions would require substantial new code.

## 10. Paper-method transfer matrix

| Family | Transferable mechanism | Assumptions that fail | Variable ordered actions | Partial observability | New code | Sample efficiency | Submission cost | Failure modes | Cheapest falsification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Recurrent/listwise BC | Exact legal-option token ranking plus autoregressive without-replacement/STOP supervision. | Teacher quality, exact deck and on-policy coverage are unknown. | Excellent: native legal set and decoder already exist. | Excellent: public/event GRUs. | Small: dataset/weights/loss and feature ablation. | High if teacher is strong. | Low. | Teacher ceiling, covariate shift, order shortcut. | 5k/25k labels + 200-game H2H. |
| DAgger | Query teacher on learner-visited states and aggregate. | Strong teacher may not be callable on arbitrary states. | Excellent if rule/copied teacher exposes exact action. | Excellent. | Moderate data loop. | High. | Low. | Teacher errors and expensive queries. | Use deterministic rule teacher on 5k learner states only if E03 offline/on-policy diverges. |
| BC + KL/auxiliary PPO | Warm start competence; retain teacher prior while terminal reward improves. | Teacher may be suboptimal; KL can block improvement or prevent forgetting. | Excellent with current exact compound log-prob stack. | Excellent. | Moderate: E04 bridge + auxiliary batch. | High expected fit. | Low at submission. | Forgetting, sparse critic, nonstationarity. | E05 100k choices. |
| Pure recurrent PPO | Directly optimize wins without teacher bias. | No competence, sparse terminal reward, no bridge, small compute vs reported millions. | Implemented algorithmically. | Excellent. | Bridge only, but high experience cost. | Uncertain/low from scratch. | Low. | Exploration, critic weakness, cycling, deck entanglement. | One 100k predeclared canary only if imitation gate fails. |
| IMPALA/V-trace/APPO | Scale asynchronous actors and correct lag. | Project deliberately enforces zero lag; systems rewrite under deadline. | Possible but unnecessary. | Good. | High. | Potential high throughput, lower decision value now. | Low. | Off-policy instability, queueing complexity. | Do not implement unless synchronous throughput <35 choices/s after E04. |
| R2D2/Ape-X | Recurrent replay, burn-in and prioritized distributed learning. | Requires replay/off-policy Q or actor-critic redesign. | Structured actions complicate Q. | Good. | High. | Potentially high long-run. | Low. | Stale recurrent states, Q overestimation. | No first-pass experiment. |
| AWAC/IQL/CQL | Use offline returns/advantages conservatively, then online. | Behavior probabilities and rewards/support are incomplete; action is a variable sequence. | Poor-to-moderate without new Q/action representation. | Possible. | High. | Unclear with tiny biased data. | Low. | Extrapolation, reward/teacher bias. | Reject until >=100k diverse rewarded trajectories and a defensible Q representation. |
| Decision Transformer | Condition action sequences on return and history. | Tiny, selected dataset; return and deck diversity insufficient. | Technically compatible but needs sequence/action grammar. | Strong. | High. | Low now. | Low. | Dataset coverage/conditioning failure. | No current experiment. |
| NFSP/PSRO/league | Train best responses against a population; preserve historical policies. | Full equilibrium solving unnecessary; hidden meta changes. | Good. | Good. | Low for lightweight historical league; high for full PSRO. | Moderate. | Low. | Meta overfit/cycling. | Use frozen historical checkpoints and one exploiter in E05/E10. |
| AlphaZero/MuZero family | Policy/value guided search and policy improvement. | Large compute, hidden information, long variable actions; exact simulator already exists. | Search can consume compound actions but engineering is large. | Needs belief/recurrent root state. | Very high. | Low before deadline. | High. | Model/search bias and runtime. | Do not implement; test only E09 selective exact-simulator search. |
| POMCP/ISMCTS | Search over hidden-state particles/information sets. | Legal hidden deck/prize hypotheses and particle quality are hard; determinization pathologies. | Possible with existing search API. | Belief state required. | High. | Unclear. | High. | Strategy fusion, leakage, latency. | Only one tactical context after no-search champion and runtime proof. |
| Deep CFR/ReBeL | Equilibrium/public-belief learning for imperfect information. | Requires game traversal, counterfactual values/public belief representation and much more compute. | Poor near-term. | Central but absent. | Very high. | Low before deadline. | High. | Implementation risk. | Stop. |
| Macro/turn-plan modeling | Reduce horizon by predicting semantic plans then legal micro-actions. | Requires plan ontology and labels. | Good if plans map to legal options. | Good. | Moderate-high. | Potential later. | Low. | Bad plan labels/rigidity. | Only after E03 plateau; not first 72h. |
| Auxiliary representation/value warm start | Predict next public event, card counts, terminal value or teacher value. | Targets can be noisy/biased and distract policy. | Excellent. | Excellent. | Moderate. | Potential moderate. | Low. | Auxiliary shortcut/leakage. | E12 with shuffled-target and width-matched controls. |

## 11. Kaggle discussion synthesis and contradiction table

The archived July 16 research process read 56 high-signal topics in full, including all available comments and nested replies. It covered 14 RL, 14 replay/meta, 19 engine/runtime and 9 submission/evaluation topics. This exceeds the 15-thread floor for the historical snapshot. The current late-July full index/comments could not be refreshed anonymously; the research log marks those rows as snippet-only rather than inventing content.

| Claim/report | Evidence for | Contradiction/limitation | Audit decision |
| --- | --- | --- | --- |
| Pure RL can reach silver after millions of games and bugs fixed (717697). | Small/optimized pure RL is possible. | Other reports show rule/search outperform PPO; project has no real bridge or competence. | Treat as existence proof; allow only a 100k canary after cheaper gates. |
| BC/DAgger reaches very high action accuracy (713608/711644). | Teacher behavior can be learned offline. | Teacher H2H can remain 10-41%; covariate shift dominates. | Use on-policy H2H, full-action NLL, state divergence, and held-out matchups as gates. |
| Shallow search gave +11.3 pp on weak Alakazam. | Search can repair tactical mistakes. | Same report shows -15.4 pp on strong Starmie; 10-rollout PUCT not robust. | Only selective/gated search after a champion, with no-search control and runtime proof. |
| Native option 0 reportedly beats random 88-90%. | Engine option order contains a strong prior. | Order may change, encode triviality, or fail under perturbation. | Run E02; never treat order accuracy as strength. |
| Top-game timing suggests bounded search (724362). | Some strong agents may search. | Inference from timing, not disclosed method; startup/model latency confounds. | Do not copy inferred architecture; test exact runtime/benefit. |
| Rule agents reached meaningful ranks (728168/older threads). | Low-compute hedge can be competitive. | Ratings provisional and meta/counters evolve. | Maintain a rule specialist, but confirm locally and do not equate rank spike with gold. |
| Daily top episodes reveal current meta. | Useful for candidate/teacher discovery. | Kaggle staff says sampling favors high average rating; public visibility and strategic withholding bias it. | Use 3/7/14-day sensitivity, lower bands, and explicit uncertainty. |
| Seeded engine modification may reduce variance (728301). | CRN could greatly improve paired tests. | Normal wrapper exposes no seed; native engine omitted/licensed; modified engine may diverge from submission runtime. | No CRN claim until official/legal seed path and measured variance reduction are verified. |

No forum claim is promoted to project fact. Detailed participant reports deserve replication priority, but strategic withholding, survivorship bias, deck differences, changing engine versions, provisional ratings and author incentives remain material.

## 12. Current meta reconstruction and bias analysis

### Observable evidence

The archived visible snapshots changed rapidly: Crustle-heavy, then Lucario/Psychic, then Starmie/Archaludon/Psychic; one top-100 snapshot reported Fighting 43%, Psychic 20%, Lightning 19% and sustain 7%. These are FRs from selected public episodes, not a hidden-field distribution. [FR]

The July 24 snapshot’s operational frontier is: #1 1198.0, #5 1136.5, #10 1115.6, #20 1102.1 and #25 1092.8. The #1–#10 gap is 82.4 and #10–#25 only 22.8, consistent with a dense, noisy frontier. Exact gold medal cutoff is not established. [PM]

### Bias controls

Use 3/7/14-day deck weights, report unweighted anchor results, include lower-rating bands and losing episodes, separate teacher-discovery data from evaluation opponents, and expose uncertainty for partially revealed decks. A human Bo3 tournament result can inform sequencing/skill ceiling but cannot be treated as Kaggle Bo1 agent strength without card-pool/list verification.

## 13. Specialist deck shortlist and exact-list acquisition plan

| Archetype | Current evidence | Teacher availability | Branching | Ceiling | Rule baseline | Imitation fit | RL fit | Latency | Decision | Key risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mega Lucario | Included exact list + 508-line tactical policy | High | Moderate | Moderate-high | High | High | Moderate | Low | 1 — default first specialist and hedge | Field/meta strength still unproven. |
| Starmie | Forum/current-meta signal; exact list/teacher absent | Low now | Low | High | Low now | High if corpus found | High | Low | 2 — data-gated challenger | Selection bias and missing exact-list provenance. |
| Dragapult/Psychic | Included exact list + 853-line planner | High rule teacher; replay unknown | High | High | High | Moderate | Low-moderate | Moderate | 3 — hard anchor/high-ceiling second wave | Prize mapping/spread sequencing raises sample cost. |
| Crustle | Historic public/forum support | Moderate | Low | Low-moderate | Moderate | High | High | Low | 4 — comparator/hedge candidate | Likely countered/stale; ceiling concern. |
| Alakazam | Forum search experiments | Low | High | Moderate-high | Low | Low-moderate | Low | High if search | 5 — research only | Search-sensitive and exact list/teacher uncertain. |
| Mega Abomasnow | Included exact list + 267-line simple policy | High rule teacher | Very low | Low-moderate | High | High | High | Very low | 6 — engineering anchor only | Ease can create false confidence; likely ceiling. |

### Exact-list acquisition plan

1. Refresh current public episode index and leaderboard under the owner’s authenticated Kaggle session; retain receipts, not credentials.
2. For each candidate, obtain an exact publicly usable 60-card source or submitted `deck.csv`; validate card IDs, duplicate-name limits, Basic/ACE SPEC and current designated card pool.
3. Freeze `deck.csv`, SHA-256, provenance URL/date, archetype label and any list variants. Do not merge examples across variants without a deck-version feature and split.
4. Require two independent teachers and >=25k meaningful decisions for confirmation; retain lower-rated/losing examples only for coverage/negative analysis.
5. Build teacher-by-matchup/time coverage and duplicate-adjusted effective sample size. Fail closed on partially inferred exact lists.

The first learned specialist is Mega Lucario because the archive already contains an exact list and a tactical policy. Starmie can replace it only through equal-budget evidence, not current meta narrative.

## 14. Recommended policy stack

**Actor:** existing G2 recurrent semantic policy, plus only E02-validated option-position signal.  
**Pretraining:** weighted recurrent autoregressive BC over legal options; full compound action and STOP.  
**Fine-tuning:** synchronous recurrent PPO with existing exact replay/GAE/checkpoint stack, initialized from BC, adaptive teacher KL and decaying auxiliary BC batches.  
**Population:** rule anchors, teachers, historical checkpoints, self-play and one held-out exploiter; opponent fixed for the episode.  
**Safety:** deterministic first-legal fallback only in submission; any fallback during training/evaluation is a failure.  
**Search:** off by default; only the smallest E09-passing selective search.  
**Portfolio:** one learned specialist plus one deterministic complementary specialist; not two simultaneous learned decks until the first path is confirmed.

## 15. Rule/copied-policy/search hedge

The included policies have materially different complexity: Mega Abomasnow is a simple engineering anchor; Mega Lucario contains tactical switching/prize targeting; Dragapult explicitly manages spread damage, prize maps and deck counts. [VF]

Use Mega Lucario as the baseline hedge because it is concrete, exact-list and moderate complexity. Reproduce only public/included logic; do not copy withheld/private submissions. Add guards only when a loss-bucket hypothesis beats the unchanged policy under perturbation and held-out controls.

Native option order may itself be a strong copied prior; E02 tests it. Search is conditional. It can help a weak value/policy and harm a strong one. Confirm API availability in the exact package, hidden-state hypothesis legality, fair randomness, and cumulative latency. No modified-engine CRN or search-dependent design is promoted without official/legal parity.

## 16. Training curriculum with exact budgets

1. **0 choices:** E01 data/deck gate and E04 bridge qualification.
2. **5k labels:** debug action grammar and option-order ablation.
3. **25k labels:** three-seed BC screen with strong controls; 200-game cells only for large effects.
4. **100k labels:** BC confirmation; 600-game finalist cells where needed.
5. **100k on-policy choices:** one-seed BC→KL-PPO canary; six full updates plus 1,696-choice predeclared remainder handling.
6. **100k × three seeds:** only after one-seed pass.
7. **500k choices:** staged 100k chunks, two seeds then third confirmation; stop at the best historical checkpoint.
8. **Beyond 500k:** new decision record required. The current audit does not authorize 1M/5M per seed.

Reward remains terminal W/D/L initially. Reward shaping is a separate decision because it can change the objective and exploit simulator quirks. A supervised critic warm start may be tested after BC competence, not before.

## 17. Evaluation and statistics protocol

### Populations and reporting

Maintain separate training opponents, fixed held-out opponents, historical checkpoints, public rule agents, specialist exploiters and current-meta decks. Report: meta-weighted primary; equal-anchor diagnostic; each matchup/seat; and worst important cell. Never blend reliability into a strength score—reliability is a hard gate.

### Screening, confirmation and live validation

- **Screen:** 100–200 games/cell, sequential stopping for large effects, point estimates used only to decide what deserves confirmation.
- **Confirm:** 600–1,200 games/cell for finalists, 3,000+ frozen-population games for champion selection.
- **Live:** package-ready champion/challenger only; allow ratings to settle; do not react to a short spike.

At 50% win probability, approximate 95% half-widths are ±9.8 pp (100), ±6.9 (200), ±5.7 (300), ±4.9 (400), ±4.0 (600), ±2.8 (1,200) and ±1.27 (6,000). Independent two-arm 80%-power MDEs are roughly 14.0 pp at 200/arm, 11.4 at 300, 9.9 at 400, 8.1 at 600 and 5.7 at 1,200. Small early differences are not decision-grade.

Use Wilson or beta/Dirichlet-multinomial intervals, episode-level bootstrap for paired/clustered summaries, seat balancing, sequential alpha spending and Holm correction across promoted comparisons. Common random numbers are not currently claimed: the normal wrapper exposes no seed, and engine modification is a licensing/runtime-parity risk. Use matched opponent/checkpoint order and paired seats; adopt CRN only after an official seed path and measured variance reduction.

## 18. Compute budget with low/base/high estimates

| Basis | Choices/s | 1M choices h | 5M h | 15M h | Class |
| --- | --- | --- | --- | --- | --- |
| TPU host provisional high | 344.26 | 0.81 | 4.03 | 12.10 | PM |
| TPU host provisional base | 251.74 | 1.10 | 5.52 | 16.55 | PM |
| G2 T4x2 measured inference-only | 228.60 | 1.22 | 6.08 | 18.23 | VF |
| Conservative integrated base | 100.00 | 2.78 | 13.89 | 41.67 | AH |
| Low case | 57.15 | 4.86 | 24.30 | 72.91 | AH |
| G3b minimum gate | 35.00 | 7.94 | 39.68 | 119.05 | AH |

The measured 228.6 choices/s is inference/reliability throughput, not integrated PPO throughput. The TPU numbers are provisional. At the frozen minimum of 35 choices/s, 15M experience alone takes about 119 hours before evaluation/optimization. This is incompatible with an evidence-first programme unless early competence is already established.

The July 24 pre-refresh quota snapshot shows 24.358 GPU hours and 18.425 TPU hours. Treat it as PM; refresh before scheduling. Recommended first-72-hour spend is 0.5–8 GPU hours, zero TPU, and 3–24 CPU evaluation hours. Seven-day maximum before a new decision is 20 GPU hours, 4 optional TPU hours and 500k on-policy choices.

A 6,000-game evaluation at the G2 reliability rate would take about 0.843 hours of engine wall time, but learned-policy CPU/package evaluation may be 1–3+ hours. A full learner checkpoint is estimated at 15–30 MB; 150 checkpoints for 5M×3 seeds would be about 2.2–4.4 GiB. This estimate is blocked by the omitted full checkpoint.

## 19. Experiment priority queue

| Priority | ID | Experiment | Entry gate | Wall low/base/high | Screen | Failure action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | E01 | Exact-deck teacher and replay-safety qualification | Read-only acquisition/analysis authorization and official rules check. | 1.0/3.0/6.0 h | One candidate with exact legal 60-card list, >=1 strong teacher, >=5k valid decisions, zero unresolved labels. | Stop imitation; retain deterministic hedge and run only bounded PPO canary after E04. |
| 2 | E04 | Minimal CABT actor/learner bridge qualification | No omitted native asset required for source audit; execution requires authorized private engine. | 0.5/2.0/6.0 h | 10 games complete with zero reliability events and exact action replay. | Do not run PPO; fix bridge while BC/offline analysis and deterministic hedge continue. |
| 3 | E02 | Native option-order signal ablation | E01 screening pass. | 0.2/0.6/1.5 h | Position arm improves held-out NLL >=5% relative and no permutation-control collapse >10 pp. | Keep current semantic order-blind projection. |
| 4 | E03 | Recurrent autoregressive BC scaling pilot | E01 confirmation pass and E02 decision recorded. | 0.5/2.0/5.0 h | At 25k: >=25% NLL reduction vs strongest non-neural baseline, >=60% full-action exact match, zero illegal/fallback, and >=30% H2H vs teacher or >=5 pp over deterministic baseline. | Stop imitation expansion; use deterministic hedge and consider a 100k-choice PPO canary only. |
| 5 | E08 | Deterministic specialist hedge and perturbation controls | Submission runtime/package smoke. | 0.5/2.0/5.0 h | Variant point estimate >=+5 pp versus original on targeted loss bucket and aggregate not worse by >2 pp. | Revert to unmodified strongest included rule policy. |
| 6 | E05 | BC to KL-regularized recurrent PPO canary | E03 pass and E04 pass. | 0.4/1.5/4.0 h | At 100k one seed: point estimate >=+5 pp aggregate, no matchup <=-5 pp, KL within target, zero reliability events. | Revert to BC champion and stop this PPO configuration. |
| 7 | E06 | Starmie specialist challenger gate | Exact-list/current-teacher E01 gate. | 0.5/2.0/5.0 h | E01 confirmation plus 25k BC meets E03 screen and is >=5 pp above Lucario at equal budget. | Stop Starmie branch. |
| 8 | E07 | 500k-choice hybrid confirmation and historical league | E05 confirmation pass. | 1.0/4.0/12.0 h | At least one of 200k/300k/500k beats 100k champion by >=3 pp with no catastrophic regression. | Return to best earlier BC/hybrid checkpoint; no 5M extension. |
| 9 | E09 | Selective search availability, latency, and strength ablation | Official runtime/API verification and stable champion. | 1.0/4.0/10.0 h | Targeted +5 pp and aggregate >=-2 pp; API present in exact package; p99 game inference <60 s and max projected cumulative <300 s. | Ship no-search policy. |
| 10 | E10 | Frozen local tournament and meta-weighted confirmation | At least two frozen, package-ready candidates. | 3.0/10.0/30.0 h | Candidate point estimate >=+5 pp vs current champion and no floor breach. | Keep prior champion and hedge. |
| 11 | E11 | Repaired TPU v2 environment qualification | E05 pass or T4 throughput <100 choices/s; retained v2 outputs required. | 0.5/2.0/4.0 h | >=100 integrated choices/s and no false cap/recompilation. | Use T4x2/CPU; stop TPU work. |
| 12 | E12 | Representation ceiling and auxiliary-objective ablation | Documented plateau after E03/E05; not a first-72-hour task. | 1.0/4.0/10.0 h | Hard-matchup +5 pp and aggregate not worse, or held-out NLL >=10% better. | Keep existing 970k architecture. |

The ranking is expected gold-decision value divided by compute plus engineering cost. E01 can kill the recommendation at near-zero compute. E04 is the hard integration gate. E02/E03 test the cheapest competence path. TPU and representation redesign are deliberately late because they optimize throughput/capacity before the method is known to work.

Full experiment cards are in `KPTCG_EXPERIMENT_BACKLOG.csv`.

## 20. 72-hour action plan

**By July 25 18:00 UTC:** issue `DEC-AUDIT-001` that preserves the stack but supersedes PPO-first sequencing; refresh official rules/leaderboard/quota/forum under the owner’s authenticated session; freeze E01 evidence schema; keep all data/training/submission authorizations separate.

**By July 26 00:00 UTC:** complete E04 10-game smoke and 100-game no-update bridge qualification, including injected stale/duplicate/worker/terminal/multiselect tests.

**By July 26 12:00 UTC:** if E01 has a 5k-label screen, run E02 option-order ablation. In parallel package the unchanged Mega Lucario deterministic hedge.

**By July 27–28:** run E03 5k/25k/100k staged BC only if E01 confirms exact list, two teachers and label integrity. Use the first on-policy 200-game screen to stop a bad imitation path. Do not wait for perfect data infrastructure before testing 5k, but do not scale unqualified labels.

## 21. Seven-day action plan

- Finish 100k BC with three seeds and held-out teacher/time/matchup splits.
- Complete 600-game confirmation only for the best BC and deterministic hedge.
- If E03 passes, run E05 100k KL-PPO; otherwise stop learned imitation expansion.
- Acquire/evaluate Starmie only if its exact-list/two-teacher gate passes; no speculative model branch.
- Freeze a package-ready deterministic active agent and a rollback learned checkpoint.
- Run E11 TPU qualification only if the learning path passes and T4 integrated throughput is the bottleneck.
- Publish no data/model/engine assets and make no submission without explicit authorization.

## 22. Deadline-to-submission plan

At audit time approximately 16.6 days remain to the Simulation entry/team deadline, 23.6 days to the Simulation final deadline, 44.6 days to the Strategy entry deadline and 51.6 days to the Strategy final deadline. The organizer site states Simulation submissions through **August 17 08:59 JST** and Strategy reports through **September 14 08:59 JST**; an official Kaggle announcement confirms the **August 9** Simulation entry and **September 6** Strategy entry dates. The exact 23:59 UTC entry/team-merger timestamp is also retained in `project/configs/official.json`. [VL/VF]

- **August 5:** final learned-method redecision; no 5M extension without a proven 500k curve.
- **August 7:** primary deck/architecture lock; only bug fixes/runtime reductions after this date.
- **August 9:** entry/team actions complete before 23:59 UTC.
- **August 10:** package parity/soak and active-pair plan frozen.
- **August 12:** stable champion and hedge submitted early enough to accumulate games, subject to authorization.
- **August 13 onward:** no architectural experiments; only confirmed rollback, packaging and critical exploit fixes.
- **August 16 23:59 UTC:** final simulation deadline; retain two deliberately complementary active submissions.
- **September 6 23:59 UTC:** Strategy entry deadline; verify participation linkage and rules acceptance well before this point.
- **September 13 23:59 UTC:** Strategy report deadline; preserve all decision/evidence manifests now.

## 23. Gold-path pass/fail decision tree

```text
E01 exact-list/teacher/replay gate?
├─ FAIL → stop imitation; ship/improve deterministic Lucario; complete E04;
│        run at most one 100k scratch-PPO canary if bridge passes.
└─ PASS → E02 order ablation + E03 25k BC
          ├─ BC on-policy screen FAIL → stop BC scaling; deterministic hedge;
          │                           optional DAgger-like rule-teacher slice only.
          └─ PASS → 100k BC confirmation
                    ├─ FAIL → revert/stop learned branch
                    └─ PASS → E05 100k KL-PPO
                              ├─ regression/KL/reliability FAIL → freeze BC champion
                              └─ PASS → 3-seed confirmation → E07 500k staged
                                        ├─ no corrected gain → best earlier checkpoint
                                        └─ confirmed gain → E10 tournament/package

At any node: zero reliability or package failure tolerance.
Starmie replaces Lucario only after exact data gate and >=8 pp equal-budget advantage.
Search is never on the critical path; E09 can only decorate a stable champion.
```

## 24. Risk register

| Class | Risk | Severity | Likelihood | Mitigation/stop | Owner |
| --- | --- | --- | --- | --- | --- |
| Technical | CABT bridge corrupts action/logprob/recurrent state | Critical | Medium | E04 fail-closed qualification; zero updates before pass | Systems lead |
| Statistical | Checkpoint/deck multiple comparisons produce false winner | High | High | Holm/alpha spending; frozen candidates; confirmation after screen | Evaluation lead |
| Strategic | Visible replay/meta selection bias chooses wrong deck | High | High | 3/7/14-day sensitivity; lower bands; exact teacher/deck gates | Research lead |
| Data | Duplicate/near-duplicate episodes leak across splits | High | Medium | Episode fingerprint/dedup before split; teacher/time holdouts | Data lead |
| Learning | BC action accuracy fails on policy | Critical | High | H2H/state-divergence gates; no scale based on accuracy alone | Model lead |
| Learning | PPO forgets teacher or collapses entropy/value | High | Medium | KL/aux BC, 100k canary, per-update checkpoints/stops | RL lead |
| Runtime | Search/model exceeds CPU cumulative limit | Critical | Medium | Package-equivalent p99/game latency and 300s projected cap | Runtime lead |
| Runtime | Native memory/process leak across games | High | Medium | One battle/process where needed; soak and restart accounting | Systems lead |
| Legal/license | Modified engine/CRN or copied assets violate scope | Critical | Low-medium | Official rules review; no redistribution; no engine modification promotion | Owner/legal |
| Schedule | Data/bridge work consumes deadline without competence | Critical | Medium | 72h hard gates; deterministic hedge; abandon branches on time | Project owner |
| Leaderboard | Early rating spike drives over-selection | High | High | Local confirmation; settled games; two active distinct paths | Evaluation lead |
| Meta | Counter archetype collapses specialist | High | Medium-high | Worst-matchup floors, exploiters, complementary hedge | Policy lead |

## 25. Items to stop doing immediately

1. Stop treating the 10,000-game reliability pass, toy PPO, action accuracy or random-agent wins as progress toward gold.
2. Stop planning the 15M-choice scratch run on the engineering Abomasnow deck.
3. Stop deferring specialist/teacher selection until after generic competence training.
4. Stop treating equal anchor weights as the only ranking and the public daily top episodes as an unbiased meta sample.
5. Stop adding search, reward shaping, guards or architecture width without a predeclared control and abandonment threshold.
6. Stop optimizing TPU throughput before E03/E05 identify a promising objective.
7. Stop using live ladder spikes or current profile rank as settled evidence.
8. Stop silently changing the frozen G3b plan; issue a superseding decision record.

## 26. Research/source log summary

The accompanying log contains 142 rows: 34 project sources, 10 official/live sources, 56 archived full-read high-signal discussions, 6 late/current snippet-only discussion rows, 31 primary research sources and 5 other high-quality implementation/domain sources.

The strongest competition evidence is the combination of: (a) detailed negative results showing BC accuracy/search do not automatically transfer; (b) an existence proof that optimized pure RL can work with millions of games; (c) evidence that rule/copied specialists can be strong at low compute; and (d) the project’s unusually mature recurrent/action/PPO engineering but total absence of real competence. No one source establishes the recommended stack; it is a risk-minimizing synthesis.

## 27. Missing evidence and archive limitations

- Raw replay episode bodies and public source receipts are omitted; label safety cannot be independently completed.
- Native engine binaries/source and official raw card data are omitted; exact runtime, search, deck legality and CRN modification cannot be executed here.
- Full G2 checkpoint and TPU v2 output are omitted; exact checkpoint size and repaired throughput are unavailable.
- Live Kaggle dynamic content/leaderboard/full forum trees require authenticated access; no credentials were requested. The July 24 snapshot and July 16 full-read archive are separately labeled.
- Some tests require the original `.git` root, private layout or interpreter version. The first audit run’s environment failures are not promoted to passes.
- No exact current Starmie/Alakazam/Crustle 60-card lists are established by this pack.

## 28. Strongest argument against the recommended strategy

The imitation path may be a schedule tax. Public replays are selected, exact teachers/decks may be unavailable or unauthorized, and participant evidence shows that 66–99% offline action agreement can still produce 10–41% teacher H2H. The project already has a correct PPO stack; one participant reports pure RL reaching silver after bugs and large-scale self-play. Therefore the fastest route could be to finish the bridge immediately, choose the simplest exact deck, and spend the remaining quota on scratch PPO rather than build a data-governance/imitation pipeline.

This argument is serious. The response is not faith in imitation; it is **E01/E03 hard time and compute limits**. If no safe 25k-label corpus exists by July 26, or 25k/100k BC fails on-policy gates, the recommendation explicitly abandons imitation. Conversely, launching 15M scratch choices before a 100k competence curve is available creates a much larger irreversible opportunity cost.

## 29. Conditions that would change the recommendation

- Safe exact-deck labels do not exist: switch to deterministic hedge + bounded scratch PPO.
- A 100k scratch PPO canary reaches >55% held-out aggregate with a >50% lower bound while BC fails: reconsider PPO-first for that deck.
- Starmie passes E01 and beats Lucario by >=8 pp equal-budget with no important matchup regression: switch learned specialist.
- A deterministic specialist sustains the operational top-10 frontier with sufficient settled games: prioritize robust packaging and counter coverage over additional learning.
- E05 causes >=5 pp aggregate or >=10 pp matchup regression: stop that PPO configuration.
- Official runtime/search behavior invalidates assumptions: disable search and rerun package parity.
- Repaired TPU shows <1.5x information/hour over T4: stop TPU work.

### Mandatory self-review checklist

| Review pass | Result | Residual limitation |
| --- | --- | --- |
| Evidence completeness | **PASS WITH LIMITATION** | Every major conclusion is classed and sourced; same-minute leaderboard/full current forum tree and omitted private assets remain unavailable. |
| Adversarial | **PASS** | The pure-PPO/schedule-tax counterargument and explicit reversal triggers are included. |
| Execution | **PASS WITH GATES** | The plan fits nominal time/quota only with E01–E05 stops; no major run is authorized by this report. |

## FINAL RECOMMENDATION TO THE USER

**Primary path:** issue a new decision record that supersedes PPO-first sequencing; qualify an exact-deck teacher corpus; train the existing recurrent semantic policy by full-action autoregressive BC; then run a 100k-choice, rollback-safe, KL-regularized recurrent PPO canary and at most a staged 500k confirmation before another decision.

**Backup path:** freeze and package the included Mega Lucario deterministic specialist, with only perturbation-validated guards. Keep it shippable and evaluated while learned branches run. Dragapult is a hard anchor/high-ceiling second-wave candidate; Mega Abomasnow remains an engineering anchor.

**First three experiments:** E01 exact-deck teacher/replay-safety qualification; E04 minimal CABT bridge qualification; E02 native option-order ablation. E03 BC scaling begins immediately after E01/E02 pass.

**Abandon the imitation path** if no exact-list/two-teacher/>=25k safe corpus is available by July 26, or if 100k BC fails the on-policy/held-out thresholds. **Abandon the PPO configuration** if the 100k canary regresses aggregate by >=5 pp, an important matchup by >=10 pp, breaches KL/reliability, or fails cross-seed confirmation. **Abandon search** if the exact package lacks the API, runtime headroom, or aggregate benefit.

**Largest remaining unknown:** whether current exact-deck teacher data is safe and strong enough to create on-policy competence that transfers to the hidden, changing ladder.

**Expected compute envelope:** first 72 hours 0.5–8 GPU hours, zero TPU and 3–24 CPU evaluation hours; seven days <=20 GPU hours, <=4 optional TPU hours and <=500k on-policy choices before redecision. The 15M-choice scratch programme is not authorized.

**Preserve:** G1/G1R, G2, G3a, R1, the PPO/checkpoint/evaluation correctness stack, immutable manifests, and deterministic rule agents. **Amend:** G3b sequencing, anchor weighting, partial-update handling and option-order treatment. **Stop:** scratch PPO on the engineering deck, competence claims from diagnostics, premature TPU/search/offline-RL work, and narrative guard changes without controls.

**Gold remains possible but is not yet realistically demonstrated.** It becomes a realistic target only if the next 72 hours produce (1) a qualified specialist/teacher corpus or an unexpectedly strong deterministic/PPO canary, (2) a passing CABT bridge, and (3) an on-policy policy that clears held-out and catastrophic-matchup gates. Without those, the rational objective is a robust deterministic specialist and a disciplined final submission—not an expensive scientific programme.
