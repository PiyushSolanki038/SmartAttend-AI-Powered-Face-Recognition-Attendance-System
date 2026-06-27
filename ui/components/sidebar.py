import customtkinter as ctk

NAV_ITEMS = [
    ("Home", "HomeScreen", None),
    ("Enroll Student", "EnrollScreen", None),
    ("Live Attendance", "SessionScreen", None),
    ("Reports", "ReportsScreen", None),
    ("Manage Users", "UserManagementScreen", "admin"),
    ("Settings", "SettingsScreen", None),
]


class Sidebar(ctk.CTkFrame):
    """Persistent role-aware navigation sidebar shown once a user is logged in."""

    def __init__(self, master, app, width: int = 200):
        super().__init__(master, width=width, corner_radius=0)
        self.app = app
        self._nav_buttons = {}

        ctk.CTkLabel(self, text=self.app.title(), font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 4), padx=16)
        self.user_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color="#AAAAAA")
        self.user_label.pack(pady=(0, 16), padx=16)

        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=10)
        for label, screen_name, role in NAV_ITEMS:
            btn = ctk.CTkButton(
                self.nav_frame, text=label, anchor="w", fg_color="transparent",
                command=lambda s=screen_name: self.app.show_screen(s),
            )
            btn.pack(fill="x", pady=3)
            self._nav_buttons[screen_name] = (btn, role)

        ctk.CTkButton(
            self, text="Logout", fg_color="#E74C3C", hover_color="#C0392B", command=self.app.logout,
        ).pack(side="bottom", fill="x", padx=10, pady=20)

    def refresh(self, active_screen: str = None):
        user = self.app.current_user
        if user:
            self.user_label.configure(text=f"{user['full_name'] or user['username']} ({user['role']})")
        for screen_name, (btn, role) in self._nav_buttons.items():
            visible = role is None or (user and user["role"] == role)
            if visible:
                btn.pack(fill="x", pady=3)
                btn.configure(fg_color="#1F6AA5" if screen_name == active_screen else "transparent")
            else:
                btn.pack_forget()
