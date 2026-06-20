from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from application_bot.models import EmailQueueItem, Job, ScoreResult, utc_now


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
    submission_policy TEXT,
    packet_status TEXT,
    claim_gaps_json TEXT NOT NULL DEFAULT '[]',
    packet_reason_codes_json TEXT NOT NULL DEFAULT '[]',
    recommended_next_action TEXT,
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
    sender TEXT,
    body TEXT,
    classification TEXT,
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

CREATE TABLE IF NOT EXISTS email_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL UNIQUE,
    packet_id INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    compliance_flags_json TEXT NOT NULL DEFAULT '[]',
    preview_path TEXT,
    error TEXT,
    queued_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id),
    FOREIGN KEY(packet_id) REFERENCES application_packets(id)
);

CREATE INDEX IF NOT EXISTS idx_email_queue_status ON email_queue(status);
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
            self._ensure_column(connection, "confirmations", "sender", "TEXT")
            self._ensure_column(connection, "confirmations", "body", "TEXT")
            self._ensure_column(connection, "confirmations", "classification", "TEXT")
            self._ensure_column(connection, "jobs", "submission_policy", "TEXT")
            self._ensure_column(connection, "jobs", "packet_status", "TEXT")
            self._ensure_column(
                connection, "jobs", "claim_gaps_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._ensure_column(
                connection,
                "jobs",
                "packet_reason_codes_json",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection, "jobs", "recommended_next_action", "TEXT"
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_confirmations_classification
                ON confirmations(classification)
                """
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

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

    def record_event(
        self,
        event_type: str,
        *,
        job_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    job_id,
                    event_type,
                    json.dumps(details or {}, sort_keys=True),
                    utc_now(),
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
                        WHEN status IN (
                            'APPLIED', 'PACKET_EXPORTED', 'REVIEW_REQUIRED', 'BLOCKED'
                        ) THEN status
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
                UPDATE jobs
                SET packet_status = ?,
                    claim_gaps_json = ?,
                    packet_reason_codes_json = ?,
                    recommended_next_action = ?,
                    submission_policy = ?,
                    status = CASE
                        WHEN status IN ('REVIEW_REQUIRED', 'BLOCKED') THEN status
                        ELSE 'PACKET_EXPORTED'
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    packet.get("packet_status"),
                    json.dumps(packet.get("claim_gaps") or [], sort_keys=True),
                    json.dumps(packet.get("reason_codes") or [], sort_keys=True),
                    packet.get("recommended_next_action"),
                    packet.get("policy"),
                    utc_now(),
                    job_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'PACKET_EXPORTED', ?, ?)
                """,
                (job_id, json.dumps({"path": export_path}), utc_now()),
            )

    def save_packet_assessment(
        self,
        job_id: int,
        *,
        packet_status: str,
        claim_gaps: list[str],
        reason_codes: list[str],
        recommended_next_action: str,
        submission_policy: str,
    ) -> None:
        details = {
            "packet_status": packet_status,
            "claim_gaps": claim_gaps,
            "reason_codes": reason_codes,
            "recommended_next_action": recommended_next_action,
            "submission_policy": submission_policy,
        }
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET packet_status = ?, claim_gaps_json = ?,
                    packet_reason_codes_json = ?, recommended_next_action = ?,
                    submission_policy = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    packet_status,
                    json.dumps(claim_gaps, sort_keys=True),
                    json.dumps(reason_codes, sort_keys=True),
                    recommended_next_action,
                    submission_policy,
                    utc_now(),
                    job_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'PACKET_ASSESSED', ?, ?)
                """,
                (job_id, json.dumps(details, sort_keys=True), utc_now()),
            )

    def latest_packet(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM application_packets
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

    def queue_email(
        self,
        job_id: int,
        packet_id: int,
        recipient: str,
        compliance_flags: list[str] | None = None,
    ) -> tuple[int, bool]:
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM email_queue WHERE job_id = ?", (job_id,)
            ).fetchone()
            connection.execute(
                """
                INSERT INTO email_queue(
                    job_id, packet_id, recipient, status,
                    compliance_flags_json, queued_at, updated_at
                ) VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    packet_id = excluded.packet_id,
                    recipient = excluded.recipient,
                    compliance_flags_json = excluded.compliance_flags_json,
                    updated_at = excluded.updated_at,
                    status = CASE
                        WHEN email_queue.status = 'SENT' THEN email_queue.status
                        ELSE 'QUEUED'
                    END,
                    error = NULL
                """,
                (
                    job_id,
                    packet_id,
                    recipient,
                    json.dumps(compliance_flags or [], sort_keys=True),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM email_queue WHERE job_id = ?", (job_id,)
            ).fetchone()
            queue_id = int(row["id"])
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO events(job_id, event_type, details_json, created_at)
                    VALUES (?, 'EMAIL_QUEUED', ?, ?)
                    """,
                    (job_id, json.dumps({"recipient": recipient}), now),
                )
            return queue_id, existing is None

    def list_email_queue(
        self,
        *,
        statuses: set[str] | None = None,
    ) -> list[EmailQueueItem]:
        query = """
            SELECT q.*, j.company, j.title, j.apply_url, p.packet_json
            FROM email_queue q
            JOIN jobs j ON j.id = q.job_id
            JOIN application_packets p ON p.id = q.packet_id
        """
        parameters: list[Any] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE q.status IN ({placeholders})"
            parameters.extend(sorted(statuses))
        query += " ORDER BY q.id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            EmailQueueItem(
                id=int(row["id"]),
                job_id=int(row["job_id"]),
                packet_id=int(row["packet_id"]),
                recipient=str(row["recipient"]),
                status=str(row["status"]),
                compliance_flags_json=str(row["compliance_flags_json"]),
                preview_path=row["preview_path"],
                error=row["error"],
                queued_at=str(row["queued_at"]),
                updated_at=str(row["updated_at"]),
                sent_at=row["sent_at"],
                company=str(row["company"]),
                title=str(row["title"]),
                apply_url=str(row["apply_url"]),
                packet_json=str(row["packet_json"]),
            )
            for row in rows
        ]

    def mark_email_preview(self, queue_id: int, preview_path: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM email_queue WHERE id = ?", (queue_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Email queue item {queue_id} does not exist")
            connection.execute(
                """
                UPDATE email_queue
                SET status = 'PREVIEW_GENERATED', preview_path = ?,
                    error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (preview_path, now, queue_id),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'EMAIL_PREVIEW_GENERATED', ?, ?)
                """,
                (int(row["job_id"]), json.dumps({"path": preview_path}), now),
            )

    def mark_email_sent(self, queue_id: int) -> None:
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM email_queue WHERE id = ?", (queue_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Email queue item {queue_id} does not exist")
            connection.execute(
                """
                UPDATE email_queue
                SET status = 'SENT', error = NULL, sent_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, queue_id),
            )
            connection.execute(
                """
                INSERT INTO applications(
                    job_id, submission_mode, status, applied_at, notes, created_at
                ) VALUES (?, 'EMAIL', 'APPLIED', ?, 'Email sent by guarded adapter', ?)
                """,
                (int(row["job_id"]), now, now),
            )
            connection.execute(
                """
                INSERT INTO events(job_id, event_type, details_json, created_at)
                VALUES (?, 'EMAIL_SENT', '{}', ?)
                """,
                (int(row["job_id"]), now),
            )

    def mark_email_blocked(self, queue_id: int, reason: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE email_queue
                SET status = 'BLOCKED', error = ?, updated_at = ?
                WHERE id = ?
                """,
                (reason, utc_now(), queue_id),
            )

    def save_confirmation(
        self,
        *,
        source: str,
        external_id: str | None,
        subject: str,
        sender: str,
        body: str,
        classification: str,
        received_at: str | None,
        raw_payload: dict[str, Any],
        job_id: int | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO confirmations(
                    job_id, source, external_id, subject, sender, body,
                    classification, received_at, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source,
                    external_id,
                    subject,
                    sender,
                    body,
                    classification,
                    received_at,
                    json.dumps(raw_payload, sort_keys=True),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

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
            email_queue = connection.execute(
                "SELECT status, COUNT(*) AS count FROM email_queue GROUP BY status"
            ).fetchall()
            confirmations = connection.execute(
                """
                SELECT COALESCE(classification, 'unclassified') AS classification,
                       COUNT(*) AS count
                FROM confirmations
                GROUP BY COALESCE(classification, 'unclassified')
                """
            ).fetchall()
            source_runs = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM source_runs
                GROUP BY status
                """
            ).fetchall()
            packet_statuses = connection.execute(
                """
                SELECT COALESCE(packet_status, 'UNASSESSED') AS packet_status,
                       COUNT(*) AS count
                FROM jobs
                GROUP BY COALESCE(packet_status, 'UNASSESSED')
                """
            ).fetchall()
        return {
            "total_jobs": int(total["count"]),
            "by_status": {row["status"]: int(row["count"]) for row in by_status},
            "by_verdict": {row["verdict"]: int(row["count"]) for row in by_verdict},
            "packet_count": int(packets["count"]),
            "application_count": int(applications["count"]),
            "email_queue": {
                row["status"]: int(row["count"]) for row in email_queue
            },
            "confirmations": {
                row["classification"]: int(row["count"]) for row in confirmations
            },
            "source_runs": {
                row["status"]: int(row["count"]) for row in source_runs
            },
            "packet_statuses": {
                row["packet_status"]: int(row["count"]) for row in packet_statuses
            },
            "top_jobs": [dict(row) for row in top_jobs],
        }

    def review_queue_rows(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, company, title, score, verdict, submission_policy,
                       packet_status, claim_gaps_json, apply_url,
                       recommended_next_action, packet_reason_codes_json
                FROM jobs
                WHERE score IS NOT NULL
                ORDER BY
                    CASE packet_status
                        WHEN 'PACKET_READY' THEN 0
                        WHEN 'REVIEW_PACKET_CLAIM_GAPS' THEN 1
                        WHEN 'NOT_WORTH_PACKET' THEN 2
                        WHEN 'BLOCKED' THEN 3
                        ELSE 4
                    END,
                    score DESC,
                    id
                """
            ).fetchall()
        return [
            {
                "job_id": int(row["id"]),
                "company": row["company"],
                "title": row["title"],
                "score": row["score"],
                "verdict": row["verdict"],
                "submission_policy": row["submission_policy"],
                "packet_status": row["packet_status"] or "UNASSESSED",
                "claim_gaps": json.loads(row["claim_gaps_json"] or "[]"),
                "apply_url": row["apply_url"],
                "recommended_next_action": row["recommended_next_action"] or "",
                "reason_codes": json.loads(
                    row["packet_reason_codes_json"] or "[]"
                ),
            }
            for row in rows
        ]

    def source_quality_report(self) -> dict[str, Any]:
        with self.connect() as connection:
            runs = connection.execute(
                """
                SELECT status, jobs_seen, jobs_written
                FROM source_runs
                """
            ).fetchall()
            jobs = connection.execute(
                """
                SELECT score, verdict, score_details_json, packet_status,
                       packet_reason_codes_json
                FROM jobs
                WHERE score IS NOT NULL
                """
            ).fetchall()
        no_packet_reasons: dict[str, int] = {}
        target_level_matches = 0
        function_matches = 0
        verdicts = {
            "APPLY_PRIORITY": 0,
            "GOOD_FIT": 0,
            "MAYBE": 0,
            "NOT_WORTH_TIME": 0,
            "BLOCKED": 0,
        }
        packet_statuses = {
            "PACKET_READY": 0,
            "REVIEW_PACKET_CLAIM_GAPS": 0,
            "NOT_WORTH_PACKET": 0,
            "BLOCKED": 0,
        }
        for row in jobs:
            details = json.loads(row["score_details_json"] or "{}")
            dimensions = details.get("dimensions") or {}
            if int(dimensions.get("seniority") or 0) > 0:
                target_level_matches += 1
            if int(dimensions.get("function_fit") or 0) > 0:
                function_matches += 1
            verdict = str(row["verdict"] or "")
            if verdict in verdicts:
                verdicts[verdict] += 1
            packet_status = str(row["packet_status"] or "")
            if packet_status in packet_statuses:
                packet_statuses[packet_status] += 1
            if packet_status in {"NOT_WORTH_PACKET", "BLOCKED"}:
                for reason in json.loads(
                    row["packet_reason_codes_json"] or "[]"
                ):
                    no_packet_reasons[reason] = no_packet_reasons.get(reason, 0) + 1
        return {
            "sources_attempted": len(runs),
            "sources_succeeded": sum(row["status"] == "COMPLETED" for row in runs),
            "jobs_discovered": sum(int(row["jobs_seen"]) for row in runs),
            "jobs_after_dedupe": len(jobs),
            "target_level_matches": target_level_matches,
            "function_matches": function_matches,
            "apply_priority": verdicts["APPLY_PRIORITY"],
            "good_fit": verdicts["GOOD_FIT"],
            "maybe": verdicts["MAYBE"],
            "not_worth_time": verdicts["NOT_WORTH_TIME"],
            "packets_ready": packet_statuses["PACKET_READY"],
            "review_packets_claim_gaps": packet_statuses[
                "REVIEW_PACKET_CLAIM_GAPS"
            ],
            "blocked": packet_statuses["BLOCKED"],
            "no_packet_reason_counts": no_packet_reasons,
        }

    def daily_metrics(self, day: str) -> dict[str, Any]:
        prefix = f"{day}%"
        with self.connect() as connection:
            discovered = connection.execute(
                """
                SELECT COUNT(DISTINCT job_id) AS count
                FROM events
                WHERE event_type = 'JOB_DISCOVERED' AND created_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            scored = connection.execute(
                """
                SELECT COUNT(DISTINCT job_id) AS count
                FROM events
                WHERE event_type = 'JOB_SCORED' AND created_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            verdict_rows = connection.execute(
                """
                SELECT COALESCE(verdict, 'UNSCORED') AS verdict, COUNT(*) AS count
                FROM jobs GROUP BY COALESCE(verdict, 'UNSCORED')
                """
            ).fetchall()
            packet_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM events
                WHERE event_type = 'PACKET_EXPORTED' AND created_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            preview_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM events
                WHERE event_type = 'EMAIL_PREVIEW_GENERATED' AND created_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            applications = connection.execute(
                """
                SELECT COUNT(*) AS count FROM applications
                WHERE applied_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            compliance_blocks = connection.execute(
                """
                SELECT COUNT(*) AS count FROM jobs
                WHERE status = 'BLOCKED' OR verdict = 'BLOCKED'
                """
            ).fetchone()
        verdicts = {row["verdict"]: int(row["count"]) for row in verdict_rows}
        for verdict in (
            "APPLY_PRIORITY",
            "GOOD_FIT",
            "MAYBE",
            "NOT_WORTH_TIME",
            "BLOCKED",
        ):
            verdicts.setdefault(verdict, 0)
        return {
            "date": day,
            "jobs_discovered": int(discovered["count"]),
            "jobs_scored": int(scored["count"]),
            "verdicts": verdicts,
            "packets_exported": int(packet_count["count"]),
            "email_previews_generated": int(preview_count["count"]),
            "applications_submitted": int(applications["count"]),
            "compliance_blocks": int(compliance_blocks["count"]),
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
                "submission_policy",
                "packet_status",
                "claim_gaps_json",
                "packet_reason_codes_json",
                "recommended_next_action",
            )
        }
        return Job(**fields)
