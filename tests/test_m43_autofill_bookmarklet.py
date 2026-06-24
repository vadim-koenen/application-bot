"""M43: one-click autofill bookmarklet.

The bookmarklet embeds only approved, role-independent values and drops any
REVIEW_REQUIRED answer. It must never carry submit/attestation logic — those
stay the human's act.
"""

from __future__ import annotations

from application_bot.apply_helper import (
    build_autofill_bookmarklet,
    build_autofill_spec,
)

CONTACT = {
    "email": "person@example.com",
    "phone": "(555) 123-4567",
    "website": "example.com",
    "linkedin": "linkedin.com/in/person",
    "location": "Plano, TX",
    "city": "Plano",
    "state": "Texas",
    "zip": "75025",
    "street_address": "1 Main St.",
}
IDENTITY = {"name": "Test Person"}
ANSWERS = {
    "Current company": "Acme Co",
    "Work authorization": "Authorized to work in the United States.",
    "Sponsorship": "Does not require visa sponsorship.",
    "Compensation expectations": "REVIEW_REQUIRED — confirm against the range.",
}


def test_spec_includes_approved_and_splits_name():
    spec = build_autofill_spec(CONTACT, IDENTITY, ANSWERS)
    by_concept = {f["concept"]: f["value"] for f in spec["fields"]}
    assert by_concept["first_name"] == "Test"
    assert by_concept["last_name"] == "Person"
    assert by_concept["email"] == "person@example.com"
    # Bare website/linkedin get https-normalized.
    assert by_concept["website"].startswith("https://")
    assert by_concept["linkedin"].startswith("https://")
    yesno = {q["concept"]: q["answer"] for q in spec["yesno"]}
    assert yesno["work_authorization"] == "Yes"
    assert yesno["sponsorship"] == "No"


def test_review_required_answers_are_excluded():
    spec = build_autofill_spec(CONTACT, IDENTITY, ANSWERS)
    blob = str(spec)
    assert "REVIEW_REQUIRED" not in blob
    assert "Compensation" not in blob
    # Empty contact values produce no field entry.
    spec2 = build_autofill_spec({"email": "a@b.co"}, {"name": "A B"}, {})
    concepts = {f["concept"] for f in spec2["fields"]}
    assert "phone" not in concepts and "website" not in concepts
    assert spec2["yesno"] == []


def test_bookmarklet_is_javascript_url_with_values():
    bm = build_autofill_bookmarklet(CONTACT, IDENTITY, ANSWERS)
    assert bm.startswith("javascript:")
    assert "person@example.com" in bm
    assert "(555) 123-4567" in bm
    # No submit/click-submit/attestation automation is present.
    low = bm.lower()
    assert ".submit(" not in low
    assert "click()" not in low
    assert "requestsubmit" not in low
