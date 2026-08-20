import os
import secrets
import tempfile
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import config
from db import queries
from db.schema import init_db
from services import announcements as announcement_service
from services import leave_requests as leave_service
from services import qr_checkin
from services import requests as request_service
from services.auth import (
    AccountLockedError, PasswordResetError, change_password, login as auth_login,
    request_password_reset, reset_password_with_token, verify_password,
)
from services.dashboard import render_student_charts_base64
from services.pdf_report import export_student_pdf
from webportal.api import router as api_router
from webportal.auth_backfill import backfill_student_logins

SESSION_TIMEOUT_SECONDS = 30 * 60  # auto-logout after 30 minutes idle
HISTORY_PAGE_SIZE = 50

app = FastAPI(title="SmartAttend Student Portal")
# secret_key is a persisted random value (config.get_session_secret), not a string baked
# into source — a hardcoded key would let anyone with the repo forge session cookies.
# same_site="lax" blocks the cookie being sent on cross-site POSTs, which combined with
# the CSRF token below covers login/profile/change-password against CSRF.
app.add_middleware(
    SessionMiddleware,
    secret_key=config.get_session_secret(),
    max_age=SESSION_TIMEOUT_SECONDS,
    same_site="lax",
)
# Absolute, __file__-relative paths rather than "webportal/static" — relative paths only
# resolve correctly if the process cwd happens to be the repo root, which isn't guaranteed
# under every deploy target (e.g. a serverless runtime's working directory).
_HERE = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))
app.include_router(api_router)


@app.on_event("startup")
def startup():
    init_db()
    backfill_student_logins()


def _current_student(request: Request):
    student_id = request.session.get("student_id")
    if student_id is None:
        return None
    return queries.get_student(student_id)


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["csrf_token"] = token
    return token


def _check_csrf(request: Request, submitted_token: str):
    expected = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, submitted_token or ""):
        raise HTTPException(status_code=403, detail="Invalid or expired form submission, please retry.")


def _must_change_password(request: Request) -> bool:
    user_id = request.session.get("user_id")
    if user_id is None:
        return False
    user = queries.get_user(user_id)
    return bool(user and user["must_change_password"])


def _dashboard_data(student):
    cohort = dict(department=student["department"], year=student["year"], semester=student["semester"])
    subjects = queries.get_student_subject_summary(student["id"])
    class_averages = queries.get_subject_class_averages(**cohort)
    for s in subjects:
        s["class_average"] = class_averages.get(s["subject"], 0.0)

    total_present = sum(s["present"] for s in subjects)
    total_sessions = sum(s["total"] for s in subjects)
    overall_pct = (total_present / total_sessions * 100) if total_sessions else 0.0
    threshold = config.DEFAULTER_THRESHOLD

    days_needed = 0
    if total_sessions and overall_pct < threshold:
        denom = 1 - threshold / 100
        days_needed = max(0, int((threshold / 100 * total_sessions - total_present) / denom) + 1)

    rank, rank_total = queries.get_student_rank(student["id"], **cohort)
    streak = queries.get_current_streak(student["id"])
    late_arrivals = queries.get_late_arrivals(student_id=student["id"])

    return {
        "student": student,
        "subjects": subjects,
        "overall_pct": overall_pct,
        "total_present": total_present,
        "total_sessions": total_sessions,
        "threshold": threshold,
        "is_low": overall_pct < threshold if total_sessions else False,
        "days_needed": days_needed,
        "rank": rank,
        "rank_total": rank_total,
        "streak": streak,
        "late_count": len(late_arrivals),
    }


@app.get("/")
def root(request: Request):
    if _current_student(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")


@app.get("/login")
def login_form(request: Request):
    if _current_student(request):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(request, "login.html", {"error": None, "csrf_token": _csrf_token(request)})


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...),
                  csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    backfill_student_logins()  # picks up students enrolled after the portal started
    try:
        user = auth_login(username, password)
    except AccountLockedError as e:
        return templates.TemplateResponse(request, "login.html", {"error": str(e), "csrf_token": _csrf_token(request)})
    if user is None or user["role"] != "student":
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid roll number or password", "csrf_token": _csrf_token(request)},
        )
    request.session["student_id"] = user["student_id"]
    request.session["user_id"] = user["id"]
    if user["must_change_password"]:
        return RedirectResponse("/change-password", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/dashboard")
def dashboard(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(student))


@app.get("/history")
def history(request: Request, page: int = 1, status: str = "all", subject: str = "all"):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    page = max(1, page)
    status_filter = status if status in ("present", "absent", "manual", "unknown") else None
    subject_filter = subject if subject and subject != "all" else None

    total = queries.count_student_history(student["id"], status=status_filter, subject=subject_filter)
    records = queries.get_student_history(
        student["id"], limit=HISTORY_PAGE_SIZE, offset=(page - 1) * HISTORY_PAGE_SIZE,
        status=status_filter, subject=subject_filter,
    )
    total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    counts = queries.get_student_status_counts(student["id"])
    subjects = queries.get_distinct_subjects_for_student(student["id"])
    return templates.TemplateResponse(request, "history.html", {
        "student": student, "records": records, "page": page, "total_pages": total_pages,
        "counts": counts, "subjects": subjects,
        "active_status": status if status in ("all", "present", "absent", "manual", "unknown") else "all",
        "active_subject": subject_filter or "all",
    })



def _profile_context(request: Request, student, saved: bool = False):
    cohort = dict(department=student["department"], year=student["year"], semester=student["semester"])
    rank, rank_total = queries.get_student_rank(student["id"], **cohort)
    streak = queries.get_current_streak(student["id"])
    subjects = queries.get_student_subject_summary(student["id"])
    total_present = sum(s["present"] for s in subjects)
    total_sessions = sum(s["total"] for s in subjects)
    overall_pct = (total_present / total_sessions * 100) if total_sessions else 0.0

    user = queries.get_user_by_student_id(student["id"])
    last_login = queries.get_last_login(user["id"]) if user else None

    return {
        "student": student, "saved": saved, "csrf_token": _csrf_token(request),
        "rank": rank, "rank_total": rank_total, "streak": streak, "overall_pct": overall_pct,
        "last_login": last_login["occurred_at"] if last_login else None,
    }


@app.get("/profile")
def profile(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "profile.html", _profile_context(request, student))


@app.post("/profile")
def profile_update(request: Request, email: str = Form(""), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    queries.update_student_email(student["id"], email.strip() or None)
    student = queries.get_student(student["id"])
    return templates.TemplateResponse(request, "profile.html", _profile_context(request, student, saved=True))


@app.get("/change-password")
def change_password_form(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    forced = _must_change_password(request)
    return templates.TemplateResponse(request, "change_password.html", {
        "error": None, "success": False, "forced": forced, "csrf_token": _csrf_token(request),
    })


@app.post("/change-password")
def change_password_submit(request: Request, current_password: str = Form(...),
                            new_password: str = Form(...), confirm_password: str = Form(...),
                            csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    forced = _must_change_password(request)
    user = queries.get_user(request.session.get("user_id"))

    def _rerender(error):
        return templates.TemplateResponse(request, "change_password.html", {
            "error": error, "success": False, "forced": forced, "csrf_token": _csrf_token(request),
        })

    if user is None or not verify_password(current_password, user["salt"], user["password_hash"]):
        return _rerender("Current password is incorrect")
    if len(new_password) < 4:
        return _rerender("New password must be at least 4 characters")
    if new_password != confirm_password:
        return _rerender("New passwords do not match")
    change_password(user["id"], new_password)
    return templates.TemplateResponse(request, "change_password.html", {
        "error": None, "success": True, "forced": False, "csrf_token": _csrf_token(request),
    })


@app.get("/report.pdf")
def download_report(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    data = _dashboard_data(student)
    filepath = os.path.join(tempfile.gettempdir(), f"smartattend_{student['roll_no']}.pdf")
    export_student_pdf(filepath, student, data["subjects"], data["overall_pct"],
                        data["total_present"], data["total_sessions"])
    return FileResponse(filepath, filename=f"attendance_{student['roll_no']}.pdf", media_type="application/pdf")


@app.get("/analytics")
def analytics(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    chart_data_uri = render_student_charts_base64(student["id"])

    subjects = queries.get_student_subject_summary(student["id"])
    scored = [s for s in subjects if s["total"] > 0]
    best_subject = max(scored, key=lambda s: s["percentage"]) if scored else None
    worst_subject = min(scored, key=lambda s: s["percentage"]) if scored else None
    streak = queries.get_current_streak(student["id"])

    return templates.TemplateResponse(request, "analytics.html", {
        "student": student, "chart_data_uri": chart_data_uri, "subjects": subjects,
        "best_subject": best_subject, "worst_subject": worst_subject, "streak": streak,
    })


_STATUS_FILTERS = ("all", "pending", "approved", "rejected")


def _disputes_context(request: Request, student, status: str = "all", error: str = None):
    history = queries.get_student_history(student["id"], limit=50)
    disputable = [r for r in history if r["status"] in ("absent", "unknown")]
    my_disputes = queries.list_disputes_for_student(student["id"])
    disputed_ids = {d["attendance_id"] for d in my_disputes}
    disputable = [r for r in disputable if r["attendance_id"] not in disputed_ids]

    counts = {"all": len(my_disputes)}
    for s in ("pending", "approved", "rejected"):
        counts[s] = sum(1 for d in my_disputes if d["status"] == s)
    status = status if status in _STATUS_FILTERS else "all"
    filtered = my_disputes if status == "all" else [d for d in my_disputes if d["status"] == status]

    return {
        "student": student, "disputable": disputable, "disputes": filtered,
        "counts": counts, "active_status": status,
        "error": error, "csrf_token": _csrf_token(request),
    }


@app.get("/disputes")
def disputes(request: Request, status: str = "all"):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "disputes.html", _disputes_context(request, student, status))


@app.post("/disputes")
def disputes_submit(request: Request, attendance_id: int = Form(...), reason: str = Form(...),
                     csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        request_service.submit_dispute(student["id"], attendance_id, reason)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "disputes.html", _disputes_context(request, student, error=str(e)))
    return RedirectResponse("/disputes", status_code=303)


@app.post("/disputes/cancel")
def disputes_cancel(request: Request, dispute_id: int = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        request_service.cancel_dispute(student["id"], dispute_id)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "disputes.html", _disputes_context(request, student, error=str(e)))
    return RedirectResponse("/disputes", status_code=303)


def _checkin_context(request: Request, student, status: str = "all", error: str = None):
    open_session = queries.get_open_auto_session_today()
    already_marked = False
    if open_session:
        existing = queries.get_session_attendance(open_session["id"])
        already_marked = any(r["student_id"] == student["id"] for r in existing)
    pending = queries.get_pending_checkin_request_today(student["id"])
    history = queries.list_checkin_requests_for_student(student["id"])

    counts = {"all": len(history)}
    for s in ("pending", "approved", "rejected"):
        counts[s] = sum(1 for r in history if r["status"] == s)
    status = status if status in _STATUS_FILTERS else "all"
    filtered = history if status == "all" else [r for r in history if r["status"] == status]

    return {
        "student": student, "open_session": open_session, "already_marked": already_marked,
        "pending": pending, "history": filtered, "counts": counts, "active_status": status,
        "error": error, "csrf_token": _csrf_token(request),
    }


@app.get("/checkin-request")
def checkin_request_form(request: Request, status: str = "all"):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "checkin_request.html", _checkin_context(request, student, status))


@app.post("/checkin-request")
def checkin_request_submit(request: Request, reason: str = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    open_session = queries.get_open_auto_session_today()
    if open_session is None:
        return templates.TemplateResponse(
            request, "checkin_request.html",
            _checkin_context(request, student, error="There's no active attendance session right now."),
        )
    try:
        request_service.submit_checkin_request(student["id"], open_session["id"], reason)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "checkin_request.html", _checkin_context(request, student, error=str(e)))
    return RedirectResponse("/checkin-request", status_code=303)


@app.post("/checkin-request/cancel")
def checkin_request_cancel(request: Request, request_id: int = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        request_service.cancel_checkin_request(student["id"], request_id)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "checkin_request.html", _checkin_context(request, student, error=str(e)))
    return RedirectResponse("/checkin-request", status_code=303)


def _rescan_context(request: Request, student, status: str = "all", error: str = None):
    pending = queries.get_pending_rescan_request(student["id"])
    history = queries.list_rescan_requests_for_student(student["id"])

    counts = {"all": len(history)}
    for s in ("pending", "approved", "rejected"):
        counts[s] = sum(1 for r in history if r["status"] == s)
    status = status if status in _STATUS_FILTERS else "all"
    filtered = history if status == "all" else [r for r in history if r["status"] == status]

    return {
        "student": student, "pending": pending, "history": filtered, "counts": counts,
        "active_status": status, "error": error, "csrf_token": _csrf_token(request),
    }


@app.get("/rescan-request")
def rescan_request_form(request: Request, status: str = "all"):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "rescan_request.html", _rescan_context(request, student, status))


@app.post("/rescan-request")
def rescan_request_submit(request: Request, reason: str = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        request_service.submit_rescan_request(student["id"], reason)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "rescan_request.html", _rescan_context(request, student, error=str(e)))
    return RedirectResponse("/rescan-request", status_code=303)


@app.post("/rescan-request/cancel")
def rescan_request_cancel(request: Request, request_id: int = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        request_service.cancel_rescan_request(student["id"], request_id)
    except request_service.RequestError as e:
        return templates.TemplateResponse(request, "rescan_request.html", _rescan_context(request, student, error=str(e)))
    return RedirectResponse("/rescan-request", status_code=303)


@app.get("/requests")
def requests_hub(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    counts = queries.get_request_counts_for_student(student["id"])
    recent = queries.get_recent_requests_for_student(student["id"], limit=5)
    return templates.TemplateResponse(request, "requests_hub.html", {
        "student": student, "counts": counts, "recent": recent,
    })


@app.get("/timetable")
def timetable_view(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    slots = queries.list_timetable_for_cohort(student["department"], student["year"], student["semester"])
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day = {i: [] for i in range(7)}
    for slot in slots:
        by_day[slot["day_of_week"]].append(slot)
    schedule = [(i, days[i], sorted(by_day[i], key=lambda s: s["start_time"])) for i in range(7) if by_day[i]]

    now = datetime.now()
    today_idx = now.weekday()
    current_time = now.strftime("%H:%M")

    next_class = None
    today_slots = sorted(by_day[today_idx], key=lambda s: s["start_time"])
    for s in today_slots:
        if s["start_time"] >= current_time:
            next_class = (days[today_idx], s, True)
            break
    if next_class is None:
        for offset in range(1, 8):
            idx = (today_idx + offset) % 7
            day_slots = sorted(by_day[idx], key=lambda s: s["start_time"])
            if day_slots:
                next_class = (days[idx], day_slots[0], False)
                break

    return templates.TemplateResponse(request, "timetable.html", {
        "student": student, "schedule": schedule, "today_idx": today_idx, "next_class": next_class,
    })


# ---------- Leave / absence requests ----------

def _leave_context(request: Request, student, status: str = "all", error: str = None):
    pending = queries.get_pending_leave_request(student["id"])
    history = queries.list_leave_requests_for_student(student["id"])
    counts = {"all": len(history)}
    for s in ("pending", "approved", "rejected"):
        counts[s] = sum(1 for r in history if r["status"] == s)
    status = status if status in _STATUS_FILTERS else "all"
    filtered = history if status == "all" else [r for r in history if r["status"] == status]
    return {
        "student": student, "pending": pending, "history": filtered, "counts": counts,
        "active_status": status, "error": error, "csrf_token": _csrf_token(request),
    }


@app.get("/leave-request")
def leave_request_form(request: Request, status: str = "all"):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    return templates.TemplateResponse(request, "leave_request.html", _leave_context(request, student, status))


@app.post("/leave-request")
def leave_request_submit(request: Request, start_date: str = Form(...), end_date: str = Form(...),
                          reason: str = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        leave_service.submit_leave_request(student["id"], start_date, end_date, reason)
    except leave_service.LeaveRequestError as e:
        return templates.TemplateResponse(request, "leave_request.html", _leave_context(request, student, error=str(e)))
    return RedirectResponse("/leave-request", status_code=303)


@app.post("/leave-request/cancel")
def leave_request_cancel(request: Request, request_id: int = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    try:
        leave_service.cancel_leave_request(student["id"], request_id)
    except leave_service.LeaveRequestError as e:
        return templates.TemplateResponse(request, "leave_request.html", _leave_context(request, student, error=str(e)))
    return RedirectResponse("/leave-request", status_code=303)


# ---------- Announcements (read-only) ----------

@app.get("/announcements")
def announcements_view(request: Request):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    items = announcement_service.list_for_cohort(student["department"], student["year"], student["semester"])
    return templates.TemplateResponse(request, "announcements.html", {"student": student, "announcements": items})


# ---------- QR self check-in ----------

@app.get("/checkin/qr/{token}")
def qr_checkin_view(request: Request, token: str):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    error = None
    session_id = None
    try:
        session_id = qr_checkin.check_in_with_token(token, student["id"])
    except qr_checkin.QRCheckinError as e:
        error = str(e)
    return templates.TemplateResponse(request, "qr_checkin.html", {
        "student": student, "error": error, "session_id": session_id,
    })


# ---------- Calendar view of attendance ----------

@app.get("/calendar")
def calendar_view(request: Request, year: int = None, month: int = None):
    student = _current_student(request)
    if student is None:
        return RedirectResponse("/login")
    if _must_change_password(request):
        return RedirectResponse("/change-password")
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    history = queries.get_student_history(student["id"], limit=1000)
    by_date = {}
    for r in history:
        started_at = r["started_at"]
        date_part = started_at.strftime("%Y-%m-%d") if started_at else ""
        if date_part.startswith(f"{year:04d}-{month:02d}"):
            existing = by_date.get(date_part)
            # 'absent' should not be overridden by a later 'unknown' row for the same day, etc.
            # simple precedence: present/manual > absent > unknown
            precedence = {"present": 3, "manual": 3, "absent": 2, "unknown": 1}
            if existing is None or precedence.get(r["status"], 0) > precedence.get(existing, 0):
                by_date[date_part] = r["status"]

    import calendar as _cal
    cal = _cal.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return templates.TemplateResponse(request, "calendar.html", {
        "student": student, "year": year, "month": month, "weeks": weeks, "by_date": by_date,
        "month_name": _cal.month_name[month], "prev_month": prev_month, "next_month": next_month,
    })


# ---------- Password reset (webportal self-service only) ----------

@app.get("/forgot-password")
def forgot_password_form(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {
        "sent": False, "csrf_token": _csrf_token(request),
    })


@app.post("/forgot-password")
def forgot_password_submit(request: Request, username_or_email: str = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    base_url = str(request.base_url)
    request_password_reset(username_or_email.strip(), base_url)
    # Always show the same "check your email" message — avoids leaking whether an
    # account/email exists.
    return templates.TemplateResponse(request, "forgot_password.html", {
        "sent": True, "csrf_token": _csrf_token(request),
    })


@app.get("/reset-password")
def reset_password_form(request: Request, token: str = ""):
    return templates.TemplateResponse(request, "reset_password.html", {
        "token": token, "error": None, "success": False, "csrf_token": _csrf_token(request),
    })


@app.post("/reset-password")
def reset_password_submit(request: Request, token: str = Form(...), new_password: str = Form(...),
                           confirm_password: str = Form(...), csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    if new_password != confirm_password:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token, "error": "Passwords do not match", "success": False, "csrf_token": _csrf_token(request),
        })
    try:
        reset_password_with_token(token, new_password)
    except PasswordResetError as e:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token, "error": str(e), "success": False, "csrf_token": _csrf_token(request),
        })
    return templates.TemplateResponse(request, "reset_password.html", {
        "token": token, "error": None, "success": True, "csrf_token": _csrf_token(request),
    })
