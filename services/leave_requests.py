"""Student leave/absence requests — clones services/requests.py's exact pending ->
approved/rejected pattern for a fourth request type: pre-notifying an upcoming absence
(vs. disputing/checking-in/re-scanning after the fact)."""

from datetime import date

from db import queries
from services import audit


class LeaveRequestError(Exception):
    pass


def submit_leave_request(student_id: int, start_date: str, end_date: str, reason: str, session_id: int = None) -> int:
    if not reason or not reason.strip():
        raise LeaveRequestError("Please describe the reason for your leave.")
    if not start_date or not end_date:
        raise LeaveRequestError("Start and end date are required.")
    if end_date < start_date:
        raise LeaveRequestError("End date cannot be before start date.")
    if queries.get_pending_leave_request(student_id):
        raise LeaveRequestError("You already have a pending leave request.")
    return queries.create_leave_request(student_id, start_date, end_date, reason.strip(), session_id)


def cancel_leave_request(student_id: int, request_id: int):
    if not queries.cancel_leave_request(request_id, student_id):
        raise LeaveRequestError("Unable to cancel — it may have already been resolved.")


def resolve_leave_request(request_id: int, approve: bool, resolved_by_user_id: int = None):
    request = queries.get_leave_request(request_id)
    if request is None:
        raise LeaveRequestError("Leave request not found.")
    if request["status"] != "pending":
        raise LeaveRequestError("This request has already been resolved.")
    status = "approved" if approve else "rejected"
    queries.resolve_leave_request(request_id, status, resolved_by_user_id)
    audit.log_action(resolved_by_user_id, f"leave_request_{status}", "leave_request", request_id,
                      details=f"student_id={request['student_id']}")
