import numpy as np

import db.connection as connection
from db import queries


def _make_student(roll_no="21CE001"):
    return queries.insert_student(roll_no, "Alice", "CE", 2, 4, np.zeros(128))


def test_corrupt_encoding_is_skipped_not_raised(caplog):
    student_id = _make_student()
    conn = connection.get_connection()
    conn.execute(
        "INSERT INTO student_encodings (student_id, encoding, source) VALUES (?, ?, 'test')",
        (student_id, b"not-a-valid-pickle"),
    )
    conn.commit()
    with caplog.at_level("WARNING"):
        result = queries.get_encodings_for_student(student_id)
    assert result == []
    assert any("Corrupt encoding blob" in msg for msg in caplog.messages)


def test_student_history_pagination():
    student_id = _make_student()
    session_ids = [queries.start_session("Auto Attendance", None, None) for _ in range(5)]
    for sid in session_ids:
        queries.mark_present(sid, student_id, confidence=0.9)

    total = queries.count_student_history(student_id)
    assert total == 5

    page1 = queries.get_student_history(student_id, limit=2, offset=0)
    page2 = queries.get_student_history(student_id, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2


def test_recent_login_failures_counts_within_window():
    queries.log_auth_event(None, "someuser", "login_failure")
    queries.log_auth_event(None, "someuser", "login_failure")
    assert queries.count_recent_login_failures("someuser", minutes=15) == 2
    assert queries.count_recent_login_failures("otheruser", minutes=15) == 0
