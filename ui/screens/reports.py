from datetime import date, timedelta
from tkinter import filedialog, messagebox

import customtkinter as ctk

import config
from config import DEFAULTER_THRESHOLD
from db import queries
from services import dashboard, notifications, pdf_report, report
from ui.components.chart_embed import ChartEmbed
from ui.components.student_table import StudentTable
from ui.components.toast import show_toast


class ReportsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._sort_col = None
        self._sort_reverse = False
        self._current_rows = []

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Reports & Dashboard", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=10)
        self.tabs.add("Records")
        self.tabs.add("Defaulters")
        self.tabs.add("Dashboard")

        self._build_records_tab(self.tabs.tab("Records"))
        self._build_defaulters_tab(self.tabs.tab("Defaulters"))
        self._build_dashboard_tab(self.tabs.tab("Dashboard"))

    # ---------- Records tab ----------

    def _build_records_tab(self, parent):
        filter_bar = ctk.CTkFrame(parent, fg_color="transparent")
        filter_bar.pack(fill="x", pady=10)

        ctk.CTkLabel(filter_bar, text="Branch").pack(side="left", padx=5)
        self.branch_filter = ctk.CTkOptionMenu(filter_bar, values=["All"], width=110, command=lambda _: self._apply_filters())
        self.branch_filter.pack(side="left", padx=5)

        ctk.CTkLabel(filter_bar, text="Subject").pack(side="left", padx=5)
        self.subject_filter = ctk.CTkEntry(filter_bar, width=100)
        self.subject_filter.pack(side="left", padx=5)

        ctk.CTkLabel(filter_bar, text="Section").pack(side="left", padx=5)
        self.section_filter = ctk.CTkEntry(filter_bar, width=100)
        self.section_filter.pack(side="left", padx=5)

        ctk.CTkLabel(filter_bar, text="Start").pack(side="left", padx=5)
        self.start_date_filter = ctk.CTkEntry(filter_bar, width=100, placeholder_text="YYYY-MM-DD")
        self.start_date_filter.pack(side="left", padx=5)

        ctk.CTkLabel(filter_bar, text="End").pack(side="left", padx=5)
        self.end_date_filter = ctk.CTkEntry(filter_bar, width=100, placeholder_text="YYYY-MM-DD")
        self.end_date_filter.pack(side="left", padx=5)

        ctk.CTkButton(filter_bar, text="Apply", width=70, command=self._apply_filters).pack(side="left", padx=10)
        ctk.CTkButton(filter_bar, text="Export PDF", width=110, command=self._export_pdf).pack(side="right", padx=5)
        ctk.CTkButton(filter_bar, text="Export Excel", width=110, command=self._export_excel).pack(side="right", padx=5)

        quick_bar = ctk.CTkFrame(parent, fg_color="transparent")
        quick_bar.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(quick_bar, text="Quick range:").pack(side="left", padx=5)
        ctk.CTkButton(quick_bar, text="Today", width=70, command=lambda: self._quick_range(0)).pack(side="left", padx=5)
        ctk.CTkButton(quick_bar, text="This Week", width=90, command=lambda: self._quick_range(7)).pack(side="left", padx=5)
        ctk.CTkButton(quick_bar, text="This Month", width=90, command=lambda: self._quick_range(30)).pack(side="left", padx=5)
        ctk.CTkButton(quick_bar, text="All Time", width=80, command=self._clear_range).pack(side="left", padx=5)

        self.table = StudentTable(parent, headers=["Roll No", "Name", "Subject", "Date", "Status"], on_sort=self._sort_records)
        self.table.pack(fill="both", expand=True, padx=10, pady=10)

    def _quick_range(self, days_back: int):
        self.start_date_filter.delete(0, "end")
        self.end_date_filter.delete(0, "end")
        today = date.today()
        start = today - timedelta(days=days_back)
        self.start_date_filter.insert(0, start.isoformat())
        self.end_date_filter.insert(0, today.isoformat())
        self._apply_filters()

    def _clear_range(self):
        self.start_date_filter.delete(0, "end")
        self.end_date_filter.delete(0, "end")
        self._apply_filters()

    def _refresh_branch_options(self):
        branches = ["All"] + queries.get_distinct_departments()
        self.branch_filter.configure(values=branches)
        if self.branch_filter.get() not in branches:
            self.branch_filter.set("All")

    def _get_branch_filter(self):
        selected = self.branch_filter.get()
        return None if selected in (None, "All") else selected

    def _apply_filters(self):
        self._refresh_branch_options()
        subject = self.subject_filter.get().strip() or None
        section = self.section_filter.get().strip() or None
        start_date = self.start_date_filter.get().strip() or None
        end_date = self.end_date_filter.get().strip() or None
        department = self._get_branch_filter()

        rows = queries.get_filtered_attendance(subject, section, start_date, end_date, department)
        self._current_rows = [
            (row["roll_no"] or "--", row["name"] or "Unknown", row["subject"],
             (row["started_at"] or "").split(" ")[0], row["status"])
            for row in rows
        ]
        self._render_records()

    def _sort_records(self, col_idx: int):
        if self._sort_col == col_idx:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col_idx
            self._sort_reverse = False
        self._render_records()

    def _render_records(self):
        rows = self._current_rows
        if self._sort_col is not None:
            rows = sorted(rows, key=lambda r: str(r[self._sort_col]), reverse=self._sort_reverse)
        self.table.set_rows(rows)

    def _export_excel(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not filepath:
            return
        try:
            subject = self.subject_filter.get().strip() or None
            section = self.section_filter.get().strip() or None
            start_date = self.start_date_filter.get().strip() or None
            end_date = self.end_date_filter.get().strip() or None
            department = self._get_branch_filter()
            report.export_excel(filepath, subject, section, start_date, end_date, department)
            show_toast(self, f"Saved to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _export_pdf(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not filepath:
            return
        try:
            subject = self.subject_filter.get().strip() or None
            section = self.section_filter.get().strip() or None
            start_date = self.start_date_filter.get().strip() or None
            end_date = self.end_date_filter.get().strip() or None
            department = self._get_branch_filter()
            pdf_report.export_pdf(filepath, subject, section, start_date, end_date, department=department)
            show_toast(self, f"Saved to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ---------- Defaulters tab ----------

    def _build_defaulters_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=10)
        ctk.CTkLabel(top, text=f"Students below {DEFAULTER_THRESHOLD:.0f}% attendance").pack(side="left", padx=10)
        ctk.CTkButton(top, text="Refresh", width=80, command=self._refresh_defaulters).pack(side="right", padx=10)

        self.defaulters_table = StudentTable(
            parent, headers=["Roll No", "Name", "Present", "Total Sessions", "Attendance %"],
            on_row_click=self._show_student_detail,
        )
        self.defaulters_table.pack(fill="both", expand=True, padx=10, pady=10)

    def _refresh_defaulters(self):
        defaulters = queries.get_defaulters(DEFAULTER_THRESHOLD)
        self._defaulter_ids = [d["id"] for d in defaulters]
        rows = [(d["roll_no"], d["name"], d["present"], d["total"], f"{d['percentage']:.1f}%") for d in defaulters]
        self.defaulters_table.set_rows(rows)
        if config.NOTIFY_DEFAULTER_CHECK:
            notifications.check_and_notify_defaulters(DEFAULTER_THRESHOLD)

    def _show_student_detail(self, row_idx: int):
        if row_idx >= len(self._defaulter_ids):
            return
        student_id = self._defaulter_ids[row_idx]
        student = queries.get_student(student_id)
        history = queries.get_student_history(student_id)

        popup = ctk.CTkToplevel(self)
        popup.title(f"Attendance History — {student['name']}")
        popup.geometry("520x480")

        ctk.CTkLabel(popup, text=f"{student['name']} ({student['roll_no']})", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        history_table = StudentTable(popup, headers=["Subject", "Section", "Date", "Status"])
        history_table.pack(fill="both", expand=True, padx=10, pady=10)
        rows = [(h["subject"], h["section"] or "--", (h["started_at"] or "").split(" ")[0], h["status"]) for h in history]
        history_table.set_rows(rows)

    # ---------- Dashboard tab ----------

    def _build_dashboard_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(top, text="Branch:").pack(side="left", padx=5)
        self.dashboard_branch = ctk.CTkOptionMenu(top, values=["All"], command=lambda _: self._refresh_dashboard())
        self.dashboard_branch.pack(side="left", padx=5)

        ctk.CTkLabel(top, text="Subject filter:").pack(side="left", padx=5)
        self.dashboard_subject = ctk.CTkOptionMenu(top, values=["All"], command=lambda _: self._refresh_dashboard())
        self.dashboard_subject.pack(side="left", padx=5)

        ctk.CTkButton(top, text="Refresh Charts", command=self._refresh_dashboard).pack(side="right", padx=5)
        ctk.CTkButton(top, text="Export PNG", command=self._export_png).pack(side="right", padx=5)
        ctk.CTkButton(top, text="Export PDF", command=self._export_dashboard_pdf).pack(side="right", padx=5)

        self.today_card = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(weight="bold"))
        self.today_card.pack(padx=10, pady=(0, 5), anchor="w")

        self.dashboard_subtabs = ctk.CTkTabview(parent)
        self.dashboard_subtabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_subtabs.add("Overview")
        self.dashboard_subtabs.add("Advanced Analytics")

        self.chart_embed = ChartEmbed(self.dashboard_subtabs.tab("Overview"))
        self.chart_embed.pack(fill="both", expand=True)

        self.advanced_chart_embed = ChartEmbed(self.dashboard_subtabs.tab("Advanced Analytics"))
        self.advanced_chart_embed.pack(fill="both", expand=True)

    def _refresh_dashboard(self):
        subjects = ["All"] + queries.get_distinct_subjects()
        self.dashboard_subject.configure(values=subjects)
        if self.dashboard_subject.get() not in subjects:
            self.dashboard_subject.set("All")

        branches = ["All"] + queries.get_distinct_departments()
        self.dashboard_branch.configure(values=branches)
        if self.dashboard_branch.get() not in branches:
            self.dashboard_branch.set("All")

        subject_filter = None if self.dashboard_subject.get() == "All" else self.dashboard_subject.get()
        department_filter = None if self.dashboard_branch.get() == "All" else self.dashboard_branch.get()

        today = queries.get_today_summary()
        overall = queries.get_overall_average()
        self.today_card.configure(
            text=f"Today: {today['present']}/{today['total']} present ({today['percentage']:.1f}%)   |   Overall average: {overall:.1f}%"
        )

        self.chart_embed.show_figure(dashboard.render_charts(subject_filter, department_filter))
        self.advanced_chart_embed.show_figure(dashboard.render_advanced_charts(subject_filter, department_filter))

    def _export_png(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if not filepath:
            return
        try:
            subject_filter = None if self.dashboard_subject.get() == "All" else self.dashboard_subject.get()
            department_filter = None if self.dashboard_branch.get() == "All" else self.dashboard_branch.get()
            dashboard.export_png(filepath, subject_filter, department_filter)
            show_toast(self, f"Saved to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _export_dashboard_pdf(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not filepath:
            return
        try:
            subject_filter = None if self.dashboard_subject.get() == "All" else self.dashboard_subject.get()
            department_filter = None if self.dashboard_branch.get() == "All" else self.dashboard_branch.get()
            pdf_report.export_dashboard_pdf(filepath, subject_filter, department_filter)
            show_toast(self, f"Saved to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def on_show(self):
        self._apply_filters()
        self._refresh_defaulters()
        self._refresh_dashboard()
