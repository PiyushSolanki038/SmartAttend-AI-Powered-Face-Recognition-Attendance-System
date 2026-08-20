from tkinter import messagebox

import customtkinter as ctk

from config import APP_NAME, COLOR_THEME, THEME
from services import auth
from ui.components.sidebar import Sidebar
from ui.components.toast import show_toast
from ui.screens.home import HomeScreen
from ui.screens.enroll import EnrollScreen
from ui.screens.session import SessionScreen
from ui.screens.reports import ReportsScreen
from ui.screens.settings import SettingsScreen
from ui.screens.login import LoginScreen
from ui.screens.user_management import UserManagementScreen
from ui.screens.approvals import ApprovalsScreen
from ui.screens.timetable import TimetableScreen
from ui.screens.system_settings import SystemSettingsScreen
from ui.screens.audit_log import AuditLogScreen
from ui.screens.engagement import EngagementScreen
from services import backup_scheduler
from services import session_autoclose

ctk.set_appearance_mode(THEME)
ctk.set_default_color_theme(COLOR_THEME)

# Screens restricted to specific roles; any screen not listed is open to all logged-in users.
SCREEN_ROLES = {
    "UserManagementScreen": {"admin"},
    "SystemSettingsScreen": {"admin"},
    "AuditLogScreen": {"admin"},
}

BACKUP_POLL_INTERVAL_MS = 10 * 60 * 1000  # check every 10 minutes whether a scheduled backup is due
SESSION_AUTOCLOSE_POLL_INTERVAL_MS = 60 * 1000   # check every minute - slot end times are HH:MM granularity


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x650")

        self.current_user = None
        self._current_screen_name = None

        self._root_layout = ctk.CTkFrame(self, fg_color="transparent")
        self._root_layout.pack(fill="both", expand=True)

        self.sidebar = Sidebar(self._root_layout, self)

        self._screen_area = ctk.CTkFrame(self._root_layout, fg_color="transparent")
        self._screen_area.pack(side="right", fill="both", expand=True)

        self._screens = {}
        for ScreenClass in (LoginScreen, HomeScreen, EnrollScreen, SessionScreen, ReportsScreen, SettingsScreen,
                            UserManagementScreen, ApprovalsScreen, TimetableScreen, SystemSettingsScreen,
                            AuditLogScreen, EngagementScreen):
            screen = ScreenClass(self._screen_area, self)
            self._screens[ScreenClass.__name__] = screen
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_screen("LoginScreen")
        self._poll_backup_schedule()
        self._poll_session_autoclose()

    def _poll_backup_schedule(self):
        """Runs only while the desktop app is open — no OS-level cron, documented limitation."""
        try:
            backup_scheduler.run_scheduled_backup_if_due()
        except Exception as exc:
            print(f"scheduled backup check failed: {exc}")
        self.after(BACKUP_POLL_INTERVAL_MS, self._poll_backup_schedule)

    def _poll_session_autoclose(self):
        try:
            session_autoclose.close_expired_sessions_if_any()
        except Exception as exc:
            print(f"session autoclose check failed: {exc}")
        self.after(SESSION_AUTOCLOSE_POLL_INTERVAL_MS, self._poll_session_autoclose)

    def set_current_user(self, user):
        self.current_user = user
        # Always-on auto-attendance: start watching the moment login succeeds, not only
        # when the user happens to open the Live Attendance screen.
        self._screens["SessionScreen"].on_show()

    def can_access(self, name: str) -> bool:
        required_roles = SCREEN_ROLES.get(name)
        if required_roles is None:
            return True
        return self.current_user is not None and self.current_user["role"] in required_roles

    def show_screen(self, name: str):
        if name != "LoginScreen" and self.current_user is None:
            name = "LoginScreen"
        elif not self.can_access(name):
            show_toast(self._screens["HomeScreen"], "Access denied: insufficient permissions.", "error")
            name = "HomeScreen"

        if name == "LoginScreen":
            self.sidebar.pack_forget()
        else:
            self.sidebar.pack(side="left", fill="y")
            self.sidebar.refresh(active_screen=name)

        self._current_screen_name = name
        screen = self._screens[name]
        screen.tkraise()
        if hasattr(screen, "on_show"):
            screen.on_show()

    def release_camera_for_other_use(self):
        """Temporarily stops Live Attendance's camera so another screen (e.g. Enroll's face
        scan dialog) can use the same physical webcam without contention. Call
        reclaim_camera() afterwards to resume auto-attendance watching."""
        self._screens["SessionScreen"].pause_for_external_camera_use()

    def reclaim_camera(self):
        self._screens["SessionScreen"].resume_after_external_camera_use()

    def refresh_known_faces(self):
        """Call after enrolling/editing/deleting a student so Live Attendance's running camera
        loop picks up the change immediately instead of needing an app restart."""
        self._screens["SessionScreen"].refresh_encodings()

    def prompt_forced_password_change(self, user):
        """Blocks the app behind a modal until the user sets a real password, for accounts
        flagged must_change_password (default admin password, or a student's roll-number
        default). Reused by the Settings screen's own "Change Password" button."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Set a New Password")
        dialog.geometry("360x280")
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # must not be dismissible without changing

        ctk.CTkLabel(
            dialog, text="For security, set a new password\nbefore continuing.",
            font=ctk.CTkFont(size=13), justify="center",
        ).pack(pady=(20, 16))

        ctk.CTkLabel(dialog, text="New Password").pack(anchor="w", padx=30)
        new_entry = ctk.CTkEntry(dialog, width=280, show="*")
        new_entry.pack(padx=30, pady=(2, 12))

        ctk.CTkLabel(dialog, text="Confirm New Password").pack(anchor="w", padx=30)
        confirm_entry = ctk.CTkEntry(dialog, width=280, show="*")
        confirm_entry.pack(padx=30, pady=(2, 12))

        error_label = ctk.CTkLabel(dialog, text="", text_color="#E74C3C")
        error_label.pack(pady=(0, 6))

        def _submit():
            new_password = new_entry.get()
            confirm_password = confirm_entry.get()
            if len(new_password) < 4:
                error_label.configure(text="Password must be at least 4 characters.")
                return
            if new_password != confirm_password:
                error_label.configure(text="Passwords do not match.")
                return
            auth.change_password(user["id"], new_password)
            self.current_user = dict(user)
            self.current_user["must_change_password"] = 0
            dialog.grab_release()
            dialog.destroy()

        ctk.CTkButton(dialog, text="Set Password", command=_submit).pack(pady=6)

    def logout(self):
        auth.logout(self.current_user)
        self.current_user = None
        self.show_screen("LoginScreen")

    def on_close(self):
        for screen in self._screens.values():
            if hasattr(screen, "on_close"):
                screen.on_close()
        self.destroy()


def run_app():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
