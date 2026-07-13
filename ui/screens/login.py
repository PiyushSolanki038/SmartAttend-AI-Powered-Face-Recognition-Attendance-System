import customtkinter as ctk

from config import APP_NAME, VERSION
from services import auth
from ui.components.toast import show_toast

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
PANEL_BG = "#111827"
CARD_BG = "#1F2937"
MUTED = "#9CA3AF"


class LoginScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=PANEL_BG)
        self.app = app

        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=6)
        self.grid_rowconfigure(0, weight=1)

        # Left brand panel
        brand = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        brand.grid(row=0, column=0, sticky="nsew")

        brand_content = ctk.CTkFrame(brand, fg_color="transparent")
        brand_content.place(relx=0.5, rely=0.5, anchor="center")

        logo = ctk.CTkLabel(
            brand_content, text="◆", font=ctk.CTkFont(size=42),
            text_color="white", fg_color="transparent",
        )
        logo.pack(pady=(0, 12))
        ctk.CTkLabel(
            brand_content, text=APP_NAME, font=ctk.CTkFont(size=32, weight="bold"), text_color="white",
        ).pack()
        ctk.CTkLabel(
            brand_content, text="AI-Powered Attendance System",
            font=ctk.CTkFont(size=14), text_color="#DBEAFE",
        ).pack(pady=(6, 24))
        ctk.CTkLabel(
            brand_content,
            text="Face recognition  •  Liveness detection\nAutomatic reports",
            font=ctk.CTkFont(size=12), text_color="#BFDBFE", justify="center",
        ).pack()

        # Right form panel
        form_area = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        form_area.grid(row=0, column=1, sticky="nsew")

        card = ctk.CTkFrame(form_area, fg_color=CARD_BG, corner_radius=16, width=340)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            card, text="Welcome back", font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(40, 4), padx=48)
        ctk.CTkLabel(
            card, text="Sign in to continue", font=ctk.CTkFont(size=13), text_color=MUTED,
        ).pack(pady=(0, 28), padx=48)

        ctk.CTkLabel(card, text="Username", font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w").pack(fill="x", padx=48)
        self.username_entry = ctk.CTkEntry(
            card, width=260, height=40, corner_radius=8, placeholder_text="Enter your username",
            border_width=1,
        )
        self.username_entry.pack(padx=48, pady=(4, 16))

        ctk.CTkLabel(card, text="Password", font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w").pack(fill="x", padx=48)
        self.password_entry = ctk.CTkEntry(
            card, width=260, height=40, corner_radius=8, placeholder_text="Enter your password",
            show="*", border_width=1,
        )
        self.password_entry.pack(padx=48, pady=(4, 24))
        self.password_entry.bind("<Return>", lambda e: self._login())

        self.login_btn = ctk.CTkButton(
            card, text="Login", width=260, height=42, corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._login,
        )
        self.login_btn.pack(padx=48, pady=(0, 40))

        ctk.CTkLabel(self, text=f"v{VERSION}", font=ctk.CTkFont(size=11), text_color=MUTED).place(
            relx=0.5, rely=0.98, anchor="s",
        )

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
