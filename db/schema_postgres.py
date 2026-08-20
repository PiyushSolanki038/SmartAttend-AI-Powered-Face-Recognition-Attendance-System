"""Postgres (Supabase-hosted) schema — the final, flattened state of every table.

Replaces the old SQLite CREATE_* + db/migrations.py (49 sequential ALTER/CREATE statements)
approach: since we're starting fresh on Postgres, there's no need to replay history — each
table is created directly in its final shape. See db/migrations.py for the historical record
of how the SQLite schema evolved to this point.

Conversions applied vs. the SQLite originals:
  INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
  DATETIME                          -> TIMESTAMP
  BLOB                              -> BYTEA
  boolean-like INTEGER columns      -> left as INTEGER NOT NULL DEFAULT 0/1 (unchanged)
  CHECK / FOREIGN KEY / ON DELETE CASCADE syntax is unchanged (valid in Postgres as-is)
"""

from db.connection import get_connection

CREATE_STUDENTS = """
CREATE TABLE IF NOT EXISTS students (
    id          SERIAL PRIMARY KEY,
    roll_no     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    department  TEXT,
    year        INTEGER,
    semester    INTEGER,
    encoding    BYTEA NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    email       TEXT
);
"""

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id                         SERIAL PRIMARY KEY,
    subject                    TEXT NOT NULL,
    section                    TEXT,
    faculty                    TEXT,
    started_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at                   TIMESTAMP,
    created_by_user_id         INTEGER REFERENCES users(id),
    qr_token                   TEXT,
    qr_token_expires_at        TIMESTAMP,
    substitute_faculty_user_id INTEGER REFERENCES users(id),
    timetable_slot_id          INTEGER REFERENCES timetable_slots(id),
    session_date               TEXT
);
"""

CREATE_ATTENDANCE = """
CREATE TABLE IF NOT EXISTS attendance (
    id               SERIAL PRIMARY KEY,
    session_id       INTEGER NOT NULL REFERENCES sessions(id),
    student_id       INTEGER REFERENCES students(id),
    status           TEXT CHECK(status IN ('present','absent','manual','unknown')),
    confidence       REAL,
    marked_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    check_in_method  TEXT,
    is_late          INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id                    SERIAL PRIMARY KEY,
    username              TEXT NOT NULL UNIQUE,
    password_hash         TEXT NOT NULL,
    salt                  TEXT NOT NULL,
    role                  TEXT NOT NULL CHECK(role IN ('admin','faculty','student','hod','coordinator')),
    full_name             TEXT,
    is_active             INTEGER NOT NULL DEFAULT 1,
    student_id            INTEGER REFERENCES students(id) ON DELETE CASCADE,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    must_change_password  INTEGER NOT NULL DEFAULT 0,
    department            TEXT,
    email                 TEXT,
    totp_secret           TEXT,
    totp_enabled          INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_AUTH_LOGS = """
CREATE TABLE IF NOT EXISTS auth_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    username    TEXT,
    event       TEXT NOT NULL CHECK(event IN ('login_success','login_failure','logout')),
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STUDENT_ENCODINGS = """
CREATE TABLE IF NOT EXISTS student_encodings (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    encoding    BYTEA NOT NULL,
    source      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SPOOF_LOGS = """
CREATE TABLE IF NOT EXISTS spoof_logs (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DISPUTE_REQUESTS = """
CREATE TABLE IF NOT EXISTS dispute_requests (
    id                  SERIAL PRIMARY KEY,
    student_id          INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    attendance_id       INTEGER NOT NULL REFERENCES attendance(id),
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by_user_id INTEGER REFERENCES users(id)
);
"""

CREATE_CHECKIN_REQUESTS = """
CREATE TABLE IF NOT EXISTS checkin_requests (
    id                  SERIAL PRIMARY KEY,
    student_id          INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    session_id          INTEGER NOT NULL REFERENCES sessions(id),
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by_user_id INTEGER REFERENCES users(id)
);
"""

CREATE_RESCAN_REQUESTS = """
CREATE TABLE IF NOT EXISTS rescan_requests (
    id                  SERIAL PRIMARY KEY,
    student_id          INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by_user_id INTEGER REFERENCES users(id)
);
"""

CREATE_TIMETABLE_SLOTS = """
CREATE TABLE IF NOT EXISTS timetable_slots (
    id          SERIAL PRIMARY KEY,
    department  TEXT,
    year        INTEGER,
    semester    INTEGER,
    subject     TEXT NOT NULL,
    section     TEXT,
    faculty     TEXT,
    day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL
);
"""

CREATE_APP_SETTINGS = """
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

CREATE_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id             SERIAL PRIMARY KEY,
    actor_user_id  INTEGER REFERENCES users(id),
    action         TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    entity_id      INTEGER,
    details        TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_LEAVE_REQUESTS = """
CREATE TABLE IF NOT EXISTS leave_requests (
    id                  SERIAL PRIMARY KEY,
    student_id          INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    session_id          INTEGER REFERENCES sessions(id),
    start_date          TEXT NOT NULL,
    end_date            TEXT NOT NULL,
    reason              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at         TIMESTAMP,
    resolved_by_user_id INTEGER REFERENCES users(id)
);
"""

CREATE_ANNOUNCEMENTS = """
CREATE TABLE IF NOT EXISTS announcements (
    id                  SERIAL PRIMARY KEY,
    sender_user_id      INTEGER REFERENCES users(id),
    department          TEXT,
    year                INTEGER,
    semester            INTEGER,
    section             TEXT,
    subject             TEXT NOT NULL,
    body                TEXT NOT NULL,
    is_institution_wide INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PASSWORD_RESET_TOKENS = """
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at   TIMESTAMP NOT NULL,
    used         INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_API_KEYS = """
CREATE TABLE IF NOT EXISTS api_keys (
    id            SERIAL PRIMARY KEY,
    label         TEXT,
    key_hash      TEXT NOT NULL UNIQUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at  TIMESTAMP,
    request_count INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1
);
"""

# Order matters: FK-referenced tables must exist before the tables that reference them.
# students -> users -> sessions -> attendance -> everything else.
CREATE_TABLES = [
    CREATE_STUDENTS,
    CREATE_USERS,
    CREATE_SESSIONS,
    CREATE_ATTENDANCE,
    CREATE_AUTH_LOGS,
    CREATE_STUDENT_ENCODINGS,
    CREATE_SPOOF_LOGS,
    CREATE_DISPUTE_REQUESTS,
    CREATE_CHECKIN_REQUESTS,
    CREATE_RESCAN_REQUESTS,
    CREATE_TIMETABLE_SLOTS,
    CREATE_APP_SETTINGS,
    CREATE_AUDIT_LOG,
    CREATE_LEAVE_REQUESTS,
    CREATE_ANNOUNCEMENTS,
    CREATE_PASSWORD_RESET_TOKENS,
    CREATE_API_KEYS,
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_students_roll ON students(roll_no);",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
    "CREATE INDEX IF NOT EXISTS idx_users_student ON users(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_student_encodings_student ON student_encodings(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_dispute_student ON dispute_requests(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_checkin_student ON checkin_requests(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_rescan_student ON rescan_requests(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_leave_student ON leave_requests(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_announcements_created ON announcements(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_slot_date ON sessions(timetable_slot_id, session_date);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_open ON sessions(ended_at, session_date);",
]


def init_db_postgres():
    conn = get_connection()
    # sessions references users(id) and timetable_slots(id); users is created before sessions
    # above, but timetable_slots is created after sessions — Postgres allows forward FK
    # references to a not-yet-existing table only within the same transaction/session as long
    # as the referenced table exists by the time the constraint is checked... actually it does
    # NOT: CREATE TABLE with a REFERENCES to a table that doesn't exist yet fails immediately.
    # So sessions must be created after timetable_slots. Reorder here rather than in the list
    # above (list order also documents the natural entity order for readers).
    conn.execute(CREATE_STUDENTS)
    conn.execute(CREATE_USERS)  # references students (already created)
    conn.execute(CREATE_TIMETABLE_SLOTS)
    conn.execute(CREATE_SESSIONS)  # references users + timetable_slots (both already created)
    conn.execute(CREATE_ATTENDANCE)
    conn.execute(CREATE_AUTH_LOGS)
    conn.execute(CREATE_STUDENT_ENCODINGS)
    conn.execute(CREATE_SPOOF_LOGS)
    conn.execute(CREATE_DISPUTE_REQUESTS)
    conn.execute(CREATE_CHECKIN_REQUESTS)
    conn.execute(CREATE_RESCAN_REQUESTS)
    conn.execute(CREATE_APP_SETTINGS)
    conn.execute(CREATE_AUDIT_LOG)
    conn.execute(CREATE_LEAVE_REQUESTS)
    conn.execute(CREATE_ANNOUNCEMENTS)
    conn.execute(CREATE_PASSWORD_RESET_TOKENS)
    conn.execute(CREATE_API_KEYS)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()
