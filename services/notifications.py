import smtplib
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


def send_email(to_address: str, subject: str, body: str) -> bool:
    if not config.SMTP_HOST or not config.SMTP_USER or not config.SMTP_PASSWORD:
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = to_address
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [to_address], msg.as_string())
        return True
    except Exception:
        return False


def check_and_notify_defaulters(threshold: float = None):
    threshold = threshold if threshold is not None else config.DEFAULTER_THRESHOLD
    defaulters = queries.get_defaulters(threshold)
    if defaulters:
        send_desktop_notification(
            "Attendance Alert",
            f"{len(defaulters)} student(s) below {threshold:.0f}% attendance.",
        )
    return defaulters


def notify_session_absentees(session_id: int):
    rows = queries.get_session_attendance(session_id)
    absentees = [r for r in rows if r["status"] == "absent"]
    if absentees:
        send_desktop_notification("Session Ended", f"{len(absentees)} student(s) marked absent.")
    return absentees
