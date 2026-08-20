import numpy as np
import pytest

from db import queries
from services import requests as request_service


def _make_student(roll_no="21CE001"):
    return queries.insert_student(roll_no, "Alice", "CE", 2, 4, np.zeros(128))


def test_dispute_approve_flips_attendance_to_manual():
    student_id = _make_student()
    session_id = queries.start_session("Auto Attendance", None, None)
    queries.manual_override(session_id, student_id, "absent")
    attendance_id = queries.get_session_attendance(session_id)[0]["id"]

    dispute_id = request_service.submit_dispute(student_id, attendance_id, "I was here, camera missed me")
    request_service.resolve_dispute(dispute_id, approve=True)

    attendance = queries.get_session_attendance(session_id)[0]
    assert attendance["status"] == "manual"
    assert queries.get_dispute(dispute_id)["status"] == "approved"


def test_dispute_reject_leaves_attendance_untouched():
    student_id = _make_student()
    session_id = queries.start_session("Auto Attendance", None, None)
    queries.manual_override(session_id, student_id, "absent")
    attendance_id = queries.get_session_attendance(session_id)[0]["id"]

    dispute_id = request_service.submit_dispute(student_id, attendance_id, "reason")
    request_service.resolve_dispute(dispute_id, approve=False)

    attendance = queries.get_session_attendance(session_id)[0]
    assert attendance["status"] == "absent"
    assert queries.get_dispute(dispute_id)["status"] == "rejected"


def test_dispute_rejects_duplicate_pending():
    student_id = _make_student()
    session_id = queries.start_session("Auto Attendance", None, None)
    queries.manual_override(session_id, student_id, "absent")
    attendance_id = queries.get_session_attendance(session_id)[0]["id"]

    request_service.submit_dispute(student_id, attendance_id, "first")
    with pytest.raises(request_service.RequestError):
        request_service.submit_dispute(student_id, attendance_id, "second")


def test_checkin_request_approve_marks_present():
    student_id = _make_student()
    session_id = queries.start_session("Auto Attendance", None, None)

    request_id = request_service.submit_checkin_request(student_id, session_id, "camera was down")
    request_service.resolve_checkin_request(request_id, approve=True)

    rows = queries.get_session_attendance(session_id)
    assert rows[0]["status"] == "manual"


def test_checkin_request_blocks_second_pending_same_day():
    student_id = _make_student()
    session_id = queries.start_session("Auto Attendance", None, None)
    request_service.submit_checkin_request(student_id, session_id, "reason 1")
    with pytest.raises(request_service.RequestError):
        request_service.submit_checkin_request(student_id, session_id, "reason 2")


def test_rescan_request_blocks_second_pending():
    student_id = _make_student()
    request_service.submit_rescan_request(student_id, "new haircut")
    with pytest.raises(request_service.RequestError):
        request_service.submit_rescan_request(student_id, "again")


def test_rescan_request_reject_allows_resubmission():
    student_id = _make_student()
    request_id = request_service.submit_rescan_request(student_id, "reason")
    request_service.resolve_rescan_request(request_id, approve=False)
    # should not raise now that the previous one is resolved
    request_service.submit_rescan_request(student_id, "reason again")


def test_timetable_cohort_filtering():
    queries.insert_timetable_slot("CE", 2, 4, "Maths", "A", "Prof X", 0, "09:00", "10:00")
    queries.insert_timetable_slot("CE", 3, 4, "Physics", "A", "Prof Y", 1, "10:00", "11:00")
    slots = queries.list_timetable_for_cohort("CE", 2, 4)
    assert len(slots) == 1
    assert slots[0]["subject"] == "Maths"
