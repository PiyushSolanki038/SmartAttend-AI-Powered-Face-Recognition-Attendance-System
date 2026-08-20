from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from config import DEFAULTER_THRESHOLD, LATE_THRESHOLD_MINUTES
from db import queries


def _attendance_by_student(subject_filter: str = None, department_filter: str = None):
    rows = queries.get_filtered_attendance(subject=subject_filter, department=department_filter)
    totals = defaultdict(lambda: [0, 0])  # name -> [present, total]
    for row in rows:
        if row["name"] is None:
            continue
        totals[row["name"]][1] += 1
        if row["status"] == "present":
            totals[row["name"]][0] += 1
    return {name: (present / total * 100 if total else 0) for name, (present, total) in totals.items()}


def _attendance_by_date(subject_filter: str = None, department_filter: str = None):
    rows = queries.get_filtered_attendance(subject=subject_filter, department=department_filter)
    totals = defaultdict(lambda: [0, 0])  # date -> [present, total]
    for row in rows:
        started_at = row["started_at"]
        date_part = started_at.strftime("%Y-%m-%d") if started_at else ""
        if not date_part:
            continue
        totals[date_part][1] += 1
        if row["status"] == "present":
            totals[date_part][0] += 1
    dates = sorted(totals.keys())
    return dates, [totals[d][0] / totals[d][1] * 100 if totals[d][1] else 0 for d in dates]


def _attendance_by_subject(department_filter: str = None):
    rows = queries.get_filtered_attendance(department=department_filter)
    totals = defaultdict(lambda: [0, 0])  # subject -> [present, total]
    for row in rows:
        totals[row["subject"]][1] += 1
        if row["status"] == "present":
            totals[row["subject"]][0] += 1
    subjects = sorted(totals.keys())
    return subjects, [totals[s][0] / totals[s][1] * 100 if totals[s][1] else 0 for s in subjects]


def render_charts(subject_filter: str = None, department_filter: str = None):
    """Returns a matplotlib Figure with 4 subplots: per-student %, trend over time,
    subject comparison, and defaulters below the configured threshold."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    title_suffix = " — ".join(f for f in (subject_filter, department_filter) if f)
    fig.suptitle("SmartAttend Dashboard" + (f" — {title_suffix}" if title_suffix else ""))

    student_pct = _attendance_by_student(subject_filter, department_filter)
    names = list(student_pct.keys())
    values = list(student_pct.values())
    axes[0][0].barh(names, values, color="#1F6AA5")
    axes[0][0].set_title("Attendance % per Student")
    axes[0][0].set_xlabel("Attendance %")

    dates, date_values = _attendance_by_date(subject_filter, department_filter)
    axes[0][1].plot(dates, date_values, marker="o", color="#2ECC71")
    axes[0][1].set_title("Class Trend Over Time")
    axes[0][1].set_ylabel("% Present")
    axes[0][1].tick_params(axis="x", rotation=45)

    subjects, subject_values = _attendance_by_subject(department_filter)
    axes[1][0].bar(subjects, subject_values, color="#F39C12")
    axes[1][0].set_title("Subject-wise Comparison")
    axes[1][0].set_ylabel("% Present")

    defaulters = queries.get_defaulters(DEFAULTER_THRESHOLD, subject_filter)
    if department_filter:
        defaulters = [d for d in defaulters if queries.get_student(d["id"])["department"] == department_filter]
    def_names = [d["name"] for d in defaulters]
    def_values = [d["percentage"] for d in defaulters]
    axes[1][1].barh(def_names, def_values, color="#E74C3C")
    axes[1][1].set_title(f"Defaulters (< {DEFAULTER_THRESHOLD:.0f}%)")
    axes[1][1].set_xlabel("Attendance %")
    if not def_names:
        axes[1][1].text(0.5, 0.5, "No defaulters", ha="center", va="center", transform=axes[1][1].transAxes)

    fig.tight_layout()
    return fig


def export_png(filepath: str, subject_filter: str = None, department_filter: str = None):
    fig = render_charts(subject_filter, department_filter)
    fig.savefig(filepath)
    plt.close(fig)
    return filepath


_STATUS_VALUE = {"present": 2, "manual": 2, "unknown": 1, "absent": 0}


def _build_attendance_matrix(subject_filter: str = None, department_filter: str = None):
    rows = queries.get_attendance_matrix(subject_filter, department_filter)
    names = sorted({r["name"] for r in rows})
    dates = sorted({r["session_date"] for r in rows})
    name_idx = {n: i for i, n in enumerate(names)}
    date_idx = {d: i for i, d in enumerate(dates)}
    matrix = np.full((len(names), len(dates)), np.nan)
    for r in rows:
        matrix[name_idx[r["name"]], date_idx[r["session_date"]]] = _STATUS_VALUE.get(r["status"], np.nan)
    return names, dates, matrix


def render_advanced_charts(subject_filter: str = None, department_filter: str = None):
    """Returns a Figure with: attendance heatmap (student x date), late-arrival ranking,
    and subject-wise trend over time."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    title_suffix = " — ".join(f for f in (subject_filter, department_filter) if f)
    fig.suptitle("Advanced Analytics" + (f" — {title_suffix}" if title_suffix else ""))

    names, dates, matrix = _build_attendance_matrix(subject_filter, department_filter)
    ax = axes[0]
    if matrix.size:
        mesh = ax.pcolormesh(matrix, cmap="RdYlGn", vmin=0, vmax=2)
        ax.set_yticks(np.arange(len(names)) + 0.5)
        ax.set_yticklabels(names, fontsize=7)
        ax.set_xticks(np.arange(len(dates)) + 0.5)
        ax.set_xticklabels(dates, rotation=45, fontsize=7, ha="right")
        fig.colorbar(mesh, ax=ax, label="0=Absent 1=Unknown 2=Present")
    else:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("Attendance Heatmap")

    late_rows = queries.get_late_arrivals(threshold_minutes=LATE_THRESHOLD_MINUTES)
    if subject_filter:
        late_rows = [r for r in late_rows if r["subject"] == subject_filter]
    if department_filter:
        dept_names = {s["name"] for s in queries.list_students() if s["department"] == department_filter}
        late_rows = [r for r in late_rows if r["name"] in dept_names]
    late_counts = defaultdict(int)
    for r in late_rows:
        late_counts[r["name"]] += 1
    top_late = sorted(late_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ax = axes[1]
    if top_late:
        ax.barh([n for n, _ in top_late], [c for _, c in top_late], color="#E67E22")
    else:
        ax.text(0.5, 0.5, "No late arrivals", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(f"Late Arrivals (> {LATE_THRESHOLD_MINUTES} min)")
    ax.set_xlabel("Times late")

    ax = axes[2]
    rows = queries.get_filtered_attendance(subject=subject_filter, department=department_filter)
    by_subject_date = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for row in rows:
        started_at = row["started_at"]
        date_part = started_at.strftime("%Y-%m-%d") if started_at else ""
        if not date_part:
            continue
        bucket = by_subject_date[row["subject"]][date_part]
        bucket[1] += 1
        if row["status"] == "present":
            bucket[0] += 1
    for subject, date_map in sorted(by_subject_date.items()):
        dates_sorted = sorted(date_map.keys())
        pct = [date_map[d][0] / date_map[d][1] * 100 if date_map[d][1] else 0 for d in dates_sorted]
        ax.plot(dates_sorted, pct, marker="o", label=subject)
    ax.set_title("Subject-wise Trend Over Time")
    ax.set_ylabel("% Present")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    if by_subject_date:
        ax.legend(fontsize=7)

    fig.tight_layout()
    return fig


def export_advanced_png(filepath: str, subject_filter: str = None, department_filter: str = None):
    fig = render_advanced_charts(subject_filter, department_filter)
    fig.savefig(filepath)
    plt.close(fig)
    return filepath


def render_student_charts(student_id: int):
    """Returns a Figure with two subplots scoped to a single student, for the portal's
    Analytics page: their per-subject attendance % (bar) and their attendance trend over
    time across all subjects (line) — the richer chart quality the desktop dashboard has,
    made available to the student instead of only plain numbers."""
    subjects = queries.get_student_subject_summary(student_id)
    history = queries.get_student_history(student_id)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    names = [s["subject"] for s in subjects]
    values = [s["percentage"] for s in subjects]
    colors = ["#E74C3C" if v < DEFAULTER_THRESHOLD else "#1F6AA5" for v in values]
    axes[0].bar(names, values, color=colors or "#1F6AA5")
    axes[0].axhline(DEFAULTER_THRESHOLD, color="#F39C12", linestyle="--", linewidth=1,
                     label=f"{DEFAULTER_THRESHOLD:.0f}% threshold")
    axes[0].set_title("Your Attendance by Subject")
    axes[0].set_ylabel("% Present")
    axes[0].set_ylim(0, 100)
    axes[0].tick_params(axis="x", rotation=30, labelsize=8)
    axes[0].legend(fontsize=7)

    # Trend: cumulative present-rate after each session, oldest to newest.
    ordered = list(reversed(history))
    running_present, running_total, trend = 0, 0, []
    for row in ordered:
        running_total += 1
        if row["status"] in ("present", "manual"):
            running_present += 1
        trend.append(running_present / running_total * 100)
    axes[1].plot(range(1, len(trend) + 1), trend, marker="o", markersize=3, color="#2ECC71")
    axes[1].set_title("Your Attendance Trend")
    axes[1].set_xlabel("Session # (oldest to newest)")
    axes[1].set_ylabel("Cumulative % Present")
    axes[1].set_ylim(0, 100)
    if not trend:
        axes[1].text(0.5, 0.5, "No sessions yet", ha="center", va="center", transform=axes[1].transAxes)

    fig.tight_layout()
    return fig


def render_student_charts_base64(student_id: int) -> str:
    """Same as render_student_charts but returns a base64 PNG data URI, ready to drop
    straight into an <img src="..."> tag in the portal — avoids needing a static file
    per student or a second network round-trip."""
    import base64
    from io import BytesIO

    fig = render_student_charts(student_id)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")
