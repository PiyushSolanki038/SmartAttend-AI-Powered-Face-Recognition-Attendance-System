import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()
_connection = None


def get_connection() -> sqlite3.Connection:
    global _connection
    with _lock:
        if _connection is None:
            _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA foreign_keys = ON")
    return _connection
