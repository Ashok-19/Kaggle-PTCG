# 04 — Filtered Replay Ingestion and Meta Pipeline

## Purpose and hard constraint

The official [episode index dataset](https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index) is small and points to one daily replay dataset per published day. At the time of this handoff, daily datasets were often capped near 20 GiB and contained thousands of episodes. The local machine has about 30 GiB free, so a whole-daily-dataset fallback is forbidden.

The required flow is:

```text
small index manifest
  → new/changed daily rows
  → one daily manifest.csv per selected day
  → local filter + byte estimate
  → explicit approved file plan
  → individual episode downloads
  → validation/catalog
  → normalized analytical tables
```

Kaggle’s official [KaggleHub client](https://github.com/Kaggle/kagglehub) documents single-file dataset download via `dataset_download(handle, path=...)`. The user prefers a local Kaggle MCP workflow. Implement a provider abstraction so MCP is preferred but KaggleHub/CLI can be a tested fallback. Never invent an MCP API: the user will supply the exact local tool names and filter/download semantics.

## Data-use firewall

Create separate packages and storage roots:

- `replay/intelligence`: may read public replay actions for analysis/debugging;
- `rl/rollout`: accepts only trajectories tagged `source=self_rollout`;
- `data/public_replays`: never imported by training modules;
- `data/self_play`: only location accepted by PPO dataset constructors.

Enforce with:

- typed provenance enum (`PUBLIC_REPLAY`, `SELF_ROLLOUT`, `ENGINE_FIXTURE`);
- PPO buffer assertion `source == SELF_ROLLOUT`;
- dependency test that `ptcg_rl.rl` does not import `ptcg_rl.replay.parse`;
- integration test attempting public-to-PPO ingestion and expecting rejection.

Public actions may be inspected to extract strategy hypotheses, context coverage and mistakes. They are not action labels, policy logits, advantages or v0 value targets.

## Provider protocol

```python
@dataclass(frozen=True)
class DatasetRef:
    owner: str
    slug: str
    version: int

class ReplayProvider(Protocol):
    def resolve_latest(self, owner: str, slug: str) -> DatasetMetadata: ...
    def fetch_file(self, dataset: DatasetRef, filename: str, destination: Path) -> FileReceipt: ...
    def stat_file(self, dataset: DatasetRef, filename: str) -> RemoteFileInfo | None: ...
```

Implement:

1. `McpInboxProvider` — Python exports a version-pinned plan; local Codex uses the real MCP to place exact named files plus a structured receipt in an inbox; Python verifies/imports them. This is the preferred default because an interactive MCP is not automatically callable from project Python.
2. `KaggleMcpProvider` — optional direct adapter only after R0 proves the actual callable interface and version resolution.
3. `KaggleHubProvider` — official Python fallback using a version-pinned **single file path**.
4. `KaggleCliProvider` — optional operational fallback after confirming its exact single-file behavior.
5. `FilesystemProvider` — deterministic tests and already-downloaded data.

Provider requirements:

- never log credentials, tokens or signed URLs;
- accept only `manifest.csv` or filenames matching `^[0-9]+\.json$`, and keep destinations inside the replay root;
- return file bytes/path plus dataset handle/version, requested filename, actual byte count, hash and retrieval time;
- atomic `.partial` download followed by hash/parse validation and rename;
- bounded retries with exponential backoff for transport errors only;
- no automatic whole-dataset call when a file is missing;
- fail closed if the provider cannot guarantee single-file retrieval.

The index supplies daily slugs but not their version numbers. Resolve and record each dataset’s `currentVersionNumber` before fetching its manifest, then pin that explicit version in the immutable plan and every receipt. A “latest” handle is never valid inside an executable plan. The MCP inbox receipt is machine-readable JSON containing dataset owner/slug/version, requested filename, manifest or content SHA-256, actual bytes, retrieval time and provider identity. Import fails closed if the receipt is missing, its pinned version differs from the plan, or its hash does not match the delivered file.

Inspect returned magic bytes. Some client modes may materialize a ZIP even for a requested file; if so, extract only the exact expected member with path and expanded-size limits. Set `KAGGLEHUB_CACHE` inside the accounted replay root so hidden cache copies cannot bypass the local disk cap.

## R0 — Schema discovery before downloader implementation

The index manifest schema observed on 2026-07-17 was:

```text
date,daily_dataset_slug,daily_dataset_url,episode_count,total_bytes,top_avg_score,median_avg_score
```

Re-fetch and validate it; do not hardcode this snapshot as eternal.

The 2026-07-16 daily `manifest.csv` was independently verified as:

```text
episode_id,create_time,avg_score,min_score,sum_score,agent_count,size_bytes
```

It had 4,760 rows and `sum(size_bytes)=21,473,862,236`, matching the index. Median episode size was about 4.27 MB, p95 about 6.97 MB and maximum about 265 MB. Episode filenames were `<episode_id>.json`. Re-verify this against the user’s current dataset/version rather than treating it as permanent.

R0 procedure:

1. retrieve only the official index `manifest.csv`;
2. select one recent daily dataset row;
3. retrieve only that daily `manifest.csv`;
4. save header, dtypes, 5 redacted sample rows and byte-size summary;
5. identify the exact episode ID/path convention, rating/score columns, episode size and timestamp fields;
6. map aliases into a versioned canonical schema;
7. show the user a dry-run filter plan before any episode JSON download.

The verified daily manifest has only episode-level scores—not seat-specific rating, agent, card, deck or archetype fields. Never assign `avg_score`, `min_score` or `sum_score` to one player/deck. Pre-download filtering can use date/time, episode-level score and size; deck/archetype diversity becomes possible only after parsing. If a future manifest lacks sizes, `stat_file` individually or use a conservative configured maximum when calculating the hard cap. Unknown size means ineligible unless the user explicitly raises the risk budget.

## Catalog

Use SQLite in WAL mode with one writer for the transactional operational ledger. Write normalized analytical tables as versioned, partitioned Parquet and query/report them with DuckDB. This separates download state/recovery from columnar analysis while staying lightweight.

Minimum tables:

### `dataset_versions`

```text
dataset_handle, version, published_at, source_hash, first_seen_at, last_seen_at
```

### `daily_manifests`

```text
date, dataset_handle, version, manifest_hash, episode_count, total_bytes,
top_avg_score, median_avg_score, fetched_at, schema_version
```

### `episode_catalog`

```text
(dataset_handle, dataset_version, episode_id) primary key,
date, remote_filename, declared_bytes, episode-level score fields,
filter_features_json, selection_status, rejection_reason
```

### `download_ledger`

```text
(dataset_handle, dataset_version, episode_id) foreign/source key,
remote_filename, planned_bytes, actual_bytes, sha256,
provider, started_at, completed_at, state, error_code, retry_count, local_path
```

### `episodes`

```text
source key, date, status_0, status_1, reward_0, reward_1, quality_class,
players, turns, decision_count, terminal_reason,
raw_sha256, parser_version, valid, validation_errors
```

### `decks` and `episode_decks`

Canonical sorted multiset fingerprint plus the original 60-card ordered/list representation, card counts, inferred archetype, confidence and player side.

### `decisions` / `events`

Normalized public context/event statistics for analysis. Keep action contents in the intelligence namespace and never export them to self-play rollout files.

Use primary keys and foreign-key/referential QA queries. Schema changes require a migration and parser version bump.

## Selection plan

Configuration lives in the replay profile files under `configs/`. `replay_schema_probe.yaml` is a one-time R0 probe, `replay_filter.example.yaml` is a one-time seven-day bootstrap, `replay_daily_latest.example.yaml` is the standing incremental job, and `replay_stability_extension.example.yaml` supplies low-budget days 8–14 when needed. The planner must support:

- date range and rolling windows;
- rolling windows anchored to the latest published index date, not the local clock;
- daily top `k` or episode-level score/rating quantile;
- exact agent/deck inclusion/exclusion only if a future verified source exposes it;
- explicitly post-parse per-deck/archetype coverage checks for later iterative refresh plans;
- per-day and total episode caps;
- per-day and total byte caps;
- maximum single-file size;
- deduplication by episode ID and content hash;
- deterministic sampling seed over manifest rows;
- already-downloaded/parsed exclusion;

The default first run is deliberately small: one day, the manifest plus at most 20 episodes and at most 250 MiB. The user must edit/approve the real filter after inspecting R0 columns. Source-profile type and its completed watermark are part of the immutable plan, so a standing daily sync cannot accidentally reuse one-time bootstrap semantics.

Initial pre-download selection should be stratified, not only top-rated:

- about 60% uniformly sampled without replacement where daily `avg_score` quantile ≥0.85 and `min_score` quantile ≥0.70;
- about 25% uniformly sampled without replacement from remaining rows where daily `avg_score` quantile ≥0.85;
- about 15% uniformly sampled without replacement from remaining rows across deterministic source-day time blocks;
- a 64 MiB default maximum individual file size, with oversize exclusions reported;
- a smaller broad sample to avoid top-only selection bias;
- explicit equal-per-day quotas (or another predeclared allocation rule) so large/new days cannot consume the whole plan.

Compute daily quantile thresholds over **all structurally valid manifest rows before** downloaded-state, file-size and byte-budget filters. Record those populations, thresholds and the exact selection algorithm in the immutable plan. Do not prefer the smallest files merely to maximize episode count; unusually small files may overrepresent early failures/errors. Size is a cap, not a quality score. Once an initial corpus is parsed, measure exact deck/archetype coverage and request additional date/time/rating strata iteratively, but do not claim deck-prefiltering that the manifest cannot perform.

If sampled quotas exceed the byte cap, deterministically reduce/resample quotas proportionally across day × stratum cells until the plan fits. Do not truncate by manifest row order or greedily keep smaller files. Record every removed row/reason, final cell population and inclusion probability.

Preserve `create_time` as its raw string. Current values contain fractional seconds but no verified timezone suffix; any UTC interpretation must be an explicit parser assumption. Define time blocks within the published source day unless/until timezone semantics are verified.

The host dataset is itself selected and size-capped, so its distribution is not the complete ladder. Report both (a) raw share in the intentional downloaded mixture and (b) an inclusion-weighted estimate for the **eligible host daily corpus** using recorded stratum population sizes/probabilities. Neither is ladder prevalence; label both accordingly and use sensitivity analysis before deriving evaluation weights.

## Dry-run is mandatory

Target CLI contract for local Codex to implement (these commands do not exist until R0 code is written):

```bash
# Python creates exact MCP requests; local Codex executes them with the real MCP.
uv run ptcg replay plan-mcp-index --out runs/mcp-index-request.json
# Local Codex downloads the named index manifest to the request inbox.
uv run ptcg replay inbox import-index --request runs/mcp-index-request.json
uv run ptcg replay plan-mcp-manifests --latest-published-days 1 --out runs/mcp-manifest-request.json
# Local Codex downloads the named daily manifests to the request inbox.
uv run ptcg replay inbox import-manifests --request runs/mcp-manifest-request.json
uv run ptcg replay plan --config configs/replay_schema_probe.yaml --out runs/replay-plan.json
uv run ptcg replay download --plan runs/replay-plan.json --dry-run
# User reviews exact count/bytes/files.
uv run ptcg replay plan export-mcp --plan runs/replay-plan.json --out runs/mcp-plan.json
# Local Codex downloads only named files through the configured MCP into the plan inbox.
# Python verifies receipts/hashes, atomically promotes files and updates the ledger.
uv run ptcg replay inbox import-episodes --plan runs/replay-plan.json
# Or, only after provider proof: direct version-pinned KaggleHub single-file downloads.
uv run ptcg replay download --provider kagglehub --plan runs/replay-plan.json --confirm-plan-sha256 <hash>
uv run ptcg replay parse --plan runs/replay-plan.json
uv run ptcg replay meta --windows 3d,7d,14d
```

The plan contains:

- immutable index/daily manifest hashes;
- exact remote dataset version and filenames;
- selection/rejection reason per row;
- declared/estimated bytes per file and totals;
- hard caps;
- deterministic plan hash.

Synchronization always resolves the newest index first; only the generated plan pins the resolved index and daily dataset versions. The downloader refuses a changed manifest, version or plan hash. `--dry-run` must perform zero episode-file network writes.

Distinguish idempotent plan replay from new backfill. Rerunning the same completed plan transfers zero bytes. The standing daily job persists a completed watermark `(manifest_hash, selection_profile_hash, planner_version)` and skips that source/profile unless `--backfill` or `--refresh` is explicit; otherwise “exclude already verified” would silently select a new unseen batch on every run.

## Download and storage policy

Recommended local allocation (change only after checking free space):

- 8 GiB minimum emergency free-space floor;
- 10 GiB raw replay hard ceiling;
- 8 GiB normalized/derived ceiling;
- remaining space for source, environment, engine, logs and checkpoints.

Before executing a plan require `free space >= planned content + worst-case temporary/cache duplication + emergency floor`.

Before each file:

1. verify remaining plan and filesystem hard caps;
2. create destination on the same filesystem for atomic rename;
3. stream to `.partial`;
4. verify extracted JSON content bytes against manifest `size_bytes` and record content hash separately from compressed/transport bytes/hash;
5. parse JSON envelope and expected episode identity;
6. rename and update ledger transactionally.

After successful normalization and backup, raw episode retention can be `keep`, `compress` or `delete_after_hash_and_backup`. Default to compression until the parser is trusted. Deletion mode must fail unless a configured backup target produces a verified checksum receipt. Never delete the only copy of an expensive filtered corpus.

## Parser and normalization QA

Current replay probes observed top-level fields including `configuration`, `id`, `info`, `module_version`, `rewards`, `schema_version`, `statuses`, `steps` and `specification`. Register parsers by `(environment, schema_version, module_version major/minor)` and quarantine unknown schemas instead of guessing.

Current exact-deck extraction pattern:

- each seat submits a 60-integer deck action early in the replay;
- detect the **first qualifying 60-card action per seat** before ordinary play;
- do not hardcode `steps[1]`;
- store replay `module_version` plus the local engine and card-CSV hashes used for validation;
- claim exact replay-version validation only when a maintained `module_version → engine/card assets` mapping identifies those exact assets; otherwise label the result **current-asset compatibility**, not exact historical legality;
- canonical deck identity is the card-data hash plus the sorted `(card_id, multiplicity)` multiset; preserve original order separately for audit.

Do not depend on a `visualize` field: it may expose complete state, may exist for only one seat and may disappear in later schemas. It is offline/debug-only.

For replay terminal truth, prefer top-level `statuses` and `rewards`, then final per-agent status/reward. Do not reuse the live-engine `current.result` assumption blindly in replay parsing; terminal observations can be stale. Make terminal quality classes mutually exclusive. Classify at least:

- `VALID_DECISIVE`: both top-level statuses are `DONE` and rewards are exactly `{-1,+1}`;
- `VALID_DRAW`: both top-level statuses are `DONE` and rewards are exactly `{0,0}`;
- `AGENT_ERROR`;
- `TIMEOUT`;
- `INCOMPLETE`;
- `SCHEMA_UNSUPPORTED`;
- `CORRUPT`;
- `DECK_EXTRACTION_FAILED`;
- `DECK_ILLEGAL_CURRENT_RULESET`.

Very small files are not automatically efficient useful samples; they can be early errors. Keep size as a safety constraint, not a quality proxy.

Validate:

- JSON is complete, parseable and within nesting/size limits;
- exactly one episode identity and coherent players;
- initial deck response, forced one-option, optional empty selection, multi-select and terminal/no-op rows are understood;
- decisions are monotonic and terminal result exists or is explicitly classified incomplete;
- card IDs resolve against the declared validation card-data hash, with unknowns reported and exact-versus-current-compatibility status explicit;
- deck lists satisfy the observed/official format; partial hidden decks are labeled partial, never silently completed;
- top-level statuses/rewards agree with final per-agent statuses/rewards; treat `current.result` and log disagreements as diagnostic warnings, never terminal truth;
- no impossible player/zone reference;
- duplicate content hashes are linked, not reprocessed.

For starting-player analysis, scan observations in chronological order and take the first populated `current.firstPlayer` value in `{0,1}`. Every later populated value must agree. If no valid value exists or later values conflict, store `UNKNOWN` and exclude that episode from starting-player denominators while retaining it for other valid analyses.

Quarantine malformed data under an error code. Never silently drop malformed rows from denominators; reports include counts and reasons.

## Meta outputs

For rolling 3/7/14-day windows, generate:

- exact deck fingerprints and archetype clusters;
- frequency with uncertainty and selection-bias warning;
- episode-level rating context among sampled games containing each deck, never attributed to a particular seat or deck;
- deck × opponent result matrix where observable;
- starting-seat split;
- game length/decision-count distributions;
- legal branching and multi-select context distributions if parsable;
- emerging/declining deck changes;
- unknown/low-confidence clustering rate;
- source-day and pseudonymized display-name coverage, without treating display names as stable agent IDs;
- candidate deck lists with provenance.

Use the last seven days as the primary deck-selection meta, last three days for emergence and last fourteen days for stability. A 14-day result is legal only when the catalog contains declared coverage for days 8–14, normally from `replay_stability_extension.example.yaml`; otherwise emit `INSUFFICIENT_COVERAGE` instead of silently reusing a shorter window. Freeze a timestamped snapshot before every deck bakeoff or promotion evaluation.

Deck/matchup win-rate tables include only `VALID_DECISIVE` and `VALID_DRAW`. Analyze `AGENT_ERROR`, `TIMEOUT`, null-reward, incomplete and other quality classes separately so infrastructure failures cannot masquerade as strategic evidence.

## Incremental update schedule

Daily local job (manual or scheduled later):

1. fetch index manifest;
2. compare dataset/version/hash with catalog;
3. fetch only new/changed daily manifests;
4. produce plan and summary;
5. require approval if bytes exceed the standing daily cap or filters changed;
6. download selected files;
7. parse, QA and update rolling reports;
8. emit `replay_sync_report.json` and progress summary.

Idempotency acceptance: running the same job twice with unchanged manifests downloads zero episode bytes and produces semantically identical derived tables.

## Tests and Gate R1

- provider contract tests with a fake filesystem server;
- MCP plan/export/inbox verification tests; direct MCP provider remains optional;
- path-traversal and malicious filename tests;
- no whole-dataset-call sentinel test;
- byte cap tested under declared, missing and incorrect sizes;
- atomic interruption/resume tests;
- manifest version/hash drift test;
- deterministic planner golden test;
- composite source-version/episode key plus duplicate-content-hash test;
- corrupted/truncated/oversized JSON quarantine test;
- parser fixtures for all selection shapes;
- provenance firewall test rejecting public data in PPO;
- end-to-end test using only one manifest and 2–5 tiny local fixtures.

Gate R1 additionally requires a user-reviewed real dry run, a small successful real download, zero duplicate transfer on rerun and a reproducible seven-day meta report.
