"""M48: configurable JSearch endpoint.

The JSearch search URL was hardcoded, so a different RapidAPI jobs API couldn't
be pointed in without code. It's now overridable — full URL via
RAPIDAPI_JSEARCH_URL, or host + path (RAPIDAPI_JSEARCH_HOST / _PATH, default
/search). The X-RapidAPI-Host header still uses the host.
"""

from __future__ import annotations

from copy import deepcopy

from application_bot.adapters.jsearch import DEFAULT_SEARCH_URL, JSearchAdapter
from application_bot.config import DEFAULT_CONFIG
from application_bot.database import Database
from application_bot.pipeline import discover_jsearch


class _Capture:
    """A transport that records the requested URL and returns no jobs."""

    def __init__(self):
        self.url = None

    def __call__(self, url):
        self.url = url
        return {"data": []}


def test_adapter_defaults_to_jsearch_url():
    cap = _Capture()
    JSearchAdapter(transport=cap).discover_jobs(what="revops")
    assert cap.url.startswith(DEFAULT_SEARCH_URL + "?")


def test_adapter_uses_custom_search_url():
    cap = _Capture()
    alt = "https://alt-jobs.p.rapidapi.com/v2/jobs"
    JSearchAdapter(transport=cap, search_url=alt).discover_jobs(what="revops")
    assert cap.url.startswith(alt + "?")


def test_discover_jsearch_honors_full_url_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
    monkeypatch.setenv("RAPIDAPI_JSEARCH_URL", "https://my-jobs-api.p.rapidapi.com/find")
    db = Database(tmp_path / "crm.sqlite"); db.initialize()
    cap = _Capture()
    discover_jsearch(db, deepcopy(DEFAULT_CONFIG), transport=cap, queries=["revops"])
    assert cap.url.startswith("https://my-jobs-api.p.rapidapi.com/find?")


def test_discover_jsearch_builds_url_from_host_and_path(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
    monkeypatch.delenv("RAPIDAPI_JSEARCH_URL", raising=False)
    monkeypatch.setenv("RAPIDAPI_JSEARCH_HOST", "jsearch2.p.rapidapi.com")
    monkeypatch.setenv("RAPIDAPI_JSEARCH_PATH", "search")  # no leading slash → normalized
    db = Database(tmp_path / "crm.sqlite"); db.initialize()
    cap = _Capture()
    discover_jsearch(db, deepcopy(DEFAULT_CONFIG), transport=cap, queries=["revops"])
    assert cap.url.startswith("https://jsearch2.p.rapidapi.com/search?")


def test_discover_jsearch_disabled_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    db = Database(tmp_path / "crm.sqlite"); db.initialize()
    result = discover_jsearch(db, deepcopy(DEFAULT_CONFIG))
    assert result["enabled"] is False
