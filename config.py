import json
import os
import secrets

APP_NAME = "SmartAttend"
VERSION = "1.0.0"

BASE_DIR = os.path.join(os.path.expanduser("~"), ".smartattend")
# DB_PATH: no longer used by the webportal or by db/connection.py (both now talk to Postgres
# via DATABASE_URL — see db/connection.py, which is Postgres-only going forward). Left defined
# here only in case any local/desktop-mode code still references it directly.
DB_PATH = os.path.join(BASE_DIR, "smartattend.db")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
SESSION_SECRET_PATH = os.path.join(BASE_DIR, "session_secret.key")

# ML Settings
CAMERA_INDEX = 0
FRAME_SKIP = 3
RESIZE_FACTOR = 0.5  # higher than the old MediaPipe-era default — the HOG face detector needs more pixels per face
TOLERANCE = 0.6
ATTENDANCE_CONFIRM_STREAK = 2  # consecutive detection ticks a student must match before being marked present
MIN_ENCODINGS = 3
SESSION_TIMEOUT_MINUTES = 60
LIVENESS_ENABLED = True
LIVENESS_TEXTURE_MIN = 25.0  # lower = more lenient; raise if photo/screen spoofs get through, lower if real faces get flagged
# Blink detection (Eye Aspect Ratio) catches a photo/video held up to the camera, which the
# texture check alone misses since an on-screen photo can look just as "sharp" as a real face.
# A static photo can't blink, so attendance requires a detected blink within this window.
LIVENESS_BLINK_WINDOW = 10  # rolling number of detection ticks (~FRAME_SKIP apart) of EAR history kept per face
LIVENESS_EAR_OPEN_MIN = 0.22  # EAR must have been at least this high (eye clearly open) right before the dip
LIVENESS_EAR_CLOSED_MAX = 0.17  # EAR at or below this counts as "closed" — the dip that confirms a blink
LOW_LIGHT_ENHANCEMENT_ENABLED = True

# UI
THEME = "dark"
COLOR_THEME = "blue"

# Report
EXCEL_HEADERS = ["Roll No", "Name", "Department", "Date", "Time", "Status", "Confidence"]
DEFAULTER_THRESHOLD = 75.0  # attendance % below this is flagged as a defaulter
LATE_THRESHOLD_MINUTES = 10  # minutes after session start beyond which a present mark counts as "late"

# Notifications
# Env vars win when present (needed for the cloud-deployed webportal, which has no settings.json
# UI to re-enter these in); falls back to the previous "" / 587 literals otherwise, which
# load_settings() below can still override from settings.json for the desktop app.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
# never persisted to settings.json — re-entered per app session for basic security (desktop
# mode), or supplied via the SMTP_PASSWORD env var for cloud deployment (webportal).
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
NOTIFY_ON_SESSION_END = True
NOTIFY_DEFAULTER_CHECK = True

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

_PERSISTED_KEYS = [
    "CAMERA_INDEX", "FRAME_SKIP", "TOLERANCE", "MIN_ENCODINGS",
    "THEME", "DEFAULTER_THRESHOLD", "SESSION_TIMEOUT_MINUTES",
    "LIVENESS_ENABLED", "LIVENESS_TEXTURE_MIN", "LIVENESS_BLINK_WINDOW",
    "LIVENESS_EAR_OPEN_MIN", "LIVENESS_EAR_CLOSED_MAX",
    "LOW_LIGHT_ENHANCEMENT_ENABLED", "LATE_THRESHOLD_MINUTES",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "NOTIFY_ON_SESSION_END", "NOTIFY_DEFAULTER_CHECK",
]


def load_settings():
    """Overwrite module globals with values saved in settings.json, if present."""
    if not os.path.exists(SETTINGS_PATH):
        return
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    globals_dict = globals()
    for key in _PERSISTED_KEYS:
        if key in data:
            globals_dict[key] = data[key]


def save_settings():
    globals_dict = globals()
    data = {key: globals_dict[key] for key in _PERSISTED_KEYS}
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_session_secret() -> str:
    """Returns a random secret persisted to disk on first call, instead of a hardcoded
    string baked into the source (which would let anyone with the repo forge portal
    session cookies). Reused across restarts so existing sessions stay valid."""
    if os.path.exists(SESSION_SECRET_PATH):
        with open(SESSION_SECRET_PATH, "r") as f:
            secret = f.read().strip()
        if secret:
            return secret
    secret = secrets.token_hex(32)
    with open(SESSION_SECRET_PATH, "w") as f:
        f.write(secret)
    return secret


load_settings()
