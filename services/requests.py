"""Student-initiated requests that require faculty/admin approval: disputing a wrong
attendance mark, requesting a manual check-in when the camera/lighting failed, and
requesting a face re-scan. Each request type has its own table (db/migrations.py) and
mirrors the same pending -> approved/rejected lifecycle."""

from db import queries
from services import audit


class RequestError(Exception):
    pass


# ---------- Disputes ----------

def submit_dispute(student_id: int, attendance_id: int, reason: str) -> int:
    if not reason or not reason.strip():
        raise RequestError("Please describe why this mark is wrong.")
    if queries.get_pending_dispute_for_attendance(attendance_id):
        raise RequestError("There's already a pending dispute for this record.")
    return queries.create_dispute(student_id, attendance_id, reason.strip())


def cancel_dispute(student_id: int, dispute_id: int):
    if not queries.cancel_dispute(dispute_id, student_id):
        raise RequestError("Unable to cancel — it may have already been resolved.")


def resolve_dispute(dispute_id: int, approve: bool, resolved_by_user_id: int = None):
    dispute = queries.get_dispute(dispute_id)
    if dispute is None:
        raise RequestError("Dispute not found.")
    if dispute["status"] != "pending":
        raise RequestError("This dispute has already been resolved.")
    if approve:
        conn = queries.get_connection()
        conn.execute("UPDATE attendance SET status = 'manual', marked_at = CURRENT_TIMESTAMP WHERE id = %s",
                     (dispute["attendance_id"],))
        conn.commit()
    status = "approved" if approve else "rejected"
    queries.resolve_dispute(dispute_id, status, resolved_by_user_id)
    audit.log_action(resolved_by_user_id, f"dispute_{status}", "dispute_request", dispute_id,
                      details=f"student_id={dispute['student_id']}")


# ---------- Check-in requests ----------

def submit_checkin_request(student_id: int, session_id: int, reason: str) -> int:
    if not reason or not reason.strip():
        raise RequestError("Please describe why you couldn't check in via camera.")
    if queries.get_pending_checkin_request_today(student_id):
        raise RequestError("You already have a pending check-in request for today.")
    return queries.create_checkin_request(student_id, session_id, reason.strip())


def cancel_checkin_request(student_id: int, request_id: int):
    if not queries.cancel_checkin_request(request_id, student_id):
        raise RequestError("Unable to cancel — it may have already been resolved.")


def resolve_checkin_request(request_id: int, approve: bool, resolved_by_user_id: int = None):
    request = queries.get_checkin_request(request_id)
    if request is None:
        raise RequestError("Request not found.")
    if request["status"] != "pending":
        raise RequestError("This request has already been resolved.")
    if approve:
        queries.manual_override(request["session_id"], request["student_id"], "manual")
    status = "approved" if approve else "rejected"
    queries.resolve_checkin_request(request_id, status, resolved_by_user_id)
    audit.log_action(resolved_by_user_id, f"checkin_request_{status}", "checkin_request", request_id,
                      details=f"student_id={request['student_id']}")


# ---------- Re-scan requests ----------

def submit_rescan_request(student_id: int, reason: str) -> int:
    if not reason or not reason.strip():
        raise RequestError("Please describe why you need a re-scan.")
    if queries.get_pending_rescan_request(student_id):
        raise RequestError("You already have a pending re-scan request.")
    return queries.create_rescan_request(student_id, reason.strip())


def cancel_rescan_request(student_id: int, request_id: int):
    if not queries.cancel_rescan_request(request_id, student_id):
        raise RequestError("Unable to cancel — it may have already been resolved.")


def resolve_rescan_request(request_id: int, approve: bool, resolved_by_user_id: int = None):
    request = queries.get_rescan_request(request_id)
    if request is None:
        raise RequestError("Request not found.")
    if request["status"] != "pending":
        raise RequestError("This request has already been resolved.")
    status = "approved" if approve else "rejected"
    queries.resolve_rescan_request(request_id, status, resolved_by_user_id)
    audit.log_action(resolved_by_user_id, f"rescan_request_{status}", "rescan_request", request_id,
                      details=f"student_id={request['student_id']}")
