import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
from db import queries

try:
    from plyer import notification as _plyer_notification
    _HAS_PLYER = True
except Exception:
    _HAS_PLYER = False


def send_desktop_notification(title: str, message: str):
    if not _HAS_PLYER:
        return
    try:
        _plyer_notification.notify(title=title, message=message, app_name=config.APP_NAME, timeout=8)
    except Exception:
        pass


def send_email(to_address: str, subject: str, body: str, html_body: str = None) -> bool:
    """Sends a plain-text email, or (if html_body is given) a multipart email with the plain
    text as a fallback for clients that don't render HTML. `body` is always required — some
    mail clients show only the plain-text part, or use it for notification previews."""
    if not config.SMTP_HOST or not config.SMTP_USER or not config.SMTP_PASSWORD:
        return False
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"{config.APP_NAME} <{config.SMTP_USER}>"
    msg["To"] = to_address
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [to_address], msg.as_string())
        return True
    except Exception:
        return False


_BRAND_COLOR = "#1F6AA5"


def render_email_html(heading: str, paragraphs: list, credentials: dict = None, note: str = None,
                       button: dict = None) -> str:
    """Builds a small branded HTML email body — inline-styled (email clients ignore <style>
    blocks/external CSS), single-column, safe in both light and dark mail-client themes since
    it sets its own background/text colors rather than relying on the client's defaults.
    `paragraphs`: list of plain strings, each rendered as its own <p> (HTML-escaped).
    `credentials`: optional {label: value} dict rendered as a highlighted key/value box
    (e.g. {"Username": "...", "Temporary Password": "..."}).
    `note`: optional small muted line rendered directly under the credentials box.
    `button`: optional {"text": ..., "url": ...} rendered as a call-to-action button."""
    body_html = "".join(f'<p style="margin:0 0 16px;color:#333333;font-size:15px;line-height:1.5;">{html.escape(p)}</p>' for p in paragraphs)

    creds_html = ""
    if credentials:
        rows = "".join(
            f'<tr>'
            f'<td style="padding:6px 12px;color:#666666;font-size:13px;">{html.escape(str(k))}</td>'
            f'<td style="padding:6px 12px;color:#111111;font-size:15px;font-family:Consolas,Menlo,monospace;font-weight:bold;">{html.escape(str(v))}</td>'
            f'</tr>'
            for k, v in credentials.items()
        )
        creds_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:#F4F7FA;border:1px solid #E1E8ED;border-radius:8px;margin:0 0 12px;">{rows}</table>'
        )

    note_html = f'<p style="margin:0 0 20px;color:#9AA5B1;font-size:13px;">{html.escape(note)}</p>' if note else ""

    button_html = ""
    if button:
        button_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 4px;">'
            f'<tr><td style="border-radius:6px;background:{_BRAND_COLOR};">'
            f'<a href="{html.escape(button["url"])}" target="_blank" '
            f'style="display:inline-block;padding:12px 28px;color:#ffffff;font-size:15px;font-weight:bold;'
            f'text-decoration:none;border-radius:6px;">{html.escape(button["text"])}</a>'
            f'</td></tr></table>'
        )

    return f"""\
<html>
<body style="margin:0;padding:0;background:#EEF2F5;font-family:Segoe UI,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F5;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.06);">
        <tr><td style="background:{_BRAND_COLOR};padding:22px 32px;">
          <span style="color:#ffffff;font-size:18px;font-weight:bold;letter-spacing:0.3px;">{html.escape(config.APP_NAME)}</span>
        </td></tr>
        <tr><td style="padding:28px 32px 32px;">
          <h1 style="margin:0 0 16px;font-size:20px;color:#111111;">{html.escape(heading)}</h1>
          {body_html}
          {creds_html}
          {note_html}
          {button_html}
        </td></tr>
        <tr><td style="padding:16px 32px;background:#FAFBFC;border-top:1px solid #EEF1F4;">
          <span style="color:#9AA5B1;font-size:12px;">This is an automated message from {html.escape(config.APP_NAME)}. Please don't reply to this email.</span>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def check_and_notify_defaulters(threshold: float = None):
    threshold = threshold if threshold is not None else config.DEFAULTER_THRESHOLD
    defaulters = queries.get_defaulters(threshold)
    if defaulters:
        send_desktop_notification(
            "Attendance Alert",
            f"{len(defaulters)} student(s) below {threshold:.0f}% attendance.",
        )
    return defaulters


def notify_low_attendance_students(threshold: float = None):
    """Emails every student below the threshold who has an email on file. Called after a day
    closes so students find out the same day, not just when they check the portal."""
    threshold = threshold if threshold is not None else config.DEFAULTER_THRESHOLD
    defaulters = queries.get_defaulters(threshold)
    sent = []
    for row in defaulters:
        student = queries.get_student(row["id"])
        if student is None or not student["email"]:
            continue
        body = (
            f"Hi {student['name']},\n\n"
            f"Your current attendance is {row['percentage']:.1f}%, which is below the "
            f"required {threshold:.0f}%. Please check the student portal for details.\n\n"
            f"- SmartAttend"
        )
        html_body = render_email_html(
            heading="Low Attendance Alert ⚠️",
            paragraphs=[
                f"Hi {student['name']}, your current attendance is below the required threshold.",
            ],
            credentials={"Current Attendance": f"{row['percentage']:.1f}%", "Required": f"{threshold:.0f}%"},
            note="Please check the student portal for a subject-wise breakdown.",
        )
        if send_email(student["email"], "Low Attendance Alert", body, html_body):
            sent.append(student["roll_no"])
    return sent


def notify_session_absentees(session_id: int):
    rows = queries.get_session_attendance(session_id)
    absentees = [r for r in rows if r["status"] == "absent"]
    if absentees:
        send_desktop_notification("Session Ended", f"{len(absentees)} student(s) marked absent.")
    return absentees
