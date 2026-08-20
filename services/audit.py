from db.connection import get_connection


def log_action(actor_user_id, action: str, entity_type: str, entity_id=None, details: str = None) -> None:
    """Best-effort audit trail write. Never raises — a logging failure must not break
    the calling operation, so any DB error here is swallowed and printed instead."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, details) "
            "VALUES (%s, %s, %s, %s, %s)",
            (actor_user_id, action, entity_type, entity_id, details),
        )
        conn.commit()
    except Exception as exc:
        print(f"audit log_action failed: {exc}")


def list_audit_log(actor_user_id=None, entity_type=None, limit: int = 200):
    conn = get_connection()
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if actor_user_id is not None:
        sql += " AND actor_user_id = %s"
        params.append(actor_user_id)
    if entity_type is not None:
        sql += " AND entity_type = %s"
        params.append(entity_type)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    return conn.execute(sql, params).fetchall()
