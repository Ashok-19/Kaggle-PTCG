# Dashboard D0 Audit

Date: 2026-07-17  
Status: PASS  
Timebox: D0-D2 only, four active engineering hours maximum

## Security Precondition

The approved and sole active source is the private repository
`https://github.com/Ashok-19/Kaggle-PTCG`. Its `main` was replaced with the
verified history-free lineage rooted at `08be5cec...` and none of the seven
restricted paths or blobs. `Ashok-19/Kaggle-PTCG-RL` is a private, inactive
migration backup. The Packages permission gap is recorded and explicitly
waived as non-blocking for agent development.

Dashboard ingestion is read-only and limited to tracked status/report records,
small run manifests and small job status JSON. It excludes `private/`, raw
replays, checkpoints, `.env` files, submission staging and arbitrary paths.
Serving is restricted to loopback.

## Source Inventory

| Path | Format | Authority | Available fields |
|---|---|---|---|
| `PROJECT_STATUS.md` | Markdown | Authoritative project state | gate ledger, blockers, decisions, mission clock |
| `PROGRESS_REPORT.md` | Markdown | Authoritative latest gate report | gate/status/time/commit/runs, outcomes, tests, cost, commands |
| `G0_REPOSITORY_REMEDIATION_REPORT.md` | Markdown | Authoritative remediation evidence | repository mutations, refs, scans, Packages gap, clone proof |
| `reports/gates/*.md` | Markdown | Reviewer/source evidence | decision, findings, required next work |
| `reports/gates/*.json` | JSON | Structured sidecar | gate decision, criteria, blockers, next action |
| `reports/incidents/*.{md,json}` | Markdown/JSON | Incident evidence and sidecars | exposure, containment, regression, state |
| `reports/events/*.json` | JSON | Append-only project events | timestamp, before/after, evidence |
| `configs/official.json` | JSON | Source-backed runtime config | verified limits/resources and provisional fields |
| `schemas/run_manifest.schema.json` | JSON Schema | Run producer contract | provenance, limits, status, cost, reliability |
| `runs/*/run_manifest.json` | JSON | Future authoritative run output | no tracked manifests currently exist |
| `jobs/*/*.json` | JSON | Future authoritative job output | no job records currently exist |

Ignored `runs/preflight/*.json` contains local doctor evidence. It is not
required to rebuild the tracked dashboard state and is exposed only through
the summarized gate sidecar.

## Markdown-Only Fields

The existing progress report stores exact commands, deviations, unexpected
behavior, reviewer requests, and several metric tables only in free-form
Markdown. The D1 adapter extracts stable heading fields and keeps the original
text as bounded plain text. Uncertain values remain `UNKNOWN`. Future reports
should add validated JSON sidecars rather than expanding heuristic parsing.

## Conflicts And Missing Producers

- Run schema uses `COMPLETED`/`ABORTED`; dashboard operational state uses
  `SUCCEEDED`/`ABANDONED`. The adapter maps without changing the source schema.
- Run success, experiment verdict and gate decision are independent fields.
- There are no experiment, training, replay, deck, evaluation, checkpoint or
  cloud-job producers yet. D2 shows `NOT_STARTED`, never synthetic zeroes.
- The old report's 1.6-vCPU/8-GiB claims are superseded by the current raw
  simulation settings and are retained only as historical conflict evidence.
- Exact Python patch is `PROVISIONAL` and timeout is `CONFLICT`; both are
  deferred submission-qualification work. Packages permission is `WAIVED` for
  development.

## Minimal Contracts And Adapters

- One versioned Pydantic envelope and enums for status, gate decision and
  experiment verdict.
- Structured gate, incident, event, report, run, experiment and job records.
- A bounded Markdown progress/review adapter plus direct JSON sidecars.
- One SQLite `records` index keyed by `(kind, record_id)` and source SHA-256;
  it is disposable and rebuilt only from allowlisted sources.
- Existing run manifests are adapted, not replaced or weakened.

## Layout And Commands

```text
src/ptcg_rl/dashboard/       backend models, scanner/store and FastAPI app
dashboard/frontend/          isolated React/TypeScript/Vite client
schemas/dashboard/           dashboard record contract
reports/{gates,incidents}/   authoritative sidecars and evidence
data/dashboard/              ignored disposable SQLite cache
tests/dashboard/             parser, rebuild and security checks
```

Commands: `ptcg dashboard doctor`, `ingest --once`, `rebuild`, `serve`, and
`export-snapshot --format json`. D2 adds only Command Center, Review Inbox,
Gates/Roadmap, Timeline, Reports and basic Runs/Experiments/job summaries.

## True Blockers

There is no repository/security blocker to agent implementation. G1 local work
is limited to code, unit/contract tests and tiny engine smoke. Meaningful
self-play, PPO/league training and large evaluation remain cloud-only, and
dashboard mutation controls remain out of scope.
