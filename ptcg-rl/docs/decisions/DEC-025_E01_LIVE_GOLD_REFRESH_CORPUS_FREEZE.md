# DEC-025 - Refresh live gold state, freeze the approved corpus, and prepare bounded unauthorized requests

Status: Accepted

Date: 2026-08-04

## Decision

Accept the authenticated August 4 live-state refresh and supersede DEC-024 only for the current source-wait conclusion. Current rank-1 Majkel1337 submission `55186239` has an exact metadata-only intersection of `271` available replay JSON files totaling `1,031,040,048` declared bytes with `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03`, version `1`, status `Ready`.

Prepare, but do not authorize or execute, the smallest exact opposite-seat, both-winning source probe:

- `89651832.json` - `376,976` bytes - teacher seat 1 - teacher reward +1
- `89802438.json` - `455,901` bytes - teacher seat 0 - teacher reward +1
- exact total: `832,877` bytes
- request: `configs/e01_majkel_live_gold_teacher_probe_request_v1.json`

The request requires a new exact request and separate explicit user approval before either replay body may be retrieved. No replay body, agent log, private export, label file, optimizer step, external-compute run, submission, commit, or push is authorized by this decision.

Independently accept the immutable inventory of all already approved replay bodies:

- `82` files
- `453,143,981` bytes
- `66` qualified teacher episodes
- `50 / 8 / 8` episode-level train / validation / test split
- zero duplicate source keys, duplicate content hashes, or cross-split episodes

Correct the confirmation accounting. The previously reported `7,542` value is the number of active teacher requests. It includes `402` deterministic forced singleton requests that must advance recurrent state but must create no policy loss. The valid policy-loss target count is therefore `7,140`, leaving shortfalls of `134` episodes and `17,860` policy-loss targets against the `200` episode and `25,000` target floors.

Preserve the full supervision contract: lag alignment, complete compound actions, ordered multi-selection without replacement, first-class STOP, exact legal-option masks, recurrent sequence boundaries, terminal/truncation boundaries, and forced recurrence without policy loss.

Prepare, but do not authorize or execute, the exact local-CPU BC engineering canary in `configs/e01_bc_engineering_canary_request_v1.json`: eight train-split episodes, two independent teachers, four seat/result strata per teacher, at most 64 AdamW optimizer steps, deterministic resume checks, and a non-promotable checkpoint. This is an engineering canary only and cannot establish policy competence or authorize production training.

## Live evidence

The official competition evidence refreshed in `reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json` records:

- final deadline: `2026-08-16 23:59 UTC`
- entry and team-merger cutoff: `2026-08-09 23:59 UTC`
- daily submission limit: `5`
- latest complete source: August 3 dataset version 1, `4,720` available JSON bodies and one manifest CSV
- four manifest metadata rows have no corresponding JSON body; exact intersections use available JSON filenames only
- simulation scores are dynamic snapshots and are not an authorization basis; stable team, submission, dataset, episode, and byte identities are the authorization basis
- exact post-July-30 host messages are recorded, including the August 2-3 Strategy-qualification and second-round simulation clarifications

## Implementation update - exact Majkel probe

The user separately approved the exact request SHA-256 `e0b43f2a507728f5b2048a9ac7d8e30b6f444448e74885503267058477029886`. The one-time authorization was consumed on 2026-08-04. Exactly the two named replay bodies were retrieved into the bound output directory at the exact `832,877`-byte cap:

- `89651832.json` - `376,976` bytes - SHA-256 `6e03791819464b8376423a7e2d0cda171cf4abfc1541ac84cd2b90069aeec288`
- `89802438.json` - `455,901` bytes - SHA-256 `ec5ab4bce6e29c8062f504ae24aac754d83c32689103ec3e997d4ab44cfe97e2`

Deterministic body-level review passed schema, environment, terminal, reward, opposite-seat, current-card deck construction and lag-aligned action checks. Both episodes use exact Mega Lucario deck multiset SHA-256 `dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278`. The pair spans a reviewed module transition from `1.32.2` to `1.32.3`; both modules satisfy the same action contract. It contains 35 teacher requests, including 3 forced singleton requests, leaving 32 potential policy-loss targets if a later approval permits promotion.

The consumed request SHA-256 is `5a35b00b201dd4ab8cf9f054ec62a152ea06ce121726e89c3f78139ff1efd63f`. Evidence is `reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json`, review self-hash `a9dfd2d92f10b95aad3032566e3f5bd7973d007d81ef19722ebf3ec4452efead`.

The two episodes are not added to the approved corpus and no labels were created. No agent logs, additional replay, optimizer steps, training, external compute, submission, commit or push occurred.

## Authorization state

- replay transfer: false
- agent logs: false
- raw/private exports: false
- label generation: false
- BC optimizer steps: false
- PPO optimizer steps: false
- production training: false
- external compute: false
- model promotion: false
- competition submission: false
- Git commit: false
- Git push: false

## Required next approvals

1. The exact two-file Majkel approval is consumed and cannot authorize any further replay or corpus promotion.
2. Separate explicit approval of the exact 64-step local-CPU BC engineering canary request after its implementation and preflight reviews remain hash-valid.
3. Separate explicit approval before promoting either Majkel episode or its 32 potential policy-loss targets into the approved corpus.

Training and submission remain blocked. Gold remains the optimization target, not a guarantee.

## Revisit trigger

Revisit when the BC canary is approved or rejected; Majkel corpus promotion is proposed; any bound source, submission, episode, byte, corpus, split, semantic, code, asset, or review hash changes; a stronger source becomes available; or any further optimizer, replay, external-compute, submission, commit, or push scope is proposed.
