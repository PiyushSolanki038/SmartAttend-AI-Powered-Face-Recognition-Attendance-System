from db.schema_postgres import init_db_postgres


def init_db():
    """Creates the full consolidated Postgres schema (idempotent — every statement is
    CREATE TABLE/INDEX IF NOT EXISTS). Supabase starts empty, so schema_postgres.py's
    already-final schema is applied directly; there is no longer a step-by-step
    run_migrations() replay — see db/migrations.py's module docstring for why."""
    init_db_postgres()
