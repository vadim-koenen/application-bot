from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from application_bot.models import Job, ScoreResult, utc_now


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    ats TEXT,
    registry_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    apply_url TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    remote_type TEXT NOT NULL DEFAULT 'unknown',
    salary_min INTEGER,
    salary_max INTEGER,
    currency TEXT NOT NULL DEFAULT 'USD',
    description TEXT NOT NULL DEFAULT '',
    requirements TEXT NOT NULL DEFAULT '',
    responsibilities TEXT NOT NULL DEFAULT '',
    posted_at TEXT,
    discovered_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    raw_payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',
    score INTEGER,
    verdict TEXT,
    score_details_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);

CREATE TABLE IF NOT EXISTS application_packets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    export_path TEXT NOT NULL,
    packet_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    submission_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    applied_at TEXT,
    external_confirmation TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    source TEXT NOT NULL,
    external_id TEXT,
    subject TEXT,
    received_at TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    jobs_seen INTEGER NOT NULL DEFAULT 0,
    jobs_written INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def start_source_run(self, source: str, details: dict[str, Any] | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO source_runs(source, started_at, status, details_json)
                VALUES (?, ?, 'RUNNING', ?)
                """,
                (source, utc_now(), json.dumps(details or {}, sort_keys=True)),
            )
            return int(cursor.lastrowid)

    def finish_source_run(
        self,
        run_id: int,
        *,
        status: str,
        jobs_seen: int,
        jobs_written: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE source_runs
                SET completed_at = ?, status = ?, jobs_seen = ?, jobs_written = ?,
                    details_json = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    status,
                    jobs_seen,
                    jobs_written,
                    json.dumps(details or {}, sort_keys=True),
                    run_id,
                ),
            )

    def register_company(self, company: dict[str, Any]) -> None:
        name = str(company.get("name") or "").strip()
        if not name:
            return
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO companies(name, ats, registry_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    ats = excluded.ats,
                    registry_json = excluded.registry_json
                """,
                (
                    name,
                    company.get("ats"),
                    json.dumps(company, sort_keys=True),
                    utc_now(),
                ),
            )

    def upsert_job(self, job: Job) -> tuple[int, bool]:
        now = utc_now()
        values = (
            job.external_id,
            job.source,
            job.source_url,
            job.apply_url,
            job.company,
            job.title,
            job.department,
            job.location,
            job.remote_type,
            job.salary_min,
            job.salary_max,
            job.currency,
            job.description,
            job.requirements,
            job.responsibilities,
            job.posted_at,
            job.discovered_at,
            job.content_hash,
            job.dedupe_key,
            job.raw_payload_json,
            str(job.status),
            now,
        )
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?", (job.dedupe_key,)
            ).fetchone()
            connection.execute(
                """
                INSERT INTO jobs(
                    external_id, source, source_url, apply_url, company, title,
                    department, location, remote_type, salary_min, salary_max,
                    currency, description, requirements, responsibilities,
                    posted_at, discovered_at, content_hash, dedupe_key,
                    raw_payload_json, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    external_id = excluded.external_id,
                    source_url = excluded.source_url,
                    raw_payload_json = excluded.raw_payload_json,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            row = connection.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?", (job.dedupe_key,)
            ).fetchone()
            job_id = int(row["id"])
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO events(job_id, event_type, details_json, created_at)
                    VALUES (?, 'JOB_DISCOVERED', ?, ?)
                    """,
                    (job_id, json.dumps({"source": job.source}), now),
                )
            return job_id, existing is None

    def list_jobs(self, *, scored_only: bool = False) -> list[Job]:
        query = "SELECT * FROM jobs"
        if scored_only:
            query += " WHERE score IS NOT NULL"
        query += " ORDER BY COALESCE(score, -1) DESC, discovered_at DESC, id"
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: int) -> Job | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def save_score(self, job_id: int, result: ScoreResult) -> None:
        details = {
            "dimensions": result.dimensions,
            "reasons": result.reasons,
            "risk_flags": result.risk_flags,
        }
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET score = ?, verdict = ?, score_details_json = ?,
                    status = CASE
                        WHEN status IN ('APPLIED', 'PACKET_EXPORTED') THEN status
                        ELSE 'SCORED'
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    result.score,
                    str(result.verdict),
                    json.dumps(details, sort_keys=True),
                    utc_now(),
                    job_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'JOB_SCORED', ?, ?)
                """,
                (
                    job_id,
                    json.dumps(
                        {"score": result.score, "verdict": str(result.verdict)}
                    ),
                    utc_now(),
                ),
            )

    def save_packet(self, job_id: int, export_path: str, packet: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO application_packets(job_id, export_path, packet_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, export_path, json.dumps(packet, sort_keys=True), utc_now()),
            )
            connection.execute(
                """
                UPDATE jobs SET status = 'PACKET_EXPORTED', updated_at = ? WHERE id = ?
                """,
                (utc_now(), job_id),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'PACKET_EXPORTED', ?, ?)
                """,
                (job_id, json.dumps({"path": export_path}), utc_now()),
            )

    def mark_applied(self, job_id: int, notes: str = "") -> None:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT id FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"Job {job_id} does not exist")
            connection.execute(
                """
                INSERT INTO applications(
                    job_id, submission_mode, status, applied_at, notes, created_at
                ) VALUES (?, 'MANUAL_OR_CONFIRMED', 'APPLIED', ?, ?, ?)
                """,
                (job_id, utc_now(), notes, utc_now()),
            )
            connection.execute(
                "UPDATE jobs SET status = 'APPLIED', updated_at = ? WHERE id = ?",
                (utc_now(), job_id),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'MARKED_APPLIED', ?, ?)
                """,
                (job_id, json.dumps({"notes": notes}), utc_now()),
            )

    def report(self) -> dict[str, Any]:
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
            by_status = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status ORDER BY status"
            ).fetchall()
            by_verdict = connection.execute(
                """
                SELECT COALESCE(verdict, 'UNSCORED') AS verdict, COUNT(*) AS count
                FROM jobs GROUP BY COALESCE(verdict, 'UNSCORED') ORDER BY verdict
                """
            ).fetchall()
            top_jobs = connection.execute(
                """
                SELECT id, company, title, score, verdict, apply_url
                FROM jobs WHERE score IS NOT NULL
                ORDER BY score DESC, id LIMIT 20
                """
            ).fetchall()
            packets = connection.execute(
                "SELECT COUNT(*) AS count FROM application_packets"
            ).fetchone()
            applications = connection.execute(
                "SELECT COUNT(*) AS count FROM applications"
            ).fetchone()
        return {
            "total_jobs": int(total["count"]),
            "by_status": {row["status"]: int(row["count"]) for row in by_status},
            "by_verdict": {row["verdict"]: int(row["count"]) for row in by_verdict},
            "packet_count": int(packets["count"]),
            "application_count": int(applications["count"]),
            "top_jobs": [dict(row) for row in top_jobs],
        }

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        fields = {
            key: row[key]
            for key in (
                "id",
                "external_id",
                "source",
                "source_url",
                "apply_url",
                "company",
                "title",
                "department",
                "location",
                "remote_type",
                "salary_min",
                "salary_max",
                "currency",
                "description",
                "requirements",
                "responsibilities",
                "posted_at",
                "discovered_at",
                "content_hash",
                "raw_payload_json",
                "status",
                "score",
                "verdict",
                "score_details_json",
            )
        }
        return Job(**fields)
