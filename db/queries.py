import logging
import pickle
from datetime import date

import numpy as np

from db.connection import get_connection

logger = logging.getLogger(__name__)


# ---------- Students ----------

def insert_student(roll_no: str, name: str, department: str, year: int, semester: int, encoding: np.ndarray,
                    email: str = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO students (roll_no, name, department, year, semester, encoding, email) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (roll_no, name, department, year, semester, pickle.dumps(encoding), email),
    )
    conn.commit()
    return cur.fetchone()["id"]


def update_student(student_id: int, roll_no: str, name: str, department: str, year: int, semester: int):
    conn = get_connection()
    conn.execute(
        "UPDATE students SET roll_no = %s, name = %s, department = %s, year = %s, semester = %s WHERE id = %s",
        (roll_no, name, department, year, semester, student_id),
    )
    conn.commit()


def update_student_encoding(student_id: int, encoding: np.ndarray):
    conn = get_connection()
    conn.execute("UPDATE students SET encoding = %s WHERE id = %s", (pickle.dumps(encoding), student_id))
    conn.commit()


def delete_student(student_id: int):
    """Hard-deletes a student and every row referencing them, in dependency order. Done
    explicitly here rather than relying on each table's ON DELETE CASCADE: dispute_requests
    also references attendance(id) with no cascade (must clear before attendance rows), and
    auth_logs references users(id) with no cascade (must clear before the student's portal
    login row) — see services/auth.py's log_auth_event, called on every portal login/logout.
    This is a deliberate, user-triggered action (the Delete button in Enroll Student)."""
    conn = get_connection()
    conn.execute("DELETE FROM dispute_requests WHERE student_id = %s", (student_id,))
    conn.execute("DELETE FROM checkin_requests WHERE student_id = %s", (student_id,))
    conn.execute("DELETE FROM rescan_requests WHERE student_id = %s", (student_id,))
    # Subqueries (not fetchone()) so these cover every users row tied to this student, not
    # just the first — student_id has no uniqueness constraint, so duplicates are possible.
    # auth_logs rows for this account are deleted outright (pure history, fine to lose).
    # The *_user_id columns below record "who created/resolved this" on rows that must
    # survive the delete (other students' sessions/requests) — those are detached (SET NULL)
    # rather than deleted, so we don't destroy unrelated attendance/request history.
    user_id_subquery = "(SELECT id FROM users WHERE student_id = %s)"
    conn.execute(f"DELETE FROM auth_logs WHERE user_id IN {user_id_subquery}", (student_id,))
    conn.execute(f"UPDATE sessions SET created_by_user_id = NULL WHERE created_by_user_id IN {user_id_subquery}", (student_id,))
    conn.execute(f"UPDATE dispute_requests SET resolved_by_user_id = NULL WHERE resolved_by_user_id IN {user_id_subquery}", (student_id,))
    conn.execute(f"UPDATE checkin_requests SET resolved_by_user_id = NULL WHERE resolved_by_user_id IN {user_id_subquery}", (student_id,))
    conn.execute(f"UPDATE rescan_requests SET resolved_by_user_id = NULL WHERE resolved_by_user_id IN {user_id_subquery}", (student_id,))
    conn.execute("DELETE FROM users WHERE student_id = %s", (student_id,))
    conn.execute("DELETE FROM attendance WHERE student_id = %s", (student_id,))
    conn.execute("DELETE FROM student_encodings WHERE student_id = %s", (student_id,))
    conn.execute("DELETE FROM students WHERE id = %s", (student_id,))
    conn.commit()


def list_students():
    conn = get_connection()
    return conn.execute("SELECT id, roll_no, name, department, year, semester FROM students ORDER BY roll_no").fetchall()


def get_all_encodings():
    """Returns list of (student_id, encoding_ndarray) across all stored encodings per student
    (multiple rows per student improve match robustness). Skips rows with corrupt BLOBs."""
    conn = get_connection()
    rows = conn.execute("SELECT student_id, encoding FROM student_encodings").fetchall()
    result = []
    for row in rows:
        try:
            encoding = pickle.loads(row["encoding"])
            result.append((row["student_id"], encoding))
        except Exception:
            logger.warning("Corrupt encoding blob for student_id=%s, skipping", row["student_id"])
    return result


def insert_student_encoding(student_id: int, encoding: np.ndarray, source: str = "enrollment"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO student_encodings (student_id, encoding, source) VALUES (%s, %s, %s)",
        (student_id, pickle.dumps(encoding), source),
    )
    conn.commit()


def get_encodings_for_student(student_id: int):
    conn = get_connection()
    rows = conn.execute("SELECT encoding FROM student_encodings WHERE student_id = %s", (student_id,)).fetchall()
    result = []
    for row in rows:
        try:
            result.append(pickle.loads(row["encoding"]))
        except Exception:
            logger.warning("Corrupt encoding blob for student_id=%s, skipping", student_id)
    return result


def get_student(student_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM students WHERE id = %s", (student_id,)).fetchone()


# ---------- Sessions ----------

def start_session(subject: str, section: str, faculty: str, created_by_user_id: int = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (subject, section, faculty, created_by_user_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (subject, section, faculty, created_by_user_id),
    )
    conn.commit()
    return cur.fetchone()["id"]


AUTO_SESSION_SUBJECT = "Auto Attendance"


def get_open_auto_session_today():
    """started_at uses sqlite's CURRENT_TIMESTAMP (UTC), so compare against UTC 'now' —
    not 'localtime' — to avoid timezone-mismatch creating duplicate day-sessions."""
    conn = get_connection()
    return conn.execute(
        """
        SELECT * FROM sessions
        WHERE subject = %s AND started_at::date = CURRENT_DATE AND ended_at IS NULL
        """,
        (AUTO_SESSION_SUBJECT,),
    ).fetchone()


def find_active_timetable_slot(department, year, semester, day_of_week, time_str):
    """Returns the timetable slot (if any) covering time_str ('HH:MM') on day_of_week for the given
    department/year/semester. Section is intentionally NOT filtered here — students table has no
    section column (see plan D3)."""
    conn = get_connection()
    return conn.execute(
        """
        SELECT * FROM timetable_slots
        WHERE department = %s AND year = %s AND semester = %s
          AND day_of_week = %s AND start_time <= %s AND end_time > %s
        LIMIT 1
        """,
        (department, year, semester, day_of_week, time_str, time_str),
    ).fetchone()


def get_open_session_for_slot(timetable_slot_id, session_date):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM sessions WHERE timetable_slot_id = %s AND session_date = %s AND ended_at IS NULL",
        (timetable_slot_id, session_date),
    ).fetchone()


def get_or_create_slot_session(slot, session_date, created_by_user_id=None):
    """Returns the id of today's open session for this timetable slot, creating it on first call.
    subject/section/faculty are copied from the slot at creation time (frozen snapshot — a later
    timetable edit doesn't retroactively rewrite already-created sessions)."""
    existing = get_open_session_for_slot(slot["id"], session_date)
    if existing:
        return existing["id"]
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (subject, section, faculty, timetable_slot_id, session_date, created_by_user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (slot["subject"], slot["section"], slot["faculty"], slot["id"], session_date, created_by_user_id),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_open_fallback_session_today(session_date):
    """The 'General/Unscheduled' session used only when a recognized student has no matching
    timetable slot right now. One per calendar day, timetable_slot_id IS NULL."""
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM sessions WHERE timetable_slot_id IS NULL AND subject = %s "
        "AND session_date = %s AND ended_at IS NULL",
        (AUTO_SESSION_SUBJECT, session_date),
    ).fetchone()


def get_or_create_fallback_session(session_date, created_by_user_id=None):
    existing = get_open_fallback_session_today(session_date)
    if existing:
        return existing["id"]
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (subject, section, faculty, timetable_slot_id, session_date, created_by_user_id) "
        "VALUES (%s, NULL, NULL, NULL, %s, %s) RETURNING id",
        (AUTO_SESSION_SUBJECT, session_date, created_by_user_id),
    )
    conn.commit()
    return cur.fetchone()["id"]


def list_open_sessions_today(session_date):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM sessions WHERE session_date = %s AND ended_at IS NULL", (session_date,)
    ).fetchall()


def close_day():
    """Finalizes absentees and ends every still-open session for today (one per subject/slot, plus
    the fallback session if any). Returns the list of closed session ids (was: single id or None)."""
    today = date.today().isoformat()
    closed_ids = []
    for session in list_open_sessions_today(today):
        finalize_absentees(session["id"])
        end_session(session["id"])
        closed_ids.append(session["id"])
    return closed_ids


def get_sessions_by_user(user_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM sessions WHERE created_by_user_id = %s ORDER BY started_at DESC", (user_id,)
    ).fetchall()


def end_session(session_id: int):
    conn = get_connection()
    conn.execute("UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = %s", (session_id,))
    conn.commit()


def get_session(session_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()


def list_sessions():
    conn = get_connection()
    return conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()


# ---------- Attendance ----------

def mark_present(session_id: int, student_id: int, confidence: float) -> bool:
    """Returns True if a new attendance row was inserted (first time seen this session)."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM attendance WHERE session_id = %s AND student_id = %s",
        (session_id, student_id),
    ).fetchone()
    if existing:
        return False
    conn.execute(
        "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (%s, %s, 'present', %s)",
        (session_id, student_id, confidence),
    )
    conn.commit()
    return True


def log_unknown(session_id: int, confidence: float = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (%s, NULL, 'unknown', %s)",
        (session_id, confidence),
    )
    conn.commit()


def manual_override(session_id: int, student_id: int, status: str):
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM attendance WHERE session_id = %s AND student_id = %s",
        (session_id, student_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE attendance SET status = %s, marked_at = CURRENT_TIMESTAMP WHERE id = %s",
            (status, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (%s, %s, %s, NULL)",
            (session_id, student_id, status),
        )
    conn.commit()


def finalize_absentees(session_id: int):
    """Mark enrolled students with no attendance row in this session as absent. If the session is
    tied to a timetable slot, scope to students in that slot's department/year/semester (its actual
    cohort); otherwise (fallback/legacy sessions) fall back to the previous all-students behavior.
    No-ops if already ended, to avoid duplicate absent rows if both the auto-close poller and a
    manual Close Day race."""
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()
    if session is None or session["ended_at"] is not None:
        return
    slot = None
    if session["timetable_slot_id"]:
        slot = conn.execute("SELECT * FROM timetable_slots WHERE id = %s", (session["timetable_slot_id"],)).fetchone()

    if slot:
        conn.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, confidence)
            SELECT %s, s.id, 'absent', NULL
            FROM students s
            WHERE (s.department IS NOT DISTINCT FROM %s AND s.year IS NOT DISTINCT FROM %s AND s.semester IS NOT DISTINCT FROM %s)
              AND s.id NOT IN (SELECT student_id FROM attendance WHERE session_id = %s AND student_id IS NOT NULL)
            """,
            (session_id, slot["department"], slot["year"], slot["semester"], session_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO attendance (session_id, student_id, status, confidence)
            SELECT %s, s.id, 'absent', NULL
            FROM students s
            WHERE s.id NOT IN (SELECT student_id FROM attendance WHERE session_id = %s AND student_id IS NOT NULL)
            """,
            (session_id, session_id),
        )
    conn.commit()


def log_spoof_attempt(session_id: int):
    conn = get_connection()
    conn.execute("INSERT INTO spoof_logs (session_id) VALUES (%s)", (session_id,))
    conn.commit()


def get_spoof_count(session_id: int) -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) as c FROM spoof_logs WHERE session_id = %s", (session_id,)).fetchone()["c"]


def get_session_attendance(session_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT a.id, a.status, a.confidence, a.marked_at,
               s.id as student_id, s.roll_no, s.name, s.department
        FROM attendance a
        LEFT JOIN students s ON a.student_id = s.id
        WHERE a.session_id = %s
        ORDER BY a.marked_at
        """,
        (session_id,),
    ).fetchall()


def get_filtered_attendance(subject: str = None, section: str = None, start_date: str = None, end_date: str = None,
                             department: str = None, limit: int = None, offset: int = 0,
                             include_unknown: bool = False):
    """By default excludes status='unknown' rows — those are raw per-frame "face detected but
    not recognized" logs (one row per detection tick, see ml/detector + services/session.py),
    not an actual student's attendance mark, and can vastly outnumber real records for a single
    unrecognized face lingering in frame. Pass include_unknown=True to see them (e.g. debugging)."""
    conn = get_connection()
    query = """
        SELECT a.status, a.confidence, a.marked_at,
               sess.subject, sess.section, sess.started_at,
               st.roll_no, st.name, st.department
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        LEFT JOIN students st ON a.student_id = st.id
        WHERE 1=1
    """
    params = []
    if not include_unknown:
        query += " AND a.status != 'unknown'"
    if subject:
        query += " AND sess.subject = %s"
        params.append(subject)
    if section:
        query += " AND sess.section = %s"
        params.append(section)
    if department:
        query += " AND st.department = %s"
        params.append(department)
    if start_date:
        query += " AND sess.started_at::date >= %s::date"
        params.append(start_date)
    if end_date:
        query += " AND sess.started_at::date <= %s::date"
        params.append(end_date)
    query += " ORDER BY sess.started_at DESC"
    if limit is not None:
        query += " LIMIT %s OFFSET %s"
        params += [limit, offset]
    return conn.execute(query, params).fetchall()


def get_distinct_subjects():
    conn = get_connection()
    return [r["subject"] for r in conn.execute("SELECT DISTINCT subject FROM sessions ORDER BY subject").fetchall()]


def get_distinct_sections():
    conn = get_connection()
    return [r["section"] for r in conn.execute("SELECT DISTINCT section FROM sessions WHERE section IS NOT NULL ORDER BY section").fetchall()]


def get_distinct_departments():
    conn = get_connection()
    return [r["department"] for r in conn.execute(
        "SELECT DISTINCT department FROM students WHERE department IS NOT NULL ORDER BY department"
    ).fetchall()]


# ---------- Analytics ----------

def get_attendance_percentages(subject: str = None, department: str = None, year: int = None, semester: int = None):
    """Returns list of rows: id, roll_no, name, present_count, total_count, percentage.
    total_count is the number of sessions the student has any attendance row for
    (present/absent/manual) — unknown rows (no student_id) are excluded.
    department/year/semester scope the result to a single class/cohort (e.g. for a student's
    portal comparisons, which should only weigh against their own batch, not the whole college)."""
    conn = get_connection()
    query = """
        SELECT st.id, st.roll_no, st.name,
               SUM(CASE WHEN a.status = 'present' OR a.status = 'manual' THEN 1 ELSE 0 END) as present_count,
               COUNT(a.id) as total_count
        FROM students st
        LEFT JOIN attendance a ON a.student_id = st.id
        LEFT JOIN sessions sess ON a.session_id = sess.id
        WHERE 1=1
    """
    params = []
    if subject:
        query += " AND sess.subject = %s"
        params.append(subject)
    if department:
        query += " AND st.department = %s"
        params.append(department)
    if year is not None:
        query += " AND st.year = %s"
        params.append(year)
    if semester is not None:
        query += " AND st.semester = %s"
        params.append(semester)
    query += " GROUP BY st.id ORDER BY st.roll_no"
    rows = conn.execute(query, params).fetchall()

    result = []
    for row in rows:
        total = row["total_count"] or 0
        present = row["present_count"] or 0
        pct = (present / total * 100) if total else 0.0
        result.append({
            "id": row["id"], "roll_no": row["roll_no"], "name": row["name"],
            "present": present, "total": total, "percentage": pct,
        })
    return result


def get_defaulters(threshold: float, subject: str = None):
    return [r for r in get_attendance_percentages(subject) if r["total"] > 0 and r["percentage"] < threshold]


def get_student_history(student_id: int, limit: int = None, offset: int = 0,
                         status: str = None, subject: str = None):
    conn = get_connection()
    query = """
        SELECT a.id as attendance_id, a.status, a.confidence, a.marked_at,
               sess.subject, sess.section, sess.started_at
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = %s
    """
    params = [student_id]
    if status:
        query += " AND a.status = %s"
        params.append(status)
    if subject:
        query += " AND sess.subject = %s"
        params.append(subject)
    query += " ORDER BY sess.started_at DESC"
    if limit is not None:
        query += " LIMIT %s OFFSET %s"
        params += [limit, offset]
    return conn.execute(query, params).fetchall()


def count_student_history(student_id: int, status: str = None, subject: str = None) -> int:
    conn = get_connection()
    query = """
        SELECT COUNT(*) as c FROM attendance a JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = %s
    """
    params = [student_id]
    if status:
        query += " AND a.status = %s"
        params.append(status)
    if subject:
        query += " AND sess.subject = %s"
        params.append(subject)
    return conn.execute(query, params).fetchone()["c"]


def get_student_status_counts(student_id: int):
    """Attendance status breakdown for one student, for the History page's stat cards/filter chips."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, COUNT(*) as c FROM attendance WHERE student_id = %s GROUP BY status", (student_id,)
    ).fetchall()
    counts = {"present": 0, "absent": 0, "manual": 0, "unknown": 0}
    for row in rows:
        if row["status"] in counts:
            counts[row["status"]] = row["c"]
    counts["all"] = sum(counts.values())
    return counts


def get_distinct_subjects_for_student(student_id: int):
    conn = get_connection()
    return [r["subject"] for r in conn.execute(
        """
        SELECT DISTINCT sess.subject FROM attendance a JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = %s ORDER BY sess.subject
        """,
        (student_id,),
    ).fetchall()]


def get_last_login(user_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT occurred_at FROM auth_logs WHERE user_id = %s AND event = 'login_success' "
        "ORDER BY occurred_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def get_today_summary():
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN a.status = 'present' OR a.status = 'manual' THEN 1 ELSE 0 END) as present_count,
            COUNT(a.id) as total_count
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE COALESCE(sess.session_date::date, sess.started_at::date) = CURRENT_DATE AND a.student_id IS NOT NULL
        """
    ).fetchone()
    total = row["total_count"] or 0
    present = row["present_count"] or 0
    pct = (present / total * 100) if total else 0.0
    return {"present": present, "total": total, "percentage": pct}


def get_late_arrivals(session_id: int = None, threshold_minutes: int = 10, student_id: int = None):
    """Returns rows of students whose 'present' mark landed more than threshold_minutes
    after their session started."""
    conn = get_connection()
    query = """
        SELECT st.roll_no, st.name, sess.subject, sess.section, sess.started_at, a.marked_at,
               EXTRACT(EPOCH FROM (a.marked_at - sess.started_at)) / 60.0 as minutes_late
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        JOIN students st ON a.student_id = st.id
        WHERE a.status = 'present'
          AND EXTRACT(EPOCH FROM (a.marked_at - sess.started_at)) / 60.0 > %s
    """
    params = [threshold_minutes]
    if session_id is not None:
        query += " AND a.session_id = %s"
        params.append(session_id)
    if student_id is not None:
        query += " AND a.student_id = %s"
        params.append(student_id)
    query += " ORDER BY minutes_late DESC"
    return conn.execute(query, params).fetchall()


def get_attendance_matrix(subject: str = None, department: str = None):
    """Returns rows of {name, date, status} for pivoting into a student x date heatmap."""
    conn = get_connection()
    query = """
        SELECT st.name, sess.started_at::date as session_date, a.status
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        JOIN students st ON a.student_id = st.id
        WHERE 1=1
    """
    params = []
    if subject:
        query += " AND sess.subject = %s"
        params.append(subject)
    if department:
        query += " AND st.department = %s"
        params.append(department)
    query += " ORDER BY st.name, session_date"
    return conn.execute(query, params).fetchall()


def get_overall_average():
    rows = get_attendance_percentages()
    rows = [r for r in rows if r["total"] > 0]
    if not rows:
        return 0.0
    return sum(r["percentage"] for r in rows) / len(rows)


# ---------- Users / Auth ----------

def insert_user(username: str, password_hash: str, salt: str, role: str, full_name: str = None,
                 department: str = None, email: str = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, role, full_name, department, email) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (username, password_hash, salt, role, full_name, department, email),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_user_by_username(username: str):
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()


def get_user(user_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def list_users():
    conn = get_connection()
    return conn.execute("SELECT id, username, role, full_name, is_active, created_at FROM users ORDER BY username").fetchall()


def list_staff_users():
    """Faculty/admin accounts only — excludes student portal logins, which are auto-created
    per-student (see webportal/auth_backfill.py) and managed via enrollment, not this screen."""
    conn = get_connection()
    return conn.execute(
        "SELECT id, username, role, full_name, is_active, created_at, department, email FROM users "
        "WHERE role IN ('admin', 'faculty', 'hod', 'coordinator') ORDER BY username"
    ).fetchall()


def list_staff_users_by_department(department: str):
    conn = get_connection()
    return conn.execute(
        "SELECT id, username, role, full_name, is_active, created_at, department, email FROM users "
        "WHERE role IN ('admin', 'faculty', 'hod', 'coordinator') AND department = %s ORDER BY username",
        (department,),
    ).fetchall()


def count_users() -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]


def set_user_active(user_id: int, is_active: bool):
    conn = get_connection()
    conn.execute("UPDATE users SET is_active = %s WHERE id = %s", (1 if is_active else 0, user_id))
    conn.commit()


def update_user_role(user_id: int, role: str):
    conn = get_connection()
    conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
    conn.commit()


def update_user_password(user_id: int, password_hash: str, salt: str, must_change_password: bool = False):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = %s, salt = %s, must_change_password = %s WHERE id = %s",
        (password_hash, salt, 1 if must_change_password else 0, user_id),
    )
    conn.commit()


def count_recent_login_failures(username: str, minutes: int) -> int:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) as c FROM auth_logs
        WHERE username = %s AND event = 'login_failure'
          AND occurred_at >= (NOW() - make_interval(mins => %s))
        """,
        (username, minutes),
    ).fetchone()
    return row["c"]


def delete_user(user_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()


def log_auth_event(user_id, username: str, event: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO auth_logs (user_id, username, event) VALUES (%s, %s, %s)",
        (user_id, username, event),
    )
    conn.commit()


def get_auth_logs(limit: int = 100):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM auth_logs ORDER BY occurred_at DESC LIMIT %s", (limit,)
    ).fetchall()


# ---------- Student logins ----------

def insert_student_user(username: str, password_hash: str, salt: str, student_id: int, full_name: str = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, role, full_name, student_id) VALUES (%s, %s, %s, 'student', %s, %s) RETURNING id",
        (username, password_hash, salt, full_name, student_id),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_user_by_student_id(student_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE student_id = %s AND role = 'student'", (student_id,)).fetchone()


def list_students_without_login():
    conn = get_connection()
    return conn.execute(
        """
        SELECT s.* FROM students s
        WHERE s.id NOT IN (SELECT student_id FROM users WHERE student_id IS NOT NULL)
        """
    ).fetchall()


def update_student_email(student_id: int, email: str):
    conn = get_connection()
    conn.execute("UPDATE students SET email = %s WHERE id = %s", (email, student_id))
    conn.commit()


def update_student_phone(student_id: int, phone: str):
    conn = get_connection()
    conn.execute("UPDATE students SET phone = %s WHERE id = %s", (phone, student_id))
    conn.commit()


def get_student_rank(student_id: int, department: str = None, year: int = None, semester: int = None):
    """Returns (rank, total_students) by overall attendance percentage, best first.
    Pass the student's own department/year/semester to rank within their own class only,
    rather than against the whole college."""
    rows = get_attendance_percentages(department=department, year=year, semester=semester)
    ranked = sorted([r for r in rows if r["total"] > 0], key=lambda r: r["percentage"], reverse=True)
    for idx, row in enumerate(ranked, start=1):
        if row["id"] == student_id:
            return idx, len(ranked)
    return None, len(ranked)


def get_subject_class_averages(department: str = None, year: int = None, semester: int = None):
    """Returns {subject: average_percentage} for comparison on the student portal dashboard.
    Pass department/year/semester to scope the average to the student's own class/batch."""
    subjects = get_distinct_subjects()
    result = {}
    for subject in subjects:
        rows = [r for r in get_attendance_percentages(subject, department, year, semester) if r["total"] > 0]
        result[subject] = sum(r["percentage"] for r in rows) / len(rows) if rows else 0.0
    return result


def get_current_streak(student_id: int) -> int:
    """Consecutive most-recent sessions (across all subjects) marked present/manual."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT a.status FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = %s
        ORDER BY sess.started_at DESC
        """,
        (student_id,),
    ).fetchall()
    streak = 0
    for row in rows:
        if row["status"] in ("present", "manual"):
            streak += 1
        else:
            break
    return streak


# ---------- Dispute requests (student flags a wrong attendance mark) ----------

def create_dispute(student_id: int, attendance_id: int, reason: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO dispute_requests (student_id, attendance_id, reason) VALUES (%s, %s, %s) RETURNING id",
        (student_id, attendance_id, reason),
    )
    conn.commit()
    return cur.fetchone()["id"]


def list_disputes_for_student(student_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT d.*, a.status as attendance_status, a.marked_at, sess.subject, sess.started_at
        FROM dispute_requests d
        JOIN attendance a ON d.attendance_id = a.id
        JOIN sessions sess ON a.session_id = sess.id
        WHERE d.student_id = %s
        ORDER BY d.created_at DESC
        """,
        (student_id,),
    ).fetchall()


def list_pending_disputes():
    conn = get_connection()
    return conn.execute(
        """
        SELECT d.*, st.roll_no, st.name, a.status as attendance_status, sess.subject, sess.started_at
        FROM dispute_requests d
        JOIN students st ON d.student_id = st.id
        JOIN attendance a ON d.attendance_id = a.id
        JOIN sessions sess ON a.session_id = sess.id
        WHERE d.status = 'pending'
        ORDER BY d.created_at
        """
    ).fetchall()


def get_pending_dispute_for_attendance(attendance_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM dispute_requests WHERE attendance_id = %s AND status = 'pending'", (attendance_id,)
    ).fetchone()


def cancel_dispute(dispute_id: int, student_id: int) -> bool:
    """Deletes a still-pending dispute owned by student_id. Returns True if a row was removed."""
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM dispute_requests WHERE id = %s AND student_id = %s AND status = 'pending'",
        (dispute_id, student_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_dispute(dispute_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM dispute_requests WHERE id = %s", (dispute_id,)).fetchone()


def resolve_dispute(dispute_id: int, status: str, resolved_by_user_id: int = None):
    conn = get_connection()
    conn.execute(
        "UPDATE dispute_requests SET status = %s, resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = %s WHERE id = %s",
        (status, resolved_by_user_id, dispute_id),
    )
    conn.commit()


# ---------- Check-in requests (camera/lighting failure fallback) ----------

def create_checkin_request(student_id: int, session_id: int, reason: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO checkin_requests (student_id, session_id, reason) VALUES (%s, %s, %s) RETURNING id",
        (student_id, session_id, reason),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_pending_checkin_request_today(student_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT c.* FROM checkin_requests c
        JOIN sessions sess ON c.session_id = sess.id
        WHERE c.student_id = %s AND sess.started_at::date = CURRENT_DATE AND c.status = 'pending'
        """,
        (student_id,),
    ).fetchone()


def list_checkin_requests_for_student(student_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT c.*, sess.subject, sess.started_at
        FROM checkin_requests c
        JOIN sessions sess ON c.session_id = sess.id
        WHERE c.student_id = %s
        ORDER BY c.created_at DESC
        """,
        (student_id,),
    ).fetchall()


def cancel_checkin_request(request_id: int, student_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM checkin_requests WHERE id = %s AND student_id = %s AND status = 'pending'",
        (request_id, student_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_pending_checkin_requests():
    conn = get_connection()
    return conn.execute(
        """
        SELECT c.*, st.roll_no, st.name, sess.subject, sess.started_at
        FROM checkin_requests c
        JOIN students st ON c.student_id = st.id
        JOIN sessions sess ON c.session_id = sess.id
        WHERE c.status = 'pending'
        ORDER BY c.created_at
        """
    ).fetchall()


def get_checkin_request(request_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM checkin_requests WHERE id = %s", (request_id,)).fetchone()


def resolve_checkin_request(request_id: int, status: str, resolved_by_user_id: int = None):
    conn = get_connection()
    conn.execute(
        "UPDATE checkin_requests SET status = %s, resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = %s WHERE id = %s",
        (status, resolved_by_user_id, request_id),
    )
    conn.commit()


# ---------- Re-scan requests (student asks for a fresh face enrollment) ----------

def create_rescan_request(student_id: int, reason: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO rescan_requests (student_id, reason) VALUES (%s, %s) RETURNING id",
        (student_id, reason),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_pending_rescan_request(student_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM rescan_requests WHERE student_id = %s AND status = 'pending'", (student_id,)
    ).fetchone()


def list_rescan_requests_for_student(student_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM rescan_requests WHERE student_id = %s ORDER BY created_at DESC", (student_id,)
    ).fetchall()


def cancel_rescan_request(request_id: int, student_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM rescan_requests WHERE id = %s AND student_id = %s AND status = 'pending'",
        (request_id, student_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_pending_rescan_requests():
    conn = get_connection()
    return conn.execute(
        """
        SELECT r.*, st.roll_no, st.name
        FROM rescan_requests r
        JOIN students st ON r.student_id = st.id
        WHERE r.status = 'pending'
        ORDER BY r.created_at
        """
    ).fetchall()


def get_rescan_request(request_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM rescan_requests WHERE id = %s", (request_id,)).fetchone()


def resolve_rescan_request(request_id: int, status: str, resolved_by_user_id: int = None):
    conn = get_connection()
    conn.execute(
        "UPDATE rescan_requests SET status = %s, resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = %s WHERE id = %s",
        (status, resolved_by_user_id, request_id),
    )
    conn.commit()


def list_resolved_requests(limit: int = 100):
    """Combines resolved (approved/rejected) rows across all 3 request types for the desktop
    Approvals screen's History tab, newest-resolved first."""
    conn = get_connection()
    items = []
    for kind, table in (("dispute", "dispute_requests"), ("checkin", "checkin_requests"), ("rescan", "rescan_requests")):
        rows = conn.execute(
            f"""
            SELECT r.id, r.reason, r.status, r.resolved_at, st.roll_no, st.name
            FROM {table} r
            JOIN students st ON r.student_id = st.id
            WHERE r.status != 'pending'
            ORDER BY r.resolved_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            items.append({"kind": kind, "id": row["id"], "roll_no": row["roll_no"], "name": row["name"],
                          "reason": row["reason"], "status": row["status"], "resolved_at": row["resolved_at"]})
    items.sort(key=lambda i: i["resolved_at"] or "", reverse=True)
    return items[:limit]


_REQUEST_TABLES = ("dispute_requests", "checkin_requests", "rescan_requests")


def get_request_counts_for_student(student_id: int):
    """Aggregate pending/approved/rejected counts across all three request types for one student."""
    conn = get_connection()
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for table in _REQUEST_TABLES:
        rows = conn.execute(
            f"SELECT status, COUNT(*) as c FROM {table} WHERE student_id = %s GROUP BY status", (student_id,)
        ).fetchall()
        for row in rows:
            if row["status"] in counts:
                counts[row["status"]] += row["c"]
    return counts


def get_recent_requests_for_student(student_id: int, limit: int = 5):
    """Combines the 3 request types into one activity feed, newest first."""
    conn = get_connection()
    items = []
    for kind, table, label_col in (
        ("dispute", "dispute_requests", "reason"),
        ("checkin", "checkin_requests", "reason"),
        ("rescan", "rescan_requests", "reason"),
    ):
        rows = conn.execute(
            f"SELECT id, status, created_at, {label_col} as label FROM {table} WHERE student_id = %s "
            f"ORDER BY created_at DESC LIMIT %s",
            (student_id, limit),
        ).fetchall()
        for r in rows:
            items.append({"kind": kind, "id": r["id"], "status": r["status"],
                          "created_at": r["created_at"], "label": r["label"]})
    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items[:limit]


# ---------- Timetable ----------

def insert_timetable_slot(department: str, year: int, semester: int, subject: str, section: str,
                           faculty: str, day_of_week: int, start_time: str, end_time: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO timetable_slots (department, year, semester, subject, section, faculty, day_of_week, start_time, end_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (department, year, semester, subject, section, faculty, day_of_week, start_time, end_time),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_timetable_slot(slot_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM timetable_slots WHERE id = %s", (slot_id,)).fetchone()


def update_timetable_slot(slot_id: int, department: str, year: int, semester: int, subject: str, section: str,
                           faculty: str, day_of_week: int, start_time: str, end_time: str):
    conn = get_connection()
    conn.execute(
        """
        UPDATE timetable_slots
        SET department = %s, year = %s, semester = %s, subject = %s, section = %s,
            faculty = %s, day_of_week = %s, start_time = %s, end_time = %s
        WHERE id = %s
        """,
        (department, year, semester, subject, section, faculty, day_of_week, start_time, end_time, slot_id),
    )
    conn.commit()


def list_timetable_for_cohort(department: str, year: int, semester: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT * FROM timetable_slots
        WHERE department IS NOT DISTINCT FROM %s AND year IS NOT DISTINCT FROM %s AND semester IS NOT DISTINCT FROM %s
        ORDER BY day_of_week, start_time
        """,
        (department, year, semester),
    ).fetchall()


def list_all_timetable_slots():
    conn = get_connection()
    return conn.execute("SELECT * FROM timetable_slots ORDER BY day_of_week, start_time").fetchall()


def delete_timetable_slot(slot_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM timetable_slots WHERE id = %s", (slot_id,))
    conn.commit()


def get_student_subject_summary(student_id: int):
    """Per-subject present/total/percentage for one student."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT sess.subject,
               SUM(CASE WHEN a.status = 'present' OR a.status = 'manual' THEN 1 ELSE 0 END) as present_count,
               COUNT(a.id) as total_count
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = %s
        GROUP BY sess.subject
        ORDER BY sess.subject
        """,
        (student_id,),
    ).fetchall()
    result = []
    for row in rows:
        total = row["total_count"] or 0
        present = row["present_count"] or 0
        pct = (present / total * 100) if total else 0.0
        result.append({"subject": row["subject"] or "General", "present": present, "total": total, "percentage": pct})
    return result


# ---------- Leave / absence requests ----------

def create_leave_request(student_id: int, start_date: str, end_date: str, reason: str, session_id: int = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO leave_requests (student_id, session_id, start_date, end_date, reason) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (student_id, session_id, start_date, end_date, reason),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_leave_request(request_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM leave_requests WHERE id = %s", (request_id,)).fetchone()


def get_pending_leave_request(student_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM leave_requests WHERE student_id = %s AND status = 'pending'", (student_id,)
    ).fetchone()


def list_leave_requests_for_student(student_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM leave_requests WHERE student_id = %s ORDER BY created_at DESC", (student_id,)
    ).fetchall()


def list_pending_leave_requests():
    conn = get_connection()
    return conn.execute(
        """
        SELECT l.*, st.roll_no, st.name
        FROM leave_requests l JOIN students st ON l.student_id = st.id
        WHERE l.status = 'pending' ORDER BY l.created_at
        """
    ).fetchall()


def cancel_leave_request(request_id: int, student_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM leave_requests WHERE id = %s AND student_id = %s AND status = 'pending'",
        (request_id, student_id),
    )
    conn.commit()
    return cur.rowcount > 0


def resolve_leave_request(request_id: int, status: str, resolved_by_user_id: int = None):
    conn = get_connection()
    conn.execute(
        "UPDATE leave_requests SET status = %s, resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = %s WHERE id = %s",
        (status, resolved_by_user_id, request_id),
    )
    conn.commit()


# ---------- Announcements ----------

def create_announcement(sender_user_id, subject: str, body: str, department=None, year=None,
                         semester=None, section=None, is_institution_wide: bool = False) -> int:
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO announcements (sender_user_id, department, year, semester, section, subject, body, is_institution_wide)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (sender_user_id, department, year, semester, section, subject, body, 1 if is_institution_wide else 0),
    )
    conn.commit()
    return cur.fetchone()["id"]


def list_announcements_for_cohort(department: str, year: int, semester: int, limit: int = 50):
    conn = get_connection()
    return conn.execute(
        """
        SELECT * FROM announcements
        WHERE is_institution_wide = 1
           OR (department IS NOT DISTINCT FROM %s AND year IS NOT DISTINCT FROM %s AND semester IS NOT DISTINCT FROM %s)
        ORDER BY created_at DESC LIMIT %s
        """,
        (department, year, semester, limit),
    ).fetchall()


def list_all_announcements(limit: int = 100):
    conn = get_connection()
    return conn.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()


# ---------- Bulk / manual attendance marking, QR check-in, substitute faculty ----------

def bulk_set_attendance(session_id: int, student_ids: list, status: str, check_in_method: str = "manual_override"):
    """Marks each student_id present/absent for session_id in one transaction, updating an
    existing row if present or inserting a new one otherwise (mirrors manual_override)."""
    conn = get_connection()
    for student_id in student_ids:
        existing = conn.execute(
            "SELECT id FROM attendance WHERE session_id = %s AND student_id = %s",
            (session_id, student_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE attendance SET status = %s, marked_at = CURRENT_TIMESTAMP, check_in_method = %s WHERE id = %s",
                (status, check_in_method, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO attendance (session_id, student_id, status, confidence, check_in_method) "
                "VALUES (%s, %s, %s, NULL, %s)",
                (session_id, student_id, status, check_in_method),
            )
    conn.commit()


def set_check_in_method(session_id: int, student_id: int, method: str):
    conn = get_connection()
    conn.execute(
        "UPDATE attendance SET check_in_method = %s WHERE session_id = %s AND student_id = %s",
        (method, session_id, student_id),
    )
    conn.commit()


def set_session_qr_token(session_id: int, token: str, expires_at: str):
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET qr_token = %s, qr_token_expires_at = %s WHERE id = %s",
        (token, expires_at, session_id),
    )
    conn.commit()


def get_session_by_qr_token(token: str):
    conn = get_connection()
    return conn.execute("SELECT * FROM sessions WHERE qr_token = %s", (token,)).fetchone()


def assign_substitute_faculty(session_id: int, user_id):
    conn = get_connection()
    conn.execute("UPDATE sessions SET substitute_faculty_user_id = %s WHERE id = %s", (user_id, session_id))
    conn.commit()


def mark_late(attendance_id: int):
    conn = get_connection()
    conn.execute("UPDATE attendance SET is_late = 1 WHERE id = %s", (attendance_id,))
    conn.commit()


# ---------- Password reset tokens ----------

def create_password_reset_token(user_id: int, token_hash: str, expires_at: str) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s) RETURNING id",
        (user_id, token_hash, expires_at),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_password_reset_token(token_hash: str):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token_hash = %s", (token_hash,)
    ).fetchone()


def mark_password_reset_token_used(token_id: int):
    conn = get_connection()
    conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = %s", (token_id,))
    conn.commit()


# ---------- API keys (ERP export) ----------

def create_api_key(label: str, key_hash: str) -> int:
    conn = get_connection()
    cur = conn.execute("INSERT INTO api_keys (label, key_hash) VALUES (%s, %s) RETURNING id", (label, key_hash))
    conn.commit()
    return cur.fetchone()["id"]


def get_api_key_by_hash(key_hash: str):
    conn = get_connection()
    return conn.execute("SELECT * FROM api_keys WHERE key_hash = %s AND is_active = 1", (key_hash,)).fetchone()


def touch_api_key(key_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP, request_count = request_count + 1 WHERE id = %s",
        (key_id,),
    )
    conn.commit()


def list_api_keys():
    conn = get_connection()
    return conn.execute("SELECT id, label, created_at, last_used_at, request_count, is_active FROM api_keys ORDER BY created_at DESC").fetchall()


# ---------- Users: role/department/email/TOTP updates (Phase 1 rebuild follow-ups) ----------

def update_user_department(user_id: int, department: str):
    conn = get_connection()
    conn.execute("UPDATE users SET department = %s WHERE id = %s", (department, user_id))
    conn.commit()


def update_user_email(user_id: int, email: str):
    conn = get_connection()
    conn.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))
    conn.commit()


def set_user_totp(user_id: int, secret: str, enabled: bool):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET totp_secret = %s, totp_enabled = %s WHERE id = %s",
        (secret, 1 if enabled else 0, user_id),
    )
    conn.commit()


def disable_user_totp(user_id: int):
    conn = get_connection()
    conn.execute("UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = %s", (user_id,))
    conn.commit()
