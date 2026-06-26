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
    "systems_lane_titles": ["manager", "lead"],
    "systems_lane_functions": [
        "systems",
        "operations",
        "revops",
        "revenue operations",
        "marketing operations",
        "marketing technology",
        "martech",
        "gtm systems",
        "marketing data",
    ],
    "systems_lane_points": 12,
    "target_keywords": [
        "growth marketing",
        "demand generation",
        "revenue systems",
        "revenue operations",
        "revops",
        "gtm systems",
        "go-to-market",
        "gtm strategy",
        "marketing operations",
        "marketing technology",
        "martech",
        "marketing systems",
        "lifecycle marketing",
        "lifecycle operations",
        "marketing automation",
        "abm",
        "ai transformation",
    ],
    "reject_keywords": [
        "account executive",
        "sales representative",
        "cold calling",
        "product marketing",
        "paid media",
        "performance marketing",
        "media buying",
        "brand marketing",
        "field marketing",
    ],
    "off_lane_titles": [
        "director, product",
        "director of product",
        "head of product",
        "product marketing",
        "customer success",
        "technical program management",
        "performance marketing",
        "paid media",
        "brand marketing",
        "field marketing",
        "consumer growth",
        # Off-lane *functions* that otherwise slip through on a Director/Head
        # title (they carry seniority points but the function is not Vadim's).
        "engineer",
        "design",
        "finance",
        "accounting",
        "controller",
        "legal",
        "counsel",
        "attorney",
        "litigation",
        "recruiter",
        "talent acquisition",
        "people operations",
        "human resources",
        "account management",
        "account executive",
        "solutions architect",
        "executive assistant",
        "administrative assistant",
        "business partner",
        "chief of staff",
    ],
    "role_mismatch_penalty": -30,
    "years_requirement_scoring": {
        "approved_years": 14,
        "moderate_threshold": 15,
        "moderate_penalty": -6,
        "high_threshold": 18,
        "high_penalty": -15,
    },
    "packet_soft_requirement_claims": ["years_of_experience"],
    # Discovery freshness window (hours) for the New tab + default scans.
    "discovery_window_hours": 72,
    # Hard location gate: a role must be remote OR in the DFW metroplex, else
    # it scores NOT_WORTH_TIME regardless of fit.
    "require_remote_or_dfw": True,
    "location_preferences": {
        "remote_us": ["remote", "united states", "us remote", "remote - us"],
        "dfw": [
            "dallas", "plano", "dfw", "fort worth", "metroplex", "irving",
            "frisco", "mckinney", "arlington", "richardson", "garland", "denton",
            "carrollton", "lewisville", "allen", "grand prairie", "addison",
            "euless", "grapevine", "southlake", "flower mound", "the colony",
            # DFW metroplex counties (Adzuna lists "City, County"); distinctive
            # enough to avoid out-of-state collisions.
            "tarrant", "collin", "rockwall", "kaufman",
        ],
        # Foreign-country / non-US markers. A "remote" role pinned to one of these
        # (with no US eligibility marker) is treated as off-geography — not
        # workable from DFW — so it's dropped like a non-DFW onsite role.
        "non_us": [
            "canada", "ontario", "toronto", "vancouver", "british columbia",
            "quebec", "montreal", "united kingdom", "england", "london",
            "scotland", "ireland", "dublin", "france", "paris", "germany",
            "berlin", "munich", "netherlands", "amsterdam", "spain", "madrid",
            "barcelona", "portugal", "lisbon", "poland", "warsaw", "romania",
            "india", "bengaluru", "bangalore", "hyderabad", "pune", "japan",
            "tokyo", "singapore", "australia", "sydney", "melbourne", "mexico",
            "brazil", "argentina", "israel", "tel aviv", "philippines", "manila",
            "china", "shanghai", "shenzhen", "hong kong", "united arab emirates",
            "dubai", "south africa", "nigeria", "kenya",
            # Regions / continents — "Remote - Europe / EMEA / APAC" is not US.
            "europe", "emea", "apac", "asia", "latam", "latin america",
            "middle east",
        ],
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
    "resume_claim_inventory": "config/resume_claim_inventory.yaml",
    "resume_master": "data/private/resume_master.yaml",
    "claim_evidence": "config/claim_evidence.yaml",
    "application_answer_bank": "config/application_answer_bank.yaml",
    "pipeline_limit": 25,
    "packet_thresholds": {
        "ready_min_score": 65,
        "review_min_score": 45,
        "strong_function_points": 10,
    },
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
    companies = []
    for entry in payload.get("companies", []):
        company = dict(entry)
        company["name"] = str(company.get("name") or company.get("company") or "").strip()
        if company["name"]:
            companies.append(company)
    return companies


def load_claim_inventory(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        inventory = yaml.safe_load(handle) or {}
    required = {
        "identity",
        "contact_assets",
        "current_business_identity",
        "target_roles",
        "approved_positioning_themes",
        "approved_skill_keywords",
        "approved_tools_platforms",
        "approved_experience_claims",
        "approved_metrics",
        "prohibited_or_unverified_claims",
        "claim_substitution_rules",
    }
    missing = sorted(required - set(inventory))
    if missing:
        raise ValueError(f"Claim inventory is missing fields: {', '.join(missing)}")
    return inventory


def load_claim_evidence(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("Claim evidence must contain a claims list")
    required = {
        "claim_id",
        "claim_text",
        "category",
        "approval_status",
        "evidence_source",
        "evidence_detail",
        "allowed_contexts",
        "prohibited_contexts",
        "confidence",
        "requires_user_approval",
        "last_verified_at",
    }
    for claim in claims:
        missing = sorted(required - set(claim))
        if missing:
            raise ValueError(
                f"Claim {claim.get('claim_id', '<unknown>')} is missing: "
                + ", ".join(missing)
            )
    return payload


def load_answer_bank(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload.get("answers"), dict):
        raise ValueError("Application answer bank must contain an answers mapping")
    return payload
