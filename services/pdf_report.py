import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import matplotlib.pyplot as plt

from config import EXCEL_HEADERS
from db import queries
from services import dashboard

STATUS_COLOR = {
    "present": colors.HexColor("#C6EFCE"),
    "absent": colors.HexColor("#FFC7CE"),
    "unknown": colors.HexColor("#FFEB9C"),
    "manual": colors.HexColor("#FFEB9C"),
}


def export_pdf(filepath: str, subject: str = None, section: str = None,
                start_date: str = None, end_date: str = None, include_charts: bool = True,
                department: str = None):
    rows = queries.get_filtered_attendance(subject, section, start_date, end_date, department)

    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("SmartAttend Attendance Report", styles["Title"]),
        Paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
        Paragraph(f"Subject: {subject or 'All'} | Section: {section or 'All'}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data = [EXCEL_HEADERS]
    row_colors = [None]
    present_count = absent_count = total_count = 0
    for row in rows:
        started = row["started_at"] or ""
        date_part = started.split(" ")[0] if started else ""
        time_part = started.split(" ")[1] if " " in started else ""
        status = row["status"] or ""
        table_data.append([
            row["roll_no"] or "--", row["name"] or "Unknown", row["department"] or "--",
            date_part, time_part, status, f"{row['confidence']:.3f}" if row["confidence"] is not None else "--",
        ])
        row_colors.append(STATUS_COLOR.get(status))
        total_count += 1
        if status == "present":
            present_count += 1
        elif status == "absent":
            absent_count += 1

    table = Table(table_data, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F6AA5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]
    for idx, color in enumerate(row_colors):
        if color:
            style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), color))
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    attendance_pct = (present_count / total_count * 100) if total_count else 0
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"<b>Total:</b> {total_count} | <b>Present:</b> {present_count} | "
        f"<b>Absent:</b> {absent_count} | <b>Attendance %:</b> {attendance_pct:.1f}%",
        styles["Normal"],
    ))

    if include_charts:
        fig = dashboard.render_charts(subject)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)
        elements.append(Spacer(1, 16))
        elements.append(Image(buf, width=480, height=384))

    doc.build(elements)
    return filepath


def export_dashboard_pdf(filepath: str, subject_filter: str = None, department_filter: str = None):
    """Charts-only PDF report (standard + advanced analytics), landscape for wider charts."""
    doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    elements = [Paragraph("SmartAttend Dashboard Export", styles["Title"]), Spacer(1, 10)]

    for fig in (dashboard.render_charts(subject_filter, department_filter),
                dashboard.render_advanced_charts(subject_filter, department_filter)):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)
        elements.append(Image(buf, width=700, height=350))
        elements.append(Spacer(1, 16))

    doc.build(elements)
    return filepath
