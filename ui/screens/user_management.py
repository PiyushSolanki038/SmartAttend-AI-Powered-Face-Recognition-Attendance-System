from tkinter import messagebox

import customtkinter as ctk

from db import queries
from services import auth
from ui.components.student_table import StudentTable
from ui.components.toast import show_toast


class UserManagementScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Manage Users", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        form = ctk.CTkFrame(self)
        form.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(form, text="Username").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        self.username_entry = ctk.CTkEntry(form, width=160)
        self.username_entry.grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(form, text="Full Name").grid(row=0, column=2, padx=8, pady=8, sticky="e")
        self.fullname_entry = ctk.CTkEntry(form, width=160)
        self.fullname_entry.grid(row=0, column=3, padx=8, pady=8)

        ctk.CTkLabel(form, text="Password").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        self.password_entry = ctk.CTkEntry(form, width=160, show="*")
        self.password_entry.grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(form, text="Role").grid(row=1, column=2, padx=8, pady=8, sticky="e")
        self.role_dropdown = ctk.CTkOptionMenu(form, values=["faculty", "admin"])
        self.role_dropdown.grid(row=1, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkButton(form, text="Create User", command=self._create_user).grid(row=0, column=4, rowspan=2, padx=12, pady=8)

        self.table = StudentTable(
            self, headers=["ID", "Username", "Role", "Full Name", "Active"],
            on_row_click=self._on_row_click, height=240,
        )
        self.table.pack(fill="both", expand=True, padx=20, pady=10)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 20))
        self.selected_label = ctk.CTkLabel(actions, text="No user selected")
        self.selected_label.pack(side="left")
        ctk.CTkButton(actions, text="Toggle Active", command=self._toggle_active).pack(side="right", padx=5)
        ctk.CTkButton(actions, text="Delete", fg_color="#E74C3C", hover_color="#C0392B", command=self._delete_user).pack(side="right", padx=5)

        self._users = []
        self._selected_user_id = None

    def on_show(self):
        self._refresh()

    def _refresh(self):
        self._users = queries.list_users()
        rows = [
            (u["id"], u["username"], u["role"], u["full_name"] or "--", "Yes" if u["is_active"] else "No")
            for u in self._users
        ]
        self.table.set_rows(rows)

    def _on_row_click(self, idx):
        user = self._users[idx]
        self._selected_user_id = user["id"]
        self.selected_label.configure(text=f"Selected: {user['username']} ({user['role']})")

    def _create_user(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        full_name = self.fullname_entry.get().strip()
        role = self.role_dropdown.get()
        if not username or not password:
            messagebox.showerror("Missing Field", "Username and password are required.")
            return
        if queries.get_user_by_username(username):
            messagebox.showerror("Duplicate", "That username already exists.")
            return
        auth.create_user(username, password, role, full_name or None)
        self.username_entry.delete(0, "end")
        self.password_entry.delete(0, "end")
        self.fullname_entry.delete(0, "end")
        show_toast(self, f"User '{username}' created", "success")
        self._refresh()

    def _toggle_active(self):
        if self._selected_user_id is None:
            show_toast(self, "Select a user first", "warning")
            return
        user = next((u for u in self._users if u["id"] == self._selected_user_id), None)
        if user is None:
            return
        if self._selected_user_id == self.app.current_user["id"] and user["is_active"]:
            messagebox.showerror("Not Allowed", "You cannot deactivate your own active account.")
            return
        queries.set_user_active(self._selected_user_id, not user["is_active"])
        self._refresh()

    def _delete_user(self):
        if self._selected_user_id is None:
            show_toast(self, "Select a user first", "warning")
            return
        if self._selected_user_id == self.app.current_user["id"]:
            messagebox.showerror("Not Allowed", "You cannot delete your own account.")
            return
        if not messagebox.askyesno("Confirm Delete", "Delete this user account? This cannot be undone."):
            return
        queries.delete_user(self._selected_user_id)
        self._selected_user_id = None
        self.selected_label.configure(text="No user selected")
        self._refresh()
