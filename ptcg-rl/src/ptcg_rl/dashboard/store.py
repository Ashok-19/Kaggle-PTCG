from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import RecordEnvelope

MAX_SOURCE_BYTES = 1_048_576
MAX_EVIDENCE_CHARS = 200_000
SECRET_PATTERN = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)
STATUS_PATTERN = re.compile(
    r"^(?:Status|Gate status):\s*\*{0,2}([^\n*]+)", re.MULTILINE | re.IGNORECASE
)
FIELD_PATTERN = re.compile(r"^([^\n:]{2,40}):\s*(.+?)\s*$", re.MULTILINE)

REPORT_KIND_DIRECTORIES = {
    "gates": "gate",
    "incidents": "incident",
    "events": "event",
    "runs": "run",
    "decisions": "decision",
    "tasks": "task",
    "hypotheses": "hypothesis",
    "experiments": "experiment",
    "submissions": "submission",
    "replays": "replay",
    "decks": "deck",
    "evaluations": "evaluation",
    "costs": "cost",
    "artifacts": "artifact",
    "learning": "learning",
}


class SourceError(ValueError):
    pass


class DashboardStore:
    def __init__(
        self,
        repo: Path,
        database: Path | None = None,
        refresh_interval_seconds: float = 2.0,
    ) -> None:
        self.repo = repo.resolve()
        self.database = database or self.repo / "data" / "dashboard" / "dashboard.sqlite"
        self.refresh_interval_seconds = max(0.0, refresh_interval_seconds)
        self._sync_lock = threading.RLock()
        self._last_signature = ""
        self._last_check_monotonic = 0.0
        self._last_refresh_result: dict[str, Any] | None = None

    def connect(self) -> sqlite3.Connection:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
              kind TEXT NOT NULL,
              record_id TEXT NOT NULL,
              created_at_utc TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              payload TEXT NOT NULL,
              PRIMARY KEY (kind, record_id)
            );
            CREATE INDEX IF NOT EXISTS records_created ON records(created_at_utc DESC, record_id);
            CREATE TABLE IF NOT EXISTS quarantine (
              source_path TEXT PRIMARY KEY,
              error TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        return connection

    def candidates(self) -> list[Path]:
        paths = [self.repo / "PROJECT_STATUS.md", self.repo / "PROGRESS_REPORT.md"]
        for pattern in (
            "reports/gates/*",
            "reports/incidents/*",
            "reports/events/*.json",
            "reports/runs/*.json",
            "reports/decisions/*.json",
            "reports/tasks/*.json",
            "reports/hypotheses/*.json",
            "reports/experiments/*.json",
            "reports/submissions/*.json",
            "reports/replays/*.json",
            "reports/decks/*.json",
            "reports/evaluations/*.json",
            "reports/costs/*.json",
            "reports/artifacts/*.json",
            "reports/learning/*.json",
            "experiments/*/manifest.json",
            "runs/*/run_manifest.json",
            "jobs/*/*.json",
        ):
            paths.extend(self.repo.glob(pattern))
        return sorted({path for path in paths if path.is_file()})

    def source_signature(self) -> str:
        payload: list[str] = []
        for path in self.candidates():
            relative = path.relative_to(self.repo).as_posix()
            try:
                stat = path.stat()
                payload.append(f"{relative}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError as error:
                payload.append(f"{relative}:ERROR:{type(error).__name__}")
        return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()

    def sync_if_needed(self, force: bool = False) -> dict[str, Any]:
        with self._sync_lock:
            now = time.monotonic()
            if (
                not force
                and self.database.exists()
                and self._last_check_monotonic
                and now - self._last_check_monotonic < self.refresh_interval_seconds
            ):
                return {
                    "status": "unchanged",
                    "source_signature": self._last_signature,
                    "checked": False,
                }

            signature = self.source_signature()
            should_refresh = force or not self.database.exists() or signature != self._last_signature
            if should_refresh:
                result = self.ingest(rebuild=True)
            else:
                result = {
                    "status": "unchanged",
                    "source_signature": signature,
                    "checked": True,
                }
                self._last_refresh_result = result
            self._last_signature = signature
            self._last_check_monotonic = now
            return result

    def _safe_relative(self, path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.repo):
            raise SourceError("source escapes the approved project root")
        current = self.repo
        for part in path.relative_to(self.repo).parts:
            current /= part
            if current.is_symlink():
                raise SourceError("symlink sources are not allowed")
        relative = resolved.relative_to(self.repo).as_posix()
        if relative.startswith(("private/", "data/replays/", "submissions/")):
            raise SourceError("private/replay/submission sources are not allowed")
        if path.name.startswith(".env") or path.suffix not in {".md", ".json"}:
            raise SourceError("source type is not previewable")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise SourceError("source exceeds the 1 MiB ingestion limit")
        return relative

    def _read(self, path: Path) -> tuple[str, str, str]:
        relative = self._safe_relative(path)
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if SECRET_PATTERN.search(text):
            raise SourceError("source contains a blocked credential pattern")
        return relative, hashlib.sha256(raw).hexdigest(), text

    @staticmethod
    def _markdown_record(relative: str, digest: str, text: str) -> tuple[str, dict[str, Any]]:
        title = next(
            (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
            Path(relative).stem,
        )
        fields = {
            key.strip().lower().replace(" ", "_"): value.strip()
            for key, value in FIELD_PATTERN.findall(text)
        }
        status_match = STATUS_PATTERN.search(text)
        status = status_match.group(1).strip().upper() if status_match else "UNKNOWN"
        if "G0 remains blocked" in text or "G0 remains blocked" in text.replace("**", ""):
            status = "BLOCKED"
        created = fields.get("date/time_utc") or fields.get("review_date") or "2026-07-17T00:00:00Z"
        record = {
            "schema_version": 1,
            "record_id": f"report-{Path(relative).stem.lower().replace('_', '-')}",
            "created_at_utc": created,
            "source_path": relative,
            "source_sha256": digest,
            "producer": "markdown-adapter",
            "title": title,
            "gate_id": fields.get("milestone/gate", "G0").split()[0],
            "status": status,
            "fields": fields,
            "markdown": text,
        }
        return "report", record

    @staticmethod
    def _json_kind(relative: str, record: dict[str, Any]) -> str:
        parts = Path(relative).parts
        if len(parts) >= 2 and parts[0] == "reports":
            kind = REPORT_KIND_DIRECTORIES.get(parts[1])
            if kind:
                return kind
        if relative.endswith("run_manifest.json"):
            return "run"
        if relative.startswith("jobs/"):
            return "job"
        if relative.startswith("experiments/") and relative.endswith("manifest.json"):
            return "experiment"
        return str(record.get("kind", "record")).lower()

    @staticmethod
    def _operational_status(value: Any) -> str:
        original = str(value or "UNKNOWN").upper()
        return {
            "PASS": "SUCCEEDED",
            "COMPLETE": "SUCCEEDED",
            "COMPLETED": "SUCCEEDED",
            "FAIL": "FAILED",
            "ERROR": "FAILED",
            "PROPOSED": "PLANNED",
            "DESIGNED": "PLANNED",
            "SMOKE_PASSED": "SUCCEEDED",
            "CV_RUNNING": "RUNNING",
            "EVALUATED": "SUCCEEDED",
            "PROMOTED": "SUCCEEDED",
            "REJECTED": "FAILED",
        }.get(original, original)

    def _adapt_run_manifest(
        self, value: dict[str, Any], path: Path, relative: str
    ) -> dict[str, Any]:
        run_id = str(value.get("run_id", path.parent.name))
        original_status = str(value.get("status", "UNKNOWN")).upper()
        return {
            **value,
            "record_id": value.get("record_id", f"run-{run_id}"),
            "created_at_utc": value.get(
                "created_at_utc", datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            ),
            "source_path": relative,
            "producer": value.get("producer", "run-manifest-adapter"),
            "run_id": run_id,
            "gate_id": value.get("gate_id", "UNKNOWN"),
            "status": self._operational_status(original_status),
            "decision": value.get("decision", "NOT_REVIEWED"),
            "internal_verdict": value.get("internal_verdict", original_status),
        }

    def _adapt_experiment_manifest(
        self, value: dict[str, Any], path: Path, relative: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        experiment_id = str(value.get("experiment_id", path.parent.name))
        created = value.get("created_at") or value.get("created_at_utc")
        created = created or datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        experiment = {
            **value,
            "record_id": value.get("record_id", f"experiment-{experiment_id}"),
            "created_at_utc": created,
            "source_path": relative,
            "producer": value.get("producer", "experiment-manifest-adapter"),
            "experiment_id": experiment_id,
            "status": self._operational_status(value.get("status")),
        }
        runs: list[dict[str, Any]] = []
        for run in value.get("runs", []):
            if not isinstance(run, dict):
                raise SourceError("experiment run entry must be an object")
            run_id = str(run.get("run_id", ""))
            if not run_id:
                raise SourceError("experiment run entry is missing run_id")
            runs.append(
                {
                    **run,
                    "schema_version": run.get("schema_version", 1),
                    "record_id": f"run-{run_id}",
                    "created_at_utc": run.get("started_at") or run.get("updated_at") or created,
                    "source_path": relative,
                    "producer": "experiment-run-adapter",
                    "run_id": run_id,
                    "experiment_id": experiment_id,
                    "status": self._operational_status(run.get("status")),
                }
            )
        return experiment, runs

    def _records(self, path: Path) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        relative, digest, text = self._read(path)
        if path.suffix == ".md":
            return relative, [self._markdown_record(relative, digest, text)]
        parsed = json.loads(text)
        values = parsed if isinstance(parsed, list) else [parsed]
        records: list[tuple[str, dict[str, Any]]] = []
        for raw_value in values:
            if not isinstance(raw_value, dict):
                raise SourceError("JSON record must be an object")
            value = dict(raw_value)
            if relative.endswith("run_manifest.json"):
                value = self._adapt_run_manifest(value, path, relative)
                adapted = [("run", value)]
            elif relative.startswith("experiments/") and relative.endswith("manifest.json"):
                experiment, runs = self._adapt_experiment_manifest(value, path, relative)
                adapted = [("experiment", experiment), *(("run", run) for run in runs)]
            else:
                adapted = [(self._json_kind(relative, value), value)]
            for kind, record in adapted:
                record = {**record, "source_sha256": digest}
                RecordEnvelope.model_validate(record)
                records.append((kind, record))
        return relative, records

    def ingest(self, rebuild: bool = False) -> dict[str, Any]:
        with self._sync_lock:
            candidates = self.candidates()
            active_relatives = {path.relative_to(self.repo).as_posix() for path in candidates}
            with self.connect() as connection:
                if rebuild:
                    connection.execute("DELETE FROM records")
                    connection.execute("DELETE FROM quarantine")
                elif active_relatives:
                    placeholders = ",".join("?" for _ in active_relatives)
                    values = tuple(sorted(active_relatives))
                    connection.execute(
                        f"DELETE FROM records WHERE source_path NOT IN ({placeholders})", values
                    )
                    connection.execute(
                        f"DELETE FROM quarantine WHERE source_path NOT IN ({placeholders})", values
                    )
                else:
                    connection.execute("DELETE FROM records")
                    connection.execute("DELETE FROM quarantine")

                ingested = 0
                quarantined = 0
                for path in candidates:
                    try:
                        relative, records = self._records(path)
                        connection.execute("DELETE FROM records WHERE source_path = ?", (relative,))
                        connection.execute("DELETE FROM quarantine WHERE source_path = ?", (relative,))
                        for kind, record in records:
                            connection.execute(
                                """INSERT OR REPLACE INTO records
                                   (kind, record_id, created_at_utc, source_path, source_sha256, payload)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (
                                    kind,
                                    record["record_id"],
                                    record["created_at_utc"],
                                    relative,
                                    record["source_sha256"],
                                    json.dumps(record, sort_keys=True),
                                ),
                            )
                            ingested += 1
                    except (OSError, UnicodeError, json.JSONDecodeError, SourceError, ValueError) as error:
                        relative = path.relative_to(self.repo).as_posix()
                        connection.execute(
                            "INSERT OR REPLACE INTO quarantine(source_path, error) VALUES (?, ?)",
                            (relative, str(error)),
                        )
                        quarantined += 1
                scanned = datetime.now(UTC).isoformat()
                signature = self.source_signature()
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES ('last_scan_utc', ?)",
                    (scanned,),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES ('source_signature', ?)",
                    (signature,),
                )
            result = {
                "status": "pass" if quarantined == 0 else "warn",
                "ingested": ingested,
                "quarantined": quarantined,
                "last_scan_utc": scanned,
                "source_signature": signature,
            }
            self._last_signature = signature
            self._last_check_monotonic = time.monotonic()
            self._last_refresh_result = result
            return result

    def list(self, kind: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self.sync_if_needed()
        limit = min(max(limit, 1), 500)
        offset = max(offset, 0)
        with self.connect() as connection:
            total = connection.execute(
                "SELECT count(*) FROM records WHERE kind = ?", (kind,)
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT payload FROM records WHERE kind = ? "
                "ORDER BY created_at_utc DESC, record_id LIMIT ? OFFSET ?",
                (kind, limit, offset),
            ).fetchall()
        return {
            "items": [json.loads(row[0]) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def snapshot(self) -> dict[str, Any]:
        self.sync_if_needed()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT kind, payload FROM records ORDER BY kind, created_at_utc, record_id"
            ).fetchall()
        return {
            "schema_version": 1,
            "records": [{"kind": row[0], **json.loads(row[1])} for row in rows],
        }

    def read_source(self, relative: str) -> dict[str, Any]:
        self.sync_if_needed()
        candidate_map = {path.relative_to(self.repo).as_posix(): path for path in self.candidates()}
        path = candidate_map.get(relative)
        if path is None:
            raise SourceError("source is not in the dashboard allowlist")
        safe_relative, digest, text = self._read(path)
        return {
            "source_path": safe_relative,
            "source_sha256": digest,
            "text": text[:MAX_EVIDENCE_CHARS],
            "truncated": len(text) > MAX_EVIDENCE_CHARS,
        }

    def health(self) -> dict[str, Any]:
        self.sync_if_needed()
        with self.connect() as connection:
            records = connection.execute("SELECT count(*) FROM records").fetchone()[0]
            errors = [
                dict(row)
                for row in connection.execute("SELECT * FROM quarantine ORDER BY source_path")
            ]
            metadata = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }
        return {
            "status": "PASS" if not errors else "WARN",
            "records": records,
            "quarantined": errors,
            "last_scan_utc": metadata.get("last_scan_utc"),
            "source_signature": metadata.get("source_signature"),
            "cache_path": str(self.database.relative_to(self.repo)),
            "cache_bytes": self.database.stat().st_size if self.database.exists() else 0,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "last_refresh_result": self._last_refresh_result,
        }
