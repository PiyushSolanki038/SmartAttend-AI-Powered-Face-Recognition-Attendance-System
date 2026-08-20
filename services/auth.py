import hashlib
import secrets
from datetime import datetime, timedelta

from db import queries
from services.notifications import send_email

PASSWORD_RESET_TOKEN_VALIDITY_MINUTES = 30

PBKDF2_ITERATIONS = 200_000

# Login lockout: after this many failed attempts for a username within the window,
# further logins are rejected even with the correct password, until the window elapses.
# Reason: neither the desktop login nor the portal login had any brake on brute-forcing
# a password, despite auth_logs already recording every failure.
MAX_LOGIN_FAILURES = 5
LOCKOUT_WINDOW_MINUTES = 15


class AccountLockedError(Exception):
    """Raised by login() when a username has too many recent failures to attempt again."""


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return digest, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest, _ = hash_password(password, salt)
    return secrets.compare_digest(digest, expected_hash)


def bootstrap_admin():
    """Seeds a default admin account on first run if no users exist yet.
    The initial password is randomly generated (not a guessable constant like the old
    'admin123') and printed once to the console; the account is flagged must_change_password
    so the very first login is forced to set a real password before anything else."""
    if queries.count_users() == 0:
        temp_password = secrets.token_urlsafe(9)
        digest, salt = hash_password(temp_password)
        user_id = queries.insert_user("admin", digest, salt, "admin", full_name="Administrator")
        queries.update_user_password(user_id, digest, salt, must_change_password=True)
        print("[SmartAttend] No users found. Created default account:")
        print(f"[SmartAttend]   username: admin   password: {temp_password}")
        print("[SmartAttend] You will be required to set a new password on first login.")


def login(username: str, password: str):
    """Returns the user row on success, or None on failure. Logs the attempt either way.
    Raises AccountLockedError if this username has too many recent failures — checked
    before verifying the password so a locked account can't be brute-forced further."""
    if queries.count_recent_login_failures(username, LOCKOUT_WINDOW_MINUTES) >= MAX_LOGIN_FAILURES:
        raise AccountLockedError(
            f"Too many failed attempts. Try again in {LOCKOUT_WINDOW_MINUTES} minutes."
        )
    user = queries.get_user_by_username(username)
    if user is None or not user["is_active"] or not verify_password(password, user["salt"], user["password_hash"]):
        queries.log_auth_event(user["id"] if user else None, username, "login_failure")
        return None
    queries.log_auth_event(user["id"], username, "login_success")
    return user


def logout(user):
    if user is not None:
        queries.log_auth_event(user["id"], user["username"], "logout")


def create_user(username: str, password: str, role: str, full_name: str = None) -> int:
    digest, salt = hash_password(password)
    return queries.insert_user(username, digest, salt, role, full_name)


def create_student_login(student_id: int, roll_no: str, full_name: str = None):
    """Creates a portal login for a newly enrolled student with a random temporary password
    (not the guessable roll-number default used by webportal/auth_backfill.py's bulk backfill),
    flagged must_change_password. Returns the plaintext temp password — this is the only chance
    to see it, so the caller is responsible for delivering it (e.g. via email). Returns None
    without creating anything if a login already exists for this student (e.g. auth_backfill
    beat this to it) — issuing a second temp password would silently invalidate one the
    student might already be using."""
    if queries.get_user_by_student_id(student_id) is not None:
        return None
    temp_password = secrets.token_urlsafe(9)
    digest, salt = hash_password(temp_password)
    user_id = queries.insert_student_user(roll_no, digest, salt, student_id, full_name=full_name)
    queries.update_user_password(user_id, digest, salt, must_change_password=True)
    return temp_password


def change_password(user_id: int, new_password: str):
    digest, salt = hash_password(new_password)
    queries.update_user_password(user_id, digest, salt, must_change_password=False)


# hod/coordinator are treated as faculty-equivalent for access purposes rather than
# getting their own permission matrix — they're granted the same screens as faculty,
# plus read-only access to admin screens (analytics, audit log) that check this helper.
FACULTY_EQUIVALENT_ROLES = {"faculty", "hod", "coordinator"}


class PasswordResetError(Exception):
    pass


def request_password_reset(email_or_username: str, base_url: str) -> bool:
    """Webportal-only self-service password reset. Looks the account up by username first
    (student roll numbers double as usernames), then by email. Always looks like it
    succeeded to the caller (no email enumeration) — returns True/False only for whether
    an email was actually sent, which the caller should not surface differently to the user."""
    user = queries.get_user_by_username(email_or_username)
    if user is None:
        conn = queries.get_connection()
        row = conn.execute("SELECT u.* FROM users u JOIN students s ON u.student_id = s.id WHERE s.email = %s",
                            (email_or_username,)).fetchone()
        user = row
    if user is None:
        return False
    student = queries.get_student(user["student_id"]) if user["student_id"] else None
    email = student["email"] if student else None
    if not email:
        return False
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_VALIDITY_MINUTES)
    queries.create_password_reset_token(user["id"], token_hash, expires_at)
    reset_link = f"{base_url.rstrip('/')}/reset-password?token={raw_token}"
    body = (
        f"A password reset was requested for your SmartAttend account.\n\n"
        f"Reset your password here (valid {PASSWORD_RESET_TOKEN_VALIDITY_MINUTES} minutes):\n{reset_link}\n\n"
        f"If you didn't request this, you can ignore this email."
    )
    from services.notifications import render_email_html
    html_body = render_email_html(
        heading="Reset your password 🔑",
        paragraphs=[
            "A password reset was requested for your SmartAttend account. Click the button "
            f"below to set a new one — this link is valid for {PASSWORD_RESET_TOKEN_VALIDITY_MINUTES} minutes.",
            "If you didn't request this, you can safely ignore this email.",
        ],
        button={"text": "Reset Password", "url": reset_link},
    )
    return send_email(email, "SmartAttend Password Reset", body, html_body)


def reset_password_with_token(raw_token: str, new_password: str):
    if len(new_password) < 4:
        raise PasswordResetError("New password must be at least 4 characters.")
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    record = queries.get_password_reset_token(token_hash)
    if record is None or record["used"]:
        raise PasswordResetError("This reset link is invalid or has already been used.")
    expires_at = record["expires_at"]
    # psycopg2 returns a native (naive) datetime for this TIMESTAMP column — same UTC wall-clock
    # semantics as sqlite3's stored string, just no longer a string, so compare as datetime.
    if isinstance(expires_at, str):
        expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
    if expires_at < datetime.utcnow():
        raise PasswordResetError("This reset link has expired.")
    change_password(record["user_id"], new_password)
    queries.mark_password_reset_token_used(record["id"])


def has_role(user, *allowed_roles: str) -> bool:
    if user is None:
        return False
    role = user["role"]
    if role in allowed_roles:
        return True
    if "faculty" in allowed_roles and role in FACULTY_EQUIVALENT_ROLES:
        return True
    return False
