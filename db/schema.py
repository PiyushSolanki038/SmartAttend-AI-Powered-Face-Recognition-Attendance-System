from db.connection import get_connection
from db.migrations import run_migrations

CREATE_STUDENTS = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    department  TEXT,
    year        INTEGER,
    semester    INTEGER,
    encoding    BLOB NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    section     TEXT,
    faculty     TEXT,
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at    DATETIME
);
"""

CREATE_ATTENDANCE = """
CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    student_id  INTEGER REFERENCES students(id),
    status      TEXT CHECK(status IN ('present','absent','manual','unknown')),
    confidence  REAL,
    marked_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin','faculty')),
    full_name     TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_AUTH_LOGS = """
CREATE TABLE IF NOT EXISTS auth_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    username    TEXT,
    event       TEXT NOT NULL CHECK(event IN ('login_success','login_failure','logout')),
    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_students_roll ON students(roll_no);",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
]


def init_db():
    conn = get_connection()
    conn.execute(CREATE_STUDENTS)
    conn.execute(CREATE_SESSIONS)
    conn.execute(CREATE_ATTENDANCE)
    conn.execute(CREATE_USERS)
    conn.execute(CREATE_AUTH_LOGS)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()
    run_migrations()
