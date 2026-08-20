"""Faculty/admin timetable management: CSV bulk import for weekly class slots, mirroring
the row-by-row error-collection pattern used by services.enrollment.bulk_import_csv."""

import csv

from db import queries

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class TimetableImportError(Exception):
    pass


def find_conflicts(faculty: str, day_of_week: int, start_time: str, end_time: str, exclude_id: int = None):
    """Returns existing slots that clash with the given faculty on the same day/time range.
    Faculty is the check that matters (a teacher can't be in two places at once); department/
    year/semester/section overlaps are allowed (e.g. two sections on the same subject/slot).
    HH:MM strings compare correctly lexicographically since the format is fixed-width."""
    if not faculty:
        return []
    conflicts = []
    for slot in queries.list_all_timetable_slots():
        if exclude_id is not None and slot["id"] == exclude_id:
            continue
        if (slot["faculty"] or "").strip().lower() != faculty.strip().lower():
            continue
        if slot["day_of_week"] != day_of_week:
            continue
        if start_time < slot["end_time"] and end_time > slot["start_time"]:
            conflicts.append(slot)
    return conflicts


def _parse_day_of_week(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw:
        raise TimetableImportError("day_of_week is required")
    if raw.isdigit():
        value = int(raw)
        if not (0 <= value <= 6):
            raise TimetableImportError(f"day_of_week must be 0-6, got {value}")
        return value
    try:
        return DAYS.index(raw.capitalize())
    except ValueError:
        raise TimetableImportError(
            f"day_of_week '{raw}' is not a valid day name (Monday-Sunday) or number (0-6)"
        )


def bulk_import_csv(csv_path: str):
    """CSV columns: department,year,semester,subject,section,faculty,day_of_week,start_time,end_time
    day_of_week accepts either a day name (Monday..Sunday) or a number (0=Monday..6=Sunday).
    start_time/end_time must be HH:MM. Returns (success_count, list_of_error_strings).
    Continues past per-row failures, same as student CSV import."""
    errors = []
    success_count = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row_num, row in enumerate(rows, start=2):
        subject = (row.get("subject") or "").strip()
        start_time = (row.get("start_time") or "").strip()
        end_time = (row.get("end_time") or "").strip()

        if not subject or not start_time or not end_time:
            errors.append(f"Row {row_num}: missing subject/start_time/end_time")
            continue

        try:
            day_of_week = _parse_day_of_week(row.get("day_of_week"))
        except TimetableImportError as e:
            errors.append(f"Row {row_num} ({subject}): {e}")
            continue

        department = (row.get("department") or "").strip() or None
        section = (row.get("section") or "").strip() or None
        faculty = (row.get("faculty") or "").strip() or None
        year_raw = (row.get("year") or "").strip()
        semester_raw = (row.get("semester") or "").strip()

        try:
            year = int(year_raw) if year_raw else None
            semester = int(semester_raw) if semester_raw else None
        except ValueError:
            errors.append(f"Row {row_num} ({subject}): year/semester must be numeric")
            continue

        queries.insert_timetable_slot(department, year, semester, subject, section,
                                       faculty, day_of_week, start_time, end_time)
        success_count += 1

    return success_count, errors


def export_csv(csv_path: str):
    """Writes every timetable slot to CSV in the same column layout bulk_import_csv reads,
    so an exported file can be re-imported unchanged (e.g. edit in Excel, re-upload)."""
    slots = queries.list_all_timetable_slots()
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["department", "year", "semester", "subject", "section", "faculty",
                          "day_of_week", "start_time", "end_time"])
        for s in slots:
            writer.writerow([
                s["department"] or "", s["year"] or "", s["semester"] or "", s["subject"],
                s["section"] or "", s["faculty"] or "", DAYS[s["day_of_week"]],
                s["start_time"], s["end_time"],
            ])
    return len(slots)
