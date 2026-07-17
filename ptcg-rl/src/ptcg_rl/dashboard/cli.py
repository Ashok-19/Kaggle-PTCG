from __future__ import annotations

import argparse
from pathlib import Path

from .store import DashboardStore


def run_dashboard(args: argparse.Namespace, repo: Path) -> dict[str, object]:
    store = DashboardStore(repo)
    if args.dashboard_command == "doctor":
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401

            dependencies = True
        except ImportError:
            dependencies = False
        result: dict[str, object] = {
            "status": "pass" if dependencies else "fail",
            "dependencies": dependencies,
            "database": str(store.database.relative_to(repo)),
            "frontend_built": (repo / "dashboard" / "frontend" / "dist" / "index.html").is_file(),
            "source_count": len(store.candidates()),
            "binding": "127.0.0.1 only",
        }
    elif args.dashboard_command == "ingest":
        result = store.ingest()
    elif args.dashboard_command == "rebuild":
        result = store.ingest(rebuild=True)
    elif args.dashboard_command == "export-snapshot":
        result = store.snapshot()
    else:
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("dashboard v0 serves loopback only")
        store.ingest()
        import uvicorn

        from .app import create_app

        uvicorn.run(create_app(repo), host=args.host, port=args.port)
        result = {"status": "pass"}
    return result
