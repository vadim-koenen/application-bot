"""M45: Playwright auto-attach — core fill/upload logic + the no-submit guard.

fill_page is driven by a fake page so we can assert the load-bearing safety
property: it fills text fields, selects yes/no answers, attaches the résumé/
cover — and NEVER clicks Submit or ticks the attestation. auto_fill_application
degrades gracefully when Playwright isn't installed.
"""

from __future__ import annotations

from application_bot.auto_apply import auto_fill_application, fill_page, reveal_form

SPEC = {
    "fields": [
        {"concept": "first_name", "value": "Vadim", "syn": ["first name"]},
        {"concept": "email", "value": "v@example.com", "syn": ["email"]},
        {"concept": "phone", "value": "(945) 344-3699", "syn": ["phone"]},
    ],
    "yesno": [
        {"concept": "work_authorization", "answer": "Yes", "syn": ["authorized to work"]},
    ],
}


class FakeLocator:
    def __init__(self, present, recorder):
        self._present = present
        self._rec = recorder

    def count(self):
        return 1 if self._present else 0

    @property
    def first(self):
        return self

    def fill(self, value):
        self._rec["fill"].append(value)

    def select_option(self, label=None):
        self._rec["select"].append(label)

    def click(self, *a, **k):  # must NEVER be called
        self._rec["click"].append(True)


class FakeFileInput:
    def __init__(self, label, recorder):
        self._label = label
        self._rec = recorder

    def evaluate(self, _js):
        return self._label

    def set_input_files(self, path):
        self._rec["files"].append(path)


class FakePage:
    """Matches the slice of the Playwright Page API that fill_page uses."""

    def __init__(self, labels, file_labels):
        # labels: set of label substrings present on the page
        self.labels = labels
        self.file_inputs = file_labels
        self.rec = {"fill": [], "select": [], "click": [], "files": [], "submit": []}

    def get_by_label(self, text, exact=False):
        present = any(text.lower() in lbl.lower() for lbl in self.labels)
        return FakeLocator(present, self.rec)

    def query_selector_all(self, _selector):
        return [FakeFileInput(lbl, self.rec) for lbl in self.file_inputs]

    # If fill_page ever tried to submit, these would record it (they must stay empty)
    def click(self, *a, **k):
        self.rec["submit"].append(True)


def test_fill_page_fills_selects_and_attaches():
    page = FakePage(
        labels=["First Name", "Email", "Phone", "Are you authorized to work in the US?"],
        file_labels=["Resume / CV", "Cover Letter"],
    )
    result = fill_page(page, SPEC, "/tmp/resume.pdf", "/tmp/cover.pdf")

    assert "first_name" in result["filled"]
    assert "email" in result["filled"]
    assert "work_authorization" in result["filled"]
    assert page.rec["fill"] == ["Vadim", "v@example.com", "(945) 344-3699"]
    assert page.rec["select"] == ["Yes"]
    # Résumé and cover both attached, to the right inputs.
    assert "/tmp/resume.pdf" in page.rec["files"]
    assert "/tmp/cover.pdf" in page.rec["files"]
    assert set(result["uploaded"]) == {"resume", "cover"}


def test_fill_page_never_submits():
    page = FakePage(labels=["First Name", "Email"], file_labels=["Resume"])
    fill_page(page, SPEC, "/tmp/resume.pdf", None)
    # The load-bearing guarantee: nothing was ever clicked/submitted.
    assert page.rec["click"] == []
    assert page.rec["submit"] == []


def test_fill_page_warns_on_missing_fields():
    page = FakePage(labels=["Email"], file_labels=[])  # no first-name/phone field
    result = fill_page(page, SPEC, None, None)
    assert any("first_name" in w for w in result["warnings"])
    assert result["uploaded"] == []


def test_unlabeled_single_file_input_defaults_to_resume():
    page = FakePage(labels=[], file_labels=[""])  # one unlabeled file input
    result = fill_page(page, {"fields": [], "yesno": []}, "/tmp/resume.pdf", "/tmp/cover.pdf")
    assert result["uploaded"] == ["resume"]


class MultiFramePage:
    """A page whose form lives in an iframe (the common ATS embed pattern)."""

    def __init__(self, frames):
        self.frames = frames


def test_fill_page_searches_iframes():
    top = FakePage(labels=[], file_labels=[])  # top document has no form
    iframe = FakePage(labels=["First Name", "Email"], file_labels=["Resume"])
    page = MultiFramePage([top, iframe])
    result = fill_page(page, SPEC, "/tmp/resume.pdf", None)
    # The fields in the iframe were filled (Playwright can reach cross-origin frames).
    assert "first_name" in result["filled"]
    assert "email" in result["filled"]
    assert "Vadim" in iframe.rec["fill"]
    assert "/tmp/resume.pdf" in iframe.rec["files"]
    # The empty top frame was never written to and nothing was submitted.
    assert top.rec["fill"] == []
    assert top.rec["click"] == [] and iframe.rec["click"] == []


class _RoleLoc:
    def __init__(self, present, rec):
        self._present = present
        self._rec = rec

    def count(self):
        return 1 if self._present else 0

    @property
    def first(self):
        return self

    def click(self, *a, **k):
        self._rec.append("apply-click")


class RevealPage:
    """Fake page for reveal_form: N text inputs + maybe an Apply control."""

    def __init__(self, text_inputs, apply_present):
        self.text_inputs = text_inputs
        self.apply_present = apply_present
        self.clicks = []

    def query_selector_all(self, selector):
        if "file" in selector:
            return []
        return [object()] * self.text_inputs

    def get_by_role(self, role, name=None, exact=False):
        present = self.apply_present and role in ("button", "link") and "apply" in (name or "").lower()
        return _RoleLoc(present, self.clicks)

    def wait_for_load_state(self, *a, **k):
        pass


def test_reveal_form_clicks_apply_when_no_form_present():
    page = RevealPage(text_inputs=0, apply_present=True)
    assert reveal_form(page) is True
    assert page.clicks == ["apply-click"]


def test_reveal_form_skips_when_form_already_present():
    page = RevealPage(text_inputs=6, apply_present=True)
    assert reveal_form(page) is False
    assert page.clicks == []  # didn't click anything


def test_reveal_form_no_apply_control():
    page = RevealPage(text_inputs=0, apply_present=False)
    assert reveal_form(page) is False
    assert page.clicks == []


def test_auto_fill_application_without_playwright(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_playwright(name, *a, **k):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("no playwright")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_playwright)
    r = auto_fill_application("https://x/apply", SPEC, "/tmp/r.pdf", "/tmp/c.pdf")
    assert r["ok"] is False
    assert "playwright" in r["error"].lower()
