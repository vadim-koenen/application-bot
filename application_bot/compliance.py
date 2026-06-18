from __future__ import annotations


PROHIBITED_CAPABILITIES = frozenset(
    {
        "captcha_bypass",
        "login_bypass",
        "rate_limit_bypass",
        "bot_detection_evasion",
        "fingerprint_evasion",
        "proxy_rotation",
        "cookie_harvesting",
        "credential_scraping",
        "linkedin_scraping",
        "linkedin_auto_click",
        "indeed_scraping",
        "ziprecruiter_scraping",
    }
)

REVIEW_TRIGGERS = frozenset(
    {
        "captcha",
        "login_required",
        "unknown_legal_attestation",
        "unknown_required_question",
        "ambiguous_consent",
    }
)


def prohibited_requested(capabilities: set[str] | list[str]) -> list[str]:
    return sorted(set(capabilities) & PROHIBITED_CAPABILITIES)


def review_triggers(flags: set[str] | list[str]) -> list[str]:
    return sorted(set(flags) & REVIEW_TRIGGERS)
