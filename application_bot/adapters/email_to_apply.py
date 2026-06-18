from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
from typing import Any

from application_bot.adapters.manual_json import ManualJsonAdapter


class EmailToApplyAdapter(ManualJsonAdapter):
    source_name = "email_to_apply"
    supports_submission = True
    submission_mode = "AUTO_SUBMIT_EMAIL"

    def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
        live_apply_enabled: bool = False,
    ) -> dict[str, Any]:
        if not live_apply_enabled:
            return {"sent": False, "dry_run": True, "reason": "LIVE_APPLY_ENABLED is false"}
        required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"]
        missing = [name for name in required if not os.getenv(name)]
        if not recipient or missing:
            return {
                "sent": False,
                "dry_run": False,
                "reason": f"Missing email configuration: {', '.join(missing) or 'recipient'}",
            }

        message = EmailMessage()
        message["From"] = os.environ["FROM_EMAIL"]
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        for path in attachments or []:
            with open(path, "rb") as handle:
                data = handle.read()
            message.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=os.path.basename(path),
            )

        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
        return {"sent": True, "dry_run": False, "recipient": recipient}
