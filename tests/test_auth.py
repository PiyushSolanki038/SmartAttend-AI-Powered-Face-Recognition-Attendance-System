import pytest

from db import queries
from services import auth


def test_hash_password_roundtrip():
    digest, salt = auth.hash_password("mypassword")
    assert auth.verify_password("mypassword", salt, digest)
    assert not auth.verify_password("wrongpassword", salt, digest)


def test_bootstrap_admin_creates_random_password_and_forces_change(capsys):
    auth.bootstrap_admin()
    user = queries.get_user_by_username("admin")
    assert user is not None
    assert user["must_change_password"] == 1
    printed = capsys.readouterr().out
    assert "admin123" not in printed  # the old hardcoded default must be gone


def test_login_success_clears_after_bootstrap():
    auth.bootstrap_admin()
    # bootstrap_admin doesn't return the generated password, so verify via a fresh known user
    auth.create_user("faculty1", "correcthorse", "faculty")
    user = auth.login("faculty1", "correcthorse")
    assert user is not None
    assert user["username"] == "faculty1"


def test_login_failure_returns_none():
    auth.create_user("faculty1", "correcthorse", "faculty")
    assert auth.login("faculty1", "wrongpassword") is None
    assert auth.login("nouser", "whatever") is None


def test_login_lockout_after_max_failures():
    auth.create_user("student1", "roll123", "faculty")
    for _ in range(auth.MAX_LOGIN_FAILURES):
        assert auth.login("student1", "wrongpassword") is None
    with pytest.raises(auth.AccountLockedError):
        auth.login("student1", "roll123")  # even the correct password is now rejected


def test_change_password_clears_must_change_flag():
    user_id = auth.create_user("faculty2", "temp1234", "faculty")
    queries.update_user_password(user_id, *auth.hash_password("temp1234"), must_change_password=True)
    assert queries.get_user(user_id)["must_change_password"] == 1
    auth.change_password(user_id, "newpassword")
    assert queries.get_user(user_id)["must_change_password"] == 0
