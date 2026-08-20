"""2FA (TOTP) for admin accounts, using totp_secret/totp_enabled added to users in the
Phase-1 rebuild. Plaintext secret storage accepted — same trust boundary as the password
hashes already in the DB file. No recovery-code UI: lockout recovery is a manual
`UPDATE users SET totp_enabled=0` by another admin, documented not built."""

import pyotp

from db import queries
from config import APP_NAME


class TOTPError(Exception):
    pass


def start_enrollment(user_id: int) -> tuple[str, str]:
    """Generates a new (unsaved) secret and its otpauth:// provisioning URI for QR display.
    Not persisted/enabled until confirm_enrollment verifies a code against it."""
    user = queries.get_user(user_id)
    if user is None:
        raise TOTPError("User not found.")
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=APP_NAME)
    return secret, uri


def confirm_enrollment(user_id: int, secret: str, code: str):
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise TOTPError("Invalid code. Please try again.")
    queries.set_user_totp(user_id, secret, True)


def verify_code(user, code: str) -> bool:
    if not user["totp_enabled"] or not user["totp_secret"]:
        return True  # 2FA not enabled for this account — nothing to verify
    totp = pyotp.TOTP(user["totp_secret"])
    return totp.verify(code or "", valid_window=1)


def disable_totp(user_id: int):
    queries.disable_user_totp(user_id)
