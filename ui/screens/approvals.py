from tkinter import messagebox

import customtkinter as ctk

from db import queries
from services import leave_requests as leave_service
from services import requests as request_service
from ui.components.student_table import StudentTable
from ui.components.toast import show_toast

_KIND_LABELS = {"dispute": "Dispute", "checkin": "Check-in", "rescan": "Re-scan", "leave": "Leave"}


class RequestList(ctk.CTkScrollableFrame):
    """Scrollable list of pending requests, each row ending in its own Approve/Reject
    buttons — no select-then-click-a-shared-button step needed."""

    def __init__(self, master, headers: list, on_resolve, **kwargs):
        super().__init__(master, **kwargs)
        self._headers = headers
        self._on_resolve = on_resolve
        self._row_widgets = []
        self._render_headers()

    def _render_headers(self):
        for col_idx, header in enumerate(self._headers):
            ctk.CTkLabel(self, text=header, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=col_idx, padx=8, pady=4, sticky="w"
            )
        ctk.CTkLabel(self, text="Actions", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=len(self._headers), padx=8, pady=4, sticky="w"
        )

    def set_rows(self, rows: list):
        """rows: list of (request_id, *display_values) tuples, one per pending request."""
        for widget in self._row_widgets:
            widget.destroy()
        self._row_widgets = []

        if not rows:
            empty = ctk.CTkLabel(self, text="Nothing pending.", text_color="gray")
            empty.grid(row=1, column=0, columnspan=len(self._headers) + 1, padx=8, pady=14, sticky="w")
            self._row_widgets.append(empty)
            return

        for row_idx, row in enumerate(rows, start=1):
            request_id, *values = row
            for col_idx, value in enumerate(values):
                label = ctk.CTkLabel(self, text=str(value))
                label.grid(row=row_idx, column=col_idx, padx=8, pady=4, sticky="w")
                self._row_widgets.append(label)

            actions = ctk.CTkFrame(self, fg_color="transparent")
            actions.grid(row=row_idx, column=len(values), padx=8, pady=4, sticky="w")
            ctk.CTkButton(
                actions, text="Approve", width=70, fg_color="#2ECC71", hover_color="#27AE60",
                command=lambda rid=request_id: self._on_resolve(rid, True),
            ).pack(side="left", padx=(0, 4))
            ctk.CTkButton(
                actions, text="Reject", width=70, fg_color="#E74C3C", hover_color="#C0392B",
                command=lambda rid=request_id: self._on_resolve(rid, False),
            ).pack(side="left")
            self._row_widgets.append(actions)


class ApprovalsScreen(ctk.CTkFrame):
    """Lets faculty/admin review student-submitted requests: attendance disputes,
    manual check-in requests (camera/lighting failures), and face re-scan requests.
    Each request row has its own Approve/Reject buttons for one-click resolution."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Student Requests", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="Refresh", width=90, command=self._refresh).pack(side="right")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=10)
        self.tabs.add("Disputes")
        self.tabs.add("Check-in Requests")
        self.tabs.add("Re-scan Requests")
        self.tabs.add("Leave Requests")
        self.tabs.add("History")

        self.dispute_list = RequestList(
            self.tabs.tab("Disputes"), headers=["Roll No", "Name", "Subject", "Date", "Reason"],
            on_resolve=self._resolve_dispute, height=320,
        )
        self.dispute_list.pack(fill="both", expand=True, padx=10, pady=10)

        self.checkin_list = RequestList(
            self.tabs.tab("Check-in Requests"), headers=["Roll No", "Name", "Subject", "Started", "Reason"],
            on_resolve=self._resolve_checkin, height=320,
        )
        self.checkin_list.pack(fill="both", expand=True, padx=10, pady=10)

        self.rescan_list = RequestList(
            self.tabs.tab("Re-scan Requests"), headers=["Roll No", "Name", "Reason"],
            on_resolve=self._resolve_rescan, height=320,
        )
        self.rescan_list.pack(fill="both", expand=True, padx=10, pady=10)

        self.leave_list = RequestList(
            self.tabs.tab("Leave Requests"), headers=["Roll No", "Name", "Start", "End", "Reason"],
            on_resolve=self._resolve_leave, height=320,
        )
        self.leave_list.pack(fill="both", expand=True, padx=10, pady=10)

        history_tab = self.tabs.tab("History")
        top = ctk.CTkFrame(history_tab, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(top, text="Recently resolved requests (approved/rejected)").pack(side="left")
        self.history_table = StudentTable(
            history_tab, headers=["Type", "Roll No", "Name", "Reason", "Status", "Resolved At"], height=320,
        )
        self.history_table.pack(fill="both", expand=True, padx=10, pady=10)

    def on_show(self):
        self._refresh()

    def _refresh(self):
        disputes = queries.list_pending_disputes()
        self.dispute_list.set_rows([
            (d["id"], d["roll_no"], d["name"], d["subject"] or "General", d["started_at"], d["reason"])
            for d in disputes
        ])
        checkins = queries.list_pending_checkin_requests()
        self.checkin_list.set_rows([
            (c["id"], c["roll_no"], c["name"], c["subject"] or "General", c["started_at"], c["reason"])
            for c in checkins
        ])
        rescans = queries.list_pending_rescan_requests()
        self.rescan_list.set_rows([
            (r["id"], r["roll_no"], r["name"], r["reason"]) for r in rescans
        ])
        leaves = queries.list_pending_leave_requests()
        self.leave_list.set_rows([
            (l["id"], l["roll_no"], l["name"], l["start_date"], l["end_date"], l["reason"]) for l in leaves
        ])

        history = queries.list_resolved_requests()
        self.history_table.set_rows([
            (_KIND_LABELS.get(h["kind"], h["kind"]), h["roll_no"], h["name"], h["reason"], h["status"], h["resolved_at"])
            for h in history
        ])

    def _resolve_dispute(self, dispute_id: int, approve: bool):
        try:
            request_service.resolve_dispute(dispute_id, approve, self.app.current_user["id"])
        except request_service.RequestError as e:
            messagebox.showerror("Error", str(e))
            return
        show_toast(self, f"Dispute {'approved' if approve else 'rejected'}", "success")
        self._refresh()

    def _resolve_checkin(self, request_id: int, approve: bool):
        try:
            request_service.resolve_checkin_request(request_id, approve, self.app.current_user["id"])
        except request_service.RequestError as e:
            messagebox.showerror("Error", str(e))
            return
        show_toast(self, f"Check-in request {'approved' if approve else 'rejected'}", "success")
        self._refresh()

    def _resolve_rescan(self, request_id: int, approve: bool):
        try:
            request_service.resolve_rescan_request(request_id, approve, self.app.current_user["id"])
        except request_service.RequestError as e:
            messagebox.showerror("Error", str(e))
            return
        if approve:
            messagebox.showinfo("Approved", "Now go to Enroll Student and re-scan this student's photos.")
        show_toast(self, f"Re-scan request {'approved' if approve else 'rejected'}", "success")
        self._refresh()

    def _resolve_leave(self, request_id: int, approve: bool):
        try:
            leave_service.resolve_leave_request(request_id, approve, self.app.current_user["id"])
        except leave_service.LeaveRequestError as e:
            messagebox.showerror("Error", str(e))
            return
        show_toast(self, f"Leave request {'approved' if approve else 'rejected'}", "success")
        self._refresh()
