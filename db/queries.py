import pickle
from datetime import date

import numpy as np

from db.connection import get_connection


# ---------- Students ----------

def insert_student(roll_no: str, name: str, department: str, year: int, semester: int, encoding: np.ndarray) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO students (roll_no, name, department, year, semester, encoding) VALUES (?, ?, ?, ?, ?, ?)",
        (roll_no, name, department, year, semester, pickle.dumps(encoding)),
    )
    conn.commit()
    return cur.lastrowid


def update_student(student_id: int, roll_no: str, name: str, department: str, year: int, semester: int):
    conn = get_connection()
    conn.execute(
        "UPDATE students SET roll_no = ?, name = ?, department = ?, year = ?, semester = ? WHERE id = ?",
        (roll_no, name, department, year, semester, student_id),
    )
    conn.commit()


def update_student_encoding(student_id: int, encoding: np.ndarray):
    conn = get_connection()
    conn.execute("UPDATE students SET encoding = ? WHERE id = ?", (pickle.dumps(encoding), student_id))
    conn.commit()


def delete_student(student_id: int):
    """Hard-deletes a student along with their attendance history and stored encodings.
    This is a deliberate, user-triggered action (the Delete button in Enroll Student) —
    attendance rows referencing this student would otherwise block the delete via the
    students(id) foreign key, so they're removed first in the same transaction."""
    conn = get_connection()
    conn.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
    conn.execute("DELETE FROM student_encodings WHERE student_id = ?", (student_id,))
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
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
            continue
    return result


def insert_student_encoding(student_id: int, encoding: np.ndarray, source: str = "enrollment"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO student_encodings (student_id, encoding, source) VALUES (?, ?, ?)",
        (student_id, pickle.dumps(encoding), source),
    )
    conn.commit()


def get_encodings_for_student(student_id: int):
    conn = get_connection()
    rows = conn.execute("SELECT encoding FROM student_encodings WHERE student_id = ?", (student_id,)).fetchall()
    result = []
    for row in rows:
        try:
            result.append(pickle.loads(row["encoding"]))
        except Exception:
            continue
    return result


def get_student(student_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


# ---------- Sessions ----------

def start_session(subject: str, section: str, faculty: str, created_by_user_id: int = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sessions (subject, section, faculty, created_by_user_id) VALUES (?, ?, ?, ?)",
        (subject, section, faculty, created_by_user_id),
    )
    conn.commit()
    return cur.lastrowid


AUTO_SESSION_SUBJECT = "Auto Attendance"


def get_open_auto_session_today():
    """started_at uses sqlite's CURRENT_TIMESTAMP (UTC), so compare against UTC 'now' —
    not 'localtime' — to avoid timezone-mismatch creating duplicate day-sessions."""
    conn = get_connection()
    return conn.execute(
        """
        SELECT * FROM sessions
        WHERE subject = ? AND date(started_at) = date('now') AND ended_at IS NULL
        """,
        (AUTO_SESSION_SUBJECT,),
    ).fetchone()


def get_or_create_today_session(created_by_user_id: int = None) -> int:
    """Returns today's open auto-attendance session id, creating one if none is open yet.
    Safe to call repeatedly across app restarts within the same day — never creates duplicates."""
    existing = get_open_auto_session_today()
    if existing:
        return existing["id"]
    return start_session(AUTO_SESSION_SUBJECT, None, None, created_by_user_id)


def close_day():
    """Finalizes absentees and ends today's open auto-attendance session, if any.
    Returns the closed session id, or None if there was nothing open."""
    session = get_open_auto_session_today()
    if session is None:
        return None
    finalize_absentees(session["id"])
    end_session(session["id"])
    return session["id"]


def get_sessions_by_user(user_id: int):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM sessions WHERE created_by_user_id = ? ORDER BY started_at DESC", (user_id,)
    ).fetchall()


def end_session(session_id: int):
    conn = get_connection()
    conn.execute("UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    conn.commit()


def get_session(session_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()


def list_sessions():
    conn = get_connection()
    return conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()


# ---------- Attendance ----------

def mark_present(session_id: int, student_id: int, confidence: float) -> bool:
    """Returns True if a new attendance row was inserted (first time seen this session)."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
        (session_id, student_id),
    ).fetchone()
    if existing:
        return False
    conn.execute(
        "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (?, ?, 'present', ?)",
        (session_id, student_id, confidence),
    )
    conn.commit()
    return True


def log_unknown(session_id: int, confidence: float = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (?, NULL, 'unknown', ?)",
        (session_id, confidence),
    )
    conn.commit()


def manual_override(session_id: int, student_id: int, status: str):
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM attendance WHERE session_id = ? AND student_id = ?",
        (session_id, student_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE attendance SET status = ?, marked_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, status, confidence) VALUES (?, ?, ?, NULL)",
            (session_id, student_id, status),
        )
    conn.commit()


def finalize_absentees(session_id: int):
    """Mark any enrolled student with no attendance row in this session as absent."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO attendance (session_id, student_id, status, confidence)
        SELECT ?, s.id, 'absent', NULL
        FROM students s
        WHERE s.id NOT IN (
            SELECT student_id FROM attendance WHERE session_id = ? AND student_id IS NOT NULL
        )
        """,
        (session_id, session_id),
    )
    conn.commit()


def log_spoof_attempt(session_id: int):
    conn = get_connection()
    conn.execute("INSERT INTO spoof_logs (session_id) VALUES (?)", (session_id,))
    conn.commit()


def get_spoof_count(session_id: int) -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) as c FROM spoof_logs WHERE session_id = ?", (session_id,)).fetchone()["c"]


def get_session_attendance(session_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT a.id, a.status, a.confidence, a.marked_at,
               s.id as student_id, s.roll_no, s.name, s.department
        FROM attendance a
        LEFT JOIN students s ON a.student_id = s.id
        WHERE a.session_id = ?
        ORDER BY a.marked_at
        """,
        (session_id,),
    ).fetchall()


def get_filtered_attendance(subject: str = None, section: str = None, start_date: str = None, end_date: str = None,
                             department: str = None):
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
    if subject:
        query += " AND sess.subject = ?"
        params.append(subject)
    if section:
        query += " AND sess.section = ?"
        params.append(section)
    if department:
        query += " AND st.department = ?"
        params.append(department)
    if start_date:
        query += " AND date(sess.started_at) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(sess.started_at) <= date(?)"
        params.append(end_date)
    query += " ORDER BY sess.started_at DESC"
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

def get_attendance_percentages(subject: str = None):
    """Returns list of rows: id, roll_no, name, present_count, total_count, percentage.
    total_count is the number of sessions the student has any attendance row for
    (present/absent/manual) — unknown rows (no student_id) are excluded."""
    conn = get_connection()
    query = """
        SELECT st.id, st.roll_no, st.name,
               SUM(CASE WHEN a.status = 'present' OR a.status = 'manual' THEN 1 ELSE 0 END) as present_count,
               COUNT(a.id) as total_count
        FROM students st
        LEFT JOIN attendance a ON a.student_id = st.id
        LEFT JOIN sessions sess ON a.session_id = sess.id
    """
    params = []
    if subject:
        query += " WHERE sess.subject = ?"
        params.append(subject)
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


def get_student_history(student_id: int):
    conn = get_connection()
    return conn.execute(
        """
        SELECT a.status, a.confidence, a.marked_at, sess.subject, sess.section, sess.started_at
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE a.student_id = ?
        ORDER BY sess.started_at DESC
        """,
        (student_id,),
    ).fetchall()


def get_today_summary():
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN a.status = 'present' OR a.status = 'manual' THEN 1 ELSE 0 END) as present_count,
            COUNT(a.id) as total_count
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        WHERE date(sess.started_at) = date('now') AND a.student_id IS NOT NULL
        """
    ).fetchone()
    total = row["total_count"] or 0
    present = row["present_count"] or 0
    pct = (present / total * 100) if total else 0.0
    return {"present": present, "total": total, "percentage": pct}


def get_late_arrivals(session_id: int = None, threshold_minutes: int = 10):
    """Returns rows of students whose 'present' mark landed more than threshold_minutes
    after their session started."""
    conn = get_connection()
    query = """
        SELECT st.roll_no, st.name, sess.subject, sess.section, sess.started_at, a.marked_at,
               (strftime('%s', a.marked_at) - strftime('%s', sess.started_at)) / 60.0 as minutes_late
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        JOIN students st ON a.student_id = st.id
        WHERE a.status = 'present'
          AND (strftime('%s', a.marked_at) - strftime('%s', sess.started_at)) / 60.0 > ?
    """
    params = [threshold_minutes]
    if session_id is not None:
        query += " AND a.session_id = ?"
        params.append(session_id)
    query += " ORDER BY minutes_late DESC"
    return conn.execute(query, params).fetchall()


def get_attendance_matrix(subject: str = None, department: str = None):
    """Returns rows of {name, date, status} for pivoting into a student x date heatmap."""
    conn = get_connection()
    query = """
        SELECT st.name, date(sess.started_at) as session_date, a.status
        FROM attendance a
        JOIN sessions sess ON a.session_id = sess.id
        JOIN students st ON a.student_id = st.id
        WHERE 1=1
    """
    params = []
    if subject:
        query += " AND sess.subject = ?"
        params.append(subject)
    if department:
        query += " AND st.department = ?"
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

def insert_user(username: str, password_hash: str, salt: str, role: str, full_name: str = None) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, role, full_name) VALUES (?, ?, ?, ?, ?)",
        (username, password_hash, salt, role, full_name),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_username(username: str):
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user(user_id: int):
    conn = get_connection()
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users():
    conn = get_connection()
    return conn.execute("SELECT id, username, role, full_name, is_active, created_at FROM users ORDER BY username").fetchall()


def count_users() -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]


def set_user_active(user_id: int, is_active: bool):
    conn = get_connection()
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
    conn.commit()


def update_user_role(user_id: int, role: str):
    conn = get_connection()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()


def update_user_password(user_id: int, password_hash: str, salt: str):
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (password_hash, salt, user_id))
    conn.commit()


def delete_user(user_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


def log_auth_event(user_id, username: str, event: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO auth_logs (user_id, username, event) VALUES (?, ?, ?)",
        (user_id, username, event),
    )
    conn.commit()


def get_auth_logs(limit: int = 100):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM auth_logs ORDER BY occurred_at DESC LIMIT ?", (limit,)
    ).fetchall()
