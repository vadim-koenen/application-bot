"""M45: Playwright auto-attach — fill the form AND upload the résumé, stop at Submit.

A page bookmarklet (M43) can fill text fields but physically cannot set a file
input (browser security). A real automation driver can: Playwright's
`set_input_files` attaches the résumé/cover for you. This module drives a *real,
headed* browser to fill the standard fields, select the approved yes/no answers,
and attach the PDFs — then STOPS. It never clicks Submit, ticks the truthfulness
attestation, touches a CAPTCHA, or logs in. The human reviews and submits.

Boundaries:
- No submit / no attestation / no CAPTCHA — `fill_page` calls only fill /
  select_option / set_input_files; there is no click-submit path here.
- Only approved values flow in (the caller builds the spec from
  apply_helper.build_autofill_spec, which drops REVIEW_REQUIRED).

Caveats (tell the operator): Playwright opens a SEPARATE browser, not their
logged-in Chrome — so it works on public ATS forms (Greenhouse/Lever/Ashby) but
not login/CAPTCHA/enterprise-iframe portals. Heavy optional dependency
(`pip install playwright` + `python3 -m playwright install chromium`); the app
runs fine without it (lazy import → instructive error).
"""

from __future__ import annotations

from typing import Any

# File-input label matching. Cover checked before résumé ("cover letter"
# contains "letter"; a résumé input shouldn't grab the cover slot).
_COVER_SYN = ("cover letter", "cover", "letter")
_RESUME_SYN = ("resume", "résumé", "cv", "attach", "upload")

# JS run on each file <input> to derive a label-ish string (own attrs + the
# nearest label / wrapping text). Mirrors the bookmarklet's label heuristic.
_FILE_LABEL_JS = (
    "el => {var t='';try{if(el.id){var l=document.querySelector('label[for=\"'+el.id+'\"]');"
    "if(l)t+=' '+l.textContent;}}catch(e){}var p=el.closest&&el.closest('label,div,fieldset,li');"
    "if(p)t+=' '+p.textContent;return (t+' '+(el.name||'')+' '+(el.id||'')+' '+"
    "((el.getAttribute&&el.getAttribute('aria-label'))||'')).toLowerCase();}"
)


def fill_page(
    page: Any,
    spec: dict[str, list[dict[str, Any]]],
    resume_pdf: str | None,
    cover_pdf: str | None,
) -> dict[str, Any]:
    """Fill text fields, select yes/no answers, and attach files on an open page.

    Operates on a Playwright Page (or a compatible fake in tests). NEVER clicks
    Submit or ticks the attestation — it only fills, selects, and attaches.
    Returns {filled, uploaded, warnings}.
    """
    filled: list[str] = []
    uploaded: list[str] = []
    warnings: list[str] = []

    for field in spec.get("fields", []):
        matched = False
        for syn in field["syn"]:
            try:
                loc = page.get_by_label(syn, exact=False)
                if loc.count() < 1:
                    continue
                loc.first.fill(field["value"])
                filled.append(field["concept"])
                matched = True
                break
            except Exception:  # noqa: BLE001 - best-effort per field
                continue
        if not matched:
            warnings.append(f"no field matched: {field['concept']}")

    for question in spec.get("yesno", []):
        for syn in question["syn"]:
            try:
                loc = page.get_by_label(syn, exact=False)
                if loc.count() < 1:
                    continue
                loc.first.select_option(label=question["answer"])
                filled.append(question["concept"])
                break
            except Exception:  # noqa: BLE001
                continue

    try:
        file_inputs = page.query_selector_all("input[type='file']")
    except Exception:  # noqa: BLE001
        file_inputs = []
    for el in file_inputs:
        try:
            label = (el.evaluate(_FILE_LABEL_JS) or "").lower()
        except Exception:  # noqa: BLE001
            label = ""
        is_cover = any(s in label for s in _COVER_SYN)
        is_resume = any(s in label for s in _RESUME_SYN)
        try:
            if cover_pdf and is_cover and "cover" not in uploaded:
                el.set_input_files(cover_pdf)
                uploaded.append("cover")
            elif resume_pdf and (is_resume or not label) and "resume" not in uploaded:
                # explicit résumé input, or an unlabeled first file input
                el.set_input_files(resume_pdf)
                uploaded.append("resume")
        except Exception:  # noqa: BLE001
            warnings.append("could not attach a file input")

    return {"filled": filled, "uploaded": uploaded, "warnings": warnings}


def auto_fill_application(
    apply_url: str,
    spec: dict[str, list[dict[str, Any]]],
    resume_pdf: str | None,
    cover_pdf: str | None,
    *,
    headed: bool = True,
) -> dict[str, Any]:
    """Launch a real browser, fill the form + attach files, and leave it open.

    Returns {ok, filled, uploaded, warnings, note} or {ok: False, error}. The
    browser stays open (in a daemon thread) for the human to review and submit —
    this function NEVER submits. Lazy-imports Playwright; returns an instructive
    error if it isn't installed.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "ok": False,
            "error": (
                "Playwright isn't installed. Run: "
                "python3 -m pip install --user --break-system-packages playwright "
                "&& python3 -m playwright install chromium"
            ),
        }

    import threading

    result: dict[str, Any] = {}
    done = threading.Event()

    def _run() -> None:
        # Run the sync Playwright API in its own thread so it never collides with
        # pywebview's event loop. The thread stays alive holding the browser open
        # until the human closes the page.
        try:
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=not headed)
            page = browser.new_page()
            page.goto(apply_url, wait_until="domcontentloaded", timeout=45000)
            result.update(fill_page(page, spec, resume_pdf, cover_pdf))
            result["ok"] = True
            done.set()
            try:
                page.wait_for_event("close", timeout=0)  # block until human closes
            finally:
                browser.close()
                pw.stop()
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["error"] = str(exc)
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    done.wait(timeout=60)
    if not result:
        return {"ok": False, "error": "Timed out launching the browser."}
    if result.get("ok"):
        result["note"] = (
            "Browser left open — review the form, attach anything still missing, "
            "tick the attestation, and submit. The app never submits for you."
        )
    return result
