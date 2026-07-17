from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import RecordEnvelope

MAX_SOURCE_BYTES = 1_048_576
SECRET_PATTERN = re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]+PRIVATE KEY-----)")
STATUS_PATTERN = re.compile(r"^(?:Status|Gate status):\s*\*{0,2}([^\n*]+)", re.MULTILINE | re.IGNORECASE)
FIELD_PATTERN = re.compile(r"^([^\n:]{2,40}):\s*(.+?)\s*$", re.MULTILINE)


class SourceError(ValueError):
    pass


class DashboardStore:
    def __init__(self, repo: Path, database: Path | None = None) -> None:
        self.repo = repo.resolve()
        self.database = database or self.repo / "data" / "dashboard" / "dashboard.sqlite"

    def connect(self) -> sqlite3.Connection:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
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
            "runs/*/run_manifest.json",
            "jobs/*/*.json",
        ):
            paths.extend(self.repo.glob(pattern))
        return sorted({path for path in paths if path.is_file()})

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
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), Path(relative).stem)
        fields = {key.strip().lower().replace(" ", "_"): value.strip() for key, value in FIELD_PATTERN.findall(text)}
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
        if "/incidents/" in f"/{relative}":
            return "incident"
        if "/events/" in f"/{relative}":
            return "event"
        if "/gates/" in f"/{relative}":
            return "gate"
        if relative.endswith("run_manifest.json"):
            return "run"
        if relative.startswith("jobs/"):
            return "job"
        return str(record.get("kind", "record")).lower()

    def _records(self, path: Path) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        relative, digest, text = self._read(path)
        if path.suffix == ".md":
            return relative, [self._markdown_record(relative, digest, text)]
        parsed = json.loads(text)
        values = parsed if isinstance(parsed, list) else [parsed]
        records: list[tuple[str, dict[str, Any]]] = []
        for value in values:
            if not isinstance(value, dict):
                raise SourceError("JSON record must be an object")
            value = {**value, "source_sha256": digest}
            RecordEnvelope.model_validate(value)
            records.append((self._json_kind(relative, value), value))
        return relative, records

    def ingest(self, rebuild: bool = False) -> dict[str, Any]:
        with self.connect() as connection:
            if rebuild:
                connection.execute("DELETE FROM records")
                connection.execute("DELETE FROM quarantine")
            ingested = 0
            quarantined = 0
            for path in self.candidates():
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
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('last_scan_utc', ?)", (scanned,)
            )
        return {"status": "pass", "ingested": ingested, "quarantined": quarantined, "last_scan_utc": scanned}

    def list(self, kind: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        limit = min(max(limit, 1), 500)
        offset = max(offset, 0)
        with self.connect() as connection:
            total = connection.execute("SELECT count(*) FROM records WHERE kind = ?", (kind,)).fetchone()[0]
            rows = connection.execute(
                "SELECT payload FROM records WHERE kind = ? ORDER BY created_at_utc DESC, record_id LIMIT ? OFFSET ?",
                (kind, limit, offset),
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total, "limit": limit, "offset": offset}

    def snapshot(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT kind, payload FROM records ORDER BY kind, created_at_utc, record_id"
            ).fetchall()
        return {"schema_version": 1, "records": [{"kind": row[0], **json.loads(row[1])} for row in rows]}

    def health(self) -> dict[str, Any]:
        with self.connect() as connection:
            records = connection.execute("SELECT count(*) FROM records").fetchone()[0]
            errors = [dict(row) for row in connection.execute("SELECT * FROM quarantine ORDER BY source_path")]
            row = connection.execute("SELECT value FROM metadata WHERE key = 'last_scan_utc'").fetchone()
        return {
            "status": "PASS" if not errors else "WARN",
            "records": records,
            "quarantined": errors,
            "last_scan_utc": row[0] if row else None,
            "cache_path": str(self.database.relative_to(self.repo)),
            "cache_bytes": self.database.stat().st_size if self.database.exists() else 0,
        }
