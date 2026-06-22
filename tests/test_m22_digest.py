"""M22: apply digest email (link + PDF attachments).

The digest is a self-notification to the user: one email listing ready roles
with the apply link, with the tailored résumé/cover PDFs attached. Dry-run
writes an .eml preview and needs no SMTP; live needs SMTP env; an empty list
sends nothing; a missing recipient is reported.
"""

from __future__ import annotations

from email import message_from_bytes
from pathlib import Path

from application_bot.email_service import build_digest_message, send_apply_digest


def _pdf(tmp_path: Path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 minimal")
    return str(p)


def _items(tmp_path: Path) -> list[dict]:
    return [
        {
            "company": "Acme",
            "title": "Director, Marketing Operations",
            "score": 81,
            "apply_url": "https://boards.greenhouse.io/acme/jobs/1",
            "attachments": [_pdf(tmp_path, "a_resume.pdf"), _pdf(tmp_path, "a_cover.pdf")],
        }
    ]


def test_message_has_link_and_pdf_attachments(tmp_path):
    msg = build_digest_message(
        _items(tmp_path), to="me@example.com", from_email="bot@example.com"
    )
    assert msg["To"] == "me@example.com"
    pdfs = [
        part
        for part in msg.iter_attachments()
        if part.get_content_type() == "application/pdf"
    ]
    assert len(pdfs) == 2
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "https://boards.greenhouse.io/acme/jobs/1" in html


def test_dry_run_writes_eml_preview_without_smtp(tmp_path):
    result = send_apply_digest(
        _items(tmp_path), to="me@example.com", output_root=tmp_path
    )
    assert result["mode"] == "DRY_RUN"
    assert result["roles"] == 1
    assert result["attachments"] == 2
    preview = Path(result["preview_path"])
    assert preview.exists()
    parsed = message_from_bytes(preview.read_bytes())
    assert parsed["Subject"].startswith("Your job apply digest")


def test_live_send_uses_injected_sender(tmp_path, monkeypatch):
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"):
        monkeypatch.setenv(var, "x")
    sent = []
    result = send_apply_digest(
        _items(tmp_path),
        to="me@example.com",
        output_root=tmp_path,
        live=True,
        sender=lambda message: sent.append(message),
    )
    assert result["mode"] == "LIVE"
    assert result["sent"] is True
    assert len(sent) == 1


def test_live_blocked_without_smtp(tmp_path, monkeypatch):
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    result = send_apply_digest(
        _items(tmp_path), to="me@example.com", output_root=tmp_path, live=True
    )
    assert result["mode"] == "LIVE_BLOCKED"
    assert "Missing SMTP config" in result["reason"]


def test_empty_and_no_recipient(tmp_path):
    assert send_apply_digest([], to="me@example.com", output_root=tmp_path)["mode"] == "EMPTY"
    assert send_apply_digest(
        _items(tmp_path), to="", output_root=tmp_path
    )["mode"] == "NO_RECIPIENT"
