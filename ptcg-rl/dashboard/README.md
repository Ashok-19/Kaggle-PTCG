# Local Dashboard

The dashboard is a read-only research cockpit over tracked, machine-readable
project evidence. SQLite is a disposable cache; source reports, gate records,
experiment manifests and other allowlisted JSON/Markdown remain authoritative.

The server computes a signature over allowlisted source files and rebuilds the
cache when they change. The browser refreshes `/api/v1/state` every 15 seconds,
so completed work appears without a manual rebuild or page reload. Deleted
records are removed from the cache. Invalid sources are quarantined and shown
through data health rather than silently ignored.

## Views

- Command Center: parallel active gates, mission clock, tasks, cost and blockers.
- Gates & Roadmap: evidence-gated campaign progress.
- Runs & Experiments: experiment manifests, immutable runs and jobs.
- Hypotheses: falsifiable claims with evidence for, evidence against and next tests.
- Evidence: decisions, append-only events, reports and bounded source previews.
- Learning Lab: beginner-first explanation backed by tracked learning records.
- Decks & Submissions: deck, evaluation and submission qualification state.
- Review Inbox: gates that are not independently reviewed or are blocked.

Missing producers display `NOT_STARTED`; the dashboard never invents scores,
costs, experiments, decks, champions or completion.

## Build and run

```bash
uv sync --frozen --group dashboard --group dev
cd dashboard/frontend
npm ci
npm test -- --run
npm run build
cd ../..
uv run --no-sync ptcg dashboard rebuild
uv run --no-sync ptcg dashboard serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The server rejects non-loopback binds. It has no
job controls, arbitrary path access, telemetry or external runtime assets.
Evidence previews are restricted to the same bounded allowlist used by the
index. Private assets, replay bodies, checkpoints, credentials and submission
staging are not served.

## Other commands

```bash
uv run --no-sync ptcg dashboard doctor
uv run --no-sync ptcg dashboard ingest --once
uv run --no-sync ptcg dashboard export-snapshot --format json
```
