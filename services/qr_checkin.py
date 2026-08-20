"""QR self check-in fallback: generates a random token bound to a session, valid only
while the session is open and only within a short time window — the one cheap guard
worth building for a token that a student photographs off a projector screen."""

import secrets
from datetime import datetime, timedelta

from db import queries

QR_TOKEN_VALIDITY_MINUTES = 15


class QRCheckinError(Exception):
    pass


def generate_qr_token(session_id: int) -> str:
    session = queries.get_session(session_id)
    if session is None:
        raise QRCheckinError("Session not found.")
    if session["ended_at"] is not None:
        raise QRCheckinError("Cannot generate a QR token for an ended session.")
    token = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(minutes=QR_TOKEN_VALIDITY_MINUTES)
    queries.set_session_qr_token(session_id, token, expires_at)
    return token


def check_in_with_token(token: str, student_id: int):
    session = queries.get_session_by_qr_token(token)
    if session is None:
        raise QRCheckinError("Invalid or expired QR code.")
    if session["ended_at"] is not None:
        raise QRCheckinError("This session has already ended.")
    qr_token_expires_at = session["qr_token_expires_at"]
    # psycopg2 returns a native (naive) datetime for this TIMESTAMP column — same UTC wall-clock
    # semantics as sqlite3's stored string, just no longer a string, so compare as datetime.
    if isinstance(qr_token_expires_at, str):
        qr_token_expires_at = datetime.strptime(qr_token_expires_at, "%Y-%m-%d %H:%M:%S")
    if qr_token_expires_at and qr_token_expires_at < datetime.utcnow():
        raise QRCheckinError("This QR code has expired. Ask your faculty to refresh it.")
    queries.manual_override(session["id"], student_id, "manual")
    queries.set_check_in_method(session["id"], student_id, "qr")
    return session["id"]
