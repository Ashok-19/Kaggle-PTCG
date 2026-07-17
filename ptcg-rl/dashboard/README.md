# Local Dashboard

The dashboard is a read-only index over tracked project evidence. SQLite is a
disposable cache; `rebuild` recovers it from source files.

Prepare and build once:

```bash
uv sync --frozen --group dashboard --group dev
cd dashboard/frontend
npm ci
npm run build
cd ../..
uv run --no-sync ptcg dashboard rebuild
```

Start the complete local dashboard:

```bash
uv run --no-sync ptcg dashboard serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The server rejects non-loopback binds. It has no
job controls, arbitrary path access, telemetry or external runtime assets.

Other commands:

```bash
uv run --no-sync ptcg dashboard doctor
uv run --no-sync ptcg dashboard ingest --once
uv run --no-sync ptcg dashboard export-snapshot --format json
```
