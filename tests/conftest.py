import os
import tempfile

import pytest

import db.connection as connection
from db.schema import init_db


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Every test gets its own fresh SQLite file instead of the real ~/.smartattend DB,
    and a fresh module-level connection (db.connection caches a single global one)."""
    db_path = os.path.join(tmp_path, "test.db")
    monkeypatch.setattr(connection, "DB_PATH", db_path)
    connection._connection = None
    init_db()
    yield
    connection._connection = None
