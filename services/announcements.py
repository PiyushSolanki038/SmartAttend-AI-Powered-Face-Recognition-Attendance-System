"""Class-scoped or institution-wide announcements, broadcast by faculty/admin. Fans out
via services/notifications.py::send_email to every student in scope who has an email on file."""

from db import queries
from services.notifications import send_email


class AnnouncementError(Exception):
    pass


def create_announcement(sender_user_id, subject: str, body: str, department=None, year=None,
                         semester=None, section=None, is_institution_wide: bool = False):
    if not subject or not subject.strip():
        raise AnnouncementError("Subject is required.")
    if not body or not body.strip():
        raise AnnouncementError("Message body is required.")
    announcement_id = queries.create_announcement(
        sender_user_id, subject.strip(), body.strip(), department=department, year=year,
        semester=semester, section=section, is_institution_wide=is_institution_wide,
    )

    if is_institution_wide:
        students = queries.list_students()
    else:
        students = [s for s in queries.list_students() if s["department"] == department]

    sent = []
    for student_row in students:
        student = queries.get_student(student_row["id"])
        email = student["email"] if student is not None else None
        if not email:
            continue
        if send_email(email, f"[SmartAttend] {subject.strip()}", body.strip()):
            sent.append(student["roll_no"])
    return announcement_id, sent


def list_for_cohort(department, year, semester):
    return queries.list_announcements_for_cohort(department, year, semester)
