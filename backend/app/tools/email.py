"""Email tool: drafts are written by Gemini, delivery happens over Gmail SMTP.

Every message is recorded in the `emails` table either way. The recorded
status is honest: "Simulated (SMTP not configured)" when there are no real
credentials, "SMTP failed: ..." on a login/send error, and
"Delivered via Gmail SMTP" only when Gmail accepted the message.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import now_local, smtp_config, smtp_configured
from ..database import connect
from ..tracing import log_action

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 20


def _send_via_gmail(sender: str, password: str, to_email: str, subject: str, body: str) -> None:
    """Raises on failure; caller converts the exception into a status string."""
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        server.starttls()
        # App passwords are displayed with spaces; Google wants them without.
        server.login(sender, password.replace(" ", ""))
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - connection may already be closed
            pass


def _record_email(to_email: str, subject: str, body: str, status: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO emails (recipient, subject, body, status, sent_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (to_email, subject, body, status, now_local().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
    finally:
        conn.close()


def send_executive_email(to_email: str, subject: str, body: str) -> str:
    """Sends (or simulates) a professional email and logs it."""
    log_action("Email API", f"Dispatching email to {to_email} | Subject: '{subject}'...")

    status = "Simulated (SMTP not configured)"
    if smtp_configured():
        sender, password = smtp_config()
        try:
            _send_via_gmail(sender, password, to_email, subject, body)
            status = "Delivered via Gmail SMTP"
        except Exception as error:  # noqa: BLE001 - report, never crash the run
            status = f"SMTP failed: {str(error)[:60]}"

    _record_email(to_email, subject, body, status)

    if status == "Delivered via Gmail SMTP":
        log_action("Email Sent", f"Delivered email to {to_email} via Gmail SMTP.")
        return f"Sent email to {to_email} with subject '{subject}' via Gmail SMTP."

    log_action("Email Not Sent", f"Email to {to_email} was only logged locally ({status}).")
    return (
        f"Logged the email to {to_email} with subject '{subject}', but it was NOT actually "
        f"delivered ({status}). Tell the user email delivery needs SMTP configuration."
    )
