"""Faculty-facing bulk/manual attendance marking helpers for the live roster
(ui/screens/session.py): multi-select bulk present/absent, and the single-student
"flag as present" override, both routed through db.queries.bulk_set_attendance so
check_in_method is recorded consistently ('manual_override' for both cases, coordinated
with QR self check-in's 'qr' and the camera pipeline's 'face')."""

from db import queries
from services import audit


class AttendanceError(Exception):
    pass


def bulk_mark_attendance(session_id: int, student_ids: list, status: str, marked_by_user_id: int = None):
    if status not in ("present", "absent", "manual"):
        raise AttendanceError("status must be 'present', 'absent', or 'manual'.")
    if not student_ids:
        raise AttendanceError("No students selected.")
    queries.bulk_set_attendance(session_id, student_ids, status, check_in_method="manual_override")
    audit.log_action(marked_by_user_id, f"bulk_mark_{status}", "attendance", session_id,
                      details=f"{len(student_ids)} student(s)")


def flag_present(session_id: int, student_id: int, marked_by_user_id: int = None):
    """Manual single-student 'flag as present' from the live roster — reuses the same
    underlying update as bulk marking, with check_in_method='manual_override'."""
    queries.bulk_set_attendance(session_id, [student_id], "manual", check_in_method="manual_override")
    audit.log_action(marked_by_user_id, "flag_present", "attendance", student_id, details=f"session_id={session_id}")
