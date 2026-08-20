from db.connection import get_connection


def get_setting(key: str, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row is not None else default


def set_setting(key: str, value) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, str(value) if value is not None else None),
    )
    conn.commit()
