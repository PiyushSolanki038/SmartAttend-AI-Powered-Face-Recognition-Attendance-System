import threading
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from dotenv import load_dotenv

load_dotenv()

import os

import psycopg2
import psycopg2.extras

_lock = threading.Lock()
_connection = None


def _ensure_sslmode(database_url: str) -> str:
    """Forces sslmode=require onto the connection string if it isn't already present —
    Supabase (and most managed Postgres hosts) require TLS, and we never want to silently
    fall back to an unencrypted connection just because the env var omitted the param."""
    parts = urlsplit(database_url)
    query_pairs = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "sslmode" not in query_pairs:
        query_pairs["sslmode"] = "require"
    new_query = urlencode(query_pairs)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _build_connection() -> "psycopg2.extensions.connection":
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and fill in your Supabase "
            "Postgres connection string (postgresql://postgres:[PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres)."
        )
    database_url = _ensure_sslmode(database_url)
    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    # Autocommit: every db/queries.py write already calls conn.commit() explicitly, but plenty
    # of read-only routes (any GET that only SELECTs) never do — without autocommit, psycopg2
    # opens an implicit transaction on the very first statement and leaves it open ("idle in
    # transaction") until something eventually commits it, which on a long-lived warm serverless
    # connection can sit for the connection's entire lifetime. An idle-in-transaction connection
    # holds locks that block unrelated DDL (e.g. `ALTER TABLE ... ADD COLUMN`) indefinitely, and
    # more generally is bad for the DB (blocks autovacuum, etc). Autocommit makes every statement
    # its own implicit transaction, so a read commits itself the instant it finishes.
    conn.autocommit = True
    return conn


class _ConnectionWrapper:
    """Thin wrapper around a psycopg2 connection that mimics the small slice of the
    sqlite3.Connection API this codebase relies on (conn.execute(sql, params) returning a
    cursor with .fetchone()/.fetchall()/.rowcount, plus .commit()/.rollback()), so the large
    body of call sites across db/queries.py and services/*.py didn't need to be restructured
    to manage cursors explicitly — only the SQL dialect (placeholders, functions) changed."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def cursor(self):
        return self._conn.cursor()

    def close(self):
        self._conn.close()


def get_connection() -> _ConnectionWrapper:
    global _connection
    with _lock:
        if _connection is None:
            raw_conn = _build_connection()
            _connection = _ConnectionWrapper(raw_conn)
    return _connection
