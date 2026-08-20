"""HISTORICAL / NOT EXECUTED AT RUNTIME as of the Postgres (Supabase) migration.

This file's step-by-step SQLite migrations used to be replayed against the desktop app's
local smartattend.db on every startup via run_migrations(). Supabase starts from an empty
database, and db/schema_postgres.py already contains the fully consolidated final schema
(equivalent to the end state of every migration that used to live here), applied directly via
CREATE TABLE/INDEX IF NOT EXISTS in db/schema.py's init_db(). run_migrations() is no longer
called from anywhere in the codebase (verified via grep across the repo).

The MIGRATIONS list and run_migrations() function body have been deleted — the SQLite-specific
syntax they contained (AUTOINCREMENT, PRAGMA user_version, PRAGMA foreign_keys, the users-table
rebuild dance for changing a CHECK constraint) has no direct Postgres equivalent and would need
a real migration tool (e.g. Alembic) if step-by-step migrations are wanted again in the future.
For the historical record of exactly how the SQLite schema evolved column-by-column, check git
history for this file as of the commit that introduced the Postgres migration.
"""
