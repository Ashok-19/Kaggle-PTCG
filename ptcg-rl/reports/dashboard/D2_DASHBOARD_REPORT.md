# Dashboard D0-D2 Report

Date: 2026-07-17  
Outcome: **PASS**  
Phase status: D0 PASS, D1 PASS, D2 PASS; stopped before D3

## Delivered

- D0 source/authority/security audit in `reports/dashboard/D0_AUDIT.md`.
- Pydantic record envelope and status/decision/verdict enums plus a versioned
  dashboard JSON Schema.
- Read-only allowlisted ingestion for current status, progress/review reports,
  gate/incident/event sidecars, future run manifests and future job records.
- Disposable SQLite cache in WAL mode with idempotent scan, quarantine,
  deterministic rebuild, source hashes and data-health output.
- CLI: `dashboard doctor`, `ingest --once`, `rebuild`, `serve`, and
  `export-snapshot --format json`.
- FastAPI endpoints for the D2 views plus typed empty/not-started responses for
  producers that do not yet exist.
- React/TypeScript/Vite UI with Command Center, Review Inbox, Gates/Roadmap,
  Timeline, Reports, basic Runs/Experiments and jobs/blockers summary.
- Responsive dark/light UI, persistent navigation, search, status icon/text,
  evidence drawer, safe plain-text Markdown and explicit unknown/conflict states.

The Command Center shows G0 passed and G1 as approved next work, while retaining
the contained history incident, waived Packages note, deferred submission
runtime facts, `202400 KB` limit, raw resources, timeout conflict and USD 0.

## Schemas And Cache

- Schema: `schemas/dashboard/record.schema.json`
- Models: `src/ptcg_rl/dashboard/models.py`
- Cache: ignored `data/dashboard/dashboard.sqlite`, currently about `92 KB`
- Rebuild input: 9 allowlisted sources producing 11 records and 0 quarantine errors
- Source files remain authoritative; ingestion never mutates them.

## Verification

```text
uv run --no-sync ruff check .                 All checks passed
uv run --no-sync pytest -q                    10 passed
npm test                                      2 passed
npm run build                                 PASS; 205 KB JS / 12 KB CSS
npm audit                                     0 vulnerabilities
npm run e2e                                   3 passed
ptcg dashboard rebuild                        11 ingested, 0 quarantined
ptcg dashboard doctor                         PASS, frontend built, loopback only
```

Playwright verified that G0 completion advances the command center to G1, gate
and incident evidence remains navigable, and the mobile command center is usable.
Observed test navigation completed well below two seconds; the production
bundle has no CDN or runtime external asset dependency.

## Screenshots

- `reports/dashboard/screenshots/command-center.png`
- `reports/dashboard/screenshots/gates-roadmap.png`
- `reports/dashboard/screenshots/command-center-mobile.png`

## Security Checks

- Server rejects non-loopback hosts.
- Traversal, escaping symlink, secret-pattern and oversized-source tests pass.
- Private assets, raw replays, checkpoints, `.env` and submission staging are
  outside the allowlist and never exposed.
- CSP, no-sniff and no-referrer headers are set.
- No dashboard mutation/job controls, arbitrary commands, telemetry or cloud
  credentials exist.

## Known Gaps And Deviations

- D3-D6 were intentionally not started. There are no real experiment, replay,
  deck, league, evaluation, checkpoint or cloud-job producers yet.
- Markdown parsing is a bounded compatibility adapter; structured JSON sidecars
  are the forward path.
- SQLite is intentionally simple; DuckDB, queues, WebSockets and chart libraries
  were not added without measured data need.
- GitHub Packages permission is recorded and waived as non-blocking for agent
  development.
- `Ashok-19/Kaggle-PTCG` is the sole active source; the RL repository is an
  inactive private migration backup.

## Recommended Next Phase

Do not start D3 for empty data. Begin G1 contract/schema implementation and add
D3 views only when the first real run/experiment producer exists. Training and
authoritative artifacts were not modified by dashboard ingestion or serving.
