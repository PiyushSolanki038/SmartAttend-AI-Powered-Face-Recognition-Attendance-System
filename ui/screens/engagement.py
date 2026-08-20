"""Class-wise engagement analytics screen: reuses chart_embed.py to plot the present%/late%
trend from services/analytics.py::get_class_engagement_trend, with simple rolling-window
dip flags (no ML)."""

import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from db import queries
from services import analytics
from ui.components.chart_embed import ChartEmbed


class EngagementScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Class Engagement Analytics", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(filter_bar, text="Subject").pack(side="left", padx=(0, 5))
        self.subject_dropdown = ctk.CTkOptionMenu(filter_bar, values=["All"], command=lambda _: self._refresh())
        self.subject_dropdown.pack(side="left", padx=5)
        ctk.CTkButton(filter_bar, text="Refresh", command=self._refresh).pack(side="left", padx=10)

        self.chart = ChartEmbed(self)
        self.chart.pack(fill="both", expand=True, padx=20, pady=10)

        self.flag_label = ctk.CTkLabel(self, text="", text_color="#F39C12")
        self.flag_label.pack(padx=20, pady=(0, 20), anchor="w")

    def on_show(self):
        subjects = ["All"] + queries.get_distinct_subjects()
        self.subject_dropdown.configure(values=subjects)
        self._refresh()

    def _refresh(self):
        subject = self.subject_dropdown.get()
        subject = None if subject == "All" else subject
        trend = analytics.get_class_engagement_trend(subject=subject)
        fig, ax = plt.subplots(figsize=(7, 4))
        if not trend:
            ax.text(0.5, 0.5, "No session data yet.", ha="center", va="center")
            ax.axis("off")
        else:
            dates = [t["session_date"] for t in trend]
            ax.plot(dates, [t["present_pct"] for t in trend], marker="o", label="Present %")
            ax.plot(dates, [t["late_pct"] for t in trend], marker="o", label="Late %")
            ax.set_title("Engagement Trend")
            ax.set_ylabel("%")
            ax.legend()
            fig.autofmt_xdate(rotation=45)
        self.chart.show_figure(fig)
        flagged = analytics.flag_low_engagement_sessions(trend)
        self.flag_label.configure(
            text=f"Low-engagement dips flagged: {', '.join(flagged)}" if flagged else "No low-engagement dips detected."
        )
