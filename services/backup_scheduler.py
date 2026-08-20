"""Automated DB backup scheduling. Explicitly only runs while the desktop app is open —
polled via customtkinter's after() loop from ui/app.py, no OS-level cron. Uses SQLite's
backup() API (not a raw file copy) so an in-progress write can't corrupt the backup file."""

import os
import sqlite3
from datetime import datetime

import config
from db.connection import get_connection
from services.settings import get_setting, set_setting

BACKUP_INTERVAL_HOURS_DEFAULT = 24


def run_backup_now() -> str:
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    filename = f"smartattend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest_path = os.path.join(config.BACKUP_DIR, filename)
    source = get_connection()
    dest = sqlite3.connect(dest_path)
    with dest:
        source.backup(dest)
    dest.close()
    set_setting("last_backup_at", datetime.now().isoformat())
    return dest_path


def restore_backup(backup_path: str):
    """Restores the live DB from a backup file, using SQLite's backup() API in the
    opposite direction so the running connection's data is atomically replaced."""
    source = sqlite3.connect(backup_path)
    dest = get_connection()
    with dest:
        source.backup(dest)
    source.close()


def run_scheduled_backup_if_due(interval_hours: float = None) -> bool:
    """Returns True if a backup was just taken. Call periodically (e.g. every few minutes)
    from ui/app.py's after() loop; cheap no-op if not yet due."""
    interval_hours = interval_hours if interval_hours is not None else float(
        get_setting("backup_interval_hours", BACKUP_INTERVAL_HOURS_DEFAULT)
    )
    last = get_setting("last_backup_at")
    if last:
        try:
            elapsed_hours = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
            if elapsed_hours < interval_hours:
                return False
        except ValueError:
            pass
    run_backup_now()
    return True


def list_backups():
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    files = sorted(
        (f for f in os.listdir(config.BACKUP_DIR) if f.endswith(".db")),
        reverse=True,
    )
    return [os.path.join(config.BACKUP_DIR, f) for f in files]
