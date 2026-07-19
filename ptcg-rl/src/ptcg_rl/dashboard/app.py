from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .store import DashboardStore, SourceError

ROADMAP = ("G0", "G1R", "R1", "G2", "G3a", "G3b", "D1", "G4", "G5", "G6")
ACTIVE_STATUSES = {"PLANNED", "QUEUED", "RUNNING", "BLOCKED", "IN_REVIEW"}


def create_app(repo: Path, refresh_interval_seconds: float = 2.0) -> FastAPI:
    store = DashboardStore(repo, refresh_interval_seconds=refresh_interval_seconds)
    app = FastAPI(title="PTCG RL Dashboard", version="0.2.0", docs_url="/api/docs")

    @app.middleware("http")
    async def security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def page(kind: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return store.list(kind, limit, offset)

    def ordered_gates() -> list[dict[str, Any]]:
        gates = page("gate", 100)["items"]
        order = {gate_id: index for index, gate_id in enumerate(ROADMAP)}
        return sorted(
            gates,
            key=lambda item: (
                order.get(str(item.get("gate_id")), len(order)),
                str(item.get("created_at_utc", "")),
            ),
        )

    def cost_summary(gates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        records = page("cost", 500)["items"]
        if records:
            actual = sum(float(item.get("actual_usd", 0.0) or 0.0) for item in records)
            latest = max(str(item.get("created_at_utc", "")) for item in records)
            return {
                "actual_usd": actual,
                "status": "VERIFIED",
                "as_of_utc": latest,
                "source": "cost_records",
                "items": records,
            }
        gates = gates or ordered_gates()
        actual = sum(float(item.get("cost_usd", 0.0) or 0.0) for item in gates)
        latest = max((str(item.get("updated_at_utc", "")) for item in gates), default=None)
        return {
            "actual_usd": actual,
            "status": "VERIFIED",
            "as_of_utc": latest,
            "source": "gate_records",
            "items": [],
        }

    def review_items(gates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        gates = gates or ordered_gates()
        return [
            {
                "gate_id": gate.get("gate_id"),
                "decision": gate.get("decision", "NOT_REVIEWED"),
                "status": gate.get("status", "UNKNOWN"),
                "authorization": gate.get("authorization"),
                "blockers": gate.get("blockers", []),
                "warnings": gate.get("warnings", []),
                "next_action": gate.get("approved_next_action"),
                "source_path": gate.get("source_path"),
            }
            for gate in gates
            if gate.get("decision") in {"BLOCKED", "NOT_REVIEWED"}
            and gate.get("status") != "SUCCEEDED"
        ]

    def overview_payload() -> dict[str, Any]:
        gates = ordered_gates()
        active_gates = [item for item in gates if str(item.get("status")) in ACTIVE_STATUSES]
        completed_gates = [
            item
            for item in gates
            if item.get("decision") == "PASS" or item.get("status") == "SUCCEEDED"
        ]
        incidents = page("incident", 5)["items"]
        reports = page("report", 5)["items"]
        jobs = page("job", 100)["items"]
        runtime = json.loads((repo / "configs" / "official.json").read_text(encoding="utf-8"))
        costs = cost_summary(gates)
        return {
            "objective": "Top-20 / gold finish",
            "current_gate": active_gates[0] if active_gates else (gates[-1] if gates else None),
            "active_gates": active_gates,
            "latest_completed_gate": completed_gates[-1] if completed_gates else None,
            "latest_reports": reports,
            "recent_incidents": incidents,
            "jobs": jobs,
            "active_jobs": sum(job.get("status") in {"QUEUED", "RUNNING"} for job in jobs),
            "runtime": runtime,
            "costs": costs,
            "data_health": store.health(),
            "progress": {
                "passed": len({str(item.get("gate_id")) for item in completed_gates}),
                "total": len(ROADMAP),
            },
            "champion": next(iter(page("evaluation", 100)["items"]), None),
            "challenger": None,
            "anchor": None,
        }

    @app.get("/api/v1/state")
    def state() -> dict[str, Any]:
        store.sync_if_needed()
        gates = ordered_gates()
        kinds = (
            "event",
            "decision",
            "report",
            "task",
            "hypothesis",
            "experiment",
            "run",
            "replay",
            "deck",
            "evaluation",
            "submission",
            "job",
            "artifact",
            "learning",
        )
        collections = {kind: page(kind, 500)["items"] for kind in kinds}
        return {
            "generated_at_utc": store.health().get("last_scan_utc"),
            "overview": overview_payload(),
            "review": review_items(gates),
            "gates": gates,
            **{f"{kind}s": values for kind, values in collections.items()},
            "costs": cost_summary(gates),
        }

    @app.get("/api/v1/overview")
    def overview() -> dict[str, Any]:
        return overview_payload()

    @app.get("/api/v1/review-inbox")
    def review_inbox() -> dict[str, Any]:
        items = review_items()
        return {"items": items, "total": len(items)}

    @app.get("/api/v1/gates")
    def gates(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        items = ordered_gates()
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/v1/events")
    def events(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        return page("event", limit, offset)

    @app.get("/api/v1/decisions")
    def decisions() -> dict[str, Any]:
        return page("decision", 100, 0)

    @app.get("/api/v1/reports")
    def reports(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        return page("report", limit, offset)

    @app.get("/api/v1/tasks")
    def tasks() -> dict[str, Any]:
        return page("task", 500, 0)

    @app.get("/api/v1/hypotheses")
    def hypotheses() -> dict[str, Any]:
        return page("hypothesis", 500, 0)

    @app.get("/api/v1/experiments")
    def experiments(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        return page("experiment", limit, offset)

    @app.get("/api/v1/experiments/compare")
    def compare_experiments() -> dict[str, Any]:
        items = page("experiment", 500, 0)["items"]
        return {"items": items, "total": len(items)}

    @app.get("/api/v1/runs")
    def runs(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        return page("run", limit, offset)

    @app.get("/api/v1/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        matches = [item for item in page("run", 500)["items"] if item.get("run_id") == run_id]
        if not matches:
            raise HTTPException(404, "run not found")
        return matches[0]

    @app.get("/api/v1/runs/{run_id}/metrics")
    def run_metrics(run_id: str) -> dict[str, Any]:
        run = run_detail(run_id)
        metrics = run.get("metrics", [])
        return {"run_id": run_id, "items": metrics, "total": len(metrics)}

    @app.get("/api/v1/replays/snapshots")
    def replay_snapshots() -> dict[str, Any]:
        return page("replay", 100, 0)

    @app.get("/api/v1/decks")
    def decks() -> dict[str, Any]:
        return page("deck", 100, 0)

    @app.get("/api/v1/training/league")
    def league() -> dict[str, Any]:
        evaluations = page("evaluation", 100, 0)["items"]
        return {
            "status": "NOT_STARTED" if not evaluations else "ACTIVE",
            "items": evaluations,
        }

    @app.get("/api/v1/evaluations")
    def evaluations() -> dict[str, Any]:
        return page("evaluation", 100, 0)

    @app.get("/api/v1/submissions")
    def submissions() -> dict[str, Any]:
        return page("submission", 100, 0)

    @app.get("/api/v1/jobs")
    def jobs() -> dict[str, Any]:
        return page("job", 100, 0)

    @app.get("/api/v1/costs")
    def costs() -> dict[str, Any]:
        return cost_summary()

    @app.get("/api/v1/incidents")
    def incidents(
        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
    ) -> dict[str, Any]:
        return page("incident", limit, offset)

    @app.get("/api/v1/artifacts")
    def artifacts() -> dict[str, Any]:
        return page("artifact", 100, 0)

    @app.get("/api/v1/learning")
    def learning() -> dict[str, Any]:
        return page("learning", 100, 0)

    @app.get("/api/v1/data-health")
    def data_health() -> dict[str, Any]:
        return store.health()

    @app.get("/api/v1/evidence")
    def evidence(path: str = Query(min_length=1, max_length=500)) -> dict[str, Any]:
        try:
            return store.read_source(path)
        except SourceError as error:
            raise HTTPException(404, str(error)) from error

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
