from datetime import date, datetime

import customtkinter as ctk

from config import APP_NAME, DEFAULTER_THRESHOLD, VERSION
from db import queries

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class HomeScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.greeting_label = ctk.CTkLabel(self, text=f"Welcome to {APP_NAME}", font=ctk.CTkFont(size=26, weight="bold"))
        self.greeting_label.pack(pady=(24, 0))
        self.date_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13), text_color="#AAAAAA")
        self.date_label.pack(pady=(0, 18))

        # ---------- Quick actions ----------
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=(0, 20))
        self._quick_action(actions, "Live Session", "SessionScreen", "#2ECC71", 0, 0)
        self._quick_action(actions, "Enroll Student", "EnrollScreen", "#3B82F6", 0, 1)
        self._quick_action(actions, "Reports", "ReportsScreen", "#8B5CF6", 0, 2)
        self._quick_action(actions, "Timetable", "TimetableScreen", "#F59E0B", 0, 3)
        self._quick_action(actions, "Settings", "SettingsScreen", "#6B7280", 0, 4)

        # ---------- Stat cards ----------
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack()
        self.today_card = self._make_stat_card(cards, "Today's Attendance", "--", 0)
        self.overall_card = self._make_stat_card(cards, "Overall Average", "--", 1)
        self.enrolled_card = self._make_stat_card(cards, "Enrolled Students", "--", 2)
        self.requests_card = self._make_stat_card(cards, "Pending Student Requests", "--", 3)
        self.defaulter_card = self._make_stat_card(cards, "Defaulters (<{:.0f}%)".format(DEFAULTER_THRESHOLD), "--", 4)
        self.spoof_card = self._make_stat_card(cards, "Spoof Attempts Today", "--", 5)

        self.requests_btn = ctk.CTkButton(
            self, text="Review Student Requests", fg_color="#F39C12", hover_color="#D68910",
            command=lambda: self.app.show_screen("ApprovalsScreen"),
        )
        self.requests_btn.pack(pady=(16, 0))

        # ---------- Today's schedule + recent activity ----------
        panels = ctk.CTkFrame(self, fg_color="transparent")
        panels.pack(fill="both", expand=True, padx=30, pady=(20, 10))
        panels.grid_columnconfigure(0, weight=1)
        panels.grid_columnconfigure(1, weight=1)

        schedule_panel = ctk.CTkFrame(panels, corner_radius=10)
        schedule_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(schedule_panel, text="Today's Schedule", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.schedule_frame = ctk.CTkScrollableFrame(schedule_panel, height=140, fg_color="transparent")
        self.schedule_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        activity_panel = ctk.CTkFrame(panels, corner_radius=10)
        activity_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(activity_panel, text="Recent Recognitions (Today)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.activity_frame = ctk.CTkScrollableFrame(activity_panel, height=140, fg_color="transparent")
        self.activity_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(self, text="Use the sidebar to enroll students, start a session, view reports, or adjust settings.",
                     font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(16, 4))
        ctk.CTkLabel(self, text=f"v{VERSION}", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(side="bottom", pady=12)

    def _quick_action(self, parent, text, screen_name, color, row, col):
        ctk.CTkButton(
            parent, text=text, width=140, height=36, fg_color=color,
            command=lambda: self.app.show_screen(screen_name),
        ).grid(row=row, column=col, padx=6, pady=4)

    def _make_stat_card(self, parent, title, value, col):
        row, col = divmod(col, 3)
        card = ctk.CTkFrame(parent, width=200, height=100, corner_radius=10)
        card.grid(row=row, column=col, padx=12, pady=8)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(16, 4))
        value_label = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=24, weight="bold"))
        value_label.pack()
        return value_label

    def _clear_frame(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()

    def _refresh_schedule(self):
        self._clear_frame(self.schedule_frame)
        today_idx = date.today().weekday()
        slots = [s for s in queries.list_all_timetable_slots() if s["day_of_week"] == today_idx]
        if not slots:
            ctk.CTkLabel(self.schedule_frame, text="No classes scheduled for today.", text_color="gray").pack(anchor="w", pady=4)
            return
        for s in slots:
            text = f"{s['start_time']}-{s['end_time']}   {s['subject']}"
            sub = " · ".join(filter(None, [s["department"], s["section"], s["faculty"]]))
            row = ctk.CTkFrame(self.schedule_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=text, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            if sub:
                ctk.CTkLabel(row, text=sub, font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")

    def _refresh_activity(self):
        self._clear_frame(self.activity_frame)
        open_session = queries.get_open_auto_session_today()
        if open_session is None:
            ctk.CTkLabel(self.activity_frame, text="No active session today yet.", text_color="gray").pack(anchor="w", pady=4)
            return
        records = queries.get_session_attendance(open_session["id"])
        recognized = [r for r in records if r["status"] in ("present", "manual") and r["name"]]
        recognized = list(reversed(recognized))[:8]
        if not recognized:
            ctk.CTkLabel(self.activity_frame, text="No one recognized yet today.", text_color="gray").pack(anchor="w", pady=4)
            return
        for r in recognized:
            row = ctk.CTkFrame(self.activity_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"{r['name']} ({r['roll_no']})", font=ctk.CTkFont(weight="bold")).pack(side="left")
            time_part = (r["marked_at"] or "").split(" ")[-1][:5]
            ctk.CTkLabel(row, text=time_part, font=ctk.CTkFont(size=11), text_color="gray").pack(side="right")

    def on_show(self):
        user = self.app.current_user
        name = (user["full_name"] or user["username"]) if user else None
        hour = datetime.now().hour
        time_of_day = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")
        self.greeting_label.configure(text=f"Good {time_of_day}{', ' + name if name else ''}!")
        self.date_label.configure(text=datetime.now().strftime("%A, %B %d, %Y"))

        today = queries.get_today_summary()
        overall = queries.get_overall_average()
        enrolled = len(queries.list_students())
        pending = (len(queries.list_pending_disputes()) + len(queries.list_pending_checkin_requests())
                   + len(queries.list_pending_rescan_requests()))
        defaulters = len(queries.get_defaulters(DEFAULTER_THRESHOLD))

        open_session = queries.get_open_auto_session_today()
        spoof_count = queries.get_spoof_count(open_session["id"]) if open_session else 0

        self.today_card.configure(text=f"{today['percentage']:.0f}%")
        self.overall_card.configure(text=f"{overall:.0f}%")
        self.enrolled_card.configure(text=str(enrolled))
        self.requests_card.configure(text=str(pending))
        self.defaulter_card.configure(text=str(defaulters))
        self.spoof_card.configure(text=str(spoof_count))
        self.requests_btn.configure(
            text=f"Review Student Requests ({pending})" if pending else "No Pending Requests",
            fg_color="#F39C12" if pending else "#4B5563",
        )

        self._refresh_schedule()
        self._refresh_activity()
