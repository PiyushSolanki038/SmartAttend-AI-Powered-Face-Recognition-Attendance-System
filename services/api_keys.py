"""Bearer API keys for the ERP analytics export surface (webportal/api.py). Hashed at
rest like passwords — the raw key is shown once at creation time and never stored."""

import hashlib
import secrets

from db import queries


def generate_api_key(label: str = None) -> str:
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    queries.create_api_key(label, key_hash)
    return raw_key


def verify_api_key(raw_key: str):
    """Returns the api_keys row if valid/active, else None. Bumps usage counters on success."""
    if not raw_key:
        return None
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    record = queries.get_api_key_by_hash(key_hash)
    if record is None:
        return None
    queries.touch_api_key(record["id"])
    return record
