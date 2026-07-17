from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .store import DashboardStore


def create_app(repo: Path) -> FastAPI:
    store = DashboardStore(repo)
    app = FastAPI(title="PTCG RL Dashboard", version="0.1.0", docs_url="/api/docs")

    @app.middleware("http")
    async def security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def page(kind: str, limit: int, offset: int) -> dict[str, Any]:
        return store.list(kind, limit, offset)

    @app.get("/api/v1/overview")
    def overview() -> dict[str, Any]:
        gates = store.list("gate", 10)["items"]
        gate = next(
            (item for item in gates if item.get("status") in {"PLANNED", "QUEUED", "RUNNING", "BLOCKED"}),
            gates[0] if gates else None,
        )
        incidents = store.list("incident", 5)["items"]
        reports = store.list("report", 5)["items"]
        jobs = store.list("job", 20)["items"]
        runtime = json.loads((repo / "configs" / "official.json").read_text(encoding="utf-8"))
        return {
            "objective": "Top-20 / gold finish",
            "current_gate": gate,
            "latest_reports": reports,
            "recent_incidents": incidents,
            "jobs": jobs,
            "active_jobs": sum(job.get("status") == "RUNNING" for job in jobs),
            "runtime": runtime,
            "data_health": store.health(),
            "champion": None,
            "challenger": None,
            "anchor": None,
        }

    @app.get("/api/v1/review-inbox")
    def review_inbox() -> dict[str, Any]:
        gates = store.list("gate", 20)["items"]
        items = [
            {
                "gate_id": gate.get("gate_id"),
                "decision": gate.get("decision", "NOT_REVIEWED"),
                "blockers": gate.get("blockers", []),
                "warnings": gate.get("warnings", []),
                "next_action": gate.get("approved_next_action"),
                "source_path": gate.get("source_path"),
            }
            for gate in gates
            if gate.get("decision") in {"BLOCKED", "NOT_REVIEWED"}
        ]
        return {"items": items, "total": len(items)}

    @app.get("/api/v1/gates")
    def gates(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("gate", limit, offset)

    @app.get("/api/v1/events")
    def events(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("event", limit, offset)

    @app.get("/api/v1/decisions")
    def decisions() -> dict[str, Any]:
        return page("decision", 100, 0)

    @app.get("/api/v1/reports")
    def reports(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("report", limit, offset)

    @app.get("/api/v1/experiments")
    def experiments(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("experiment", limit, offset)

    @app.get("/api/v1/experiments/compare")
    def compare_experiments() -> dict[str, Any]:
        return {"items": [], "total": 0, "message": "No experiments have started."}

    @app.get("/api/v1/runs")
    def runs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("run", limit, offset)

    @app.get("/api/v1/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        matches = [item for item in store.list("run", 500)["items"] if item.get("run_id") == run_id]
        if not matches:
            raise HTTPException(404, "run not found")
        return matches[0]

    @app.get("/api/v1/runs/{run_id}/metrics")
    def run_metrics(run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "items": [], "total": 0, "message": "No metric producer exists yet."}

    @app.get("/api/v1/replays/snapshots")
    def replay_snapshots() -> dict[str, Any]:
        return page("replay", 100, 0)

    @app.get("/api/v1/decks")
    def decks() -> dict[str, Any]:
        return page("deck", 100, 0)

    @app.get("/api/v1/training/league")
    def league() -> dict[str, Any]:
        return {"status": "NOT_STARTED", "items": []}

    @app.get("/api/v1/evaluations")
    def evaluations() -> dict[str, Any]:
        return page("evaluation", 100, 0)

    @app.get("/api/v1/jobs")
    def jobs() -> dict[str, Any]:
        return page("job", 100, 0)

    @app.get("/api/v1/costs")
    def costs() -> dict[str, Any]:
        return {"actual_usd": 0, "status": "VERIFIED", "as_of_utc": "2026-07-17T15:51:27Z"}

    @app.get("/api/v1/incidents")
    def incidents(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return page("incident", limit, offset)

    @app.get("/api/v1/artifacts")
    def artifacts() -> dict[str, Any]:
        return page("artifact", 100, 0)

    @app.get("/api/v1/data-health")
    def data_health() -> dict[str, Any]:
        return store.health()

    dist = repo / "dashboard" / "frontend" / "dist"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(503, "frontend is not built; run npm run build in dashboard/frontend")
        return FileResponse(index)

    return app
