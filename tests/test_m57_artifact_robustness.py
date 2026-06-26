"""M57: artifact generation must never silently block the download step.

If document generation fails (bad profile path, render error, or a slow/hung
LLM call), make_artifacts returns a clean {ok: False, error} instead of raising,
so the caller surfaces the problem rather than skipping the download with no
explanation. The LLM call is also time-bounded so it can't stall the flow.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from app_api import JobAppAPI
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.models import Job


def _api(tmp_path, *, resume_master: str) -> tuple[JobAppAPI, int]:
    db_path = tmp_path / "crm.sqlite"
    database = Database(db_path)
    database.initialize()
    job = Job(
        external_id="j1", source="greenhouse", source_url="https://x/r",
        apply_url="https://x/apply", company="Acme",
        title="Director, Revenue Operations",
        description="Own revenue operations and GTM systems.",
    )
    job_id, _ = database.upsert_job(job)
    api = JobAppAPI(db_path=db_path)
    api.config = deepcopy(DEFAULT_CONFIG)
    api.config["resume_master"] = resume_master
    return api, job_id


def test_make_artifacts_reports_error_instead_of_raising(tmp_path):
    # Missing master file -> generation fails, but the bridge returns a clean
    # error dict (no exception), so the UI can show it.
    api, jid = _api(tmp_path, resume_master=str(tmp_path / "does_not_exist.yaml"))
    result = api.make_artifacts(jid)
    assert result["ok"] is False
    assert "error" in result


def test_make_artifacts_missing_job_is_clean(tmp_path):
    api, _ = _api(tmp_path, resume_master=str(tmp_path / "x.yaml"))
    assert api.make_artifacts(999999)["ok"] is False


def test_cover_letter_timeout_is_bounded(monkeypatch):
    # The Anthropic client is constructed with an explicit timeout so a hung
    # request can't stall artifact generation. Capture the kwargs.
    import application_bot.cover_letter_llm as cl

    captured: dict = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("network")

    fake_mod = type("anthropic", (), {"Anthropic": _FakeClient})
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_mod)
    monkeypatch.setenv("COVER_LETTER_TIMEOUT", "12")

    assert cl._call_claude("sys", "user", "claude-opus-4-8") is None
    assert captured.get("timeout") == 12.0
    assert captured.get("max_retries") == 1
