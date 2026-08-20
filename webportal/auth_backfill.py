from db import queries
from db.connection import get_connection
from services.auth import hash_password


def backfill_student_logins():
    """Creates a login for every enrolled student that doesn't have one yet.
    Username = roll number, default password = roll number, for low-friction bulk onboarding.
    Since a roll number is public/guessable, the account is flagged must_change_password so
    the student is forced onto a real password the first time they log in."""
    created = []
    for student in queries.list_students_without_login():
        digest, salt = hash_password(student["roll_no"])
        user_id = queries.insert_student_user(student["roll_no"], digest, salt, student["id"], full_name=student["name"])
        conn = get_connection()
        conn.execute("UPDATE users SET must_change_password = 1 WHERE id = %s", (user_id,))
        conn.commit()
        created.append(student["roll_no"])
    return created
