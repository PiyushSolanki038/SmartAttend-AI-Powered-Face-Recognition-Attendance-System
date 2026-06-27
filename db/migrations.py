from db.connection import get_connection

# Each entry: (version, sql_statement). Statements must be additive/idempotent-safe;
# duplicate-column/table errors are swallowed since CREATE TABLE already guards most cases.
MIGRATIONS = [
    (1, "ALTER TABLE sessions ADD COLUMN created_by_user_id INTEGER REFERENCES users(id);"),
    (2, """
        CREATE TABLE IF NOT EXISTS student_encodings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            encoding    BLOB NOT NULL,
            source      TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """),
    (3, "CREATE INDEX IF NOT EXISTS idx_student_encodings_student ON student_encodings(student_id);"),
    (4, """
        INSERT INTO student_encodings (student_id, encoding, source)
        SELECT id, encoding, 'legacy_backfill' FROM students
        WHERE id NOT IN (SELECT student_id FROM student_encodings);
    """),
    (5, """
        CREATE TABLE IF NOT EXISTS spoof_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id),
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """),
]


def run_migrations():
    conn = get_connection()
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, stmt in MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.execute(stmt)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"Migration {version} failed, stopping at last successful version: {exc}")
            break
