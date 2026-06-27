import hashlib
import secrets

from db import queries

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return digest, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest, _ = hash_password(password, salt)
    return secrets.compare_digest(digest, expected_hash)


def bootstrap_admin():
    """Seeds a default admin account on first run if no users exist yet."""
    if queries.count_users() == 0:
        digest, salt = hash_password("admin123")
        queries.insert_user("admin", digest, salt, "admin", full_name="Administrator")
        print("[SmartAttend] No users found. Created default account -> username: admin, password: admin123")
        print("[SmartAttend] Please change this password immediately via User Management.")


def login(username: str, password: str):
    """Returns the user row on success, or None on failure. Logs the attempt either way."""
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


def change_password(user_id: int, new_password: str):
    digest, salt = hash_password(new_password)
    queries.update_user_password(user_id, digest, salt)
