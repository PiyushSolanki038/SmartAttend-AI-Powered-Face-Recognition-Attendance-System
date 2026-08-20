"""Admin-only audit log viewer: filterable by actor/entity_type, plus a read-only view
of the existing auth_logs table (login/logout history)."""

import customtkinter as ctk

from db import queries
from services import audit
from ui.components.student_table import StudentTable


class AuditLogScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Audit Log", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="Refresh", width=90, command=self._refresh).pack(side="right")

        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(filter_bar, text="Entity type").pack(side="left", padx=(0, 5))
        self.entity_entry = ctk.CTkEntry(filter_bar, width=160, placeholder_text="e.g. dispute_request")
        self.entity_entry.pack(side="left", padx=5)
        ctk.CTkButton(filter_bar, text="Apply Filter", command=self._refresh).pack(side="left", padx=5)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=10)
        self.tabs.add("Audit Trail")
        self.tabs.add("Login History")

        self.audit_table = StudentTable(
            self.tabs.tab("Audit Trail"),
            headers=["Time", "Actor", "Action", "Entity Type", "Entity ID", "Details"], height=340,
        )
        self.audit_table.pack(fill="both", expand=True, padx=10, pady=10)

        self.auth_table = StudentTable(
            self.tabs.tab("Login History"),
            headers=["Time", "Username", "Event"], height=340,
        )
        self.auth_table.pack(fill="both", expand=True, padx=10, pady=10)

    def on_show(self):
        self._refresh()

    def _refresh(self):
        entity_type = self.entity_entry.get().strip() or None
        rows = audit.list_audit_log(entity_type=entity_type)
        self.audit_table.set_rows([
            (r["created_at"], r["actor_user_id"] or "system", r["action"], r["entity_type"],
             r["entity_id"] or "--", r["details"] or "--")
            for r in rows
        ])
        auth_rows = queries.get_auth_logs(limit=200)
        self.auth_table.set_rows([(r["occurred_at"], r["username"], r["event"]) for r in auth_rows])
