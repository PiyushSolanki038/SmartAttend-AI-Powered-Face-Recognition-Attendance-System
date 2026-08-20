"""Analytics export API for ERP integration, mounted at /api/v1 by webportal/main.py.
Pull/export model only — no OAuth2, no webhooks, no rate limiting beyond the basic
request counter in api_keys. Auth via X-API-Key header, bearer tokens hashed at rest
(services/api_keys.py)."""

from fastapi import APIRouter, Header, HTTPException

from db import queries
from services.api_keys import verify_api_key

router = APIRouter(prefix="/api/v1")


def _require_api_key(x_api_key: str = Header(None)):
    record = verify_api_key(x_api_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")
    return record


@router.get("/students")
def list_students(x_api_key: str = Header(None)):
    _require_api_key(x_api_key)
    rows = queries.list_students()
    return [dict(r) for r in rows]


@router.get("/attendance")
def export_attendance(x_api_key: str = Header(None), subject: str = None, department: str = None,
                       start_date: str = None, end_date: str = None):
    _require_api_key(x_api_key)
    rows = queries.get_filtered_attendance(subject=subject, department=department,
                                            start_date=start_date, end_date=end_date)
    return [dict(r) for r in rows]


@router.get("/attendance/percentages")
def export_percentages(x_api_key: str = Header(None), subject: str = None, department: str = None):
    _require_api_key(x_api_key)
    return queries.get_attendance_percentages(subject=subject, department=department)
