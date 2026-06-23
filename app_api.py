#!/usr/bin/env python3
"""app_api.py — M23: controller bridging the desktop UI <-> application_bot logic.

`JobAppAPI` exposes plain methods that return JSON-serializable dicts. The
pywebview desktop shell hands an instance to the web UI as `js_api`, so the
front-end calls Python directly — no HTTP server for a single-user local app.
Every method is unit-testable headless by pointing it at a temp DB.

BOUNDARY: the app discovers, scores, tailors, and emails the user. It never
auto-submits web-form applications (CAPTCHA/login + ToS); the only auto-submit
is the gated email-apply path in email_service. Web-form roles are emailed to
the user to apply + mark applied.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from application_bot.config import load_config
from application_bot.database import Database
from application_bot.packets import generate_packet
from application_bot.pdf import export_application_pdfs
from application_bot.pipeline import is_fresh, run_dry_pipeline
from application_bot.policy import evaluate_job_submission_policy
from application_bot.resume import load_resume_master, render_ats_resume_text


class JobAppAPI:
    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.config = load_config(config_path)
        self.db_path = str(db_path or self.config["database_path"])
        self.export_root = self.config["export_path"]

    # --- helpers -------------------------------------------------------------
    def _db(self) -> Database:
        database = Database(self.db_path)
        database.initialize()
        return database

    def _cover_letter(self, database: Database, job: Any) -> str:
        row = database.latest_packet(int(job.id))
        if row:
            import json

            return json.loads(row["packet_json"]).get("cover_letter", "")
        policy = evaluate_job_submission_policy(job, self.config)
        return generate_packet(job, self.config, policy).cover_letter

    def _row(self, job: Any) -> dict[str, Any]:
        return {
            "id": job.id,
            "company": job.company,
            "title": job.title,
            "score": job.score,
            "verdict": job.verdict,
            "apply_url": job.apply_url,
            "posted_at": job.posted_at,
            "packet_status": job.packet_status,
            "status": job.status,
            "is_form": str(job.apply_url or "").lower().startswith("http"),
        }

    # --- methods called by the UI -------------------------------------------
    def get_status(self) -> dict[str, Any]:
        database = self._db()
        jobs = database.list_jobs()
        counts: dict[str, int] = {}
        for job in jobs:
            counts[str(job.status)] = counts.get(str(job.status), 0) + 1
        ready = [
            job
            for job in database.list_jobs(scored_only=True)
            if str(job.packet_status) == "PACKET_READY" and str(job.status) != "APPLIED"
        ]
        applied = [job for job in jobs if str(job.status) == "APPLIED"]
        return {
            "total": len(jobs),
            "outstanding": len(ready),
            "applied": len(applied),
            "status_counts": counts,
            "registry": str(self.config.get("live_company_registry")),
        }

    # Verdicts worth surfacing on the New tab — fresh roles below this are noise.
    _WORTH_A_LOOK = {"APPLY_PRIORITY", "GOOD_FIT", "MAYBE"}

    def list_roles(self, status: str = "outstanding") -> dict[str, Any]:
        database = self._db()
        rows: list[dict[str, Any]] = []
        for job in database.list_jobs(scored_only=True):
            applied = str(job.status) == "APPLIED"
            ready = str(job.packet_status) == "PACKET_READY"
            if status == "applied" and not applied:
                continue
            if status == "outstanding" and (applied or not ready):
                continue
            if status == "new":
                # Fresh AND a plausible fit — don't flood the tab with off-lane
                # postings from these general boards.
                if is_fresh(job.posted_at, 24) is not True:
                    continue
                if str(job.verdict) not in self._WORTH_A_LOOK:
                    continue
            rows.append(self._row(job))
        rows.sort(key=lambda r: (r["score"] or 0), reverse=True)
        return {"status": status, "roles": rows}

    def run_discovery(self, hours: int = 24, limit: int = 600) -> dict[str, Any]:
        """Live last-N-hours scan → score → packets. Needs network.

        The limit caps total roles *seen* across all boards before the freshness
        filter; with ~27 boards it must be high enough that every board is
        scanned (a low cap silently skips later boards).
        """
        result = run_dry_pipeline(
            database_path=self.db_path,
            registry_path=self.config["live_company_registry"],
            output_root=self.export_root,
            config=self.config,
            limit=int(limit),
            posted_within_hours=int(hours),
        )
        return {
            "ok": True,
            "jobs_inserted": result.get("jobs_inserted"),
            "dropped_stale": result.get("dropped_stale"),
            "dropped_undated": result.get("dropped_undated"),
            "packets_ready": result.get("packets_ready"),
            "network_status": result.get("network_status"),
        }

    def make_artifacts(self, job_id: int) -> dict[str, Any]:
        database = self._db()
        job = database.get_job(int(job_id))
        if not job:
            return {"ok": False, "error": f"Job {job_id} not found"}
        master = load_resume_master(self.config["resume_master"])
        resume_text = render_ats_resume_text(job, master, self.config)
        pdfs = export_application_pdfs(
            job, resume_text, self._cover_letter(database, job), self.export_root
        )
        return {"ok": True, **pdfs}

    def open_artifact(self, job_id: int, kind: str = "resume") -> dict[str, Any]:
        """Generate the role's optimized PDFs and open the requested one.

        kind: "resume" or "cover". The PDF opens in the OS default viewer, where
        it can be read, saved, or printed (clickable + downloadable).
        """
        result = self.make_artifacts(int(job_id))
        if not result.get("ok"):
            return result
        path = result["cover_pdf"] if kind == "cover" else result["resume_pdf"]
        try:
            subprocess.run(["open", path], check=False)
        except OSError as exc:  # pragma: no cover - platform dependent
            return {"ok": False, "error": str(exc), "path": path}
        return {"ok": True, "kind": kind, "path": path}

    def mark_applied(self, job_id: int, notes: str = "") -> dict[str, Any]:
        database = self._db()
        database.mark_applied(int(job_id), notes)
        return {"ok": True, "job_id": int(job_id), "status": "APPLIED"}
