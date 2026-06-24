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

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from application_bot.answers import build_answer_draft
from application_bot.apply_helper import build_autofill_bookmarklet, build_autofill_spec
from application_bot.assisted_apply import build_fill_plan
from application_bot.claims import matched_approved_keywords
from application_bot.config import (
    load_answer_bank,
    load_claim_evidence,
    load_claim_inventory,
    load_config,
)
from application_bot.cover_letter_llm import draft_cover_letter_llm
from application_bot.database import Database
from application_bot.models import utc_now
from application_bot.packets import generate_packet, packet_to_dict
from application_bot.pdf import export_application_pdfs
from application_bot.pipeline import (
    discover_adzuna,
    discover_jsearch,
    ingest_manual_job,
    is_fresh,
    run_dry_pipeline,
)
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
        self.downloads_dir = Path.home() / "Downloads"
        self.window_hours = int(self.config.get("discovery_window_hours", 72))

    # --- helpers -------------------------------------------------------------
    def _db(self) -> Database:
        database = Database(self.db_path)
        database.initialize()
        return database

    def _approved_impact(self) -> list[str]:
        """Approved résumé wins (selected_impact) to feed the cover letter.

        Pulled from the same approved master the résumé uses; generate_packet
        re-filters these against the prohibited-claim patterns, so passing them
        all is safe. Returns [] if the master is unavailable (e.g. in tests)."""
        try:
            master = load_resume_master(self.config["resume_master"])
        except (OSError, ValueError, KeyError):
            return []
        return [str(item) for item in (master.get("selected_impact") or [])]

    def _cover_letter(self, database: Database, job: Any) -> str:
        # Prefer a Claude-drafted letter when an API key is configured. The draft
        # passes a fabrication guard (cover_letter_llm.validate_cover_letter); on
        # no-key / SDK-absent / error / validation failure we fall back to the
        # deterministic, claim-safe template. The letter always regenerates fresh.
        policy = evaluate_job_submission_policy(job, self.config)
        try:
            master = load_resume_master(self.config["resume_master"])
            inventory = load_claim_inventory(self.config["resume_claim_inventory"])
            drafted = draft_cover_letter_llm(
                job,
                master,
                inventory,
                matched=matched_approved_keywords(job, inventory),
                model=self.config.get("cover_letter_model"),
            )
            if drafted:
                return drafted
        except (OSError, ValueError, KeyError):
            pass
        return generate_packet(
            job, self.config, policy, impact_highlights=self._approved_impact()
        ).cover_letter

    @staticmethod
    def _grade(score: int | None) -> str | None:
        """6sense-style temperature from the 0-100 fit score.

        Hot >= 80, Warm 65-79, Cold 45-64; below 45 is unscored noise that the
        New/Outstanding views never surface, so it has no badge.
        """
        if score is None:
            return None
        if score >= 80:
            return "Hot"
        if score >= 65:
            return "Warm"
        if score >= 45:
            return "Cold"
        return None

    def _row(self, job: Any) -> dict[str, Any]:
        return {
            "id": job.id,
            "company": job.company,
            "title": job.title,
            "score": job.score,
            "grade": self._grade(job.score),
            "verdict": job.verdict,
            "source": job.source,
            "location": job.location or "",
            "remote_type": job.remote_type or "unknown",
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

    def _is_new_fit(self, job: Any) -> bool:
        """Fresh (within the discovery window) AND a plausible fit AND not yet
        acted on — the New bucket. Keeps off-lane noise off the tab, and drops
        a role out of New the moment it's marked applied/responded."""
        if str(job.status) in ("APPLIED", "RESPONDED"):
            return False
        if is_fresh(job.posted_at, self.window_hours) is not True:
            return False
        return str(job.verdict) in self._WORTH_A_LOOK

    def list_roles(self, status: str = "outstanding") -> dict[str, Any]:
        database = self._db()
        rows: list[dict[str, Any]] = []
        for job in database.list_jobs(scored_only=True):
            applied = str(job.status) == "APPLIED"
            responded = str(job.status) == "RESPONDED"
            ready = str(job.packet_status) == "PACKET_READY"
            if status == "applied" and not applied:
                continue
            if status == "responded" and not responded:
                continue
            if status == "outstanding" and (applied or responded or not ready):
                continue
            if status == "new" and not self._is_new_fit(job):
                continue
            rows.append(self._row(job))
        rows.sort(key=lambda r: (r["score"] or 0), reverse=True)
        return {"status": status, "roles": rows}

    def run_discovery(self, hours: int | None = None, limit: int = 600) -> dict[str, Any]:
        """Live last-N-hours scan → score → packets. Needs network.

        hours defaults to the configured discovery window (72h). The limit caps
        total roles *seen* across all boards before the freshness filter; with
        ~27 boards it must be high enough that every board is scanned.
        """
        hours = int(hours) if hours else self.window_hours
        result = run_dry_pipeline(
            database_path=self.db_path,
            registry_path=self.config["live_company_registry"],
            output_root=self.export_root,
            config=self.config,
            limit=int(limit),
            posted_within_hours=int(hours),
        )
        # Market-wide top-ups (no-op unless the respective API keys are set).
        adzuna = discover_adzuna(self._db(), self.config, hours=int(hours))
        jsearch = discover_jsearch(self._db(), self.config, hours=int(hours))
        inserted = (
            (result.get("jobs_inserted") or 0)
            + (adzuna.get("jobs_inserted", 0) if adzuna.get("enabled") else 0)
            + (jsearch.get("jobs_inserted", 0) if jsearch.get("enabled") else 0)
        )
        return {
            "ok": True,
            "jobs_inserted": inserted,
            "dropped_stale": result.get("dropped_stale"),
            "dropped_undated": result.get("dropped_undated"),
            "packets_ready": result.get("packets_ready"),
            "network_status": result.get("network_status"),
            "adzuna": adzuna,
            "jsearch": jsearch,
        }

    def add_job(
        self,
        title: str,
        company: str,
        url: str = "",
        location: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        """Manually capture a role the automated sources missed (paste-in).

        For roles spotted anywhere (e.g. LinkedIn): the operator supplies the
        details and the app scores + tailors it like any other role. The app
        does NOT fetch/scrape the URL — only what's pasted is used, which keeps
        this ToS-clean. Returns where the role landed and its fit grade so the
        UI can jump straight to it.
        """
        title = (title or "").strip()
        company = (company or "").strip()
        if not title or not company:
            return {"ok": False, "error": "Title and company are required."}
        url = (url or "").strip()
        payload = {
            "title": title,
            "company": company,
            "apply_url": url,
            "source_url": url,
            "location": (location or "").strip(),
            "description": (description or "").strip(),
            # Freshly captured now, so a fit lands in the New bucket.
            "posted_at": utc_now(),
        }
        result = ingest_manual_job(
            self._db(), self.config, payload, output_root=self.export_root
        )
        if not result.get("ok"):
            return result
        ready = str(result.get("packet_status")) == "PACKET_READY"
        worth = str(result.get("verdict")) in self._WORTH_A_LOOK
        result["grade"] = self._grade(result.get("score"))
        result["bucket"] = (
            "outstanding" if ready else "new" if worth else "review"
        )
        return result

    def apply_autofill_bookmarklet(self) -> dict[str, Any]:
        """The reusable one-click autofill bookmarklet + a preview of what it fills.

        Built from the operator's approved contact/identity and answer draft.
        Saved once in the browser, it fills standard ATS fields on an open
        application form. It never uploads files, ticks the attestation, or
        submits — those stay the human's act.
        """
        try:
            master = load_resume_master(self.config["resume_master"])
            contact = master.get("contact", {}) or {}
            identity = master.get("identity", {}) or {}
            answer_bank = load_answer_bank(self.config["application_answer_bank"])
            evidence = load_claim_evidence(self.config["claim_evidence"])
            answers = build_answer_draft(answer_bank, evidence)
        except (OSError, ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        spec = build_autofill_spec(contact, identity, answers)
        fills = [f["concept"].replace("_", " ") for f in spec["fields"]]
        fills += [q["concept"].replace("_", " ") for q in spec["yesno"]]
        return {
            "ok": True,
            "bookmarklet": build_autofill_bookmarklet(contact, identity, answers),
            "fills": fills,
        }

    def auto_apply(self, job_id: int) -> dict[str, Any]:
        """M45 (beta): drive a real browser to fill the form AND attach the
        résumé/cover, then STOP at Submit for the human.

        Only for web-form roles. Saves both PDFs to ~/Downloads, builds the
        approved fill spec, and hands off to the Playwright driver. NEVER submits.
        """
        database = self._db()
        job = database.get_job(int(job_id))
        if not job:
            return {"ok": False, "error": f"Job {job_id} not found"}
        if not str(job.apply_url or "").lower().startswith("http"):
            return {
                "ok": False,
                "error": "This role is recruiter/ATS-routed (no web form). Use Prepare application instead.",
            }
        artifacts = self.make_artifacts(int(job_id))
        if not artifacts.get("ok"):
            return artifacts
        try:
            resume_pdf = self._download(artifacts["resume_pdf"], open_after=False)
            cover_pdf = self._download(artifacts["cover_pdf"], open_after=False)
            master = load_resume_master(self.config["resume_master"])
            answers = build_answer_draft(
                load_answer_bank(self.config["application_answer_bank"]),
                load_claim_evidence(self.config["claim_evidence"]),
            )
            spec = build_autofill_spec(
                master.get("contact", {}) or {},
                master.get("identity", {}) or {},
                answers,
            )
        except (OSError, ValueError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}
        from application_bot.auto_apply import auto_fill_application

        return auto_fill_application(job.apply_url, spec, resume_pdf, cover_pdf)

    def cover_letter_status(self) -> dict[str, Any]:
        """Whether cover letters are drafted by Claude or the offline template.

        Claude drafting needs the `anthropic` SDK installed AND an
        ANTHROPIC_API_KEY in the environment; otherwise the deterministic
        claim-safe template is used.
        """
        import importlib.util

        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_sdk = importlib.util.find_spec("anthropic") is not None
        model = (
            self.config.get("cover_letter_model")
            or os.environ.get("COVER_LETTER_MODEL")
            or "claude-opus-4-8"
        )
        return {
            "enabled": has_key and has_sdk,
            "has_key": has_key,
            "has_sdk": has_sdk,
            "model": model,
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

    def _download(self, source: str, *, open_after: bool = True) -> str:
        """Copy a generated artifact into ~/Downloads (a real download).

        Returns the destination path. Opens it in the OS viewer when
        open_after is set (single-asset clicks); the Start-application flow
        downloads both assets quietly and opens the form instead.
        """
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        dest = self.downloads_dir / Path(source).name
        shutil.copy2(source, dest)
        if open_after:
            subprocess.run(["open", str(dest)], check=False)
        return str(dest)

    def open_artifact(self, job_id: int, kind: str = "resume") -> dict[str, Any]:
        """Generate the role's optimized PDF and save it to ~/Downloads.

        kind: "resume" or "cover". The file is downloaded only — it is NOT
        opened in a viewer (the operator wants the file in the folder, not a
        Preview window popping up).
        """
        result = self.make_artifacts(int(job_id))
        if not result.get("ok"):
            return result
        source = result["cover_pdf"] if kind == "cover" else result["resume_pdf"]
        try:
            dest = self._download(source, open_after=False)
        except OSError as exc:  # pragma: no cover - platform dependent
            return {"ok": False, "error": str(exc), "path": source}
        return {"ok": True, "kind": kind, "path": dest, "downloaded": True}

    def start_application(self, job_id: int) -> dict[str, Any]:
        """One-click assisted apply — open the company's form with assets ready.

        BOUNDARY: this NEVER submits. It tailors and downloads both PDFs to
        ~/Downloads, opens the company's own apply page in the browser, and
        returns the pre-approved answers to paste plus the fields the human
        must complete personally. The submit/attestation stays the human's act.
        """
        database = self._db()
        job = database.get_job(int(job_id))
        if not job:
            return {"ok": False, "error": f"Job {job_id} not found"}
        result = self.make_artifacts(int(job_id))
        if not result.get("ok"):
            return result
        try:
            self._download(result["resume_pdf"], open_after=False)
            self._download(result["cover_pdf"], open_after=False)
        except OSError as exc:  # pragma: no cover - platform dependent
            return {"ok": False, "error": str(exc)}
        downloaded = [
            Path(result["resume_pdf"]).name,
            Path(result["cover_pdf"]).name,
        ]
        policy = evaluate_job_submission_policy(job, self.config)
        packet = packet_to_dict(
            generate_packet(
                job, self.config, policy, impact_highlights=self._approved_impact()
            )
        )
        plan = build_fill_plan(job, packet, self.export_root)
        answers = [
            {"label": field.label, "value": field.value}
            for field in plan.autofill_fields
        ]
        leave_blank = [field.label for field in plan.human_fields]
        is_form = str(job.apply_url or "").lower().startswith("http")
        if is_form:
            subprocess.run(["open", str(job.apply_url)], check=False)
        return {
            "ok": True,
            "opened": is_form,
            "is_form": is_form,
            # The raw apply channel — an http form URL, or a recruiter/ATS hint
            # like "recruiter:Savannah@Mondo …" for human-routed roles.
            "channel": job.apply_url or "",
            "apply_url": job.apply_url if is_form else "",
            "downloaded": downloaded,
            "answers": answers,
            "leave_blank": leave_blank,
        }

    def mark_applied(self, job_id: int, notes: str = "") -> dict[str, Any]:
        database = self._db()
        database.mark_applied(int(job_id), notes)
        return {"ok": True, "job_id": int(job_id), "status": "APPLIED"}

    def mark_responded(self, job_id: int, notes: str = "") -> dict[str, Any]:
        """Operator heard back — advance the role to the RESPONDED funnel stage."""
        database = self._db()
        database.mark_responded(int(job_id), notes)
        return {"ok": True, "job_id": int(job_id), "status": "RESPONDED"}

    def dashboard_summary(self) -> dict[str, Any]:
        """KPI tiles + funnel + segment breakdowns for the dashboard home.

        Pipeline stages mirror the 6sense buying stages: New -> Outstanding ->
        Applied -> Responded. by_source / by_grade describe the Outstanding
        working pile (the segment chips), and avg_score summarizes its fit.
        """
        database = self._db()
        jobs = database.list_jobs(scored_only=True)
        pipeline = {"new": 0, "outstanding": 0, "applied": 0, "responded": 0}
        by_source: dict[str, int] = {}
        by_grade = {"Hot": 0, "Warm": 0, "Cold": 0}
        outstanding_scores: list[int] = []
        for job in jobs:
            applied = str(job.status) == "APPLIED"
            responded = str(job.status) == "RESPONDED"
            ready = str(job.packet_status) == "PACKET_READY"
            if applied:
                pipeline["applied"] += 1
            if responded:
                pipeline["responded"] += 1
            if self._is_new_fit(job):
                pipeline["new"] += 1
            if ready and not applied and not responded:
                pipeline["outstanding"] += 1
                by_source[job.source] = by_source.get(job.source, 0) + 1
                grade = self._grade(job.score)
                if grade in by_grade:
                    by_grade[grade] += 1
                if job.score is not None:
                    outstanding_scores.append(int(job.score))
        avg_score = (
            round(sum(outstanding_scores) / len(outstanding_scores))
            if outstanding_scores
            else None
        )
        return {
            "pipeline": pipeline,
            "by_source": by_source,
            "by_grade": by_grade,
            "avg_score": avg_score,
            "total_scored": len(jobs),
            "window_hours": self.window_hours,
        }

    def job_detail(self, job_id: int) -> dict[str, Any]:
        """Full record for the slide-over detail panel: the enriched row plus a
        JD excerpt, fit reasons, and risk flags parsed from the score details."""
        database = self._db()
        job = database.get_job(int(job_id))
        if not job:
            return {"ok": False, "error": f"Job {job_id} not found"}
        try:
            details = json.loads(job.score_details_json or "{}")
        except (ValueError, TypeError):
            details = {}
        description = (job.description or "").strip()
        requirements = (job.requirements or "").strip()
        detail = self._row(job)
        detail.update(
            {
                "ok": True,
                "department": job.department or "",
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "description": description[:1600],
                "requirements": requirements[:1200],
                "reasons": list(details.get("reasons", [])),
                "risk_flags": list(details.get("risk_flags", [])),
                "dimensions": details.get("dimensions", {}),
                "recommended_next_action": job.recommended_next_action or "",
            }
        )
        return detail
