"""M18: assisted-apply fill plan.

Turns a claim-safe packet into a deterministic *fill plan* for the assisted-apply
step: which form fields the bot may pre-fill from approved answers, which fields
must be left blank for the human, and which ATS resume to attach.

Hard boundary (mirrors docs/PROJECT_STATE.md): this module NEVER submits. It only
produces a plan. The browser driver that consumes the plan fills the user's own
logged-in form and STOPS at Submit for a human click. There is intentionally no
code path here that clicks Submit, sends, or posts anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from application_bot.models import Job

# Values the packet uses to mark an answer the human must supply personally.
REVIEW_SENTINEL = "REVIEW_REQUIRED"

# Invariant recorded on every plan. The driver reads this and must never advance
# past the Submit control on its own.
SUBMIT_ACTION = "STOP_AT_SUBMIT_FOR_HUMAN"

# Maps the packet's human-readable "Suggested Answers" labels to a canonical
# machine key + category. Category is descriptive only; the autofill decision is
# driven by whether the value itself is a REVIEW_REQUIRED sentinel, so approvals
# that change in the claim inventory are respected automatically.
FIELD_MAP: dict[str, tuple[str, str]] = {
    "Name": ("full_name", "contact"),
    "Website": ("website", "contact"),
    "LinkedIn": ("linkedin", "contact"),
    "Current company": ("current_company", "positioning"),
    "Current positioning": ("current_positioning", "positioning"),
    "Desired role type": ("desired_role_type", "positioning"),
    "Location preference": ("location_preference", "positioning"),
    "Compensation expectations": ("compensation", "review_required"),
    "Work authorization": ("work_authorization", "authorization"),
    "Sponsorship": ("sponsorship", "authorization"),
    "Background check": ("background_check", "review_required"),
    "Legal-sensitive questions": ("legal_sensitive", "review_required"),
    "Unknown required questions": ("unknown_required", "review_required"),
    "Why interested": ("why_interested", "open_text"),
    "Why fit": ("why_fit", "open_text"),
}


@dataclass(slots=True)
class FillField:
    """One form field in the plan."""

    key: str
    label: str
    category: str
    value: str
    autofill: bool
    note: str = ""


@dataclass(slots=True)
class FillPlan:
    """A deterministic, submit-free plan for assisted apply."""

    job_id: int
    company: str
    title: str
    apply_url: str
    packet_status: str
    fields: list[FillField] = field(default_factory=list)
    resume_text_path: str | None = None
    resume_attached: bool = False
    warnings: list[str] = field(default_factory=list)
    submit_action: str = SUBMIT_ACTION

    @property
    def autofill_fields(self) -> list[FillField]:
        return [f for f in self.fields if f.autofill]

    @property
    def human_fields(self) -> list[FillField]:
        return [f for f in self.fields if not f.autofill]


def _is_review_required(value: str) -> bool:
    return not value.strip() or REVIEW_SENTINEL in value


def _looks_like_form_url(apply_url: str) -> bool:
    """A real web form lives at an http(s) URL; recruiter emails do not."""
    return apply_url.lower().startswith(("http://", "https://"))


def resolve_resume_text(
    job: Job,
    export_root: str | Path,
) -> str | None:
    """Return the newest ATS resume `.txt` for this role, or None.

    Looks under ``<export_root>/ats_resumes/<date>/<company>_<title>.txt`` and
    picks the most recent date folder, matching how ``export_ats_resume`` writes.
    """
    # Imported lazily to avoid a circular import with packets -> assisted_apply.
    from application_bot.packets import slugify

    root = Path(export_root) / "ats_resumes"
    if not root.is_dir():
        return None
    base = f"{slugify(job.company)}_{slugify(job.title)}.txt"
    candidates = sorted(
        (date_dir for date_dir in root.iterdir() if date_dir.is_dir()),
        reverse=True,
    )
    for date_dir in candidates:
        candidate = date_dir / base
        if candidate.is_file():
            return str(candidate)
    return None


def build_fill_plan(
    job: Job,
    packet: dict[str, Any],
    export_root: str | Path,
) -> FillPlan:
    """Build a submit-free fill plan from a job and its stored packet dict."""
    suggested = dict(packet.get("suggested_answers") or {})
    packet_status = str(
        packet.get("packet_status") or job.packet_status or "UNKNOWN"
    )

    fields: list[FillField] = []
    for label, value in suggested.items():
        key, category = FIELD_MAP.get(
            label, (label.lower().replace(" ", "_"), "open_text")
        )
        value = str(value)
        review = _is_review_required(value)
        fields.append(
            FillField(
                key=key,
                label=label,
                category=category,
                value="" if review else value,
                autofill=not review,
                note=(
                    "Leave blank — human must answer personally."
                    if review
                    else ""
                ),
            )
        )

    resume_text_path = resolve_resume_text(job, export_root)

    warnings: list[str] = []
    if packet_status != "PACKET_READY":
        warnings.append(
            f"Packet status is {packet_status}, not PACKET_READY — "
            "review before assisted apply."
        )
    if not _looks_like_form_url(job.apply_url):
        warnings.append(
            "Apply URL is not an http(s) form (e.g. a recruiter email). "
            "Assisted form-fill needs a live ATS posting URL."
        )
    if resume_text_path is None:
        warnings.append(
            "No ATS resume .txt found for this role — run `ats-resume` first."
        )
    human = [f.label for f in fields if not f.autofill]
    if human:
        warnings.append(
            "Fields left for the human to complete: " + ", ".join(human) + "."
        )

    return FillPlan(
        job_id=int(job.id or 0),
        company=job.company,
        title=job.title,
        apply_url=job.apply_url,
        packet_status=packet_status,
        fields=fields,
        resume_text_path=resume_text_path,
        resume_attached=resume_text_path is not None,
        warnings=warnings,
    )


def fill_plan_to_dict(plan: FillPlan) -> dict[str, Any]:
    data = asdict(plan)
    data["autofill_field_count"] = len(plan.autofill_fields)
    data["human_field_count"] = len(plan.human_fields)
    return data


def render_fill_plan_markdown(plan: FillPlan) -> str:
    def _rows(items: list[FillField]) -> str:
        if not items:
            return "- None.\n"
        return (
            "\n".join(
                f"- **{f.label}:** {f.value or '_(blank — human)_'}"
                + (f"  \n  _{f.note}_" if f.note else "")
                for f in items
            )
            + "\n"
        )

    warnings = (
        "\n".join(f"- {w}" for w in plan.warnings) + "\n"
        if plan.warnings
        else "- None.\n"
    )
    return f"""# Assisted-Apply Fill Plan: {plan.company} — {plan.title}

> **Submit policy:** `{plan.submit_action}`. This plan never submits. The driver
> fills the user's own logged-in form and stops at Submit for a human click.

## Opportunity

- **Job ID:** {plan.job_id}
- **Apply URL:** {plan.apply_url or "Not provided"}
- **Packet status:** {plan.packet_status}
- **Resume to attach:** {plan.resume_text_path or "None found"}

## Fields to pre-fill (approved)

{_rows(plan.autofill_fields)}
## Fields left for the human

{_rows(plan.human_fields)}
## Warnings

{warnings}"""
