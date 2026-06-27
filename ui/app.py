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

ctk.set_appearance_mode(THEME)
ctk.set_default_color_theme(COLOR_THEME)

# Screens restricted to specific roles; any screen not listed is open to all logged-in users.
SCREEN_ROLES = {
    "UserManagementScreen": {"admin"},
}


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
        for ScreenClass in (LoginScreen, HomeScreen, EnrollScreen, SessionScreen, ReportsScreen, SettingsScreen, UserManagementScreen):
            screen = ScreenClass(self._screen_area, self)
            self._screens[ScreenClass.__name__] = screen
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_screen("LoginScreen")

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
