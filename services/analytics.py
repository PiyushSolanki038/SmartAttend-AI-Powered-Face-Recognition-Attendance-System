"""Class-wise engagement analytics: simple rolling-window threshold flags (no ML), built
on the attendance.is_late column added in migration 42. Reused by the desktop engagement
screen's chart via ui/components/chart_embed.py."""

from collections import defaultdict

from db import queries


def get_class_engagement_trend(subject: str = None, department: str = None):
    """Returns a list of {session_date, present_pct, late_pct} across sessions matching the
    filters, ordered chronologically, for a simple line/bar chart of engagement over time."""
    rows = queries.get_filtered_attendance(subject=subject, department=department, include_unknown=False)
    by_date = defaultdict(lambda: {"present": 0, "late": 0, "total": 0})
    for row in rows:
        started_at = row["started_at"]
        date_part = started_at.strftime("%Y-%m-%d") if started_at else ""
        if not date_part:
            continue
        bucket = by_date[date_part]
        bucket["total"] += 1
        if row["status"] in ("present", "manual"):
            bucket["present"] += 1

    conn = queries.get_connection()
    late_query = """
        SELECT date(sess.started_at) as d, COUNT(*) as c
        FROM attendance a JOIN sessions sess ON a.session_id = sess.id
        LEFT JOIN students st ON a.student_id = st.id
        WHERE a.is_late = 1
    """
    params = []
    if subject:
        late_query += " AND sess.subject = %s"
        params.append(subject)
    if department:
        late_query += " AND st.department = %s"
        params.append(department)
    late_query += " GROUP BY d"
    for r in conn.execute(late_query, params).fetchall():
        d_key = r["d"].strftime("%Y-%m-%d") if r["d"] else None
        if d_key in by_date:
            by_date[d_key]["late"] = r["c"]

    result = []
    for date_part in sorted(by_date.keys()):
        b = by_date[date_part]
        present_pct = (b["present"] / b["total"] * 100) if b["total"] else 0.0
        late_pct = (b["late"] / b["total"] * 100) if b["total"] else 0.0
        result.append({"session_date": date_part, "present_pct": present_pct, "late_pct": late_pct,
                        "total": b["total"]})
    return result


LOW_ENGAGEMENT_THRESHOLD = 60.0


def flag_low_engagement_sessions(trend: list):
    """Rolling-window flag: any session whose present_pct is more than 15 points below the
    trailing 3-session average is flagged as a low-engagement dip."""
    flagged = []
    window = []
    for point in trend:
        if window:
            avg = sum(window) / len(window)
            if point["present_pct"] < avg - 15:
                flagged.append(point["session_date"])
        window.append(point["present_pct"])
        if len(window) > 3:
            window.pop(0)
    return flagged
