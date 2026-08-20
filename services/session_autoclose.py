from datetime import date, datetime

from db import queries
from db.connection import get_connection


def close_expired_sessions_if_any():
    """Ends+finalizes any open per-slot session whose timetable slot's end_time has already passed
    today. Safe to call repeatedly; no-op if nothing is due. Does NOT touch the fallback
    'Auto Attendance' session (no natural end_time to compare against)."""
    conn = get_connection()
    today = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    due = conn.execute(
        """
        SELECT sess.id FROM sessions sess
        JOIN timetable_slots ts ON sess.timetable_slot_id = ts.id
        WHERE sess.session_date = %s AND sess.ended_at IS NULL AND ts.end_time <= %s
        """,
        (today, now_str),
    ).fetchall()
    for row in due:
        queries.finalize_absentees(row["id"])
        queries.end_session(row["id"])
    return [row["id"] for row in due]
