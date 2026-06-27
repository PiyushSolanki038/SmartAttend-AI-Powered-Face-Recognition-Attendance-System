import customtkinter as ctk

from config import APP_NAME, VERSION
from services import auth
from ui.components.toast import show_toast


class LoginScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        card = ctk.CTkFrame(self, width=360)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(card, text=APP_NAME, font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(30, 0), padx=40)
        ctk.CTkLabel(card, text="AI-Powered Attendance System", font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(0, 24), padx=40)

        self.username_entry = ctk.CTkEntry(card, width=260, placeholder_text="Username")
        self.username_entry.pack(padx=40, pady=8)

        self.password_entry = ctk.CTkEntry(card, width=260, placeholder_text="Password", show="*")
        self.password_entry.pack(padx=40, pady=8)
        self.password_entry.bind("<Return>", lambda e: self._login())

        self.login_btn = ctk.CTkButton(card, text="Login", width=260, command=self._login)
        self.login_btn.pack(padx=40, pady=(16, 30))

        ctk.CTkLabel(card, text="", height=4).pack()
        ctk.CTkLabel(self, text=f"v{VERSION}", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(side="bottom", pady=20)

    def on_show(self):
        self.username_entry.delete(0, "end")
        self.password_entry.delete(0, "end")
        self.username_entry.focus_set()

    def _login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            show_toast(self, "Enter username and password", "warning")
            return
        user = auth.login(username, password)
        if user is None:
            show_toast(self, "Invalid credentials or inactive account", "error")
            self.password_entry.delete(0, "end")
            return
        self.app.set_current_user(user)
        self.app.show_screen("HomeScreen")
