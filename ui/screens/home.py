import customtkinter as ctk

from config import APP_NAME, VERSION
from db import queries


class HomeScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        ctk.CTkLabel(self, text=f"Welcome to {APP_NAME}", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(50, 0))
        ctk.CTkLabel(self, text="AI-Powered Attendance System", font=ctk.CTkFont(size=14)).pack(pady=(0, 40))

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack()
        self.today_card = self._make_stat_card(cards, "Today's Attendance", "--", 0)
        self.overall_card = self._make_stat_card(cards, "Overall Average", "--", 1)
        self.enrolled_card = self._make_stat_card(cards, "Enrolled Students", "--", 2)

        ctk.CTkLabel(self, text="Use the sidebar to enroll students, start a session, view reports, or adjust settings.",
                     font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=30)

        ctk.CTkLabel(self, text=f"v{VERSION}", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(side="bottom", pady=20)

    def _make_stat_card(self, parent, title, value, col):
        card = ctk.CTkFrame(parent, width=220, height=120, corner_radius=10)
        card.grid(row=0, column=col, padx=15)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(18, 4))
        value_label = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=26, weight="bold"))
        value_label.pack()
        return value_label

    def on_show(self):
        today = queries.get_today_summary()
        overall = queries.get_overall_average()
        enrolled = len(queries.list_students())
        self.today_card.configure(text=f"{today['percentage']:.0f}%")
        self.overall_card.configure(text=f"{overall:.0f}%")
        self.enrolled_card.configure(text=str(enrolled))
