"""Session-level admin actions that don't belong in services/session.py's live camera
controller: substitute faculty assignment (audit-logged, per the plan's first real
Phase-1 audit retrofit)."""

from db import queries
from services import audit


class SessionAssignError(Exception):
    pass


def assign_substitute_faculty(session_id: int, substitute_user_id: int, assigned_by_user_id: int = None):
    session = queries.get_session(session_id)
    if session is None:
        raise SessionAssignError("Session not found.")
    queries.assign_substitute_faculty(session_id, substitute_user_id)
    audit.log_action(assigned_by_user_id, "assign_substitute_faculty", "session", session_id,
                      details=f"substitute_user_id={substitute_user_id}")
