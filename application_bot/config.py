from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "target_titles": [
        "director",
        "senior director",
        "sr director",
        "vice president",
        "vp",
        "head of",
        "executive",
    ],
    "reject_titles": ["coordinator", "specialist", "associate", "manager"],
    "target_keywords": [
        "growth marketing",
        "demand generation",
        "revenue systems",
        "gtm systems",
        "go-to-market",
        "gtm strategy",
        "marketing operations",
        "lifecycle marketing",
        "performance marketing",
        "ai transformation",
    ],
    "reject_keywords": ["account executive", "sales representative", "cold calling"],
    "location_preferences": {
        "remote_us": ["remote", "united states", "us remote", "remote - us"],
        "dfw": ["dallas", "plano", "dfw", "fort worth"],
    },
    "salary_minimums": {
        "default": 140000,
        "director": 150000,
        "senior_director": 175000,
        "vp": 200000,
    },
    "source_policy": {
        "greenhouse": "AUTO_PACKET_ONLY",
        "lever": "AUTO_PACKET_ONLY",
        "ashby": "AUTO_PACKET_ONLY",
        "linkedin_review_queue": "REVIEW_REQUIRED",
        "indeed_connector": "BLOCKED",
        "zip_connector": "BLOCKED",
    },
    "dry_run": True,
    "live_apply_enabled": False,
    "live_email_send_enabled": False,
    "email_send_approval_phrase": "",
    "database_path": "data/application_bot.sqlite",
    "export_path": "exports",
    "live_company_registry": "config/live_company_registry.yaml",
    "pipeline_limit": 25,
    "scheduler": {
        "enabled": False,
        "cadence": "daily",
        "time": "08:00",
        "timezone": "America/Chicago",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    candidate = Path(path) if path else Path("config/default.yaml")
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as handle:
            config = _deep_merge(config, yaml.safe_load(handle) or {})

    config["database_path"] = os.getenv(
        "APPLICATION_BOT_DB", config["database_path"]
    )
    live_flag = os.getenv("LIVE_APPLY_ENABLED")
    if live_flag is not None:
        config["live_apply_enabled"] = live_flag.strip().lower() == "true"
    live_email_flag = os.getenv("LIVE_EMAIL_SEND_ENABLED")
    if live_email_flag is not None:
        config["live_email_send_enabled"] = (
            live_email_flag.strip().lower() == "true"
        )
    config["email_send_approval_phrase"] = os.getenv(
        "EMAIL_SEND_APPROVAL_PHRASE",
        str(config.get("email_send_approval_phrase") or ""),
    )
    config["dry_run"] = not bool(config["live_apply_enabled"])
    return config


def load_company_registry(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return list(payload.get("companies", []))
